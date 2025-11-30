# Code Geassistant 𓆩𓆪

A RAG-powered codebase assistant that helps you understand and navigate large codebases using natural language queries. Built with FastAPI, ChromaDB, and local LLMs (Ollama/llama.cpp).

## Features

- **Semantic Code Search** - Find code by meaning, not just keywords
- **Natural Language Q&A** - Ask questions about your codebase in plain English
- **Smart Chunking** - Automatic code splitting with overlap for context preservation
- **Gitignore-Aware** - Respects your .gitignore patterns automatically
- **Fast Embeddings** - Powered by sentence-transformers
- **Local LLMs** - Works with Ollama or llama.cpp (no API keys needed)
- **Cross-Platform CLI** - Works on Windows, Linux, and macOS
- **REST API** - Integrate with your own tools

## Quick Start

### Prerequisites

- Python 3.8+
- [Ollama](https://ollama.ai/) (or llama.cpp)
- 8GB+ RAM (16GB recommended)
- Optional: NVIDIA GPU for faster inference

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/code-geassistant.git
cd code-geassistant

# Install dependencies
pip install -r requirements.txt

# Pull an LLM model (using Ollama)
ollama pull deepseek-coder:1.3b
```

### Basic Usage

```bash
# 1. Start the server
python code_geassistant_cli.py start

# 2. Ingest your codebase
python code_geassistant_cli.py ingest /path/to/your/repository

# 3. Ask questions!
python code_geassistant_cli.py query workspace_repository "Where is the authentication logic?"

# 4. Stop when done
python code_geassistant_cli.py stop
```

## CLI Commands

### Server Management

```bash
# Start the API server
python code_geassistant_cli.py start

# Stop the API server
python code_geassistant_cli.py stop
```

### Workspace Management

```bash
# Ingest a workspace
python code_geassistant_cli.py ingest /path/to/repo

# Ingest with custom ignore patterns
python code_geassistant_cli.py ingest /path/to/repo --ignore "*.test.js" "*.spec.ts"

# List all ingested workspaces
python code_geassistant_cli.py list
```

### Querying

```bash
# Basic query
python code_geassistant_cli.py query workspace_myrepo "Where is authentication implemented?"

# Query with a specific model
python code_geassistant_cli.py query workspace_myrepo "How does logging work?" --model phi3:mini

# Compare different models
python code_geassistant_cli.py query workspace_myrepo "Explain the routing" --model qwen2.5-coder:1.5b
```

### Cleanup

```bash
# Delete a specific workspace (ChromaDB only)
python code_geassistant_cli.py cleanup workspace_myrepo

# Delete workspace + cache files
python code_geassistant_cli.py cleanup workspace_myrepo --cache /path/to/repo

# Delete ALL workspaces (with confirmation)
python code_geassistant_cli.py cleanup --all

# Nuclear option: delete everything
python code_geassistant_cli.py cleanup --all --cache /path/to/repo
```

## Architecture

```
┌─────────────────┐
│   User Query    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  FastAPI Server │
└────────┬────────┘
         │
         ├─────────────────┐
         │                 │
         ▼                 ▼
┌─────────────────┐  ┌─────────────────┐
│   Code Chunker  │  │   ChromaDB      │
│  (File Walker)  │  │  (Vector Store) │
└─────────────────┘  └─────────────────┘
         │                 │
         ▼                 ▼
┌─────────────────┐  ┌─────────────────┐
│  Sentence       │  │   Code          │
│  Transformers   │  │   Retriever     │
└─────────────────┘  └─────────────────┘
                           │
                           ▼
                     ┌─────────────────┐
                     │  LLM Adapter    │
                     │  (Ollama/llama) │
                     └─────────────────┘
```

### Components

- **File Walker** - Discovers source files, respects .gitignore, filters binaries
- **Chunker** - Splits files into 80-line chunks with 20-line overlap
- **Embedder** - Converts chunks to vectors using `all-MiniLM-L6-v2`
- **ChromaDB** - Persistent vector database for semantic search
- **Retriever** - Fetches top-k relevant chunks for queries
- **LLM Adapter** - Unified interface for Ollama/llama.cpp models

## Configuration

### Using Different Models

**You don't need to edit code!** Just pass the model name:

```bash
# CLI
python code_geassistant_cli.py query workspace_repo "Question?" --model phi3:mini

# Test script
./test_pipeline.sh /path/to/repo "Question?" "qwen2.5-coder:1.5b"

# API
curl -X POST http://localhost:8000/query \
  -d '{"workspace_id": "workspace_repo", "model": "phi3:mini", "question": "..."}'
```

### Changing the Default Model

**Only needed if you want a different default** when no model is specified.

Edit `main.py`:

```python
pipeline = RAGPipeline(
    chroma_dir="./chroma_db",
    model_provider="ollama",
    model_name="qwen2.5-coder:1.5b",  # Change default here
    top_k=6,
)
```

### Adjusting Chunk Size

Edit `ingest/chunker.py`:

```python
DEFAULT_CHUNK_LINES = 80    # Lines per chunk
DEFAULT_OVERLAP_LINES = 20  # Overlap between chunks
```

### Tuning Retrieval

Edit `main.py`:

```python
pipeline = RAGPipeline(
    chroma_dir="./chroma_db",
    model_provider="ollama",
    model_name="deepseek-coder:1.3b",
    top_k=6,  # Number of chunks to retrieve (3-10 recommended)
)
```

## Performance

**Benchmark Environment**: Lenovo ThinkPad P53, i7-9850H, 32GB RAM, CPU-only

| Operation | Time | Notes |
|-----------|------|-------|
| API Startup | 3-5s
| Codebase Ingestion (medium) | 18-30s | One-time per workspace |
| Query Execution (CPU) | 45-55s | With k=6, deepseek-coder:1.3b |

### Optimization Tips

**For CPU-only setups:**
- Use smaller models: `phi3:mini`, `qwen2.5-coder:1.5b`
- Reduce `top_k` to 3-4 (may affect answer quality)
- Reduce `max_tokens` in `llm_adapter.py`

**For GPU acceleration:**
1. Install NVIDIA proprietary drivers:
   ```bash
   sudo ubuntu-drivers autoinstall
   sudo reboot
   ```
2. Verify with `nvidia-smi`
3. Queries will be ~10x faster!

## Testing

Run the full pipeline test:

```bash
# Linux/Mac
./test_pipeline.sh /path/to/repo "Where is authentication?"

# Windows
test_pipeline.bat C:\path\to\repo "Where is authentication?"

# With custom model
./test_pipeline.sh /path/to/repo "Where is auth?" "phi3:mini"
```


## API Reference

The REST API runs on `http://localhost:8000` by default.

### Endpoints

#### `GET /health`
Health check endpoint.

#### `POST /ingest/start`
Start ingesting a workspace.
```json
{
  "workspace_path": "/path/to/repo",
  "ignore_patterns": ["*.test.js"]  // optional
}
```

#### `GET /ingest/status/{job_id}`
Check ingestion status.

#### `GET /workspaces`
List all ingested workspaces.

#### `POST /query`
Query a workspace.
```json
{
  "workspace_id": "workspace_myrepo",
  "question": "Where is authentication?",
  "model": "phi3:mini"  // optional
}
```

### Interactive API Docs

Visit `http://localhost:8000/docs` for Swagger UI.

## Contributing

Contributions are welcome! Areas for improvement:

- [ ] Streaming responses (SSE)
- [ ] Re-ranking layer (cross-encoder)
- [ ] Hybrid search (semantic + BM25)
- [ ] AST-aware chunking (tree-sitter)
- [ ] Multi-workspace queries
- [ ] Query history and caching
- [ ] Docker support
- [ ] Web UI (Streamlit/Gradio)

## Roadmap

### V1 (Current)
- ✅ Core RAG pipeline
- ✅ CLI interface
- ✅ REST API
- ✅ Ollama/llama.cpp support
- ✅ Cross-platform support

### V2 (Planned)
- [ ] GPU optimization
- [ ] Streaming responses
- [ ] Query caching
- [ ] Re-ranking
- [ ] Web UI
- [ ] Docker images
- [ ] Incremental updates

### V3 (Future)
- [ ] Multi-modal support (images, diagrams)
- [ ] Code generation
- [ ] PR review assistant
- [ ] VSCode extension

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- [ChromaDB](https://www.trychroma.com/) - Vector database
- [Sentence Transformers](https://www.sbert.net/) - Embedding models
- [Ollama](https://ollama.ai/) - Local LLM inference
- [FastAPI](https://fastapi.tiangolo.com/) - API framework

## Contact

**Ashutosh Mishra**
- GitHub: [@AshutoshIWNL](https://github.com/AshutoshIWNL)

---

**Star this repo** if you find it helpful!