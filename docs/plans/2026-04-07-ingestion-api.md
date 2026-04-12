# Ingestion API Active Plan

**Status:** completed
**Owner:** Codex
**Branch / Worktree:** current workspace
**Last Updated:** 2026-04-07
**Related Design:** `docs/plans/2026-04-07-ingestion-api-design.md`

**Goal:** Add a minimal host-side ingestion API that writes run facts into the existing `runs/` truth layer.

**Architecture:** A new `host/ingest_api.py` module owns normalized writes into `runs/<run_id>/`. `host/web_ui.py` exposes POST endpoints for run metadata, events, round posts, and artifacts. Existing file-based collection remains valid, and the SQLite index keeps working because it already rebuilds from `runs/`.

**Verification:**

- `python3 -m pytest tests/test_web_ui.py -q`
- `python3 -m pytest -q`

**Out Of Scope:**

- Auth
- Public UI for ingestion endpoints
- Replacing orchestrator mirroring

---

## Current Slice

**Why now:** The query side now has a SQLite projection layer, so the next missing piece is a proper write-side service entrypoint that still preserves file truth.

**Stop condition:** The repo exposes `/api/ingest/runs`, `/api/ingest/events`, `/api/ingest/round-posts`, and `/api/ingest/artifacts`, with tests proving they write the expected files under `runs/<run_id>/`.

## Task 1: Implement ingestion write module

**Files:**

- Create: `host/ingest_api.py`
- Test: `tests/test_web_ui.py`

**Status:** completed

## Task 2: Expose ingestion routes in web UI

**Files:**

- Modify: `host/web_ui.py`
- Test: `tests/test_web_ui.py`

**Status:** completed

## Session Log

### 2026-04-07 00:00

- Context loaded: current collection chain, host nightly file writes, run index, and web UI route handlers.
- Changes made: ingestion API design doc and execution plan created.
- Verification run: none yet
- Next step: implement `host/ingest_api.py` and wire the routes.

### 2026-04-07 12:30

- Context loaded: host nightly write patterns, current `runs/` truth layout, run index expansion work, and web UI POST routing.
- Changes made: added `host/ingest_api.py`, exposed `/api/ingest/runs`, `/api/ingest/events`, `/api/ingest/round-posts`, and `/api/ingest/artifacts`, and verified those writes remain compatible with the run index and `run_detail` reads.
- Verification run:
  - `python3 -m pytest tests/test_web_ui.py -q`
  - `python3 -m pytest -q`
  - live HTTP probe covering all four ingestion endpoints plus `/api/overview` and `/api/runs/<run_id>`
- Next step: optional next slice is auth for ingestion or moving more writer paths to use the same module.

### 2026-04-07 13:30

- Context loaded: `host_nightly_runner.py` still used a parallel file-writing implementation instead of the new ingestion writer.
- Changes made: refactored `host_nightly_runner.py` to write run metadata, events, round posts, and artifacts through `host.ingest_api.py`, while preserving `host-runs/<slug>/<run_id>/` as truth.
- Verification run:
  - `python3 -m pytest tests/test_host_nightly_runner.py -q`
  - `python3 -m pytest -q`
- Next step: optional next slice is moving more internal writers to the same module or adding per-writer identity on top of ingestion auth.
