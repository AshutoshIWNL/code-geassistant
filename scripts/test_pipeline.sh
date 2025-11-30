#!/usr/bin/env bash
# =====================================
# Author: Ashutosh Mishra
# File: test_pipeline.sh
# Created: 2025-11-29
# =====================================
set -e # exit on first error

# ------------------------------
# ARG VALIDATION
# ------------------------------
if [ -z "$2" ]; then
cat << EOF
Usage: $0 /absolute/path/to/workspace "Your question here" [model_name]

Examples:
  $0 /path/to/repo "Where is authentication?" 
  $0 /path/to/repo "Where is authentication?" "qwen2.5-coder:1.5b"
  $0 /path/to/repo "Where is authentication?" "phi3:mini"

Default model: deepseek-coder:1.3b
EOF
exit 1
fi

WORKSPACE_PATH="$1"
QUERY_STRING="$2"
MODEL_NAME="${3:-deepseek-coder:1.3b}"  # Optional 3rd arg, defaults to deepseek
API_URL="http://127.0.0.1:8000"
RESET_DB="chroma_db"
CACHE_DIR="$WORKSPACE_PATH/.code_geassistant_cache"
UVICORN_PID=""

# Timeouts
API_STARTUP_TIMEOUT=60
INGEST_TIMEOUT=600

GREEN="\033[1;32m"
BLUE="\033[1;34m"
YELLOW="\033[1;33m"
RED="\033[1;31m"
CYAN="\033[1;36m"
NC="\033[0m"

timestamp() { date +%s; }

log() {
echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
echo -e "${GREEN}[OK]${NC} $1"
}

error() {
echo -e "${RED}[ERROR]${NC} $1"
}

info() {
echo -e "${CYAN}[CONFIG]${NC} $1"
}

# Cleanup function
cleanup() {
if [ -n "$UVICORN_PID" ] && kill -0 "$UVICORN_PID" 2>/dev/null; then
log "Stopping uvicorn (PID: $UVICORN_PID)..."
kill "$UVICORN_PID" 2>/dev/null || true
wait "$UVICORN_PID" 2>/dev/null || true
fi
}

trap cleanup EXIT

start_time=$(timestamp)

echo -e "${YELLOW}==============================================="
echo " Code Geassistant – Pipeline Test Script"
echo "===============================================${NC}"
echo -e "Workspace: ${WORKSPACE_PATH}"
info "LLM Model: ${MODEL_NAME}"
info "Query: ${QUERY_STRING}"
echo ""

# Validate workspace exists
if [ ! -d "$WORKSPACE_PATH" ]; then
error "Workspace directory does not exist: $WORKSPACE_PATH"
exit 1
fi

# ---------------------------------------------
# 1. Stop old uvicorn
# ---------------------------------------------
log "Stopping any running uvicorn..."
pkill -f uvicorn 2>/dev/null || true
sleep 1

# ---------------------------------------------
# 2. Reset Chroma DB + Workspace cache
# ---------------------------------------------
log "Resetting chroma_db directory..."
rm -rf "$RESET_DB"
mkdir -p "$RESET_DB"

log "Resetting workspace .code_geassistant_cache..."
rm -rf "$CACHE_DIR"

reset_time=$(timestamp)
reset_duration=$((reset_time - start_time))
success "Environment reset in ${reset_duration}s"

# ---------------------------------------------
# 3. Start backend server
# ---------------------------------------------
log "Starting backend (uvicorn)..."

uvicorn main:app --reload --port 8000 > /tmp/code_geassistant_uvicorn.log 2>&1 &
UVICORN_PID=$!

if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
error "Backend failed to start immediately. Check /tmp/code_geassistant_uvicorn.log"
exit 1
fi

success "Backend started (PID: $UVICORN_PID)"

# Wait for API to be ready with timeout
log "Waiting for API to be ready (timeout: ${API_STARTUP_TIMEOUT}s)..."
api_start=$(timestamp)
api_ready=false

while [ $(($(timestamp) - api_start)) -lt $API_STARTUP_TIMEOUT ]; do
if curl -s -f "$API_URL/health" >/dev/null 2>&1; then
api_ready=true
break
fi
echo -n "."
sleep 2
done

echo ""

if [ "$api_ready" = false ]; then
error "API did not become ready within ${API_STARTUP_TIMEOUT}s"
error "Check logs: /tmp/code_geassistant_uvicorn.log"
exit 1
fi

success "API is ready"

# ---------------------------------------------
# 4. Start ingestion
# ---------------------------------------------
log "Starting ingestion..."

ingest_start_time=$(timestamp)

ingest_response=$(curl -s -X POST "$API_URL/ingest/start" \
-H "Content-Type: application/json" \
-d "{\"workspace_path\":\"$WORKSPACE_PATH\"}" 2>/dev/null)

job_id=$(echo "$ingest_response" | jq -r '.job_id' 2>/dev/null)

if [[ -z "$job_id" || "$job_id" == "null" ]]; then
error "Failed to start ingestion."
error "Response: $ingest_response"
exit 1
fi

success "Ingestion job started: $job_id"

# ---------------------------------------------
# 5. Poll ingestion until ready
# ---------------------------------------------
log "Waiting for ingestion + embedding to finish (timeout: ${INGEST_TIMEOUT}s)..."

while true; do
elapsed=$(($(timestamp) - ingest_start_time))
  
if [ $elapsed -ge $INGEST_TIMEOUT ]; then
error "Ingestion timeout after ${INGEST_TIMEOUT}s"
exit 1
fi

status_response=$(curl -s "$API_URL/ingest/status/$job_id" 2>/dev/null)
status=$(echo "$status_response" | jq -r '.status' 2>/dev/null)

if [[ "$status" == "ready" ]]; then
ingest_end_time=$(timestamp)
echo ""
success "Ingestion + Embedding complete!"
break
fi

if [[ "$status" == "error" ]]; then
echo ""
error "Ingestion error:"
echo "$status_response" | jq . 2>/dev/null || echo "$status_response"
exit 1
fi

echo -n "."
sleep 2
done

ingest_duration=$((ingest_end_time - ingest_start_time))
success "Ingestion duration: ${ingest_duration}s"

# ---------------------------------------------
# 6. Check collections
# ---------------------------------------------
log "Checking available workspaces..."

list_start=$(timestamp)
collections=$(curl -s "$API_URL/workspaces" 2>/dev/null)
list_end=$(timestamp)

if ! echo "$collections" | jq . >/dev/null 2>&1; then
error "Invalid JSON response from /workspaces"
echo "$collections"
else
echo "$collections" | jq .
fi

list_duration=$((list_end - list_start))
success "Workspace listing took ${list_duration}s"

# ---------------------------------------------
# 7. Query the codebase (WITH MODEL OVERRIDE)
# ---------------------------------------------
log "Running query with model: ${MODEL_NAME}..."

query_start=$(timestamp)
response=$(curl -s -X POST "$API_URL/query" \
-H "Content-Type: application/json" \
-d "{
\"workspace_id\": \"workspace_$(basename "$WORKSPACE_PATH")\",
\"model\": \"$MODEL_NAME\",
\"question\": \"$QUERY_STRING\"
}" 2>/dev/null)
query_end=$(timestamp)

if ! echo "$response" | jq . >/dev/null 2>&1; then
error "Invalid JSON response from /query"
echo "$response"
else
echo -e "${CYAN}--- Query Response ---${NC}"
echo "$response" | jq .
fi

query_duration=$((query_end - query_start))
success "Query executed in ${query_duration}s using ${MODEL_NAME}"

# ---------------------------------------------
# FINISH SUMMARY
# ---------------------------------------------
total_end=$(timestamp)
total_duration=$((total_end - start_time))

echo -e "${GREEN}"
echo "======================================"
echo "Pipeline Test Complete"
echo "======================================"
echo " Model Used: ${MODEL_NAME}"
echo " Environment Reset: ${reset_duration}s"
echo " API Startup: $((list_start - reset_time))s"
echo " Ingest+Embed: ${ingest_duration}s"
echo " Workspace Listing: ${list_duration}s"
echo " Query Execution: ${query_duration}s"
echo "--------------------------------------"
echo " Total Time: ${total_duration}s"
echo "======================================"
echo -e "${NC}"