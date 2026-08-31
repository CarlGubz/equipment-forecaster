"""
Prediction engine.

Goal: for each (client, part), predict WHEN the client will next need to order
it, so the supplier can pre-stage the part and prevent operational delays.

Statistical core (always runs, deterministic, explainable):
  * For each part, take the ordered history of order dates.
  * Compute the gaps (in days) between consecutive orders.
  * Estimate the reorder interval as the MEDIAN gap (robust to outliers).
  * predicted_next_order_date = last_order_date + interval.
  * days_until_due = predicted_next_order_date - today  (negative => overdue).
  * confidence from: number of observed orders + regularity of the interval
    (low coefficient of variation => high confidence).
  * suggested_quantity = median historical order quantity.

Ranking: soonest-due / most-overdue first — that is the reorder priority list.

Optional Claude layer: given the statistical summary, Claude can nudge the
date (seasonality, lumpy demand), attach a short human rationale, and flag
risk. It never invents parts; it only annotates/adjusts what the stats found.
Falls back cleanly to the statistical result when unconfigured.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from statistics import median
from typing import Optional

import pandas as pd


@dataclass
class PartPrediction:
    client: str
    part_number: str
    part_name: str
    equipment: str
    order_count: int
    last_order_date: str
    avg_interval_days: Optional[float]
    predicted_next_order_date: Optional[str]
    days_until_due: Optional[int]
    status: str                # "overdue" | "due_soon" | "scheduled" | "insufficient_history"
    confidence: float          # 0..1
    suggested_quantity: int
    rationale: str

    def to_dict(self) -> dict:
        return asdict(self)


def _cv(values: list[float]) -> float:
    if len(values) < 2:
        return 1.0
    m = sum(values) / len(values)
    if m == 0:
        return 1.0
    var = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return (var ** 0.5) / m


def _confidence(n_orders: int, intervals: list[float]) -> float:
    """More orders + more regular spacing => higher confidence."""
    if n_orders < 2:
        return 0.15
    count_factor = min(1.0, (n_orders - 1) / 6.0)     # saturates ~7 orders
    regularity = max(0.0, 1.0 - min(_cv(intervals), 1.0))
    return round(0.35 * count_factor + 0.65 * regularity, 3)


def predict_dataframe(
    df: pd.DataFrame,
    as_of: Optional[date] = None,
    due_soon_days: int = 21,
    global_default_interval: Optional[float] = None,
) -> list[PartPrediction]:
    """
    df must be the canonical, cleaned dataframe:
    client | order_date (ISO str) | part_number | part_name | quantity | equipment
    """
    if as_of is None:
        as_of = date.today()

    data = df.copy()
    data["order_date"] = pd.to_datetime(data["order_date"])

    # A fallback interval for single-order parts: median of all known intervals.
    all_intervals: list[float] = []
    for _, g in data.groupby(["client", "part_number"]):
        dts = g["order_date"].sort_values().tolist()
        all_intervals += [(dts[i] - dts[i - 1]).days for i in range(1, len(dts))]
    if global_default_interval is None:
        global_default_interval = median(all_intervals) if all_intervals else 90.0

    predictions: list[PartPrediction] = []

    for (client, part_number), g in data.groupby(["client", "part_number"]):
        g = g.sort_values("order_date")
        dts = g["order_date"].tolist()
        last_dt = dts[-1]
        part_name = g["part_name"].iloc[-1]
        equipment = next((e for e in g["equipment"] if e), "")
        qty = int(round(median(g["quantity"].tolist())))
        n = len(dts)

        intervals = [(dts[i] - dts[i - 1]).days for i in range(1, len(dts))]

        if intervals:
            interval = float(median(intervals))
            method_note = f"median of {len(intervals)} observed intervals"
        else:
            interval = float(global_default_interval)
            method_note = "no repeat history; using fleet-wide default interval"

        next_dt = (last_dt + timedelta(days=round(interval))).date()
        days_until = (next_dt - as_of).days
        conf = _confidence(n, intervals)

        if n < 2:
            status = "insufficient_history"
        elif days_until < 0:
            status = "overdue"
        elif days_until <= due_soon_days:
            status = "due_soon"
        else:
            status = "scheduled"

        if status == "overdue":
            rationale = (
                f"Ordered {n} times, typically every ~{round(interval)} days "
                f"({method_note}). Last order {last_dt.date().isoformat()} means "
                f"a reorder was expected by {next_dt.isoformat()} — now "
                f"{abs(days_until)} days overdue. Stage this part immediately."
            )
        elif status == "due_soon":
            rationale = (
                f"Ordered {n} times on a ~{round(interval)}-day cycle. Due around "
                f"{next_dt.isoformat()} ({days_until} days out) — pre-stage now to "
                f"avoid a downtime gap."
            )
        elif status == "scheduled":
            rationale = (
                f"Regular ~{round(interval)}-day cycle over {n} orders; next order "
                f"projected around {next_dt.isoformat()} ({days_until} days out)."
            )
        else:
            rationale = (
                f"Only {n} order on record, so timing is a rough estimate using a "
                f"fleet-wide ~{round(interval)}-day interval. Confirm before staging."
            )

        predictions.append(PartPrediction(
            client=client,
            part_number=part_number,
            part_name=part_name,
            equipment=equipment,
            order_count=n,
            last_order_date=last_dt.date().isoformat(),
            avg_interval_days=round(interval, 1),
            predicted_next_order_date=next_dt.isoformat(),
            days_until_due=days_until,
            status=status,
            confidence=conf,
            suggested_quantity=qty,
            rationale=rationale,
        ))

    # Reorder priority: overdue/soonest first, then by confidence.
    order = {"overdue": 0, "due_soon": 1, "scheduled": 2, "insufficient_history": 3}
    predictions.sort(key=lambda p: (order[p.status],
                                    p.days_until_due if p.days_until_due is not None else 9999,
                                    -p.confidence))
    return predictions


def refine_with_claude(predictions: list[PartPrediction], claude, as_of: date) -> list[PartPrediction]:
    """
    Optional: let Claude adjust dates and rewrite rationales using the whole
    picture (relationships between parts, lumpy demand). Only adjusts existing
    predictions; never adds or removes parts. No-op if Claude isn't configured.
    """
    if not claude.is_configured or not predictions:
        return predictions

    compact = [
        {
            "part_number": p.part_number,
            "part_name": p.part_name,
            "equipment": p.equipment,
            "order_count": p.order_count,
            "last_order_date": p.last_order_date,
            "interval_days": p.avg_interval_days,
            "stat_next_date": p.predicted_next_order_date,
            "status": p.status,
        }
        for p in predictions
    ]
    prompt = (
        "You are a maintenance-planning analyst. Below is a statistical reorder "
        "forecast for one client's equipment parts. Today's date is "
        f"{as_of.isoformat()}.\n\n"
        f"{compact}\n\n"
        "For each part, keep the statistical date unless there is a clear reason "
        "to adjust it (e.g. clustered demand across parts on the same equipment). "
        "Return ONLY a JSON array; each element: "
        '{\"part_number\": str, \"adjusted_next_date\": \"YYYY-MM-DD\", '
        '\"note\": str (<= 25 words)}. No markdown, no prose outside the JSON.'
    )
    data = claude.complete_json(prompt, max_tokens=1500)
    if not isinstance(data, list):
        return predictions

    by_pn = {p.part_number: p for p in predictions}
    for item in data:
        if not isinstance(item, dict):
            continue
        pn = item.get("part_number")
        p = by_pn.get(pn)
        if not p:
            continue
        new_date = item.get("adjusted_next_date")
        note = item.get("note")
        try:
            nd = datetime.strptime(new_date, "%Y-%m-%d").date()
            p.predicted_next_order_date = nd.isoformat()
            p.days_until_due = (nd - as_of).days
        except (TypeError, ValueError):
            pass
        if isinstance(note, str) and note.strip():
            p.rationale = f"{note.strip()} (AI-reviewed)"

    order = {"overdue": 0, "due_soon": 1, "scheduled": 2, "insufficient_history": 3}
    predictions.sort(key=lambda p: (order[p.status],
                                    p.days_until_due if p.days_until_due is not None else 9999,
                                    -p.confidence))
    return predictions
