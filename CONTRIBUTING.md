# Contributing Guide

Thanks for contributing to Code Geassistant.

This project is moving fast. Keep changes small, test-backed, and easy to review.

## Development Setup

## Windows (PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
.\.venv\Scripts\Activate.ps1
```

## macOS/Linux

```bash
bash scripts/setup.sh
source .venv/bin/activate
```

## Branching and PRs

1. Create a branch from `main`.
2. Keep PRs focused on one concern.
3. Include tests for behavior changes.
4. Update docs when API/CLI behavior changes.

## Local Checks Before PR

```bash
python -m pytest -q
python -m compileall main.py ingest rag llm cli tests
```

## Coding Guidelines

1. Keep APIs backward-compatible unless a breaking change is explicitly planned.
2. Prefer additive evolution (`query_mode`, optional fields) over breaking rewrites.
3. Use structured logging for new operational events.
4. Keep new features language-agnostic where possible.
5. Avoid hardcoding tunables; use `settings.py`.

## Tests

Test suite is intentionally lightweight and mostly unit/integration style.

- `tests/test_query_api.py`: query contract and mode routing
- `tests/test_ingest_flow.py`: ingest lifecycle
- `tests/test_embed_idempotency.py`: upsert/idempotent embedding behavior
- `tests/test_evidence_extraction.py`: extractor outputs
- `tests/test_graph_builder.py`: graph generation and lookups
- `tests/test_incremental_ingest.py`: incremental file-change behavior

## Commit Message Style

Use concise, scoped messages, for example:

- `feat(query): add trace_flow mode`
- `fix(ingest): skip cache dir in walker`
- `docs(readme): add graph query examples`

## CI

GitHub Actions runs tests on Python 3.10 and 3.11 using `requirements-ci.txt`.

If CI fails, reproduce locally with:

```bash
python -m pip install -r requirements-ci.txt
python -m pytest -q
```
