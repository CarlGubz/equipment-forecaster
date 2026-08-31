# Equipment Reorder Predictor

Predicts the **next equipment part** each client will order — and **when** — from their
past order history, so a parts supplier can pre-stage inventory and prevent operational
downtime.

Given any client's order CSV, the app:

1. **Maps the schema** — different clients name columns differently (`SKU` vs `item_code`
   vs `MaterialNo`); these are mapped onto one unified canonical schema.
2. **Pre-processes** — normalizes mixed/regional date formats, standardizes identifiers,
   drops unusable rows and duplicates, and emits a clean, analysis-ready CSV.
3. **Predicts** — for each part it models the reorder interval and outputs a bundle of
   `{ last order date, part, predicted next order date }`, ranked by urgency.

**Stack:** Python · FastAPI · pandas (backend) · TypeScript · React · Vite (frontend).
AI features call **your own Claude (Anthropic Messages API) endpoint** and are fully
optional — the app runs end-to-end on a deterministic statistical path with no key.

---

## Quick start

### 1. Backend (FastAPI)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # optional
pip install -r requirements.txt

# optional: point at YOUR Claude endpoint to enable AI assist
cp .env.example .env        # then edit, or just export the vars:
# export ANTHROPIC_API_KEY=sk-...            (leave empty for statistical-only mode)
# export ANTHROPIC_BASE_URL=https://api.anthropic.com
# export ANTHROPIC_MODEL=claude-sonnet-4-20250514

uvicorn main:app --reload --port 8000
```

The API is now on `http://localhost:8000` (interactive docs at `/docs`).
Because a pre-built frontend ships in `frontend/dist`, the **full UI is already served
at `http://localhost:8000/`** — no frontend build needed to try it.

### 2. Frontend (only if you want to modify the UI)

```bash
cd frontend
npm install
npm run dev          # dev server on http://localhost:5173, proxies /api to :8000
# or
npm run build        # rebuilds frontend/dist, which the backend serves at /
```

---

## Using it

Open `http://localhost:8000/`, then either click a **sample client** or **upload your own
CSV**. You'll see each pipeline stage: the schema mapping, the cleaning report, the cleaned
data, and the reorder forecast. Both the cleaned CSV and the forecast CSV are downloadable.

### Sample clients (deliberately different schemas & date formats)

| Client | Columns | Date format |
|---|---|---|
| Acme Manufacturing | `Client, Order Date, SKU, Part Description, Qty, Machine` | `MM/DD/YYYY` |
| BluePeak Logistics | `account, date_ordered, item_code, item_name, units, equipment_type` | `YYYY-MM-DD` |
| Nordic Steel Works | `Kunde, Purchase_Dt, MaterialNo, Component, Amount, AssetClass` | `DD.MM.YYYY` |

They live in `sample_data/` — open one to see the raw shape before mapping.

---

## How it works

### Canonical schema

Everything downstream depends on this contract:

```
client | order_date | part_number | part_name | quantity | equipment
```

`order_date` and `part_number` are **required**; the rest are optional.

### Schema mapping (`backend/schema_mapping.py`)

A deterministic mapper scores every `(canonical field, your column)` pair using exact
matches, a synonym dictionary, fuzzy string similarity, and **value sniffing** (does a
column *look like* dates or SKUs?). It then assigns the highest-scoring pairs first
(global best-first), so a perfect match is never lost to an earlier weak one.

If required columns still can't be resolved **and** an AI endpoint is configured, Claude
is asked to resolve only the leftover columns (it sees sample rows). This layer is
optional and degrades silently to the heuristic result.

### Pre-processing (`backend/preprocessing.py`)

Applies the mapping, then infers day-first vs month-first vs ISO dates from the data
itself (so `03.09.2024` isn't silently misread), normalizes identifiers, coerces
quantities, back-fills missing part names, removes duplicates, and outputs a tidy
ISO-dated CSV plus a report of exactly what was changed.

### Prediction (`backend/prediction.py`)

For each `(client, part)`:

- gaps between consecutive orders → **median interval** (robust to outliers),
- `predicted_next_order_date = last_order_date + interval`,
- `status` ∈ `overdue | due_soon | scheduled | insufficient_history`,
- a **confidence** score from order count + interval regularity,
- a suggested reorder quantity (median historical quantity),
- a plain-English rationale.

Results are ranked overdue/soonest-first — your pre-staging priority list. If AI is on,
Claude may nudge dates for clustered demand and rewrite the rationale; it never invents or
removes parts.

---

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness |
| GET | `/api/config` | whether your Claude endpoint is configured |
| GET | `/api/samples` | list sample clients |
| GET | `/api/samples/{name}` | download a raw sample CSV |
| POST | `/api/analyze` | run the full pipeline (`file` upload **or** `sample` name; `use_ai` bool) |

`/api/analyze` returns the raw preview, schema mapping, preprocessing report, cleaned data
+ CSV, and the ranked predictions in one response.

---

## Notes & extension ideas

- **No AI key?** Everything works; the badge shows "statistical mode".
- **Your own gateway?** Set `ANTHROPIC_BASE_URL` to your proxy — no code changes.
- Swap the median-interval model for survival analysis or seasonal decomposition in
  `prediction.py` without touching the rest of the pipeline.
- Add per-client column overrides by editing the returned schema mapping before
  preprocessing.
