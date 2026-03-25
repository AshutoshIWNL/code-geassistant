import json
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .chunker import read_file_safely
from .extractors.heuristic import HeuristicPatternExtractor
from .metadata import build_file_metadata


def get_extractors():
    return [HeuristicPatternExtractor()]


def extract_evidence_for_file(workspace_path: str, file_info: Dict[str, Any]) -> List[Dict[str, Any]]:
    lines = read_file_safely(file_info.get("path", ""))
    if not lines:
        return []

    file_meta = build_file_metadata(workspace_path, file_info)
    out: List[Dict[str, Any]] = []

    for extractor in get_extractors():
        if not extractor.detect(file_info, lines):
            continue
        for rec in extractor.extract(file_info, lines):
            rec["repo"] = file_meta["repo"]
            rec["service"] = file_meta["service"]
            rec["language"] = file_meta["language"]
            rec["symbol_type"] = file_meta["symbol_type"]
            rec["symbol_name"] = file_meta["symbol_name"]
            out.append(rec)

    return out


def write_evidence_jsonl(path: Path, records: Iterable[Dict[str, Any]]):
    with path.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
