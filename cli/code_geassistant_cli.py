#!/usr/bin/env python3
# =====================================
# Author: Ashutosh Mishra
# File: code_geassistant_cli.py
# Created: 2025-11-30
# =====================================

"""
Code Geassistant CLI - Cross-platform command-line interface
Works on Windows, Linux, and macOS
"""

import argparse
import sys
import time
import subprocess
import json
import os
from pathlib import Path
from typing import Optional
import requests

API_URL = "http://127.0.0.1:8000"
DEFAULT_MODEL = "deepseek-coder:1.3b"
SERVER_PID_FILE = Path(".code_geassistant_server.pid")


class Colors:
    """ANSI color codes (work on Linux/Mac, fallback on Windows)"""
    if sys.platform == "win32":
        # Enable ANSI colors on Windows 10+
        os.system("")
    
    BLUE = "\033[1;34m"
    GREEN = "\033[1;32m"
    YELLOW = "\033[1;33m"
    RED = "\033[1;31m"
    CYAN = "\033[1;36m"
    NC = "\033[0m"


def log(message: str):
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {message}")


def success(message: str):
    print(f"{Colors.GREEN}[OK]{Colors.NC} {message}")


def error(message: str):
    print(f"{Colors.RED}[ERROR]{Colors.NC} {message}")


def warning(message: str):
    print(f"{Colors.YELLOW}[WARN]{Colors.NC} {message}")


def check_server():
    """Check if the API server is running"""
    try:
        response = requests.get(f"{API_URL}/health", timeout=2)
        return response.status_code == 200
    except:
        return False


def read_server_pid() -> Optional[int]:
    """Read tracked uvicorn PID from disk, if available."""
    if not SERVER_PID_FILE.exists():
        return None
    try:
        return int(SERVER_PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def write_server_pid(pid: int):
    SERVER_PID_FILE.write_text(str(pid), encoding="utf-8")


def clear_server_pid():
    if SERVER_PID_FILE.exists():
        SERVER_PID_FILE.unlink()


def is_pid_running(pid: int) -> bool:
    """Best-effort process existence check by PID."""
    if pid <= 0:
        return False

    if sys.platform == "win32":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True,
            text=True
        )
        return str(pid) in result.stdout

    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start_server():
    """Start the uvicorn server in the background"""
    log("Starting Code Geassistant server...")

    existing_pid = read_server_pid()
    if existing_pid and is_pid_running(existing_pid):
        success(f"Server already running (PID: {existing_pid})")
        return True
    clear_server_pid()

    # Different commands for Windows vs Unix
    if sys.platform == "win32":
        proc = subprocess.Popen(
            ["uvicorn", "main:app", "--port", "8000"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        proc = subprocess.Popen(
            ["uvicorn", "main:app", "--port", "8000"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )

    write_server_pid(proc.pid)

    # Wait for server to be ready
    max_wait = 30
    for i in range(max_wait):
        if check_server():
            success(f"Server ready (PID: {proc.pid}, took {i+1}s)")
            return True
        time.sleep(1)

    if is_pid_running(proc.pid):
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.terminate()

    clear_server_pid()
    error("Server failed to start within 30s")
    return False


def ingest_workspace(workspace_path: str, ignore_patterns: Optional[list] = None):
    """Ingest a workspace into the system"""
    workspace_path = str(Path(workspace_path).resolve())
    
    if not Path(workspace_path).exists():
        error(f"Workspace does not exist: {workspace_path}")
        return None
    
    log(f"Starting ingestion of: {workspace_path}")
    
    payload = {"workspace_path": workspace_path}
    if ignore_patterns:
        payload["ignore_patterns"] = ignore_patterns
    
    try:
        response = requests.post(f"{API_URL}/ingest/start", json=payload, timeout=10)
        response.raise_for_status()
        job_id = response.json()["job_id"]
        success(f"Ingestion started (Job ID: {job_id})")
        
        # Poll for completion
        log("Waiting for ingestion to complete...")
        start_time = time.time()
        
        while True:
            status_response = requests.get(f"{API_URL}/ingest/status/{job_id}")
            status_data = status_response.json()
            status = status_data.get("status")
            
            if status == "ready":
                duration = int(time.time() - start_time)
                success(f"Ingestion complete! ({duration}s)")
                print(f"  Files processed: {status_data.get('files_processed', 0)}")
                print(f"  Chunks created: {status_data.get('total_chunks', 0)}")
                print(
                    "  Incremental: "
                    f"new={status_data.get('new_files', 0)} "
                    f"changed={status_data.get('changed_files', 0)} "
                    f"deleted={status_data.get('deleted_files', 0)} "
                    f"unchanged={status_data.get('unchanged_files', 0)}"
                )
                return job_id
            
            elif status == "error":
                error(f"Ingestion failed: {status_data.get('error', 'Unknown error')}")
                return None
            
            # Show progress
            progress = status_data.get("progress", 0)
            current_file = status_data.get("current_file", "")
            print(f"  Progress: {progress}% - {current_file}", end="\r")
            
            time.sleep(2)
    
    except Exception as e:
        error(f"Ingestion failed: {e}")
        return None


def list_workspaces():
    """List all available workspaces"""
    try:
        response = requests.get(f"{API_URL}/workspaces", timeout=5)
        response.raise_for_status()
        data = response.json()
        collections = data.get("collections", [])
        
        if not collections:
            warning("No workspaces found. Ingest a workspace first.")
        else:
            success(f"Found {len(collections)} workspace(s):")
            for i, name in enumerate(collections, 1):
                print(f"  {i}. {name}")
        
        return collections
    
    except Exception as e:
        error(f"Failed to list workspaces: {e}")
        return []


def query_workspace(
    workspace_id: str,
    question: Optional[str] = None,
    model: Optional[str] = None,
    repo: Optional[str] = None,
    service: Optional[str] = None,
    language: Optional[str] = None,
    symbol_type: Optional[str] = None,
    symbol_name: Optional[str] = None,
    query_mode: str = "qa",
    method: Optional[str] = None,
    path: Optional[str] = None,
    direction: str = "both",
    trace_depth: int = 2,
):
    """Query a workspace"""
    log(f"Querying workspace: {workspace_id}")
    if question:
        log(f"Question: {question}")
    log(f"Mode: {query_mode}")
    
    payload = {
        "workspace_id": workspace_id,
        "query_mode": query_mode,
    }
    if question:
        payload["question"] = question
    
    if model:
        payload["model"] = model
        log(f"Using model: {model}")

    if repo:
        payload["repo"] = repo
    if service:
        payload["service"] = service
    if language:
        payload["language"] = language
    if symbol_type:
        payload["symbol_type"] = symbol_type
    if symbol_name:
        payload["symbol_name"] = symbol_name
    if method:
        payload["method"] = method
    if path:
        payload["path"] = path
    if direction:
        payload["direction"] = direction
    payload["trace_depth"] = trace_depth
    
    try:
        start_time = time.time()
        response = requests.post(f"{API_URL}/query", json=payload, timeout=120)
        response.raise_for_status()
        duration = time.time() - start_time
        
        data = response.json()
        
        print(f"\n{Colors.CYAN}{'='*60}")
        print(f"ANSWER (took {duration:.1f}s)")
        print(f"{'='*60}{Colors.NC}\n")
        
        if data.get("query_mode") == "qa":
            print(data.get("answer", "No answer generated"))
        else:
            print(json.dumps(data, indent=2))

        sources = data.get("sources", []) if data.get("query_mode") == "qa" else []
        if sources:
            print(f"\n{Colors.CYAN}{'='*60}")
            print(f"SOURCES ({len(sources)} chunks)")
            print(f"{'='*60}{Colors.NC}\n")
            
            for i, source in enumerate(sources, 1):
                print(
                    f"{i}. {source['rel_path']} "
                    f"(lines {source['start_line']}-{source['end_line']}) "
                    f"[score: {source['score']:.3f}]"
                )
                tags = []
                if source.get("service"):
                    tags.append(f"service={source['service']}")
                if source.get("repo"):
                    tags.append(f"repo={source['repo']}")
                if source.get("language"):
                    tags.append(f"language={source['language']}")
                if source.get("symbol_type"):
                    tags.append(f"symbol_type={source['symbol_type']}")
                if tags:
                    print(f"   {' | '.join(tags)}")
        
        print()
        return data
    
    except requests.exceptions.Timeout:
        error("Query timed out (>120s). Try a simpler question or use a faster model.")
        return None
    except Exception as e:
        error(f"Query failed: {e}")
        return None


def show_graph(workspace_id: str):
    try:
        response = requests.get(f"{API_URL}/graph/{workspace_id}", timeout=20)
        response.raise_for_status()
        data = response.json()
        stats = data.get("stats", {})
        success(
            f"Graph loaded: nodes={stats.get('nodes', 0)} "
            f"edges={stats.get('edges', 0)} evidence={stats.get('evidence_records', 0)}"
        )
        return data
    except Exception as e:
        error(f"Graph fetch failed: {e}")
        return None


def show_neighbors(workspace_id: str, service: str, direction: str = "both"):
    try:
        response = requests.get(
            f"{API_URL}/graph/{workspace_id}/neighbors",
            params={"service": service, "direction": direction},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        success(
            f"Neighbors for '{service}': "
            f"outgoing={len(data.get('outgoing', []))} incoming={len(data.get('incoming', []))}"
        )
        return data
    except Exception as e:
        error(f"Neighbors query failed: {e}")
        return None


def show_endpoint_owners(workspace_id: str, method: str, path: str):
    try:
        response = requests.post(
            f"{API_URL}/graph/owners",
            json={"workspace_id": workspace_id, "method": method, "path": path},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        owners = data.get("owners", [])
        if owners:
            success(f"Owners for {data.get('method')} {data.get('path')}: {', '.join(owners)}")
        else:
            warning(f"No owners found for {data.get('method')} {data.get('path')}")
        return data
    except Exception as e:
        error(f"Endpoint owner lookup failed: {e}")
        return None


def stop_server():
    """Stop the uvicorn server started by this CLI."""
    log("Stopping Code Geassistant server...")

    pid = read_server_pid()
    if not pid:
        warning("No tracked server PID found. Nothing to stop.")
        return False

    if not is_pid_running(pid):
        clear_server_pid()
        warning(f"Tracked PID {pid} is not running. Cleared PID file.")
        return False

    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            text=True
        )
    else:
        os.kill(pid, 15)

    clear_server_pid()
    success(f"Server stopped (PID: {pid})")
    return True


def cleanup_workspaces(workspace_id: Optional[str] = None, cache_path: Optional[str] = None):
    """Clean up workspace data (ChromaDB + cache files)"""
    import shutil
    
    chroma_dir = Path("./chroma_db")
    
    if workspace_id:
        # Delete specific workspace from ChromaDB
        log(f"Cleaning up workspace: {workspace_id}")
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(chroma_dir))
            client.delete_collection(workspace_id)
            success(f"Workspace '{workspace_id}' deleted from ChromaDB")
            
            # Also clean cache if path provided
            if cache_path:
                cache_dir = Path(cache_path) / ".code_geassistant_cache"
                if cache_dir.exists():
                    shutil.rmtree(cache_dir)
                    success(f"Cache deleted: {cache_dir}")
                else:
                    warning(f"Cache not found: {cache_dir}")
            else:
                warning("Cache path not provided. Use --cache flag to also delete cache files.")
                
        except Exception as e:
            error(f"Failed to delete workspace: {e}")
    else:
        # Delete all workspaces
        log("Cleaning up ALL workspaces and cache files...")
        print(f"\n⚠️  This will:")
        print(f"  - Delete all ChromaDB collections")
        print(f"  - Delete all .code_geassistant_cache directories (if paths provided)")
        print()
        response = input("Continue? (yes/no): ")
        
        if response.lower() != "yes":
            warning("Cleanup cancelled")
            return
        
        try:
            # Clean ChromaDB
            if chroma_dir.exists():
                shutil.rmtree(chroma_dir)
                chroma_dir.mkdir(parents=True, exist_ok=True)
                success("All workspaces deleted from ChromaDB")
            else:
                warning("No ChromaDB directory found")
            
            # Clean cache if path provided
            if cache_path:
                cache_dir = Path(cache_path) / ".code_geassistant_cache"
                if cache_dir.exists():
                    shutil.rmtree(cache_dir)
                    success(f"Cache deleted: {cache_dir}")
                else:
                    warning(f"Cache not found: {cache_dir}")
            else:
                warning("To also delete cache files, provide workspace path with --cache flag")
                
        except Exception as e:
            error(f"Failed to cleanup: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Code Geassistant - AI-powered codebase assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start the server
  python cli/code_geassistant_cli.py start

  # Stop the server
  python cli/code_geassistant_cli.py stop

  # Ingest a workspace
  python cli/code_geassistant_cli.py ingest /path/to/repo

  # List workspaces
  python cli/code_geassistant_cli.py list

  # Query a workspace
  python cli/code_geassistant_cli.py query workspace_myrepo "Where is authentication?"

  # Query with custom model
  python cli/code_geassistant_cli.py query workspace_myrepo "Where is auth?" --model phi3:mini

  # Show graph stats
  python cli/code_geassistant_cli.py graph workspace_myrepo

  # Find service neighbors
  python cli/code_geassistant_cli.py neighbors workspace_myrepo orders --direction both

  # Find endpoint owners
  python cli/code_geassistant_cli.py owners workspace_myrepo GET /orders

  # Clean up a specific workspace
  python cli/code_geassistant_cli.py cleanup workspace_myrepo

  # Clean up ALL workspaces
  python cli/code_geassistant_cli.py cleanup --all
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Start command
    subparsers.add_parser("start", help="Start the API server")
    
    # Stop command
    subparsers.add_parser("stop", help="Stop the API server")
    
    # Ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Ingest a workspace")
    ingest_parser.add_argument("workspace", help="Path to workspace directory")
    ingest_parser.add_argument("--ignore", nargs="+", help="Additional ignore patterns")
    
    # List command
    subparsers.add_parser("list", help="List available workspaces")
    
    # Query command
    query_parser = subparsers.add_parser("query", help="Query a workspace")
    query_parser.add_argument("workspace_id", help="Workspace ID (from list command)")
    query_parser.add_argument("question", nargs="?", help="Your question about the codebase (required for qa mode)")
    query_parser.add_argument("--model", help=f"LLM model to use (default: {DEFAULT_MODEL})")
    query_parser.add_argument("--mode", default="qa", choices=["qa", "owner_of_endpoint", "neighbors", "trace_flow"])
    query_parser.add_argument("--repo", help="Filter by repository name")
    query_parser.add_argument("--service", help="Filter by inferred service name")
    query_parser.add_argument("--language", help="Filter by inferred language")
    query_parser.add_argument("--symbol-type", help="Filter by inferred symbol type")
    query_parser.add_argument("--symbol-name", help="Filter by inferred symbol name")
    query_parser.add_argument("--method", help="Endpoint method for owner/trace modes, e.g. GET")
    query_parser.add_argument("--path", help="Endpoint path for owner/trace modes, e.g. /orders")
    query_parser.add_argument("--direction", default="both", choices=["in", "out", "both"], help="Direction for neighbors mode")
    query_parser.add_argument("--trace-depth", type=int, default=2, help="Traversal depth for trace_flow mode")

    # Graph command
    graph_parser = subparsers.add_parser("graph", help="Show graph stats for a workspace")
    graph_parser.add_argument("workspace_id", help="Workspace ID (from list command)")

    # Neighbors command
    neighbors_parser = subparsers.add_parser("neighbors", help="Show graph neighbors for a service")
    neighbors_parser.add_argument("workspace_id", help="Workspace ID (from list command)")
    neighbors_parser.add_argument("service", help="Service name")
    neighbors_parser.add_argument("--direction", default="both", choices=["in", "out", "both"])

    # Owners command
    owners_parser = subparsers.add_parser("owners", help="Find owner service(s) for an endpoint")
    owners_parser.add_argument("workspace_id", help="Workspace ID (from list command)")
    owners_parser.add_argument("method", help="HTTP method, e.g. GET")
    owners_parser.add_argument("path", help="Endpoint path, e.g. /orders")
    
    # Cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Clean up workspace data")
    cleanup_parser.add_argument("workspace_id", nargs="?", help="Workspace ID to delete (optional)")
    cleanup_parser.add_argument("--all", action="store_true", help="Delete ALL workspaces")
    cleanup_parser.add_argument("--cache", help="Path to workspace (to also delete .code_geassistant_cache)")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Handle commands
    if args.command == "start":
        start_server()

    elif args.command == "stop":
        stop_server()
    
    elif args.command == "ingest":
        if not check_server():
            warning("Server not running. Starting it...")
            if not start_server():
                sys.exit(1)
        ingest_workspace(args.workspace, args.ignore)
    
    elif args.command == "list":
        if not check_server():
            error("Server not running. Start it with: python cli/code_geassistant_cli.py start")
            sys.exit(1)
        list_workspaces()
    
    elif args.command == "query":
        if not check_server():
            error("Server not running. Start it with: python cli/code_geassistant_cli.py start")
            sys.exit(1)
        query_workspace(
            args.workspace_id,
            args.question,
            args.model,
            repo=args.repo,
            service=args.service,
            language=args.language,
            symbol_type=args.symbol_type,
            symbol_name=args.symbol_name,
            query_mode=args.mode,
            method=args.method,
            path=args.path,
            direction=args.direction,
            trace_depth=args.trace_depth,
        )

    elif args.command == "graph":
        if not check_server():
            error("Server not running. Start it with: python cli/code_geassistant_cli.py start")
            sys.exit(1)
        show_graph(args.workspace_id)

    elif args.command == "neighbors":
        if not check_server():
            error("Server not running. Start it with: python cli/code_geassistant_cli.py start")
            sys.exit(1)
        show_neighbors(args.workspace_id, args.service, direction=args.direction)

    elif args.command == "owners":
        if not check_server():
            error("Server not running. Start it with: python cli/code_geassistant_cli.py start")
            sys.exit(1)
        show_endpoint_owners(args.workspace_id, args.method, args.path)
    
    elif args.command == "cleanup":
        if args.all:
            cleanup_workspaces(cache_path=args.cache)
        elif args.workspace_id:
            cleanup_workspaces(args.workspace_id, cache_path=args.cache)
        else:
            error("Specify a workspace_id or use --all to delete everything")
            sys.exit(1)


if __name__ == "__main__":
    main()
