# Retry Integrity And Diagnostics Active Plan

**Status:** active
**Owner:** Codex
**Branch / Worktree:** current workspace
**Last Updated:** 2026-04-05
**Related Design:** none

**Goal:** Make manual retry credential-consistent and surface invalid-response diagnostics in the host/UI layer.

**Architecture:** `host/web_ui.py` will record and validate an API key fingerprint so manual retry does not silently switch credentials. `host/orchestrator.py` will mirror invalid-response round artifacts to the host run archive. `host/web_ui.py` and `host/static/container.js` will expose those synced artifacts as part of run detail/log viewing.

**Verification:**

- `python3 -m pytest tests/test_web_ui.py tests/test_orchestrator.py -q`

**Out Of Scope:**

- Storing raw API keys in run metadata
- Full round-directory mirroring for every artifact

---

## Current Slice

**Why now:** The previous review found that manual retry could drift onto a different API key and that invalid-response evidence was written only inside the container runtime, not to host/UI surfaces where an operator can inspect it.

**Stop condition:** Manual retry refuses to run when the current API key fingerprint does not match the original run, and invalid response artifacts become visible from the host-side run detail/log view.

## Task 1: Add API key fingerprint checks for manual retry

**Files:**

- Modify: `host/web_ui.py`
- Test: `tests/test_web_ui.py`

**Status:** pending

## Task 2: Sync and expose invalid-response artifacts

**Files:**

- Modify: `host/orchestrator.py`
- Modify: `host/web_ui.py`
- Modify: `host/static/container.js`
- Test: `tests/test_orchestrator.py`
- Test: `tests/test_web_ui.py`

**Status:** pending

## Decision Log

- 2026-04-05: Manual retry may reuse the current resolved API key only if its fingerprint matches the one recorded at launch time; otherwise it must fail loudly.

## Session Log

### 2026-04-05 00:00

- Context loaded: recent code-review findings, retry/manual retry implementation, host sync file list, and container detail log tabs.
- Changes made: none yet
- Verification run: none yet
- Next step: implement fingerprint guard and host-visible invalid-response artifact sync.

## Open Questions

- None blocking.
