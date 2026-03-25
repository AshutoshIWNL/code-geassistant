$ErrorActionPreference = "Stop"

if (Test-Path ".venv\\Scripts\\Activate.ps1") {
  . .\.venv\Scripts\Activate.ps1
}

Write-Host "[INFO] Running compile check"
python -m compileall main.py ingest rag llm cli tests

Write-Host "[INFO] Running tests"
python -m pytest -q

Write-Host "[OK] Dev checks passed."
