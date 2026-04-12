# Model Connectivity And Theme Toggle Active Plan

**Status:** completed
**Owner:** Codex
**Branch / Worktree:** current workspace
**Last Updated:** 2026-04-04
**Related Design:** `docs/plans/2026-04-04-model-connectivity-theme-design.md`

**Goal:** Add a model connectivity test action, complete model-config persistence/reuse, and visible theme toggle icons to Marathon Core.

**Architecture:** `host/web_ui.py` gains a small model probe endpoint layered on top of the existing model config parsing. `host/static/new.html` and `host/static/new.js` expose the test action and ensure saved profile fields round-trip fully. `host/static/app.js` and `host/static/app.css` own global theme persistence plus a nav-level icon toggle for operator pages.

**Verification:**

- `python3 -m pytest tests/test_web_ui.py -q`
- Browser smoke check: open `/new`, test the new button visibility and saved-field reuse, verify the theme toggle appears and flips the page theme

**Out Of Scope:**

- Public-site changes
- Multi-profile UI
- Theme support for design-lab prototypes

---

## Current Slice

**Why now:** The runtime-budget work already expanded the task-launch surface. This slice finishes the operator ergonomics around model configuration and operator visibility without changing deeper run semantics.

**Stop condition:** `/new` shows a working connectivity-test button and full config persistence, and operator pages expose a visible theme toggle icon that persists across refresh.

## Task 1: Add model connectivity probe endpoint

**Files:**

- Modify: `host/web_ui.py`
- Test: `tests/test_web_ui.py`

**Status:** completed

## Task 2: Complete new-page model config persistence and test action

**Files:**

- Modify: `host/static/new.html`
- Modify: `host/static/new.js`
- Test: `tests/test_web_ui.py`

**Status:** completed

## Task 3: Add global theme toggle icon

**Files:**

- Modify: `host/static/app.js`
- Modify: `host/static/app.css`
- Test: `tests/test_web_ui.py`

**Status:** completed

## Decision Log

- 2026-04-04: Model connectivity probing stays on the host web UI side and uses the same request shape as normal chat-completions launches, but with a tiny prompt and short output target.
- 2026-04-04: Theme override is stored client-side only and does not become server state.

## Session Log

### 2026-04-04 00:00

- Context loaded: new task page, app shell JS/CSS, model profile persistence, and web UI route handlers.
- Changes made: Added design doc and active plan for model connectivity and theme toggle work.
- Verification run: none yet
- Next step: implement the probe endpoint and wire the new-page button to it.

### 2026-04-04 08:00

- Context loaded: current `new.html` / `new.js` model form, `app.js` shell helpers, `app.css` theme variables, and `web_ui.py` model profile parsing.
- Changes made: added `/api/model-connectivity-test`, completed saved-model advanced field round-trip, exposed a `测试连通性` button in the new-task model card, and injected a persistent nav-level light/dark toggle icon for operator pages.
- Verification run:
  - `python3 -m pytest tests/test_web_ui.py -q`
  - Playwright smoke on `/new`: confirmed `测试连通性` button and theme toggle icon render
  - Playwright eval: `document.documentElement.dataset.theme` returned `"dark"` after toggle
  - Live route probe: `POST /api/model-connectivity-test` returned a structured backend error instead of 404, confirming the new endpoint is active
- Next step: none required for this slice

## Open Questions

- None blocking.
