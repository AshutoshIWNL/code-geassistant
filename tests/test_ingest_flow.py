from pathlib import Path
from fastapi import BackgroundTasks

import main


def test_ingest_job_lifecycle(monkeypatch, tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "a.py").write_text("print('x')\n", encoding="utf-8")

    def _fake_ingest_workspace_to_chunks(workspace_path, job_state, extra_ignores=None):
        job_state["status"] = "done"
        job_state["progress"] = 100
        job_state["files_processed"] = 1
        job_state["total_chunks"] = 1
        return {
            "workspace": workspace_path,
            "total_files": 1,
            "total_chunks": 1,
            "chunks_file": str(Path(workspace_path) / ".code_geassistant_cache" / "chunks.jsonl"),
        }

    def _fake_embed_workspace(
        workspace_path,
        chroma_dir="./chroma_db",
        changed_or_new_rel_paths=None,
        deleted_rel_paths=None,
    ):
        return None

    monkeypatch.setattr(main, "ingest_workspace_to_chunks", _fake_ingest_workspace_to_chunks)
    import ingest.embedder as embedder
    monkeypatch.setattr(embedder, "embed_workspace", _fake_embed_workspace)

    payload = main.IngestStartRequest(workspace_path=str(workspace), ignore_patterns=[])
    bg = BackgroundTasks()
    resp = main.ingest_start(payload, bg)

    assert "job_id" in resp
    job_id = resp["job_id"]
    assert main.INGEST_JOBS[job_id]["status"] == "queued"

    assert len(bg.tasks) == 1
    task = bg.tasks[0]
    task.func(*task.args, **task.kwargs)

    assert main.INGEST_JOBS[job_id]["status"] == "ready"
    assert main.INGEST_JOBS[job_id]["progress"] == 100
    assert main.INGEST_JOBS[job_id]["files_processed"] == 1
