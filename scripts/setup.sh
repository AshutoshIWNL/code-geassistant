#!/usr/bin/env bash
set -euo pipefail

if [ ! -d ".venv" ]; then
  echo "[INFO] Creating virtual environment (.venv)"
  python3 -m venv .venv
fi

echo "[INFO] Activating virtual environment"
source .venv/bin/activate

echo "[INFO] Upgrading pip"
python -m pip install --upgrade pip

REQ_FILE="requirements.txt"
if [ ! -f "$REQ_FILE" ]; then
  echo "[ERROR] requirements.txt not found"
  exit 1
fi

echo "[INFO] Installing runtime dependencies from $REQ_FILE"
python -m pip install -r "$REQ_FILE"

if [ "${1:-}" != "--no-dev" ] && [ -f "requirements-dev.txt" ]; then
  echo "[INFO] Installing dev dependencies"
  python -m pip install -r requirements-dev.txt
fi

cat <<'EOF'

[OK] Setup complete.
Next steps:
  1) Activate env: source .venv/bin/activate
  2) Start server: python cli/code_geassistant_cli.py start
  3) Ingest repo:  python cli/code_geassistant_cli.py ingest /path/to/repo
  4) Ask query:    python cli/code_geassistant_cli.py query workspace_repo "Where is auth?"
EOF
