@echo off
REM =====================================
REM Author: Ashutosh Mishra
REM File: test_pipeline.bat
REM Created: 2025-11-30
REM =====================================

setlocal enabledelayedexpansion

REM ------------------------------
REM ARG VALIDATION
REM ------------------------------
if "%~2"=="" (
    echo Usage: %~nx0 C:\path\to\workspace "Your question here" [model_name]
    echo.
    echo Examples:
    echo   %~nx0 C:\projects\myrepo "Where is authentication?"
    echo   %~nx0 C:\projects\myrepo "Where is auth?" "qwen2.5-coder:1.5b"
    echo.
    echo Default model: deepseek-coder:1.3b
    exit /b 1
)

set "WORKSPACE_PATH=%~1"
set "QUERY_STRING=%~2"
set "MODEL_NAME=%~3"
if "%MODEL_NAME%"=="" set "MODEL_NAME=deepseek-coder:1.3b"

set "API_URL=http://127.0.0.1:8000"
set "RESET_DB=chroma_db"
set "CACHE_DIR=%WORKSPACE_PATH%\.code_geassistant_cache"
set "API_STARTUP_TIMEOUT=60"
set "INGEST_TIMEOUT=600"

echo ===============================================
echo  Code Geassistant - Pipeline Test Script
echo ===============================================
echo Workspace: %WORKSPACE_PATH%
echo Model: %MODEL_NAME%
echo Query: %QUERY_STRING%
echo.

REM Validate workspace exists
if not exist "%WORKSPACE_PATH%" (
    echo [ERROR] Workspace directory does not exist: %WORKSPACE_PATH%
    exit /b 1
)

set "START_TIME=%time%"

REM ---------------------------------------------
REM 1. Stop old uvicorn
REM ---------------------------------------------
echo [INFO] Stopping any running uvicorn...
taskkill /F /IM uvicorn.exe >nul 2>&1
timeout /t 1 /nobreak >nul

REM ---------------------------------------------
REM 2. Reset Chroma DB + Workspace cache
REM ---------------------------------------------
echo [INFO] Resetting chroma_db directory...
if exist "%RESET_DB%" rmdir /s /q "%RESET_DB%" >nul 2>&1
mkdir "%RESET_DB%"

echo [INFO] Resetting workspace cache...
if exist "%CACHE_DIR%" rmdir /s /q "%CACHE_DIR%" >nul 2>&1

echo [OK] Environment reset complete

REM ---------------------------------------------
REM 3. Start backend server
REM ---------------------------------------------
echo [INFO] Starting backend (uvicorn)...

start /B uvicorn main:app --reload --port 8000 > nul 2>&1

timeout /t 2 /nobreak >nul
tasklist /FI "IMAGENAME eq uvicorn.exe" 2>NUL | find /I /N "uvicorn.exe">NUL
if "%ERRORLEVEL%"=="1" (
    echo [ERROR] Backend failed to start
    exit /b 1
)

echo [OK] Backend started

REM Wait for API to be ready
echo [INFO] Waiting for API to be ready...
set /a ATTEMPTS=0
set /a MAX_ATTEMPTS=%API_STARTUP_TIMEOUT%

:wait_api
set /a ATTEMPTS+=1
if %ATTEMPTS% gtr %MAX_ATTEMPTS% (
    echo [ERROR] API did not become ready within %API_STARTUP_TIMEOUT%s
    exit /b 1
)

curl -s -f "%API_URL%/health" >nul 2>&1
if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto wait_api
)

echo [OK] API is ready

REM ---------------------------------------------
REM 4. Start ingestion
REM ---------------------------------------------
echo [INFO] Starting ingestion...

for /f "tokens=*" %%a in ('curl -s -X POST "%API_URL%/ingest/start" -H "Content-Type: application/json" -d "{\"workspace_path\":\"%WORKSPACE_PATH:\=\\%\"}"') do set INGEST_RESPONSE=%%a

for /f "tokens=2 delims=:" %%a in ('echo %INGEST_RESPONSE% ^| jq -r .job_id') do set JOB_ID=%%a
set "JOB_ID=%JOB_ID:"=%"
set "JOB_ID=%JOB_ID:}=%"

if "%JOB_ID%"=="null" (
    echo [ERROR] Failed to start ingestion
    echo Response: %INGEST_RESPONSE%
    exit /b 1
)

echo [OK] Ingestion job started: %JOB_ID%

REM ---------------------------------------------
REM 5. Poll ingestion until ready
REM ---------------------------------------------
echo [INFO] Waiting for ingestion + embedding to finish...

set /a INGEST_START=%time:~0,2%%time:~3,2%%time:~6,2%

:poll_ingest
timeout /t 2 /nobreak >nul

for /f "tokens=*" %%a in ('curl -s "%API_URL%/ingest/status/%JOB_ID%"') do set STATUS_RESPONSE=%%a
for /f "tokens=2 delims=:" %%a in ('echo %STATUS_RESPONSE% ^| jq -r .status') do set STATUS=%%a
set "STATUS=%STATUS:"=%"
set "STATUS=%STATUS:,=%"

if "%STATUS%"=="ready" (
    echo.
    echo [OK] Ingestion + Embedding complete!
    goto ingest_done
)

if "%STATUS%"=="error" (
    echo.
    echo [ERROR] Ingestion error:
    echo %STATUS_RESPONSE% | jq .
    exit /b 1
)

echo|set /p="."
goto poll_ingest

:ingest_done

REM ---------------------------------------------
REM 6. Check collections
REM ---------------------------------------------
echo [INFO] Checking available workspaces...

curl -s "%API_URL%/workspaces" | jq .

echo [OK] Workspace listing complete

REM ---------------------------------------------
REM 7. Query the codebase
REM ---------------------------------------------
echo [INFO] Running query with model: %MODEL_NAME%...

REM Extract workspace name from path
for %%I in ("%WORKSPACE_PATH%") do set "WORKSPACE_NAME=%%~nxI"

curl -s -X POST "%API_URL%/query" -H "Content-Type: application/json" -d "{\"workspace_id\":\"workspace_%WORKSPACE_NAME%\",\"model\":\"%MODEL_NAME%\",\"question\":\"%QUERY_STRING%\"}" | jq .

echo [OK] Query complete

REM ---------------------------------------------
REM FINISH
REM ---------------------------------------------
echo.
echo ======================================
echo Pipeline Test Complete
echo ======================================
echo Model Used: %MODEL_NAME%
echo ======================================

endlocal