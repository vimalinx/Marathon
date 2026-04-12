# Ingestion API Auth Active Plan

**Status:** completed
**Owner:** Codex
**Branch / Worktree:** current workspace
**Last Updated:** 2026-04-07
**Related Design:** `docs/plans/2026-04-07-ingestion-api-auth-design.md`

**Goal:** Add opt-in token auth to `/api/ingest/*` without breaking current local single-host development.

**Architecture:** `host/web_ui.py` already has reusable bearer-token helpers. This slice adds a dedicated ingestion-token extractor and a gate in front of the ingestion endpoints. When `MARATHON_INGEST_TOKEN` is unset, current behavior is preserved. When set, all ingestion writes require a matching token.

**Verification:**

- `python3 -m pytest tests/test_web_ui.py -q`
- `python3 -m pytest -q`

**Out Of Scope:**

- UI for editing ingestion tokens
- Multiple credentials
- Signed requests

---

## Current Slice

**Why now:** The ingestion API exists and works, but it is still effectively an unauthenticated write surface.

**Stop condition:** Ingestion endpoints accept writes anonymously only when no token is configured, and enforce a matching token whenever `MARATHON_INGEST_TOKEN` is set.

## Task 1: Add ingestion auth helpers and route guards

**Files:**

- Modify: `host/web_ui.py`
- Test: `tests/test_web_ui.py`

**Status:** completed

## Task 2: Document ingestion auth configuration

**Files:**

- Modify: `README.md`
- Modify: `SECURITY.md`

**Status:** completed

## Session Log

### 2026-04-07 00:00

- Context loaded: current ingestion routes, existing bearer token helper, and the newly added ingestion API design docs.
- Changes made: auth design doc and active plan created.
- Verification run: none yet
- Next step: implement `MARATHON_INGEST_TOKEN`-based route protection and tests.

### 2026-04-07 13:05

- Context loaded: current ingestion routes, existing agent-account token extraction helpers, and README/SECURITY docs for deployment-facing behavior.
- Changes made: added `MARATHON_INGEST_TOKEN`-based auth gate for `/api/ingest/*`, documented the token in README and SECURITY, and added tests for anonymous-vs-token-protected writes.
- Verification run:
  - `python3 -m pytest tests/test_web_ui.py -q`
  - `python3 -m pytest -q`
  - live HTTP smoke: anonymous ingestion succeeds on the default local server, and a temporary server started with `MARATHON_INGEST_TOKEN=secret` correctly returns `403 ingestion token required` without a token
- Next step: optional follow-up is per-writer identity or rotating multiple ingestion tokens.
