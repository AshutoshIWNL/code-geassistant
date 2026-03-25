from pathlib import Path
from typing import Dict


LANG_BY_EXT = {
    ".py": "python",
    ".java": "java",
    ".kt": "kotlin",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".scala": "scala",
    ".sql": "sql",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".xml": "xml",
    ".md": "markdown",
    ".sh": "shell",
    ".ps1": "powershell",
}

COMMON_CONTAINER_DIRS = {"services", "service", "apps", "packages", "modules"}
COMMON_CODE_ROOTS = {"src", "lib", "app"}


def infer_language(ext: str) -> str:
    return LANG_BY_EXT.get((ext or "").lower(), "unknown")


def infer_symbol_type(rel_path: str) -> str:
    lower_name = Path(rel_path).name.lower()
    stem = Path(rel_path).stem.lower()

    if "controller" in lower_name or "route" in lower_name:
        return "endpoint_handler"
    if "service" in lower_name:
        return "service"
    if "client" in lower_name:
        return "client"
    if "repo" in lower_name or "repository" in lower_name:
        return "repository"
    if "model" in lower_name or "schema" in lower_name:
        return "model"
    if "config" in lower_name or "settings" in lower_name:
        return "config"
    if "test" in lower_name:
        return "test"
    if stem in {"main", "app", "server"}:
        return "entrypoint"
    return "file"


def infer_service_name(workspace_name: str, rel_path: str) -> str:
    parts = [p for p in Path(rel_path).parts if p not in {"", ".", ".."}]
    if not parts:
        return workspace_name

    head = parts[0].lower()
    if head in COMMON_CONTAINER_DIRS and len(parts) > 1:
        return parts[1]
    if head in COMMON_CODE_ROOTS:
        return workspace_name
    return parts[0]


def build_file_metadata(workspace_path: str, file_info: Dict[str, str]) -> Dict[str, str]:
    workspace_name = Path(workspace_path).resolve().name
    rel_path = file_info.get("rel_path", "")
    ext = file_info.get("ext", "")
    return {
        "repo": workspace_name,
        "service": infer_service_name(workspace_name, rel_path),
        "language": infer_language(ext),
        "symbol_type": infer_symbol_type(rel_path),
        "symbol_name": Path(rel_path).stem or rel_path,
    }
