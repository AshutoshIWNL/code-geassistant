# =====================================
# Author: Ashutosh Mishra
# File: main.py
# Created: 2025-11-21
# =====================================

from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional
import uuid
import chromadb

from ingest.ingest_worker import ingest_workspace_to_chunks
from rag.pipeline import RAGPipeline


app = FastAPI(title="Code Geassistant - Local API (MVP)")

# In-memory ingest job tracking
INGEST_JOBS = {}

# Global RAG pipeline instance
pipeline = RAGPipeline(
    chroma_dir="./chroma_db",
    model_provider="ollama",
    model_name="deepseek-coder:1.3b",
    top_k=6,
)

# -----------------------------
# MODELS
# -----------------------------
class IngestStartRequest(BaseModel):
    workspace_path: str
    ignore_patterns: Optional[list[str]] = []

class QueryRequest(BaseModel):
    workspace_id: str
    model: Optional[str] = None  # Optional model override
    question: str


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
    job_id = str(uuid.uuid4())

    INGEST_JOBS[job_id] = {
        "status": "queued",
        "progress": 0,
        "workspace": payload.workspace_path,
        "ignore_patterns": payload.ignore_patterns or [],
        "total_files": 0,
        "files_processed": 0,
        "total_chunks": 0,
    }

    def real_ingest(job_id_local):
        job = INGEST_JOBS[job_id_local]
        try:
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
            embed_workspace(job["workspace"], chroma_dir="./chroma_db")

            job["status"] = "ready"

        except Exception as e:
            job["status"] = "error"
            job["error"] = repr(e)

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
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# -----------------------------
# LIST AVAILABLE WORKSPACES
# -----------------------------
@app.get("/workspaces")
def list_workspaces():
    """List all ingested workspace collections."""
    client = chromadb.PersistentClient(path="./chroma_db")
    return {
        "collections": [c.name for c in client.list_collections()]
    }


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
        # --- Validate workspace / collection ---
        client = chromadb.PersistentClient(path="./chroma_db")
        collections = {c.name for c in client.list_collections()}

        if req.workspace_id not in collections:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": f"Collection '{req.workspace_id}' not found.",
                    "available_collections": list(collections),
                }
            )

        # --- Optional: Dynamic Model Switching ---
        if req.model and req.model != pipeline.llm.model:
            from llm.llm_adapter import LLMAdapter
            pipeline.llm = LLMAdapter(
                provider="ollama",
                model=req.model
            )

        # --- Run full retrieval + LLM reasoning ---
        result = pipeline.answer_query(req.workspace_id, req.question)
        
        # Add metadata to response
        result["model_used"] = req.model or "deepseek-coder:1.3b"
        result["workspace"] = req.workspace_id
        
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {repr(e)}")


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
            "query": "POST /query"
        }
    }