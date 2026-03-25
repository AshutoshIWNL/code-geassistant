import json
from pathlib import Path

from ingest.evidence import extract_evidence_for_file
from ingest.ingest_worker import ingest_workspace_to_chunks


def test_extract_evidence_for_file_detects_route_and_outbound(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    file_path = workspace / "services" / "orders" / "routes.js"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        'app.get("/orders", handler)\n'
        'const response = await fetch("https://orders.internal/api")\n',
        encoding="utf-8",
    )

    file_info = {
        "path": str(file_path),
        "rel_path": "services/orders/routes.js",
        "ext": ".js",
        "size": file_path.stat().st_size,
    }
    records = extract_evidence_for_file(str(workspace), file_info)
    ev_types = {r["evidence_type"] for r in records}

    assert "route" in ev_types
    assert "outbound_http" in ev_types
    assert all(r["service"] == "orders" for r in records)
    assert all(r["language"] == "javascript" for r in records)


def test_ingest_writes_evidence_jsonl(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    file_path = workspace / "src" / "api.py"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(
        '@app.get("/health")\n'
        "def health():\n"
        '    return requests.get("https://example.com/ping").status_code\n',
        encoding="utf-8",
    )

    job_state = {}
    summary = ingest_workspace_to_chunks(str(workspace), job_state, extra_ignores=[])

    evidence_file = Path(summary["evidence_file"])
    assert evidence_file.exists()
    assert summary["total_evidence"] >= 1
    assert job_state["total_evidence"] >= 1

    lines = [json.loads(line) for line in evidence_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) >= 1
    assert {"route", "outbound_http"} & {r["evidence_type"] for r in lines}
