#!/usr/bin/env bash
# One-shot launcher: installs backend deps and serves the app (UI + API) on :8000.
set -e
cd "$(dirname "$0")/backend"
python3 -m pip install -q -r requirements.txt
echo "Starting on http://localhost:8000  (UI at /, docs at /docs)"
exec uvicorn main:app --host 0.0.0.0 --port 8000
