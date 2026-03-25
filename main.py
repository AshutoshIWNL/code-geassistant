# =====================================
# Author: Ashutosh Mishra
# File: main.py
# Created: 2025-11-21
# =====================================

from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
import uuid
import chromadb
import logging
from pathlib import Path

from ingest.ingest_worker import ingest_workspace_to_chunks
from ingest.graph_builder import load_graph, find_neighbors, find_endpoint_owners, trace_service_flow
from rag.pipeline import RAGPipeline
from settings import get_settings


app = FastAPI(title="Code Geassistant - Local API (MVP)")
settings = get_settings()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s level=%(levelname)s logger=%(name)s message=%(message)s",
)
logger = logging.getLogger("code_geassistant.api")

# In-memory ingest job tracking
INGEST_JOBS = {}
GRAPH_INDEX = {}

# Lazy-initialized global RAG pipeline instance
PIPELINE: Optional[RAGPipeline] = None


def get_pipeline() -> RAGPipeline:
    global PIPELINE
    if PIPELINE is None:
        logger.info(
            "event=pipeline_init chroma_dir=%s model_provider=%s model=%s top_k=%s",
            settings.chroma_dir,
            settings.model_provider,
            settings.default_llm_model,
            settings.top_k,
        )
        PIPELINE = RAGPipeline(
            chroma_dir=settings.chroma_dir,
            model_provider=settings.model_provider,
            model_name=settings.default_llm_model,
            top_k=settings.top_k,
        )
    return PIPELINE


def error_detail(code: str, message: str, details: Optional[dict] = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        }
    }

# -----------------------------
# MODELS
# -----------------------------
class IngestStartRequest(BaseModel):
    workspace_path: str
    ignore_patterns: List[str] = Field(default_factory=list)

class QueryRequest(BaseModel):
    workspace_id: str
    model: Optional[str] = None  # Optional model override
    question: Optional[str] = None
    query_mode: Literal["qa", "owner_of_endpoint", "neighbors", "trace_flow"] = "qa"
    repo: Optional[str] = None
    service: Optional[str] = None
    language: Optional[str] = None
    symbol_type: Optional[str] = None
    symbol_name: Optional[str] = None
    method: Optional[str] = None
    path: Optional[str] = None
    direction: str = "both"
    trace_depth: int = 2


class GraphOwnersRequest(BaseModel):
    workspace_id: str
    method: str
    path: str


def build_metadata_filter(req: QueryRequest) -> dict:
    metadata_filter = {}
    if req.repo:
        metadata_filter["repo"] = req.repo
    if req.service:
        metadata_filter["service"] = req.service
    if req.language:
        metadata_filter["language"] = req.language
    if req.symbol_type:
        metadata_filter["symbol_type"] = req.symbol_type
    if req.symbol_name:
        metadata_filter["symbol_name"] = req.symbol_name
    return metadata_filter


# -----------------------------
# HEALTH CHECK
# -----------------------------
@app.get("/health")
def health():
    """Health check endpoint for monitoring and startup verification."""
    return {"status": "ok", "service": "Code Geassistant"}


# -----------------------------
# INGEST START
# -----------------------------
@app.post("/ingest/start")
def ingest_start(payload: IngestStartRequest, background_tasks: BackgroundTasks):
    """
    Start a background job to ingest a workspace.
    Returns job_id for tracking progress.
    """
    workspace = Path(payload.workspace_path).resolve()
    if not workspace.exists() or not workspace.is_dir():
        raise HTTPException(
            status_code=400,
            detail=error_detail(
                "invalid_workspace",
                "workspace_path must point to an existing directory",
                {"workspace_path": payload.workspace_path},
            ),
        )

    job_id = str(uuid.uuid4())
    logger.info("event=ingest_queued job_id=%s workspace=%s", job_id, workspace)

    INGEST_JOBS[job_id] = {
        "status": "queued",
        "progress": 0,
        "workspace": str(workspace),
        "ignore_patterns": payload.ignore_patterns or [],
        "total_files": 0,
        "files_processed": 0,
        "total_chunks": 0,
        "total_evidence": 0,
        "graph_nodes": 0,
        "graph_edges": 0,
        "new_files": 0,
        "changed_files": 0,
        "deleted_files": 0,
        "unchanged_files": 0,
    }

    def real_ingest(job_id_local):
        job = INGEST_JOBS[job_id_local]
        try:
            logger.info("event=ingest_started job_id=%s workspace=%s", job_id_local, job["workspace"])
            job["status"] = "running_ingest"
            summary = ingest_workspace_to_chunks(
                job["workspace"],
                job,
                extra_ignores=job["ignore_patterns"]
            )
            job["summary"] = summary

            # ------- Auto embedding step -------
            job["status"] = "running_embedding"
            from ingest.embedder import embed_workspace
            embed_workspace(
                job["workspace"],
                chroma_dir=settings.chroma_dir,
                changed_or_new_rel_paths=summary.get("changed_or_new_rel_paths"),
                deleted_rel_paths=summary.get("deleted_rel_paths"),
            )

            job["status"] = "ready"
            workspace_id = f"workspace_{Path(job['workspace']).name}"
            graph_file = job.get("summary", {}).get("graph_file")
            if graph_file:
                GRAPH_INDEX[workspace_id] = graph_file
            logger.info(
                "event=ingest_ready job_id=%s workspace=%s files=%s chunks=%s evidence=%s graph_nodes=%s graph_edges=%s new=%s changed=%s deleted=%s unchanged=%s",
                job_id_local,
                job["workspace"],
                job.get("files_processed", 0),
                job.get("total_chunks", 0),
                job.get("total_evidence", 0),
                job.get("graph_nodes", 0),
                job.get("graph_edges", 0),
                job.get("new_files", 0),
                job.get("changed_files", 0),
                job.get("deleted_files", 0),
                job.get("unchanged_files", 0),
            )

        except Exception as e:
            job["status"] = "error"
            job["error"] = repr(e)
            logger.exception("event=ingest_error job_id=%s workspace=%s", job_id_local, job["workspace"])

    background_tasks.add_task(real_ingest, job_id)
    return {"job_id": job_id, "message": "ingest job queued"}


# -----------------------------
# INGEST STATUS
# -----------------------------
@app.get("/ingest/status/{job_id}")
def ingest_status(job_id: str):
    """Get the status of an ingestion job."""
    job = INGEST_JOBS.get(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail=error_detail("job_not_found", "Ingest job not found", {"job_id": job_id}),
        )
    return job


# -----------------------------
# LIST AVAILABLE WORKSPACES
# -----------------------------
@app.get("/workspaces")
def list_workspaces():
    """List all ingested workspace collections."""
    client = chromadb.PersistentClient(path=settings.chroma_dir)
    return {
        "collections": [c.name for c in client.list_collections()]
    }


def _resolve_graph_file(workspace_id: str) -> Path:
    graph_path = GRAPH_INDEX.get(workspace_id)
    if not graph_path:
        raise HTTPException(
            status_code=404,
            detail=error_detail(
                "graph_not_found",
                "Service graph not indexed in-memory for workspace. Re-ingest workspace to generate and register graph.",
                {"workspace_id": workspace_id},
            ),
        )
    p = Path(graph_path)
    if not p.exists():
        raise HTTPException(
            status_code=404,
            detail=error_detail(
                "graph_file_missing",
                "Indexed graph file does not exist on disk.",
                {"workspace_id": workspace_id, "graph_file": graph_path},
            ),
        )
    return p


@app.get("/graph/{workspace_id}")
def get_graph(workspace_id: str):
    graph_file = _resolve_graph_file(workspace_id)
    return load_graph(graph_file)


@app.get("/graph/{workspace_id}/neighbors")
def get_graph_neighbors(workspace_id: str, service: str, direction: str = "both"):
    graph_file = _resolve_graph_file(workspace_id)
    graph = load_graph(graph_file)
    return find_neighbors(graph, service=service, direction=direction)


@app.post("/graph/owners")
def graph_endpoint_owners(payload: GraphOwnersRequest):
    graph_file = _resolve_graph_file(payload.workspace_id)
    graph = load_graph(graph_file)
    return find_endpoint_owners(graph, method=payload.method, path=payload.path)


# -----------------------------
# QUERY (RAG)
# -----------------------------
@app.post("/query")
def query(req: QueryRequest):
    """
    Query an ingested workspace using natural language.
    Optionally override the LLM model for this request.
    """
    try:
        logger.info("event=query_received workspace=%s model_override=%s", req.workspace_id, req.model or "")
        # --- Validate workspace / collection ---
        client = chromadb.PersistentClient(path=settings.chroma_dir)
        collections = {c.name for c in client.list_collections()}

        if req.workspace_id not in collections:
            raise HTTPException(
                status_code=404,
                detail=error_detail(
                    "workspace_not_found",
                    "Workspace collection not found",
                    {
                        "workspace_id": req.workspace_id,
                        "available_collections": list(collections),
                    },
                ),
            )

        # --- Run full retrieval + LLM reasoning ---
        metadata_filter = build_metadata_filter(req)
        mode = req.query_mode

        if mode == "qa":
            if not req.question:
                raise HTTPException(
                    status_code=400,
                    detail=error_detail(
                        "missing_question",
                        "question is required when query_mode='qa'",
                    ),
                )
            result = get_pipeline().answer_query(
                req.workspace_id,
                req.question,
                model_name=req.model,
                metadata_filter=metadata_filter or None,
            )
            result["filters_applied"] = metadata_filter

        elif mode == "owner_of_endpoint":
            if not req.method or not req.path:
                raise HTTPException(
                    status_code=400,
                    detail=error_detail(
                        "missing_endpoint",
                        "method and path are required when query_mode='owner_of_endpoint'",
                    ),
                )
            graph = load_graph(_resolve_graph_file(req.workspace_id))
            owners = find_endpoint_owners(graph, method=req.method, path=req.path)
            result = {
                "query_mode": mode,
                "owners": owners,
                "confidence": "medium",
                "missing_links": [] if owners.get("owners") else ["no owner found"],
            }

        elif mode == "neighbors":
            if not req.service:
                raise HTTPException(
                    status_code=400,
                    detail=error_detail(
                        "missing_service",
                        "service is required when query_mode='neighbors'",
                    ),
                )
            graph = load_graph(_resolve_graph_file(req.workspace_id))
            neigh = find_neighbors(graph, service=req.service, direction=req.direction)
            result = {
                "query_mode": mode,
                "neighbors": neigh,
                "confidence": "medium" if (neigh.get("incoming") or neigh.get("outgoing")) else "low",
                "missing_links": [] if (neigh.get("incoming") or neigh.get("outgoing")) else ["no neighbors found"],
            }

        elif mode == "trace_flow":
            graph = load_graph(_resolve_graph_file(req.workspace_id))
            start_service = req.service
            if not start_service and req.method and req.path:
                owners = find_endpoint_owners(graph, method=req.method, path=req.path).get("owners", [])
                if owners:
                    start_service = owners[0]
            if not start_service:
                raise HTTPException(
                    status_code=400,
                    detail=error_detail(
                        "missing_trace_anchor",
                        "trace_flow requires either service, or method+path with resolvable owner",
                    ),
                )
            flow = trace_service_flow(graph, start_service=start_service, max_depth=max(1, min(req.trace_depth, 6)))
            result = {
                "query_mode": mode,
                "flow": flow,
                "confidence": flow.get("confidence", "low"),
                "missing_links": flow.get("missing_links", []),
            }

        else:
            raise HTTPException(
                status_code=400,
                detail=error_detail("invalid_query_mode", f"Unsupported query_mode: {mode}"),
            )

        # Add shared response metadata
        result["workspace"] = req.workspace_id
        result["query_mode"] = mode

        logger.info(
            "event=query_success workspace=%s mode=%s model_used=%s source_count=%s",
            req.workspace_id,
            mode,
            result.get("model_used"),
            len(result.get("sources", [])),
        )
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("event=query_error workspace=%s", req.workspace_id)
        raise HTTPException(
            status_code=500,
            detail=error_detail(
                "query_failed",
                "Query execution failed",
                {"exception": repr(e)},
            ),
        )


# -----------------------------
# ROOT
# -----------------------------
@app.get("/")
def root():
    """API information endpoint."""
    return {
        "service": "Code Geassistant",
        "version": "0.1.0-alpha",
        "docs": "/docs",
        "endpoints": {
            "health": "GET /health",
            "ingest": "POST /ingest/start",
            "status": "GET /ingest/status/{job_id}",
            "workspaces": "GET /workspaces",
            "query": "POST /query",
            "graph": "GET /graph/{workspace_id}",
            "neighbors": "GET /graph/{workspace_id}/neighbors?service=...&direction=both",
            "owners": "POST /graph/owners"
        }
    }
