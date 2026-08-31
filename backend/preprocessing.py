"""
Data pre-processing.

Takes a raw client dataframe plus a schema mapping and produces a clean,
tidy, canonical dataframe that downstream analysis and prediction can rely on:

  client | order_date (ISO) | part_number | part_name | quantity | equipment

Handles the messy realities of client exports:
  * mixed / regional date formats (MM/DD/YYYY, DD.MM.YYYY, YYYY-MM-DD)
  * stray whitespace and inconsistent casing in identifiers
  * duplicate rows, blank part numbers, non-numeric quantities
  * missing optional columns (filled with sensible defaults)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from schema_mapping import CANONICAL_FIELDS, SchemaMapResult


@dataclass
class PreprocessReport:
    input_rows: int
    output_rows: int
    dropped_missing_key: int = 0
    dropped_bad_date: int = 0
    dropped_duplicates: int = 0
    date_format_note: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__


def _parse_dates(series: pd.Series) -> tuple[pd.Series, str]:
    """
    Robustly parse a date column that may use a regional format.

    We infer day-first vs month-first from the data: if any value has a first
    component > 12 it can only be day-first; if any has a second component > 12
    it can only be month-first. This avoids silently mis-reading 03.09.2024.
    """
    import re as _re
    raw = series.astype(str).str.strip()

    dayfirst = None
    iso = False
    for v in raw.dropna():
        parts = [p for p in _re.split(r"[/\-.]", v) if p]
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            # 4-digit leading component => ISO year-first (pandas parses natively)
            if len(parts[0]) == 4:
                iso = True
                break
            a, b = int(parts[0]), int(parts[1])
            if a > 12 and b <= 12:
                dayfirst = True
                break
            if b > 12 and a <= 12:
                dayfirst = False
                break

    if iso:
        note = "ISO (YYYY-MM-DD)"
    else:
        note = {True: "day-first (e.g. DD.MM.YYYY)",
                False: "month-first (e.g. MM/DD/YYYY)",
                None: "auto"}[dayfirst]

    parsed = pd.to_datetime(
        raw, errors="coerce",
        dayfirst=bool(dayfirst) if dayfirst is not None else False,
    )
    # Second attempt for stragglers with the opposite convention.
    mask = parsed.isna()
    if mask.any():
        alt = pd.to_datetime(raw[mask], errors="coerce", dayfirst=not bool(dayfirst))
        parsed.loc[mask] = alt
    return parsed, note


def preprocess(df: pd.DataFrame, schema: SchemaMapResult) -> tuple[pd.DataFrame, PreprocessReport]:
    input_rows = len(df)
    rename = schema.as_rename_dict()
    work = df.rename(columns=rename)

    # Keep only canonical columns that are present; add the rest as empty.
    for canon in CANONICAL_FIELDS:
        if canon not in work.columns:
            work[canon] = pd.NA
    work = work[list(CANONICAL_FIELDS.keys())].copy()

    report = PreprocessReport(input_rows=input_rows, output_rows=0)

    # --- order_date ---
    work["order_date"], note = _parse_dates(work["order_date"])
    report.date_format_note = note
    bad_dates = work["order_date"].isna().sum()
    report.dropped_bad_date = int(bad_dates)
    work = work[work["order_date"].notna()]

    # --- identifiers ---
    work["part_number"] = (
        work["part_number"].astype(str).str.strip().str.upper()
        .replace({"": pd.NA, "NAN": pd.NA, "NONE": pd.NA})
    )
    before = len(work)
    work = work[work["part_number"].notna()]
    report.dropped_missing_key += before - len(work)

    work["part_name"] = work["part_name"].astype(str).str.strip().replace({"nan": ""})
    work["equipment"] = work["equipment"].astype(str).str.strip().replace({"nan": ""})

    if work["client"].isna().all():
        work["client"] = "Unknown Client"
    else:
        work["client"] = work["client"].astype(str).str.strip()

    # --- quantity ---
    work["quantity"] = pd.to_numeric(work["quantity"], errors="coerce").fillna(1)
    work.loc[work["quantity"] <= 0, "quantity"] = 1
    work["quantity"] = work["quantity"].astype(int)

    # Fill a readable part_name where missing, using the most common name seen.
    name_map = (
        work[work["part_name"] != ""]
        .groupby("part_number")["part_name"]
        .agg(lambda s: s.value_counts().idxmax())
        .to_dict()
    )
    work["part_name"] = work.apply(
        lambda r: r["part_name"] if r["part_name"] else name_map.get(r["part_number"], r["part_number"]),
        axis=1,
    )

    # --- dedupe exact duplicates (same client/date/part/qty) ---
    before = len(work)
    work = work.drop_duplicates(subset=["client", "order_date", "part_number", "quantity"])
    report.dropped_duplicates = before - len(work)

    work = work.sort_values(["client", "part_number", "order_date"]).reset_index(drop=True)
    work["order_date"] = work["order_date"].dt.strftime("%Y-%m-%d")

    report.output_rows = len(work)
    if report.output_rows == 0:
        report.warnings.append("No usable rows after cleaning — check the schema mapping.")
    return work, report
