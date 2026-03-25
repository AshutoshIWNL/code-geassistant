# Code Geassistant

Local-first codebase intelligence for large multi-service systems.

Code Geassistant ingests one or more repositories, builds semantic + structured indexes, and answers:

- General code questions (`qa` mode)
- Endpoint ownership (`owner_of_endpoint` mode)
- Service neighbors (`neighbors` mode)
- Flow traces (`trace_flow` mode)

It is designed for day-to-day "where does this API go?" debugging across microservices without running every service locally.

## What You Get

- FastAPI backend + CLI workflow
- Incremental indexing (new/changed/deleted file detection)
- Semantic retrieval with ChromaDB + sentence-transformers
- Heuristic evidence extraction (routes, outbound calls, messaging)
- Service graph generation with evidence-backed edges
- Query modes for flow/ownership analysis

## Repository Layout

- `main.py`: FastAPI app and API endpoints
- `cli/code_geassistant_cli.py`: operator CLI
- `ingest/`: file walking, chunking, evidence extraction, graph build, incremental indexing
- `rag/`: retrieval + prompt pipeline
- `llm/`: LLM provider adapter (Ollama / llama.cpp)
- `scripts/`: setup and pipeline helpers
- `ARCHITECTURE.md`: detailed architecture and phased plan

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md): implementation-level architecture
- [CONTRIBUTING.md](CONTRIBUTING.md): development and PR guide
- [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md): pre-release and publish checklist

## Prerequisites

- Python 3.10+
- Ollama installed and running
- A pulled local model, e.g.:

```bash
ollama pull deepseek-coder:1.3b
```

## Quick Setup

## Windows (PowerShell)

```powershell
# 1) Clone and enter repo
git clone https://github.com/<your-username>/code-geassistant.git
cd code-geassistant

# 2) One-command setup (creates .venv + installs deps)
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1

# 3) Activate env
.\.venv\Scripts\Activate.ps1
```

## macOS / Linux

```bash
# 1) Clone and enter repo
git clone https://github.com/<your-username>/code-geassistant.git
cd code-geassistant

# 2) One-command setup (creates .venv + installs deps)
bash scripts/setup.sh

# 3) Activate env
source .venv/bin/activate
```

## First Run (CLI)

```bash
# Start API server
python cli/code_geassistant_cli.py start

# Ingest a repository
python cli/code_geassistant_cli.py ingest /path/to/repo

# Ask semantic question (qa mode)
python cli/code_geassistant_cli.py query workspace_repo "Where is authentication implemented?"
```

Note: workspace id format is `workspace_<folder-name>`.

## Query Modes

## 1) QA Mode (default)

```bash
python cli/code_geassistant_cli.py query workspace_repo "Explain order creation flow"
```

## 2) Endpoint Owner Mode

```bash
python cli/code_geassistant_cli.py query workspace_repo --mode owner_of_endpoint --method GET --path /orders
```

## 3) Service Neighbors Mode

```bash
python cli/code_geassistant_cli.py query workspace_repo --mode neighbors --service orders --direction both
```

## 4) Flow Trace Mode

```bash
python cli/code_geassistant_cli.py query workspace_repo --mode trace_flow --service orders --trace-depth 3
```

You can also trace by endpoint anchor:

```bash
python cli/code_geassistant_cli.py query workspace_repo --mode trace_flow --method GET --path /orders
```

## Useful Filters (QA mode)

```bash
python cli/code_geassistant_cli.py query workspace_repo "Where are order APIs?" --service orders --language java --symbol-type endpoint_handler
```

Supported optional filters:

- `--repo`
- `--service`
- `--language`
- `--symbol-type`
- `--symbol-name`

## Graph Commands

```bash
# Graph stats
python cli/code_geassistant_cli.py graph workspace_repo

# Neighbors (graph endpoint wrapper)
python cli/code_geassistant_cli.py neighbors workspace_repo orders --direction both

# Endpoint owners (graph endpoint wrapper)
python cli/code_geassistant_cli.py owners workspace_repo GET /orders
```

## Incremental Indexing

Ingestion is incremental by default.

Per run, the system computes file fingerprints and classifies files as:

- `new`
- `changed`
- `deleted`
- `unchanged`

Behavior:

- Re-chunks/re-extracts only `new/changed` files
- Removes vectors for `changed/deleted` files from Chroma
- Reuses cache records for `unchanged` files
- Rebuilds service graph from latest evidence

Cache artifacts (inside target workspace):

- `.code_geassistant_cache/chunks.jsonl`
- `.code_geassistant_cache/evidence.jsonl`
- `.code_geassistant_cache/service_graph.json`
- `.code_geassistant_cache/index_manifest.json`

## Environment Configuration

Copy `.env.example` to `.env` (optional), then override as needed.

Key variables:

- `CGA_CHROMA_DIR`
- `CGA_DEFAULT_LLM_MODEL`
- `CGA_TOP_K`
- `CGA_EMBEDDING_MODEL`
- `CGA_CHUNK_LINES`
- `CGA_OVERLAP_LINES`
- `CGA_MAX_FILE_SIZE_BYTES`

All config defaults are centralized in `settings.py`.

## API Endpoints

Base URL: `http://127.0.0.1:8000`

- `GET /health`
- `POST /ingest/start`
- `GET /ingest/status/{job_id}`
- `GET /workspaces`
- `POST /query`
- `GET /graph/{workspace_id}`
- `GET /graph/{workspace_id}/neighbors?service=<name>&direction=both`
- `POST /graph/owners`

Swagger docs: `http://127.0.0.1:8000/docs`

## Development

Install dev deps and run tests:

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Run a full local developer check:

```bash
# Windows
powershell -ExecutionPolicy Bypass -File scripts/dev-check.ps1

# macOS/Linux
bash scripts/dev-check.sh
```

## CI

GitHub Actions workflow is defined at:

- `.github/workflows/ci.yml`

It runs `pytest` on Python 3.10 and 3.11 using `requirements-ci.txt`.

## Troubleshooting

## 1) `ImportError: cached_download` from `sentence_transformers`

Dependency pins in `requirements*.txt` already fix this (`huggingface-hub==0.25.2`).
Recreate venv if needed:

```bash
# Windows
rmdir /s /q .venv
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1

# macOS/Linux
rm -rf .venv
bash scripts/setup.sh
```

## 2) `workspace_not_found` on query

Run ingest first and confirm workspace name:

```bash
python cli/code_geassistant_cli.py list
```

## 3) Graph endpoints return `graph_not_found`

Graph index is registered on ingest completion. Re-ingest target workspace once.

## 4) Slow query performance

- Use smaller LLM (`phi3:mini`, etc.)
- Reduce `CGA_TOP_K`
- Ensure Ollama model is already pulled and warm

## Cleanup

```bash
# Delete one workspace from Chroma
python cli/code_geassistant_cli.py cleanup workspace_repo

# Delete all workspaces (with confirmation)
python cli/code_geassistant_cli.py cleanup --all

# Also remove a workspace cache folder
python cli/code_geassistant_cli.py cleanup workspace_repo --cache /path/to/repo
```

## License

MIT. See [LICENSE](LICENSE).
