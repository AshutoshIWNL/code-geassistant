import hashlib
import json
from pathlib import Path
from typing import Dict, Any


MANIFEST_NAME = "index_manifest.json"


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def make_fingerprint(file_info: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "sha256": file_sha256(file_info["path"]),
        "size": file_info.get("size", 0),
        "ext": file_info.get("ext", ""),
    }


def load_manifest(cache_dir: Path) -> Dict[str, Any]:
    p = cache_dir / MANIFEST_NAME
    if not p.exists():
        return {"files": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"files": {}}


def save_manifest(cache_dir: Path, files_map: Dict[str, Any]):
    p = cache_dir / MANIFEST_NAME
    payload = {"files": files_map}
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
