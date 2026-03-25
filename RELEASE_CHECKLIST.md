# Release Checklist

Use this checklist before publishing or tagging a release.

## 1. Code and Tests

1. Run local checks:
   - `python -m pytest -q`
   - `python -m compileall main.py ingest rag llm cli tests`
2. Ensure CI is green on the target branch.
3. Confirm no debug-only code/logging was accidentally committed.

## 2. Docs and UX

1. Verify [README.MD](README.MD) quick-start commands work on a clean machine.
2. Verify [ARCHITECTURE.md](ARCHITECTURE.md) reflects current implementation.
3. Verify [CONTRIBUTING.md](CONTRIBUTING.md) and [KT_RUNBOOK.md](KT_RUNBOOK.md) are current.
4. Ensure new CLI flags/endpoints are documented.

## 3. Dependency Hygiene

1. Validate pinned dependencies in:
   - `requirements.txt`
   - `requirements_win.txt`
   - `requirements-ci.txt`
2. Confirm setup scripts install successfully:
   - `scripts/setup.ps1`
   - `scripts/setup.sh`

## 4. Product Validation (Smoke)

Run this end-to-end on a small sample repo:

1. Start server.
2. Ingest repo.
3. Run query modes:
   - `qa`
   - `owner_of_endpoint`
   - `neighbors`
   - `trace_flow`
4. Validate graph endpoints and CLI wrappers.
5. Re-run ingest to verify incremental behavior (`new/changed/deleted/unchanged` counters).

## 5. GitHub Release Prep

1. Create/update release notes:
   - Highlights
   - Breaking changes (if any)
   - Migration notes
   - Known limitations
2. Tag version (SemVer recommended).
3. Push tag and publish release.

## 6. Post-Release

1. Verify install/setup from published default branch.
2. Open follow-up issues for any deferred work discovered during release validation.
