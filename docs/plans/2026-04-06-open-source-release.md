# Open Source Release Active Plan

**Status:** completed
**Owner:** Codex
**Branch / Worktree:** current workspace
**Last Updated:** 2026-04-06
**Related Design:** none

**Goal:** Move Marathon Core from experimental local tooling toward a publishable `v0.1` open-source repository baseline.

**Architecture:** The work focused on release readiness rather than product behavior: fix the remaining full-test blocker, remove repo-specific provider defaults, harden Web UI startup, add open-source support docs, and add a basic CI test workflow. License selection was the only item requiring user direction.

**Verification:**

- `python3 -m pytest -q`
- `python3 -m pytest tests/test_design_lab.py tests/test_web_ui.py tests/test_agent_loop.py tests/test_clone_script.py -q`
- `bash -n scripts/start_web_ui.sh && bash -n scripts/stop_web_ui.sh && bash -n scripts/start_run.sh`

**Out Of Scope:**

- Multi-maintainer governance
- Issue templates and PR templates
- Release tagging and changelog drafting

---

## Current Slice

**Why now:** The repository was close to being publishable, but still had one full-test failure, weak startup ergonomics, and missing open-source support files.

**Stop condition:** Full pytest passes, release blockers are removed, and the repository contains the minimal docs/workflow/legal scaffolding needed for a public `v0.1`.

## Task 1: Clear technical release blockers

**Files:**

- Modify: `host/static/index.html`
- Modify: `container/agent_loop.py`
- Modify: `scripts/start_run.sh`
- Modify: `scripts/start_web_ui.sh`
- Modify: `scripts/stop_web_ui.sh`
- Test: `tests/test_design_lab.py`
- Test: `tests/test_web_ui.py`
- Test: `tests/test_agent_loop.py`
- Test: `tests/test_clone_script.py`

**Status:** completed

## Task 2: Add open-source support files and CI

**Files:**

- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`
- Create: `CODE_OF_CONDUCT.md`
- Create: `.github/workflows/test.yml`
- Create: `LICENSE`
- Modify: `README.md`

**Status:** completed

## Decision Log

- 2026-04-06: MIT was selected as the initial repository license to minimize launch friction for a `v0.1` public release.

## Session Log

### 2026-04-06 12:00

- Context loaded: full pytest status, README, startup scripts, design-lab test failure, and current release blockers.
- Changes made: restored design-lab link on the main UI, removed hardcoded provider defaults, hardened Web UI startup against port conflicts, added CONTRIBUTING/SECURITY/CODE_OF_CONDUCT, added GitHub Actions test workflow, added MIT license, and updated README release guidance.
- Verification run:
  - `python3 -m pytest -q`
  - `python3 -m pytest tests/test_design_lab.py tests/test_web_ui.py tests/test_agent_loop.py tests/test_clone_script.py -q`
  - `bash -n scripts/start_web_ui.sh && bash -n scripts/stop_web_ui.sh && bash -n scripts/start_run.sh`
- Next step: optional next slice is issue templates / PR templates / release notes, not required for a first public push.

## Open Questions

- None blocking for a basic public `v0.1` repository release.
