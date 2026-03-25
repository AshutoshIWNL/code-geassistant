import re
from typing import Any, Dict, List

from .base import EvidenceExtractor


ROUTE_PATTERNS = [
    re.compile(r"@(?P<method>Get|Post|Put|Delete|Patch)Mapping\(\s*(?:value\s*=\s*)?[\"'](?P<path>[^\"']+)[\"']"),
    re.compile(r"\b(?:app|router)\.(?P<method>get|post|put|delete|patch|options|head)\(\s*[\"'](?P<path>[^\"']+)[\"']"),
    re.compile(r"@(?:app|router)\.(?P<method>get|post|put|delete|patch|options|head)\(\s*[\"'](?P<path>[^\"']+)[\"']"),
    re.compile(r"@app\.route\(\s*[\"'](?P<path>[^\"']+)[\"']"),
]

HTTP_CALL_PATTERNS = [
    re.compile(r"\brequests\.(?P<method>get|post|put|delete|patch)\("),
    re.compile(r"\baxios\.(?P<method>get|post|put|delete|patch)\("),
    re.compile(r"\bfetch\("),
    re.compile(r"\b(?:restTemplate|webClient)\.(?P<method>get|post|put|delete|exchange|retrieve)\b", re.IGNORECASE),
]

URL_PATTERN = re.compile(r"https?://[^\s\"')]+")

MESSAGE_PATTERNS = [
    ("message_publish", re.compile(r"\bkafkaTemplate\.send\(\s*[\"'](?P<topic>[^\"']+)[\"']")),
    ("message_subscribe", re.compile(r"@KafkaListener\(\s*topics\s*=\s*[\"'](?P<topic>[^\"']+)[\"']")),
    ("message_publish", re.compile(r"\bbasicPublish\(\s*[\"'][^\"']*[\"']\s*,\s*[\"'](?P<topic>[^\"']+)[\"']")),
]


class HeuristicPatternExtractor(EvidenceExtractor):
    name = "heuristic_v1"

    def detect(self, file_info: Dict[str, Any], lines: List[str]) -> bool:
        return bool(lines)

    def extract(self, file_info: Dict[str, Any], lines: List[str]) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []

        for idx, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line:
                continue

            route_record = self._match_route(file_info, line, idx)
            if route_record:
                records.append(route_record)

            http_record = self._match_http_call(file_info, line, idx)
            if http_record:
                records.append(http_record)

            msg_records = self._match_message(file_info, line, idx)
            if msg_records:
                records.extend(msg_records)

        return records

    def _base_record(self, file_info: Dict[str, Any], line: str, line_no: int, evidence_type: str, confidence: str):
        return {
            "extractor": self.name,
            "evidence_type": evidence_type,
            "rel_path": file_info.get("rel_path"),
            "start_line": line_no,
            "end_line": line_no,
            "raw": line[:400],
            "confidence": confidence,
        }

    def _match_route(self, file_info: Dict[str, Any], line: str, line_no: int):
        for pat in ROUTE_PATTERNS:
            m = pat.search(line)
            if not m:
                continue
            method = (m.groupdict().get("method") or "any").upper()
            path = m.groupdict().get("path")
            rec = self._base_record(file_info, line, line_no, "route", "medium")
            rec["method"] = method
            rec["path"] = path
            return rec
        return None

    def _match_http_call(self, file_info: Dict[str, Any], line: str, line_no: int):
        for pat in HTTP_CALL_PATTERNS:
            m = pat.search(line)
            if not m:
                continue
            method = m.groupdict().get("method", "unknown").upper()
            url_match = URL_PATTERN.search(line)
            rec = self._base_record(file_info, line, line_no, "outbound_http", "low")
            rec["method"] = method
            rec["target"] = url_match.group(0) if url_match else None
            return rec
        return None

    def _match_message(self, file_info: Dict[str, Any], line: str, line_no: int):
        records = []
        for ev_type, pat in MESSAGE_PATTERNS:
            m = pat.search(line)
            if not m:
                continue
            rec = self._base_record(file_info, line, line_no, ev_type, "medium")
            rec["topic"] = m.groupdict().get("topic")
            records.append(rec)
        return records
