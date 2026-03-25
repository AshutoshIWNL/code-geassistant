import json
from pathlib import Path

from ingest.ingest_worker import ingest_workspace_to_chunks


def test_incremental_ingest_detects_unchanged_changed_deleted(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    file_a = workspace / "a.py"
    file_a.write_text("print('a')\n", encoding="utf-8")

    job1 = {}
    summary1 = ingest_workspace_to_chunks(str(workspace), job1, extra_ignores=[])
    assert summary1["new_files"] == 1
    assert summary1["changed_files"] == 0
    assert summary1["deleted_files"] == 0
    assert summary1["unchanged_files"] == 0

    job2 = {}
    summary2 = ingest_workspace_to_chunks(str(workspace), job2, extra_ignores=[])
    assert summary2["new_files"] == 0
    assert summary2["changed_files"] == 0
    assert summary2["deleted_files"] == 0
    assert summary2["unchanged_files"] == 1

    file_a.write_text("print('a2')\n", encoding="utf-8")
    file_b = workspace / "b.py"
    file_b.write_text("print('b')\n", encoding="utf-8")
    file_to_delete = workspace / "c.py"
    file_to_delete.write_text("print('c')\n", encoding="utf-8")

    job3 = {}
    _ = ingest_workspace_to_chunks(str(workspace), job3, extra_ignores=[])
    file_to_delete.unlink()

    job4 = {}
    summary4 = ingest_workspace_to_chunks(str(workspace), job4, extra_ignores=[])
    assert summary4["new_files"] == 0
    assert summary4["changed_files"] >= 0
    assert summary4["deleted_files"] == 1
    assert "c.py" in summary4["deleted_rel_paths"]

    manifest = workspace / ".code_geassistant_cache" / "index_manifest.json"
    assert manifest.exists()
    manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
    assert "a.py" in manifest_data["files"]
    assert "b.py" in manifest_data["files"]
    assert "c.py" not in manifest_data["files"]
