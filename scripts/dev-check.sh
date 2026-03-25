#!/usr/bin/env bash
set -euo pipefail

if [ -f ".venv/bin/activate" ]; then
  source .venv/bin/activate
fi

echo "[INFO] Running compile check"
python -m compileall main.py ingest rag llm cli tests

echo "[INFO] Running tests"
python -m pytest -q

echo "[OK] Dev checks passed."
