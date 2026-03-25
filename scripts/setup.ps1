param(
  [switch]$NoDev
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
  Write-Host "[INFO] Creating virtual environment (.venv)"
  python -m venv .venv
}

Write-Host "[INFO] Activating virtual environment"
. .\.venv\Scripts\Activate.ps1

Write-Host "[INFO] Upgrading pip"
python -m pip install --upgrade pip

$requirements = "requirements_win.txt"
if (-not (Test-Path $requirements)) {
  $requirements = "requirements.txt"
}

Write-Host "[INFO] Installing runtime dependencies from $requirements"
python -m pip install -r $requirements

if (-not $NoDev) {
  if (Test-Path "requirements-dev.txt") {
    Write-Host "[INFO] Installing dev dependencies"
    python -m pip install -r requirements-dev.txt
  }
}

Write-Host ""
Write-Host "[OK] Setup complete."
Write-Host "Next steps:"
Write-Host "  1) Activate env: .\.venv\Scripts\Activate.ps1"
Write-Host "  2) Start server: python cli/code_geassistant_cli.py start"
Write-Host "  3) Ingest repo:  python cli/code_geassistant_cli.py ingest C:\path\to\repo"
Write-Host "  4) Ask query:    python cli/code_geassistant_cli.py query workspace_repo `"Where is auth?`""
