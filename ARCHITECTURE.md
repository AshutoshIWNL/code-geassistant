# Code Geassistant: Current Architecture (As Implemented)

This document describes the current architecture of the project as it exists in code today.
It is intended as a re-onboarding guide for development and refactoring.

## 1. Purpose and Scope

Code Geassistant is a local, single-node RAG system for codebase Q&A:

1. Ingest a repository/workspace.
2. Chunk source files into semantic windows.
3. Embed chunks into ChromaDB.
4. Retrieve top-k relevant chunks for a question.
5. Ask an LLM to answer using retrieved context.

It currently optimizes for local usage, simple operations, and rapid iteration.

## 2. High-Level Component Map

```text
CLI (optional)                    FastAPI Service                      Storage/Models
-----------------                 ------------------                   -----------------------------
cli/code_geassistant_cli.py  ---> main.py endpoints               ---> chroma_db/ (Chroma collections)
                                |                                   \
                                |                                    -> sentence-transformers model
                                |                                    -> Ollama or llama.cpp model
                                v
                           rag/pipeline.py
                             |         \
                             |          -> llm/llm_adapter.py
                             v
                        ingest/retriever.py

Ingestion Path (triggered by API background task):
main.py -> ingest/ingest_worker.py -> ingest/filewalker.py + ingest/chunker.py
       -> writes .code_geassistant_cache/chunks.jsonl
       -> ingest/embedder.py -> ingest/embed_and_store.py -> Chroma upsert
```

## 3. Runtime Topology

Single process model:

1. `uvicorn main:app --port 8000` runs one FastAPI process.
2. In-memory job state is kept in a module-level dictionary `INGEST_JOBS`.
3. Chroma is used in local persistent mode (`./chroma_db`).
4. No external queue, cache, or DB beyond Chroma.

Implication: restart loses in-memory ingest job state but preserves vector data on disk.

## 4. Main Request Flows

## 4.1 Ingest Flow (`POST /ingest/start`)

Sequence:

1. API receives `workspace_path` + optional `ignore_patterns`.
2. A `job_id` is created and inserted into `INGEST_JOBS`.
3. FastAPI `BackgroundTasks` executes `real_ingest(job_id)`.
4. `ingest_workspace_to_chunks(...)`:
   - Walk files (`filewalker.walk_files`).
   - Chunk files (`chunker.chunk_file`).
   - Write JSONL to `<workspace>/.code_geassistant_cache/chunks.jsonl`.
5. `embed_workspace(...)` calls `persist_embeddings(...)`:
   - Read `chunks.jsonl`.
   - Embed text with `SentenceTransformer(all-MiniLM-L6-v2)`.
   - `upsert` into collection `workspace_<foldername>` in Chroma.
6. Job transitions to `ready` or `error`.

Job statuses currently used:

1. `queued`
2. `running_ingest`
3. `running` (set by `ingest_worker`)
4. `done` (chunking complete)
5. `running_embedding`
6. `ready`
7. `error`

## 4.2 Query Flow (`POST /query`)

Sequence:

1. Validate `workspace_id` exists by listing Chroma collections.
2. Route by `query_mode`:
   - `qa`: run RAG (`pipeline.answer_query(...)`).
   - `owner_of_endpoint`: load graph and resolve endpoint owners.
   - `neighbors`: load graph and return service neighbors.
   - `trace_flow`: load graph and BFS-trace service flow.
3. Return mode-specific structured payload plus shared metadata.

Model override behavior:

1. `QueryRequest.model` is optional.
2. If set and different from default pipeline model, a request-scoped `LLMAdapter` is created.
3. Global pipeline model instance is not mutated.

## 4.3 CLI Flow

CLI (`cli/code_geassistant_cli.py`) wraps API endpoints:

1. `start`: launches uvicorn and stores PID in `.code_geassistant_server.pid`.
2. `ingest`: calls `/ingest/start`, polls `/ingest/status/{job_id}`.
3. `query`: calls `/query` and prints answer + sources.
4. `list`: calls `/workspaces`.
5. `stop`: kills tracked PID only.
6. `cleanup`: deletes collection(s) and optional cache directory.

## 5. Module-by-Module Responsibilities

## 5.1 `main.py` (API Layer)

Responsibilities:

1. API contracts (request/response models).
2. Background ingest scheduling.
3. Job status tracking in memory.
4. Workspace existence checks.
5. Delegation to pipeline and ingest modules.

Key design decisions:

1. In-memory job store for simplicity.
2. One global `RAGPipeline` object for default retrieval/LLM wiring.
3. Per-request model override passed into pipeline, not global mutation.

## 5.2 `ingest/filewalker.py` (File Discovery + Filtering)

Responsibilities:

1. Read `.gitignore` patterns.
2. Apply additional ignore patterns from API request.
3. Skip known binary extensions.
4. Skip files with null bytes in first 8KB.
5. Skip files larger than 2MB.

Output shape per file:

```json
{
  "path": "absolute_path",
  "rel_path": "relative/path.ext",
  "ext": ".py",
  "size": 1234
}
```

## 5.3 `ingest/chunker.py` (Chunk Construction)

Responsibilities:

1. Read file text (`utf-8`, fallback `latin-1`).
2. Split into fixed line windows with overlap.
3. Add metadata:
   - `rel_path`
   - `start_line`, `end_line`
   - `n_lines`
   - `est_tokens` (char-length heuristic)

Default chunking strategy:

1. Chunk size: 80 lines.
2. Overlap: 20 lines.

## 5.4 `ingest/ingest_worker.py` (Chunking Job Orchestration)

Responsibilities:

1. Create workspace cache directory `.code_geassistant_cache`.
2. Delete previous `chunks.jsonl` for clean rebuild.
3. Iterate files and stream chunks to JSONL.
4. Update progress fields in shared `job_state`.

Writes:

`<workspace>/.code_geassistant_cache/chunks.jsonl`

Each line is a JSON object with chunk metadata + content.

## 5.5 `ingest/embedder.py` and `ingest/embed_and_store.py` (Embedding + Persistence)

Responsibilities:

1. Load all chunks from JSONL.
2. Build deterministic vector IDs using UUIDv5:
   - key = `<workspace_path>:<rel_path>:<start_line>`
3. Embed in batches using `SentenceTransformer`.
4. Persist to Chroma collection using `upsert` (idempotent re-ingestion).

Collection naming:

`workspace_<workspace_folder_name>`

Stored metadata per vector:

1. `rel_path`
2. `start_line`
3. `end_line`
4. `n_lines`
5. `est_tokens`

## 5.6 `ingest/retriever.py` (Semantic Retrieval + Prompt Assembly)

Responsibilities:

1. Load sentence-transformer model for query embeddings.
2. Query existing Chroma collection.
3. Convert Chroma distance to similarity score (`1 - distance`).
4. Build a prompt with chunk delimiters and source line ranges.

Prompt shape:

1. System-like preface: `You are a code assistant with full context.`
2. Repeated chunk sections with file path + line spans.
3. Question section appended at end.

## 5.7 `rag/pipeline.py` (RAG Coordinator)

Responsibilities:

1. Call retriever for context.
2. Build prompt from retrieved chunks.
3. Call LLM adapter for completion.
4. Return answer + citation-friendly source list + `model_used`.

## 5.8 `llm/llm_adapter.py` (LLM Provider Abstraction)

Supported providers:

1. `ollama`
2. `llamacpp`

Responsibilities:

1. Non-streaming generation (`generate`).
2. Streaming generation (`stream`) at adapter level.

Current API path uses `generate` only (no SSE endpoint yet).

## 5.9 `cli/code_geassistant_cli.py` (Operator Interface)

Responsibilities:

1. Cross-platform UX wrapper around REST API.
2. Server lifecycle management with PID file.
3. Polling and console rendering of ingest/query results.
4. Basic cleanup operations.

## 6. Data Model and Contracts

## 6.1 API Request Contracts

`POST /ingest/start`

```json
{
  "workspace_path": "C:/path/to/repo",
  "ignore_patterns": ["*.log", "node_modules/"]
}
```

`POST /query`

```json
{
  "workspace_id": "workspace_myrepo",
  "query_mode": "qa",
  "question": "Where is authentication logic?",
  "model": "deepseek-coder:1.3b",
  "service": "orders",
  "method": "GET",
  "path": "/orders",
  "direction": "both",
  "trace_depth": 2
}
```

## 6.2 API Response Contracts

`GET /workspaces`

```json
{
  "collections": ["workspace_serviceA", "workspace_serviceB"]
}
```

`POST /query` (shape)

```json
{
  "answer": "...",
  "sources": [
    {
      "rel_path": "src/auth/service.py",
      "start_line": 10,
      "end_line": 80,
      "score": 0.78
    }
  ],
  "model_used": "deepseek-coder:1.3b",
  "workspace": "workspace_serviceA"
}
```

## 6.3 On-Disk Artifacts

1. `./chroma_db/`:
   - Persistent Chroma collections.
2. `<workspace>/.code_geassistant_cache/chunks.jsonl`:
   - Intermediate chunk cache for embedding.
3. `<workspace>/.code_geassistant_cache/evidence.jsonl`:
   - Extracted route/call/message evidence records.
4. `<workspace>/.code_geassistant_cache/service_graph.json`:
   - Generated graph sidecar with nodes/edges/indexes.
5. `<workspace>/.code_geassistant_cache/index_manifest.json`:
   - File fingerprint map used for incremental indexing.
6. `./.code_geassistant_server.pid`:
   - CLI-tracked uvicorn process ID.

## 7. Configuration Surface (Current)

Defaults are centralized in `settings.py` and can be overridden by environment variables:

1. Chroma path: `./chroma_db`
2. Default LLM model: `deepseek-coder:1.3b`
3. Retriever top-k: `6`
4. Embedding model: `all-MiniLM-L6-v2`
5. Chunking: `80` lines, `20` overlap
6. File max size: `2MB`

No centralized config file yet.

## 8. Operational Characteristics

## 8.1 Concurrency

1. Ingest jobs are background tasks in same process.
2. Job state lives in shared memory dictionary.
3. Query requests are synchronous HTTP calls.

Notes:

1. No queueing/backpressure.
2. No explicit locking around `INGEST_JOBS`.
3. Suitable for local/single-user workflows, not production multi-tenant load.

## 8.2 Failure Handling

1. Ingest errors are captured per job and surfaced in `/ingest/status/{job_id}`.
2. Query errors return HTTP 500 with exception representation.
3. Missing workspace collection returns HTTP 404 with available collections.

## 8.3 Idempotency

1. Re-ingestion is now idempotent at vector-write layer due to `upsert`.
2. Chunk/evidence cache files are rewritten each run, but unchanged file records are reused from prior cache.
3. Incremental indexing uses a fingerprint manifest to process only new/changed files.
4. Deleted file vectors are removed by metadata filter (`rel_path`) before re-embedding.

## 9. Known Gaps and Tradeoffs (Current State)

1. No authentication/authorization on API.
2. No persistent job store.
3. No streaming query API endpoint despite adapter support.
4. Prompting is raw context concatenation (no reranking/compression).
5. Ignore logic approximates `.gitignore`, not full spec parity.
6. Evidence extraction is heuristic-only; no AST parser yet.
7. Testing relies mostly on scripts, not a full `pytest` suite.
8. Config is code-first; environment/config file support is limited.

## 10. How to Read the Code Quickly

Recommended order for re-familiarization:

1. `main.py` (API entrypoints and orchestration)
2. `rag/pipeline.py` (query control flow)
3. `ingest/ingest_worker.py` (ingest control flow)
4. `ingest/filewalker.py` + `ingest/chunker.py` (input shaping)
5. `ingest/embed_and_store.py` + `ingest/retriever.py` (vector lifecycle)
6. `llm/llm_adapter.py` (model integration)
7. `cli/code_geassistant_cli.py` (operator UX and practical usage)

## 11. Current Architecture Summary

The system is a clean local RAG stack with:

1. FastAPI orchestration.
2. JSONL intermediate chunk cache.
3. Sentence-transformer embeddings in Chroma.
4. Retriever-driven prompt assembly.
5. Local LLM completion (Ollama/llama.cpp).
6. Heuristic evidence extraction and service graph sidecar generation.

It is a strong base for refactoring toward your microservice flow goal without rewriting from scratch.

## 12. Refactor Plan (Phased, No Rewrite)

This plan keeps the current architecture and adds capabilities incrementally.

## 12.1 Guiding Principles

1. Do not break existing CLI/API behavior for Q&A.
2. Add new capabilities behind optional fields/endpoints first.
3. Preserve ingestion speed and idempotency.
4. Keep language support plugin-based, not framework-specific.

## 12.2 Phase 0: Stabilization (Short)

Goal: strengthen reliability before adding features.

Tasks:

1. Add automated tests (`pytest`) for:
   - Ingest job lifecycle states.
   - Re-ingestion idempotency.
   - Query response shape (`answer`, `sources`, `model_used`, `workspace`).
2. Add a centralized config layer (`settings.py` or `.env`) for:
   - Paths (`chroma_dir`).
   - Chunk size/overlap.
   - Default model/top_k.
3. Normalize error responses for ingest/query.
4. Add structured logging (JSON or consistent key/value logs).

Success criteria:

1. Green test suite on core flows.
2. Config changes no longer require code edits.

## 12.3 Phase 1: Metadata Foundation (Language-Agnostic)

Goal: move from plain chunks to enriched retrievable evidence.

Tasks:

1. Extend chunk metadata schema with optional fields:
   - `service`
   - `repo`
   - `language`
   - `symbol_type`
   - `symbol_name`
2. Infer service/repo identity during ingest:
   - Prefer folder/repo root naming conventions.
3. Persist enriched metadata into Chroma alongside existing fields.
4. Expose metadata filters in retriever (optional `where` support).

Success criteria:

1. Query can be scoped to service/repo without changing old query format.
2. Existing workspaces still query successfully.

## 12.4 Phase 2: Pluggable Extractor Layer

Goal: collect API and call-site evidence independent of language choice.

Tasks:

1. Create extractor interface (e.g. `extractors/base.py`):
   - `detect(file_info) -> bool`
   - `extract(file_info, lines) -> list[evidence]`
2. Implement first extractor set using heuristics/regex:
   - HTTP route definitions.
   - Outbound HTTP calls.
   - Message publish/consume patterns.
3. Store extractor outputs as normalized evidence records in cache.
4. Link evidence records to source file and line spans.

Success criteria:

1. Ingest produces evidence records for at least one stack per language family.
2. Evidence records are queryable and citation-backed.

## 12.5 Phase 3: Service Graph (Sidecar Store)

Goal: represent cross-service flow explicitly.

Tasks:

1. Add lightweight graph storage (JSON/SQLite/NetworkX) per workspace.
2. Build nodes:
   - service
   - endpoint
   - topic/queue (if detected)
3. Build edges with evidence:
   - `service -> endpoint`
   - `endpoint -> outbound_call`
   - `service -> topic` / `topic -> service`
4. Add version field to graph schema for future migrations.

Success criteria:

1. Able to answer “who handles endpoint X?”
2. Able to return first-order upstream/downstream neighbors with evidence.

## 12.6 Phase 4: New Query Modes (Keep Existing Q&A)

Goal: expose flow-centric capabilities while preserving current endpoint.

Tasks:

1. Add `query_mode` in `/query` request:
   - `qa` (default, current behavior)
   - `owner_of_endpoint`
   - `trace_flow`
   - `neighbors`
2. Route mode-specific logic in `RAGPipeline` or a new orchestrator.
3. Return structured results for flow modes:
   - steps
   - edges
   - confidence
   - missing links
4. Keep LLM summarization as optional final formatting pass.

Success criteria:

1. Existing clients continue to work with `qa` default.
2. Flow questions return structured evidence, not only prose.

## 12.7 Phase 5: Incremental Indexing

Goal: make daily usage fast for multi-service environments.

Tasks:

1. Track file fingerprint (mtime/hash) in cache.
2. Re-chunk/re-embed only changed files.
3. Remove stale vectors/evidence for deleted files.
4. Rebuild graph incrementally.

Success criteria:

1. Reindex time is proportional to changed files, not full repo size.

## 12.8 Phase 6: Developer Experience

Goal: improve day-to-day usability for real debugging workflows.

Tasks:

1. Add CLI commands for flow use cases:
   - `trace-endpoint`
   - `who-owns`
   - `neighbors`
2. Add export options (`json`, `md`) for sharing investigations.
3. Add optional simple web view for graph navigation.

Success criteria:

1. Common flow questions can be solved from CLI in one command.

## 12.9 Suggested Execution Order

1. Phase 0
2. Phase 1
3. Phase 2
4. Phase 3
5. Phase 4
6. Phase 5
7. Phase 6

Rationale:

1. Stability first.
2. Metadata before graph.
3. Graph before flow query APIs.
4. Performance optimization after correctness.

## 12.10 Minimal Milestone Definition

“Useful for microservice tracing” can be declared when all are true:

1. Endpoint ownership lookup works with code evidence.
2. At least one-hop service-to-service flow trace works with evidence.
3. Unknown links are explicitly reported.
4. Reindex after small change is fast enough for daily use.
