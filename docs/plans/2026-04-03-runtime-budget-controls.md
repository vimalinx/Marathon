# Runtime Budget Controls Active Plan

**Status:** completed
**Owner:** Codex
**Branch / Worktree:** current workspace
**Last Updated:** 2026-04-03
**Related Design:** `docs/plans/2026-04-03-runtime-budget-controls-design.md`

**Goal:** Add explicit return navigation, run budget controls, and backup-safe container default settings to Marathon Core.

**Architecture:** `host/web_ui.py` remains the UI/API boundary, `host/orchestrator.py` keeps the host-to-container launch contract, and `container/agent_loop.py` enforces runtime budgets inside the container. Container-scoped defaults live in `state/containers/*.json`, with write-ahead backups under a dedicated host-side backup directory. Static operator pages expose the new controls while keeping the public-site code path untouched.

**Verification:**

- `python3 -m pytest tests/test_web_ui.py tests/test_orchestrator.py tests/test_agent_loop.py tests/test_clone_script.py -q`
- Browser smoke check: open `/`, open `/container?container=<name>`, inspect return nav and settings form, open `/new` and inspect new runtime controls

**Out Of Scope:**

- Public-site `/site` work
- Raw LXC network editing UI
- Secret management redesign for API keys

---

## Current Slice

**Why now:** The operator UI already has enough primitives to support run pacing and budget controls, but the settings are fragmented and invisible. This slice wires the existing runtime into a coherent control surface before adding more product layers.

**Stop condition:** A user can see an explicit return path from detail pages, configure runtime/time/token limits from the UI, save container-level defaults with backups, and the backend enforces the new limits.

## Task 1: Define and persist container default settings safely

**Files:**

- Modify: `host/web_ui.py`
- Modify: `scripts/clone_container.sh`
- Test: `tests/test_web_ui.py`
- Test: `tests/test_clone_script.py`

**Status:** completed

**Step 1:** Add container default settings normalization plus backup-safe writes in `host/web_ui.py`.

**Step 2:** Expose container settings in container detail payloads and add a write endpoint.

**Step 3:** Preserve saved agent settings when cloning a container.

## Task 2: Enforce runtime budgets through host and in-container loops

**Files:**

- Modify: `host/web_ui.py`
- Modify: `host/orchestrator.py`
- Modify: `container/agent_loop.py`
- Test: `tests/test_web_ui.py`
- Test: `tests/test_orchestrator.py`
- Test: `tests/test_agent_loop.py`

**Status:** completed

**Step 1:** Extend launch payload resolution with `max_runtime_seconds` and `max_total_tokens`.

**Step 2:** Pass the new limits through orchestrator launch and into the container loop.

**Step 3:** Track token usage and stop reasons in run status and events.

## Task 3: Surface controls in the operator UI

**Files:**

- Modify: `host/static/container.html`
- Modify: `host/static/container.js`
- Modify: `host/static/new.html`
- Modify: `host/static/new.js`
- Modify: `host/static/app.css`
- Test: `tests/test_web_ui.py`

**Status:** completed

**Step 1:** Add explicit return navigation on detail pages.

**Step 2:** Add runtime control fields to the new-task page.

**Step 3:** Add a container settings card that saves defaults and shows backup status.

## Decision Log

- 2026-04-03: Container-level defaults are stored in `state/containers/*.json` under `agent_settings`; per-change backups are written separately so the main meta file stays authoritative.
- 2026-04-03: API keys stay in model profiles, not in container default settings, to avoid duplicating secrets into backup snapshots.

## Session Log

### 2026-04-03 22:00

- Context loaded: README, PLAYBOOK, current operator UI/static files, web UI backend, orchestrator, agent loop, clone script, and relevant tests.
- Changes made: Added design doc and active plan for runtime budget controls.
- Verification run: none yet
- Next step: implement container settings persistence + backup path, then wire runtime budgets through launch flow.

### 2026-04-03 22:55

- Context loaded: container meta/state layout, orchestrator launch contract, agent loop stop conditions, and operator UI pages for `/container` and `/new`.
- Changes made: Added explicit detail-page return navigation, container default settings with backup-safe writes, clone-time settings inheritance, run time/token budget controls through host and container layers, and UI controls plus live budget visibility.
- Verification run:
  - `python3 -m pytest tests/test_web_ui.py tests/test_orchestrator.py tests/test_agent_loop.py tests/test_clone_script.py -q`
  - `bash -n scripts/start_run.sh && bash -n scripts/clone_container.sh`
  - `curl -sS --max-time 5 http://127.0.0.1:8765/ | head -n 20`
  - `curl -sS --max-time 5 'http://127.0.0.1:8765/container?container=test' | rg -n '返回总览|运行默认设置|containerSettingsForm|settingsMaxRuntimeMinutes|settingsMaxTotalTokens'`
  - `curl -sS --max-time 5 'http://127.0.0.1:8765/new' | rg -n 'maxRoundsInput|sleepSecondsInput|maxRuntimeMinutesInput|maxTotalTokensInput'`
  - Playwright smoke: opened `/container?container=test` and `/new?base=test`, confirmed the new nav/settings controls render in a real browser snapshot
- Next step: optional follow-up is adding a restore-from-backup UI if operators need rollback from the browser instead of disk-level recovery.

## Open Questions

- None blocking. This slice intentionally stops at backup creation plus latest-backup visibility; restore-from-backup remains an optional future enhancement.

## Done Definition

- The targeted behavior is implemented.
- The listed verification commands passed.
- The plan and decision log reflect the final shape.
