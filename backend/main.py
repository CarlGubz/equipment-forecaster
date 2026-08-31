"""
FastAPI application for the Equipment Reorder Predictor.

Pipeline (each stage is exposed in the /api/analyze response so the UI can
show them as steps):

    raw CSV  ->  schema mapping  ->  pre-processing  ->  prediction

Endpoints:
    GET  /api/health           liveness
    GET  /api/config           whether your Claude endpoint is configured
    GET  /api/samples          list built-in sample clients
    GET  /api/samples/{name}   download a raw sample CSV
    POST /api/analyze          run the full pipeline on an upload or a sample
"""
from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from claude_client import ClaudeClient
from prediction import predict_dataframe, refine_with_claude
from preprocessing import preprocess
from schema_mapping import claude_assisted_map, heuristic_map

BASE_DIR = Path(__file__).resolve().parent.parent
SAMPLE_DIR = BASE_DIR / "sample_data"
FRONTEND_DIST = BASE_DIR / "frontend" / "dist"

app = FastAPI(title="Equipment Reorder Predictor", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)

claude = ClaudeClient()

SAMPLE_LABELS = {
    "acme_manufacturing": "Acme Manufacturing (CNC / machining)",
    "bluepeak_logistics": "BluePeak Logistics (conveyors / forklifts)",
    "nordic_steel_works": "Nordic Steel Works (furnace / rolling mill)",
}


def _read_csv_bytes(raw: bytes) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=enc, dtype=str, keep_default_na=False)
        except (UnicodeDecodeError, pd.errors.ParserError):
            continue
    raise HTTPException(status_code=400, detail="Could not parse the file as CSV.")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/config")
def config():
    return {
        "ai_enabled": claude.is_configured,
        "model": claude.model if claude.is_configured else None,
        "base_url": claude.base_url if claude.is_configured else None,
    }


@app.get("/api/samples")
def list_samples():
    out = []
    for stem, label in SAMPLE_LABELS.items():
        p = SAMPLE_DIR / f"{stem}.csv"
        if p.exists():
            df = _read_csv_bytes(p.read_bytes())
            out.append({
                "name": stem,
                "label": label,
                "columns": list(df.columns),
                "rows": len(df),
            })
    return {"samples": out}


@app.get("/api/samples/{name}")
def get_sample(name: str):
    p = SAMPLE_DIR / f"{name}.csv"
    if not p.exists():
        raise HTTPException(status_code=404, detail="Sample not found.")
    return PlainTextResponse(p.read_text(), media_type="text/csv")


@app.post("/api/analyze")
async def analyze(
    file: UploadFile | None = File(default=None),
    sample: str | None = Form(default=None),
    use_ai: bool = Form(default=True),
):
    # --- load raw data ---
    if file is not None:
        raw = await file.read()
        df = _read_csv_bytes(raw)
        source_name = file.filename or "upload.csv"
    elif sample is not None:
        p = SAMPLE_DIR / f"{sample}.csv"
        if not p.exists():
            raise HTTPException(status_code=404, detail="Sample not found.")
        df = _read_csv_bytes(p.read_bytes())
        source_name = f"{sample}.csv"
    else:
        raise HTTPException(status_code=400, detail="Provide either a file or a sample name.")

    if df.empty:
        raise HTTPException(status_code=400, detail="The CSV appears to be empty.")

    ai_on = use_ai and claude.is_configured

    # --- stage 1: schema mapping ---
    schema = heuristic_map(df)
    if ai_on and schema.missing_required():
        schema = claude_assisted_map(df, schema, claude)
    if schema.missing_required():
        raise HTTPException(
            status_code=422,
            detail=(
                "Could not identify required column(s): "
                f"{schema.missing_required()}. Detected columns: {list(df.columns)}."
            ),
        )

    # --- stage 2: pre-processing ---
    cleaned, report = preprocess(df, schema)
    if cleaned.empty:
        raise HTTPException(status_code=422, detail="No usable rows after cleaning.")

    # --- stage 3: prediction ---
    as_of = date.today()
    predictions = predict_dataframe(cleaned, as_of=as_of)
    if ai_on:
        predictions = refine_with_claude(predictions, claude, as_of)

    cleaned_csv = cleaned.to_csv(index=False)
    preview = cleaned.head(15).to_dict(orient="records")

    summary = {
        "clients": sorted(cleaned["client"].unique().tolist()),
        "distinct_parts": int(cleaned["part_number"].nunique()),
        "overdue": sum(1 for p in predictions if p.status == "overdue"),
        "due_soon": sum(1 for p in predictions if p.status == "due_soon"),
    }

    return {
        "source_name": source_name,
        "as_of": as_of.isoformat(),
        "ai_used": ai_on,
        "raw_preview": {
            "columns": list(df.columns),
            "rows": df.head(8).to_dict(orient="records"),
        },
        "schema": schema.to_dict(),
        "preprocessing": report.to_dict(),
        "cleaned_preview": preview,
        "cleaned_csv": cleaned_csv,
        "predictions": [p.to_dict() for p in predictions],
        "summary": summary,
    }


# --- serve the built frontend (if present) ---
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


@app.get("/")
def root_fallback():
    if FRONTEND_DIST.exists():
        return FileResponse(str(FRONTEND_DIST / "index.html"))
    return {
        "message": "Equipment Reorder Predictor API is running.",
        "docs": "/docs",
        "note": "Build the frontend (npm run build) to serve the UI here.",
    }
