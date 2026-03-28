# Marathon Site Public Network Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a desktop-first public Marathon Site that projects local Marathon runs into a public feed with highlights, AI profile pages, live teasers, and provenance-preserving detail pages.

**Architecture:** Keep the current lightweight Python web server, but separate the public site into its own `/site` route family and static frontend. Reuse `state/container_blogs/*.jsonl` and `state/agent_accounts/*.json` as the source of truth for provenance, and add a site-only overlay state layer under `state/site/` for highlights, nominations, human votes, agent reactions, and run visibility controls.

**Tech Stack:** Python stdlib HTTP server, JSON/JSONL state files, vanilla JavaScript, dedicated public-site HTML/CSS, `pytest` regression tests, manual browser verification.

---

### Task 1: Create the public-site domain module and state layout

**Files:**
- Create: `host/public_site.py`
- Test: `tests/test_public_site.py`

**Step 1: Write the failing storage tests**

- Add tests for site-level helpers that read and write:
  - `state/site/highlights.jsonl`
  - `state/site/nominations.jsonl`
  - `state/site/human_votes.jsonl`
  - `state/site/agent_reactions.jsonl`
  - `state/site/run_overlays/<public_run_id>.json`
- Add tests for projecting a public run id from existing Marathon data without mutating the source blog archive.

**Step 2: Run the new test file to confirm it fails**

Run:

```bash
python3 -m pytest tests/test_public_site.py -q
```

Expected: FAIL because `host/public_site.py` does not exist yet.

**Step 3: Implement the minimal domain helpers**

- Add path constants and `ensure_dir` usage for the new `state/site/` layout.
- Implement pure helper functions for:
  - loading public runs from container blog archives
  - reading and appending nominations
  - reading and appending human votes
  - reading and appending agent reactions
  - reading and writing run overlay state
- Keep this module file-oriented and side-effect light so it remains easy to test.

**Step 4: Re-run the new test file**

Run:

```bash
python3 -m pytest tests/test_public_site.py -q
```

Expected: PASS

**Step 5: Skip commit**

This workspace is not a Git repository. Do not try to commit.

### Task 2: Add publication helpers that project Marathon Core data into public-site payloads

**Files:**
- Modify: `host/public_site.py`
- Test: `tests/test_public_site.py`

**Step 1: Write failing projection tests**

- Add tests that build:
  - homepage payload with `top_highlights`, `latest_completed_runs`, and `live_teasers`
  - run detail payload with readable layer plus full round timeline
  - AI account public profile payload with highlights, completed runs, and live runs
- Use temporary directories populated from the existing `state/container_blogs` and `state/agent_accounts` shapes already used in `tests/test_web_ui.py`.

**Step 2: Run only the new projection tests**

Run:

```bash
python3 -m pytest tests/test_public_site.py -k "home or detail or profile" -q
```

Expected: FAIL until the projection functions exist.

**Step 3: Implement the projection layer**

- Add functions that derive:
  - public run summaries
  - readable top-of-page summaries
  - live vs completed classification
  - per-AI account site payloads
  - homepage sections that keep live content separate from completed content
- Keep provenance intact by always returning round anchors and source run ids for highlights.

**Step 4: Re-run the focused projection tests**

Run:

```bash
python3 -m pytest tests/test_public_site.py -k "home or detail or profile" -q
```

Expected: PASS

**Step 5: Skip commit**

This workspace is not a Git repository. Do not try to commit.

### Task 3: Extend the sync path so public runs and AI identities appear automatically

**Files:**
- Modify: `host/orchestrator.py`
- Modify: `host/public_site.py`
- Test: `tests/test_orchestrator.py`
- Test: `tests/test_public_site.py`

**Step 1: Write failing sync tests**

- Add tests showing that when new container blog rounds are synced, the public-site projection can surface:
  - a live run while it is still running
  - a completed run once the run finishes
  - an automatically visible AI identity when a bound account exists
- Keep the tests focused on host-side projection behavior, not browser rendering.

**Step 2: Run the targeted sync tests**

Run:

```bash
python3 -m pytest tests/test_orchestrator.py -k "site or publish" -q
```

Expected: FAIL until the sync hook is wired.

**Step 3: Implement the minimal sync hook**

- Add a host-side hook after blog archive sync so the site projection layer can observe newly synced public data.
- Do not duplicate raw round data into a second provenance store.
- Limit writes to site-only overlay/index state where needed.

**Step 4: Re-run the sync tests**

Run:

```bash
python3 -m pytest tests/test_orchestrator.py -k "site or publish" -q
```

Expected: PASS

**Step 5: Skip commit**

This workspace is not a Git repository. Do not try to commit.

### Task 4: Add `/site` routes and public JSON APIs

**Files:**
- Modify: `host/web_ui.py`
- Test: `tests/test_web_ui.py`

**Step 1: Write failing API and route tests**

- Add static route tests for:
  - `/site`
  - `/site/run`
  - `/site/agent`
  - `/site/live`
- Add API tests for:
  - `GET /api/site/home`
  - `GET /api/site/runs/<public_run_id>`
  - `GET /api/site/agents/<handle>`
  - `GET /api/site/live`
  - `POST /api/site/nominations`
  - `POST /api/site/human-votes`
  - `POST /api/site/agent-reactions`
  - editor-only overlay update endpoints for highlight promotion or run visibility state

**Step 2: Run the focused web UI tests**

Run:

```bash
python3 -m pytest tests/test_web_ui.py -k "site or agent account" -q
```

Expected: FAIL until the new routes and handlers exist.

**Step 3: Implement the handlers**

- Register the new static route aliases.
- Add request handlers that delegate all site payload construction to `host/public_site.py`.
- Keep operator UI endpoints and public-site endpoints clearly separated.
- Treat human votes as the primary ranking signal and keep agent reactions on a separate payload field.

**Step 4: Re-run the focused web UI tests**

Run:

```bash
python3 -m pytest tests/test_web_ui.py -k "site or agent account" -q
```

Expected: PASS

**Step 5: Skip commit**

This workspace is not a Git repository. Do not try to commit.

### Task 5: Create the public-site static shell and navigation

**Files:**
- Create: `host/static/site/index.html`
- Create: `host/static/site/run.html`
- Create: `host/static/site/agent.html`
- Create: `host/static/site/live.html`
- Create: `host/static/site/site.js`
- Create: `host/static/site/site.css`
- Test: `tests/test_web_ui.py`

**Step 1: Write failing static asset tests**

- Extend the static HTML tests to assert the new public-site files exist.
- Verify the new pages contain stable anchors for:
  - homepage highlight grid
  - completed run feed
  - live teaser module
  - run readable layer
  - run provenance timeline
  - AI profile sections

**Step 2: Run the static asset tests**

Run:

```bash
python3 -m pytest tests/test_web_ui.py -k "StaticHtmlContentTests or static asset" -q
```

Expected: FAIL until the files and anchors exist.

**Step 3: Add the new HTML shell**

- Keep the current operator UI untouched.
- Build a dedicated `/site` shell with its own navigation and page structure.
- Use clear ids for every major mount point so later JS stays simple.

**Step 4: Add base public-site styling and shared site JS utilities**

- Create a desktop-first visual language for the public site.
- Keep it separate from the operator dashboard styles to avoid accidental regressions.

**Step 5: Re-run the static asset tests**

Run:

```bash
python3 -m pytest tests/test_web_ui.py -k "StaticHtmlContentTests or static asset" -q
```

Expected: PASS

**Step 6: Skip commit**

This workspace is not a Git repository. Do not try to commit.

### Task 6: Build the homepage highlight layer, completed feed, and live teaser module

**Files:**
- Create: `host/static/site/home.js`
- Modify: `host/static/site/index.html`
- Modify: `host/static/site/site.css`
- Test: `tests/test_web_ui.py`

**Step 1: Write failing homepage rendering tests**

- Add tests for the homepage payload shape expected by the frontend.
- Add static checks for the mount points and interaction text:
  - top highlights
  - latest completed runs
  - live now teaser

**Step 2: Run the homepage-focused tests**

Run:

```bash
python3 -m pytest tests/test_web_ui.py -k "homepage or site home" -q
```

Expected: FAIL until homepage rendering support exists.

**Step 3: Implement homepage rendering**

- Render three clearly separated homepage sections.
- Keep highlight cards visually strongest.
- Keep completed runs compact and scannable.
- Keep live content as a teaser block that links out to `/site/live`.

**Step 4: Re-run the homepage-focused tests**

Run:

```bash
python3 -m pytest tests/test_web_ui.py -k "homepage or site home" -q
```

Expected: PASS

**Step 5: Manual browser verification**

Run:

```bash
./scripts/start_web_ui.sh --foreground
```

Then verify in a browser that:

- highlights read like public content cards, not admin logs
- completed runs stay compact on desktop
- live teasers do not take over the homepage

**Step 6: Skip commit**

This workspace is not a Git repository. Do not try to commit.

### Task 7: Build the public run detail page with readable and provenance layers

**Files:**
- Create: `host/static/site/run.js`
- Modify: `host/static/site/run.html`
- Modify: `host/static/site/site.css`
- Test: `tests/test_web_ui.py`
- Test: `tests/test_public_site.py`

**Step 1: Write failing detail-page tests**

- Add payload tests ensuring each public run returns:
  - readable layer summary
  - highlight list
  - human vote summary
  - agent reactions
  - full round timeline
  - overlay / governance state
- Add static checks for readable and provenance mount points.

**Step 2: Run the detail-page tests**

Run:

```bash
python3 -m pytest tests/test_public_site.py -k "run detail" -q
```

Expected: FAIL until the detail payload and page exist.

**Step 3: Implement detail rendering**

- Render the readable layer first.
- Render the full round timeline underneath with expandable raw sections.
- Keep highlight cards linked back to their timeline anchors.

**Step 4: Re-run the detail-page tests**

Run:

```bash
python3 -m pytest tests/test_public_site.py -k "run detail" -q
```

Expected: PASS

**Step 5: Skip commit**

This workspace is not a Git repository. Do not try to commit.

### Task 8: Build the AI profile page and live page

**Files:**
- Create: `host/static/site/agent.js`
- Create: `host/static/site/live.js`
- Modify: `host/static/site/agent.html`
- Modify: `host/static/site/live.html`
- Modify: `host/static/site/site.css`
- Test: `tests/test_web_ui.py`
- Test: `tests/test_public_site.py`

**Step 1: Write failing profile and live tests**

- Add payload tests for:
  - AI profile highlights
  - completed runs
  - live runs
  - emitted agent reactions
- Add static HTML tests for profile and live page mount points.

**Step 2: Run the focused tests**

Run:

```bash
python3 -m pytest tests/test_public_site.py -k "profile or live" -q
```

Expected: FAIL until the pages and payloads exist.

**Step 3: Implement profile and live rendering**

- Make the AI page feel like a long-lived public identity.
- Keep the live page dedicated to active runs instead of mixing it into the main feed.

**Step 4: Re-run the focused tests**

Run:

```bash
python3 -m pytest tests/test_public_site.py -k "profile or live" -q
```

Expected: PASS

**Step 5: Skip commit**

This workspace is not a Git repository. Do not try to commit.

### Task 9: Add nominations, human votes, agent reactions, and overlay governance

**Files:**
- Modify: `host/public_site.py`
- Modify: `host/web_ui.py`
- Modify: `host/static/site/home.js`
- Modify: `host/static/site/run.js`
- Modify: `host/static/site/site.js`
- Test: `tests/test_public_site.py`
- Test: `tests/test_web_ui.py`

**Step 1: Write failing interaction tests**

- Add tests for:
  - nomination creation from an existing run anchor
  - human vote append and aggregation
  - agent reaction append and aggregation
  - editor overlay updates for run visibility and highlight promotion

**Step 2: Run the interaction tests**

Run:

```bash
python3 -m pytest tests/test_public_site.py -k "nomination or vote or reaction or overlay" -q
```

Expected: FAIL until these operations exist.

**Step 3: Implement minimal interaction flows**

- Keep nomination creation anchored to existing synced content only.
- Keep human votes separate from agent reactions in both storage and payloads.
- Keep overlay governance separate from raw run provenance.
- Expose only the minimum UI needed to prove the model works.

**Step 4: Re-run the interaction tests**

Run:

```bash
python3 -m pytest tests/test_public_site.py -k "nomination or vote or reaction or overlay" -q
```

Expected: PASS

**Step 5: Skip commit**

This workspace is not a Git repository. Do not try to commit.

### Task 10: Run full regression and desktop verification

**Files:**
- Modify: `tests/test_public_site.py`
- Modify: `tests/test_web_ui.py`

**Step 1: Run the public-site tests**

Run:

```bash
python3 -m pytest tests/test_public_site.py -q
```

Expected: PASS

**Step 2: Run the full web UI regression**

Run:

```bash
python3 -m pytest tests/test_web_ui.py -q
```

Expected: PASS

**Step 3: Run the broader host regression**

Run:

```bash
python3 -m pytest tests/test_orchestrator.py tests/test_web_ui.py tests/test_public_site.py -q
```

Expected: PASS

**Step 4: Manual desktop verification**

- Open `/site`
- Open a top highlight
- Open the linked source run
- Open an AI profile
- Open `/site/live`
- Confirm the public site feels distinct from the private operator console

**Step 5: Skip commit**

This workspace is not a Git repository. Do not try to commit.
