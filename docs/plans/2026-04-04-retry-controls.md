# Retry Controls Active Plan

**Status:** completed
**Owner:** Codex
**Branch / Worktree:** current workspace
**Last Updated:** 2026-04-04
**Related Design:** none

**Goal:** Raise malformed-response auto-retry to 3 and add manual retry plus core container control buttons to the container detail page.

**Architecture:** `container/agent_loop.py` owns automatic malformed-response retry count. `host/web_ui.py` adds a retry endpoint that relaunches the latest run configuration on the same container when no active run exists. `host/static/container.html` and `host/static/container.js` expose retry and lifecycle actions from the detail toolbar, using existing container APIs where possible.

**Verification:**

- `python3 -m pytest tests/test_web_ui.py tests/test_agent_loop.py -q`
- Browser smoke check on `/container?container=<name>`

**Out Of Scope:**

- Public-site changes
- Restoring historic failed runs in place
- More than the core retry/container buttons on the detail page

---

## Current Slice

**Why now:** The retry logic exists but is too conservative for the current model behavior, and the detail page still lacks direct recovery/lifecycle actions for operators.

**Stop condition:** Invalid-response auto-retry is raised to 3, and the detail page exposes manual retry plus start/stop/restart container controls with working handlers.

## Task 1: Increase invalid-response auto-retry count

**Files:**

- Modify: `container/agent_loop.py`
- Test: `tests/test_agent_loop.py`

**Status:** completed

## Task 2: Add manual retry endpoint for latest run config

**Files:**

- Modify: `host/web_ui.py`
- Test: `tests/test_web_ui.py`

**Status:** completed

## Task 3: Expose retry and lifecycle buttons in the detail UI

**Files:**

- Modify: `host/static/container.html`
- Modify: `host/static/container.js`
- Test: `tests/test_web_ui.py`

**Status:** completed

## Decision Log

- 2026-04-04: Manual retry should relaunch the latest run configuration on the same container, not clone a new container.

## Session Log

### 2026-04-04 12:20

- Context loaded: current malformed-response retry code, failed `glm-5.1` run evidence, detail-page toolbar, and container lifecycle APIs.
- Changes made: none yet
- Verification run: none yet
- Next step: implement retry count bump plus manual retry endpoint.

### 2026-04-04 12:40

- Context loaded: verified `prepare_container_for_agent` can safely relaunch on the same container and that the detail page already had stop/refresh controls but lacked retry/lifecycle controls.
- Changes made: increased malformed-response auto-retry from 1 to 3, added a latest-run manual retry endpoint, added start/stop/restart container buttons plus a manual retry button to the detail toolbar, and wired the detail UI state/handlers.
- Verification run:
  - `python3 -m pytest tests/test_web_ui.py tests/test_agent_loop.py -q`
  - `curl -sS --max-time 5 'http://127.0.0.1:8765/container?container=test-glm5.1' | rg -n 'retryAgentBtn|startContainerBtn|stopContainerBtn|restartContainerBtn'`
  - `POST /api/containers/test-glm5.1/retry-agent` returned a live relaunch payload and started run `test-glm5.1-20260404-192104`
- Next step: optional follow-up is exposing a destroy button only if you want destructive container lifecycle actions in the detail toolbar as well.

## Open Questions

- None blocking.
