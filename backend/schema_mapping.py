"""
Schema mapping: take an arbitrary client CSV whose columns differ in name,
language, or convention, and map them onto one unified canonical schema.

Two layers:
  1. A deterministic heuristic mapper (synonyms + fuzzy matching + value
     sniffing). This always runs and never needs the network.
  2. An optional Claude-assisted pass that resolves columns the heuristic
     left as UNMAPPED. It degrades gracefully to the heuristic result when
     no API endpoint is configured.

The canonical schema is the contract every downstream stage relies on.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

import pandas as pd

# --- Canonical schema -------------------------------------------------------
# field -> whether it is required for prediction to be possible
CANONICAL_FIELDS: dict[str, bool] = {
    "client": False,        # client / account name
    "order_date": True,     # date the part was ordered  (REQUIRED)
    "part_number": True,    # SKU / material number      (REQUIRED)
    "part_name": False,     # human-readable description
    "quantity": False,      # units ordered
    "equipment": False,     # machine / asset the part belongs to
}

# Known synonyms per canonical field. Lower-cased, punctuation-insensitive.
SYNONYMS: dict[str, list[str]] = {
    "client": [
        "client", "account", "customer", "cust", "company", "kunde", "cliente",
        "client name", "account name", "customer name", "buyer",
    ],
    "order_date": [
        "order date", "date ordered", "date_ordered", "orderdate", "date",
        "purchase date", "purchase_dt", "purchased", "fecha", "order dt",
        "po date", "ordered on", "transaction date", "req date",
    ],
    "part_number": [
        "part number", "part no", "partno", "sku", "item code", "item_code",
        "material no", "materialno", "material number", "part id", "code",
        "product code", "article no", "ref", "catalog number", "stock code",
    ],
    "part_name": [
        "part name", "part description", "description", "item name",
        "item_name", "component", "product", "part desc", "material",
        "product name", "name", "designation",
    ],
    "quantity": [
        "quantity", "qty", "units", "amount", "count", "pieces", "pcs",
        "order qty", "quantity ordered", "menge", "cantidad", "no of units",
        "number ordered", "qty ordered", "number of units", "qty ordered",
    ],
    "equipment": [
        "equipment", "machine", "equipment type", "equipment_type",
        "asset", "assetclass", "asset class", "machine name", "line",
        "unit", "asset type", "system",
    ],
}


@dataclass
class ColumnMapping:
    canonical: str
    source: Optional[str]
    confidence: float
    method: str  # "exact" | "synonym" | "fuzzy" | "value" | "claude" | "none"


@dataclass
class SchemaMapResult:
    mapping: dict[str, ColumnMapping]          # canonical -> ColumnMapping
    unmapped_source_columns: list[str] = field(default_factory=list)

    def as_rename_dict(self) -> dict[str, str]:
        """source_column -> canonical_field, for columns that were mapped."""
        out = {}
        for canon, m in self.mapping.items():
            if m.source is not None:
                out[m.source] = canon
        return out

    def missing_required(self) -> list[str]:
        return [
            f for f, required in CANONICAL_FIELDS.items()
            if required and self.mapping[f].source is None
        ]

    def to_dict(self) -> dict:
        return {
            "mapping": {
                c: {
                    "source": m.source,
                    "confidence": round(m.confidence, 3),
                    "method": m.method,
                }
                for c, m in self.mapping.items()
            },
            "unmapped_source_columns": self.unmapped_source_columns,
            "missing_required": self.missing_required(),
        }


def _norm(s: str) -> str:
    """Normalise a header for comparison: lowercase, strip punctuation."""
    s = s.strip().lower()
    s = re.sub(r"[_\-/]+", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _looks_like_date(series: pd.Series) -> float:
    """Fraction of non-null values that parse as a date."""
    sample = series.dropna().astype(str).head(30)
    if sample.empty:
        return 0.0
    ok = 0
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for v in sample:
            parsed = pd.to_datetime(v, errors="coerce", dayfirst=True)
            if pd.notna(parsed):
                ok += 1
    return ok / len(sample)


def _looks_like_partno(series: pd.Series) -> float:
    """Fraction of values matching an alphanumeric SKU-ish pattern."""
    sample = series.dropna().astype(str).head(30)
    if sample.empty:
        return 0.0
    pat = re.compile(r"^[A-Za-z]{1,6}[-_ ]?\d{2,6}[A-Za-z0-9-]*$")
    ok = sum(1 for v in sample if pat.match(v.strip()))
    return ok / len(sample)


def _header_score(nc: str, canon: str) -> tuple[float, str]:
    """Best score+method for a normalised header against one canonical field."""
    syns = [_norm(s) for s in SYNONYMS[canon]]
    if nc in syns:
        return (1.0, "exact") if nc == _norm(canon) else (0.95, "synonym")
    fuzzy = max((_similar(nc, s) for s in syns), default=0.0)
    return fuzzy, "fuzzy"


def heuristic_map(df: pd.DataFrame) -> SchemaMapResult:
    """
    Deterministic mapping using synonyms, fuzzy matching and value sniffing.

    Uses GLOBAL best-first assignment: we score every (canonical, source) pair,
    then assign the highest-scoring pairs first. This prevents an early field
    from greedily stealing a column that is a far better match for a later
    field (e.g. a 'Line' column matching 'equipment' perfectly should not be
    lost to a weak fuzzy 'client' match just because client is checked first).
    """
    source_cols = list(df.columns)
    norm_cols = {c: _norm(c) for c in source_cols}

    HEADER_THRESHOLD = 0.72
    VALUE_THRESHOLD = 0.6

    # Build all candidate (score, canonical, source, method) tuples.
    candidates: list[tuple[float, str, str, str]] = []
    for canon in CANONICAL_FIELDS:
        for src in source_cols:
            score, method = _header_score(norm_cols[src], canon)
            if score >= HEADER_THRESHOLD:
                candidates.append((score, canon, src, method))

    # Value sniffing for the required fields — strong signal, add as candidates.
    for src in source_cols:
        ds = _looks_like_date(df[src])
        if ds >= VALUE_THRESHOLD:
            candidates.append((0.6 + 0.39 * ds, "order_date", src, "value"))
        ps = _looks_like_partno(df[src])
        if ps >= VALUE_THRESHOLD:
            candidates.append((0.6 + 0.39 * ps, "part_number", src, "value"))

    candidates.sort(key=lambda t: t[0], reverse=True)

    mapping: dict[str, ColumnMapping] = {
        f: ColumnMapping(f, None, 0.0, "none") for f in CANONICAL_FIELDS
    }
    used_sources: set[str] = set()
    filled_canon: set[str] = set()
    for score, canon, src, method in candidates:
        if canon in filled_canon or src in used_sources:
            continue
        mapping[canon] = ColumnMapping(canon, src, min(score, 1.0), method)
        filled_canon.add(canon)
        used_sources.add(src)

    unmapped = [c for c in source_cols if c not in used_sources]
    return SchemaMapResult(mapping=mapping, unmapped_source_columns=unmapped)


def claude_assisted_map(
    df: pd.DataFrame,
    base_result: SchemaMapResult,
    claude,
) -> SchemaMapResult:
    """
    Ask Claude to resolve columns the heuristic could not confidently map.
    `claude` is a ClaudeClient (see claude_client.py). Falls back silently to
    `base_result` if Claude is unavailable or returns nothing usable.
    """
    still_missing = [f for f in CANONICAL_FIELDS
                     if base_result.mapping[f].source is None]
    if not still_missing or not claude.is_configured:
        return base_result

    sample_rows = df.head(5).to_dict(orient="records")
    prompt = (
        "You map messy CSV column headers onto a fixed canonical schema for an "
        "equipment-parts reordering system.\n\n"
        f"Canonical fields still needing a match: {still_missing}\n"
        f"Available source columns (not yet used): "
        f"{base_result.unmapped_source_columns}\n"
        f"Here are 5 sample rows so you can inspect the values:\n{sample_rows}\n\n"
        "Return ONLY a JSON object mapping each canonical field that you can "
        "confidently match to exactly one source column name, e.g. "
        '{\"order_date\": \"Purchase_Dt\"}. Omit fields you cannot match. '
        "No prose, no markdown fences."
    )
    data = claude.complete_json(prompt, max_tokens=400)
    if not isinstance(data, dict):
        return base_result

    result = base_result
    used = set(result.as_rename_dict().keys())
    for canon, src in data.items():
        if (
            canon in CANONICAL_FIELDS
            and isinstance(src, str)
            and src in df.columns
            and src not in used
            and result.mapping[canon].source is None
        ):
            result.mapping[canon] = ColumnMapping(canon, src, 0.85, "claude")
            used.add(src)
    result.unmapped_source_columns = [
        c for c in df.columns if c not in used
    ]
    return result
