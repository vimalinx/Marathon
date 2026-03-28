# Marathon Design Lab Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a sidecar `design-lab` frontend to Marathon that compares three UI variants against the same run or container context without replacing the current host Web UI.

**Architecture:** Keep the current `/` Web UI intact, add safe static serving for `/design-lab/...`, and introduce one shared client-side data loader that all three variant pages use. Extend the observation contract just enough to make self-modification visible by exposing prompt/tool/loop source changes in existing run detail payloads and deriving a compact self-modification summary server-side.

**Tech Stack:** Python stdlib HTTP server, existing Marathon run artifacts, static HTML/CSS/JavaScript, `unittest`, optional `@browse` verification

---

**Execution Notes:**
- Use `@superpowers:test-driven-development` task by task.
- Use `@superpowers:verification-before-completion` before claiming the feature is done.
- Use `@browse` for final browser QA of the three variants.
- Skip Git commit steps in this workspace: `/home/vimalinx/Research/Marathon` is not currently a Git repository.

## File Structure

- Modify: `container/agent_loop.py`
  Responsibility: include `prompt_source` and `loop_source` in collected runtime state so the UI can observe self-modification beyond `tool_source`.
- Modify: `host/web_ui.py`
  Responsibility: derive observation/self-modification summaries, safely serve `/design-lab/...` static assets, and optionally expose a root-page link into the design lab.
- Create: `host/static/design-lab/index.html`
  Responsibility: comparison landing page and variant picker that preserves `run_id` / `container` context.
- Create: `host/static/design-lab/shared.css`
  Responsibility: shared reset, type scale, utility classes, card styles, and common status tokens used by all variants.
- Create: `host/static/design-lab/shared.js`
  Responsibility: query parsing, context-preserving link generation, API fetching, empty/error state rendering, and shared self-modification display helpers.
- Create: `host/static/design-lab/design-consultation.html`
  Responsibility: observation-deck variant focused on chronology and experiment visibility.
- Create: `host/static/design-lab/ui-ux-pro-max.html`
  Responsibility: control-cockpit variant focused on product polish and strong state presentation.
- Create: `host/static/design-lab/penpot-uiux-design.html`
  Responsibility: flow-desk variant focused on low cognitive load and clear information architecture.
- Modify: `host/static/index.html`
  Responsibility: optional entry link into the design lab without changing the current operational layout.
- Modify: `tests/test_agent_loop.py`
  Responsibility: lock in prompt/loop source capture in runtime state.
- Create: `tests/test_design_lab.py`
  Responsibility: cover safe static route serving, observation summary derivation, served-page smoke markers, and context preservation helpers.

## Chunk 1: Observation Contract And Static Routing

### Task 1: Expose prompt and loop source in collected runtime state

**Files:**
- Modify: `container/agent_loop.py`
- Test: `tests/test_agent_loop.py`

- [ ] **Step 1: Write the failing test**

Add focused tests that prove `collect_state()` now captures:
- `prompt_source` from `resolve_prompt_file()`
- `loop_source` from `container/agent_loop.py`

Example:

```python
def test_collect_state_includes_prompt_and_loop_source(self) -> None:
    with TemporaryDirectory() as tmpdir:
        prompt_file = Path(tmpdir) / "prompt.txt"
        sandbox_dir = Path(tmpdir) / "sandbox"
        prompt_file.write_text("SYSTEM PROMPT", encoding="utf-8")
        sandbox_dir.mkdir()
        with mock.patch.dict(
            os.environ,
            {
                "MARATHON_PROMPT_FILE": str(prompt_file),
                "MARATHON_SANDBOX": str(sandbox_dir),
            },
            clear=False,
        ):
            state = agent_loop.collect_state()

    self.assertEqual(state["prompt_source"], "SYSTEM PROMPT")
    self.assertIn("def collect_state", state["loop_source"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_agent_loop -v`
Expected: FAIL because `collect_state()` does not yet return `prompt_source` or `loop_source`

- [ ] **Step 3: Write minimal implementation**

Read the resolved prompt file and the current loop file alongside the existing `tool_source` capture.

Implementation shape:

```python
prompt_file = resolve_prompt_file()
loop_file = Path(__file__).resolve()
prompt_source = prompt_file.read_text(encoding="utf-8", errors="replace") if prompt_file.exists() else ""
loop_source = loop_file.read_text(encoding="utf-8", errors="replace") if loop_file.exists() else ""
```

Return both fields in the collected state dictionary without changing existing keys.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_agent_loop -v`
Expected: PASS

- [ ] **Step 5: Commit**

Skip in this workspace: `/home/vimalinx/Research/Marathon` is not a Git repository.

### Task 2: Derive self-modification summaries in the host API

**Files:**
- Modify: `host/web_ui.py`
- Create: `tests/test_design_lab.py`

- [ ] **Step 1: Write the failing test**

Add tests for a small helper such as `derive_self_modification_summary(...)` or `derive_observation_summary(...)`.

Cover:
- prompt source changed
- tool source changed
- loop source changed
- no self-modification observed
- count and latest round metadata when round artifacts are available

Example:

```python
def test_derive_self_modification_summary_flags_tool_change(self) -> None:
    summary = web_ui.derive_self_modification_summary(
        {"tool_source": "old", "prompt_source": "same", "loop_source": "same"},
        {"tool_source": "new", "prompt_source": "same", "loop_source": "same"},
    )

    self.assertTrue(summary["observed"])
    self.assertEqual(summary["latest_category"], "tool")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_design_lab -v`
Expected: FAIL because the helper and test file do not exist

- [ ] **Step 3: Write minimal implementation**

Add small, explicit helpers in `host/web_ui.py`:

- `derive_self_modification_summary(state_before, state_after)`
- `summarize_run_self_modification(run_dir, latest_state_before, latest_state_after)`
- `derive_run_observation(summary, latest_state_before, latest_state_after, recent_rounds, self_modification)`

Keep detection simple:
- compare `prompt_source`
- compare `tool_source`
- compare `loop_source`
- mark `observed=False` if all tracked sources are unchanged or missing

Required summary fields:

- `observed`
- `categories`
- `latest_category`
- `latest_round`
- `count`

If per-round artifacts under `runs/<run_id>/rounds/` are present, scan them to compute `count` and `latest_round`. If they are absent, fall back to the latest before/after state only and report `count` as `1` or `0`.

Then attach the derived payload to `run_detail()`:

```python
self_modification = summarize_run_self_modification(
    run_dir,
    latest_state_before,
    latest_state_after,
)

"observation": derive_run_observation(
    summary,
    latest_state_before,
    latest_state_after,
    read_recent_rounds(run_dir / "events.jsonl"),
    self_modification,
),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_design_lab -v`
Expected: PASS

- [ ] **Step 5: Commit**

Skip in this workspace: `/home/vimalinx/Research/Marathon` is not a Git repository.

### Task 3: Serve design-lab static assets safely

**Files:**
- Modify: `host/web_ui.py`
- Modify: `tests/test_design_lab.py`

- [ ] **Step 1: Write the failing test**

Extend `tests/test_design_lab.py` with route-level checks for:
- `GET /design-lab/index.html`
- `GET /design-lab/shared.js`
- rejection of traversal like `/design-lab/../../README.md`

Prefer a small in-process HTTP server using `ThreadingHTTPServer` and `urllib.request`.

Example:

```python
with urllib.request.urlopen(f"{base_url}/design-lab/index.html") as response:
    html = response.read().decode("utf-8")
self.assertIn("Marathon Design Lab", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_design_lab.DesignLabRouteTests -v`
Expected: FAIL because `/design-lab/...` is not served yet

- [ ] **Step 3: Write minimal implementation**

Add safe static resolution in `host/web_ui.py`:

- map `/` to the current main UI exactly as today
- map `/design-lab/...` into `STATIC_DIR / "design-lab"`
- use a helper like `resolve_static_asset_path(request_path)` to prevent traversal
- use `mimetypes.guess_type()` for HTML/CSS/JS content types

Implementation shape:

```python
asset_path = resolve_static_asset_path(parsed.path)
if asset_path is not None:
    self.send_text(
        asset_path.read_text(encoding="utf-8"),
        content_type=guess_content_type(asset_path),
    )
    return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_design_lab.DesignLabRouteTests -v`
Expected: PASS

- [ ] **Step 5: Commit**

Skip in this workspace: `/home/vimalinx/Research/Marathon` is not a Git repository.

## Chunk 2: Shared Frontend Foundation

### Task 4: Create the shared design-lab shell and context loader

**Files:**
- Create: `host/static/design-lab/index.html`
- Create: `host/static/design-lab/shared.css`
- Create: `host/static/design-lab/shared.js`
- Modify: `tests/test_design_lab.py`

- [ ] **Step 1: Write the failing test**

Add smoke tests that assert:
- `index.html` exists and contains `Marathon Design Lab`
- `shared.js` contains query parsing for `run_id` and `container`
- `shared.js` builds context-preserving variant links

Example:

```python
html = Path("host/static/design-lab/index.html").read_text(encoding="utf-8")
script = Path("host/static/design-lab/shared.js").read_text(encoding="utf-8")
self.assertIn("Marathon Design Lab", html)
self.assertIn("run_id", script)
self.assertIn("container", script)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_design_lab.DesignLabStaticFileTests -v`
Expected: FAIL because the files do not exist yet

- [ ] **Step 3: Write minimal implementation**

Create `shared.js` with these core helpers:

```javascript
export function getSelectedContext() {
  const params = new URLSearchParams(window.location.search);
  const runId = params.get("run_id");
  const container = params.get("container");
  return runId ? { run_id: runId } : container ? { container } : {};
}

export function buildVariantHref(page, context) {
  const params = new URLSearchParams(context);
  return `/design-lab/${page}?${params.toString()}`;
}
```

Also add:
- `fetchOverview()`
- `fetchRunDetail(runId)`
- `fetchContainerDetail(container)`
- `renderEmptyState(...)`
- `renderErrorState(...)`

Keep `shared.css` limited to common typography, spacing, status pills, cards, and utility classes. Do not force one visual identity into it.

Implement `index.html` as a comparison landing page with:
- three variant cards
- context selector or carry-forward links
- compact rubric copy

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_design_lab.DesignLabStaticFileTests -v`
Expected: PASS

- [ ] **Step 5: Commit**

Skip in this workspace: `/home/vimalinx/Research/Marathon` is not a Git repository.

### Task 5: Build the observation-deck variant

**Files:**
- Create: `host/static/design-lab/design-consultation.html`
- Modify: `tests/test_design_lab.py`

- [ ] **Step 1: Write the failing test**

Add a smoke test that the page contains the required sections:
- current summary
- recent timeline
- self-modification rail
- command output

Example:

```python
html = Path("host/static/design-lab/design-consultation.html").read_text(encoding="utf-8")
self.assertIn("Observation Deck", html)
self.assertIn("Self-Modification", html)
self.assertIn("Recent Rounds", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_design_lab.DesignVariantMarkupTests.test_observation_deck_sections -v`
Expected: FAIL because the page does not exist

- [ ] **Step 3: Write minimal implementation**

Build a page that loads `shared.js` and renders:
- top experiment summary strip
- central current-round and recent-round timeline
- right rail for self-modification and workspace change highlights

Minimum DOM targets:

```html
<section id="deck-summary"></section>
<section id="deck-current-round"></section>
<section id="deck-timeline"></section>
<aside id="deck-self-modification"></aside>
<section id="deck-command-output"></section>
```

Prioritize chronological understanding over KPI-style cards.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_design_lab.DesignVariantMarkupTests.test_observation_deck_sections -v`
Expected: PASS

- [ ] **Step 5: Commit**

Skip in this workspace: `/home/vimalinx/Research/Marathon` is not a Git repository.

### Task 6: Build the control-cockpit variant

**Files:**
- Create: `host/static/design-lab/ui-ux-pro-max.html`
- Modify: `tests/test_design_lab.py`

- [ ] **Step 1: Write the failing test**

Add a smoke test that the page contains:
- a strong top status zone
- KPI cards
- live feed region
- self-modification block

Example:

```python
html = Path("host/static/design-lab/ui-ux-pro-max.html").read_text(encoding="utf-8")
self.assertIn("Control Cockpit", html)
self.assertIn("Live Feed", html)
self.assertIn("Self-Modification", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_design_lab.DesignVariantMarkupTests.test_control_cockpit_sections -v`
Expected: FAIL because the page does not exist

- [ ] **Step 3: Write minimal implementation**

Build the page with:
- a high-contrast status band
- KPI card row for state, rounds, and latest self-modification
- large live activity region
- lower trays for output and file changes

Minimum DOM targets:

```html
<section id="cockpit-status-band"></section>
<section id="cockpit-kpis"></section>
<section id="cockpit-live-feed"></section>
<section id="cockpit-self-modification"></section>
<section id="cockpit-output"></section>
```

This page can be visually bolder than the observation deck, but it must still answer the same first-screen questions.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_design_lab.DesignVariantMarkupTests.test_control_cockpit_sections -v`
Expected: PASS

- [ ] **Step 5: Commit**

Skip in this workspace: `/home/vimalinx/Research/Marathon` is not a Git repository.

### Task 7: Build the flow-desk variant

**Files:**
- Create: `host/static/design-lab/penpot-uiux-design.html`
- Modify: `tests/test_design_lab.py`

- [ ] **Step 1: Write the failing test**

Add a smoke test that the page contains:
- lifecycle navigation
- current context panel
- detail inspector
- self-modification section

Example:

```python
html = Path("host/static/design-lab/penpot-uiux-design.html").read_text(encoding="utf-8")
self.assertIn("Flow Desk", html)
self.assertIn("Lifecycle", html)
self.assertIn("Detail Inspector", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_design_lab.DesignVariantMarkupTests.test_flow_desk_sections -v`
Expected: FAIL because the page does not exist

- [ ] **Step 3: Write minimal implementation**

Build the page with:
- left navigation for lifecycle and variant switching
- center state/timeline panel
- right-side detail inspector for output, diffs, and self-modification

Minimum DOM targets:

```html
<nav id="flow-lifecycle"></nav>
<section id="flow-context"></section>
<section id="flow-timeline"></section>
<aside id="flow-detail-inspector"></aside>
<section id="flow-self-modification"></section>
```

Make this variant the clearest information architecture, not the flashiest one.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_design_lab.DesignVariantMarkupTests.test_flow_desk_sections -v`
Expected: PASS

- [ ] **Step 5: Commit**

Skip in this workspace: `/home/vimalinx/Research/Marathon` is not a Git repository.

## Chunk 3: Integration And Verification

### Task 8: Wire shared empty/error/self-mod rendering across all variants

**Files:**
- Modify: `host/static/design-lab/shared.js`
- Modify: `host/static/design-lab/design-consultation.html`
- Modify: `host/static/design-lab/ui-ux-pro-max.html`
- Modify: `host/static/design-lab/penpot-uiux-design.html`
- Modify: `tests/test_design_lab.py`

- [ ] **Step 1: Write the failing test**

Add smoke assertions for the shared copy that should exist in the frontend:
- `No experiment selected`
- `No self-modification observed yet`
- `Cognition link interrupted`
- `Action failed`

Example:

```python
script = Path("host/static/design-lab/shared.js").read_text(encoding="utf-8")
self.assertIn("No self-modification observed yet", script)
self.assertIn("Cognition link interrupted", script)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_design_lab.DesignLabStateCopyTests -v`
Expected: FAIL because the shared rendering helpers do not contain the required states yet

- [ ] **Step 3: Write minimal implementation**

Centralize shared rendering text in `shared.js`:

```javascript
const EMPTY_MESSAGES = {
  noContext: "No experiment selected",
  noSelfModification: "No self-modification observed yet",
};

const ERROR_MESSAGES = {
  modelFailure: "Cognition link interrupted",
  actionFailure: "Action failed",
};
```

Render the derived `observation.self_modification` block with highest-contrast styling in every variant.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_design_lab.DesignLabStateCopyTests -v`
Expected: PASS

- [ ] **Step 5: Commit**

Skip in this workspace: `/home/vimalinx/Research/Marathon` is not a Git repository.

### Task 9: Add the main-UI entry link and final verification

**Files:**
- Modify: `host/static/index.html`
- Modify: `tests/test_design_lab.py`

- [ ] **Step 1: Write the failing test**

Add a smoke test that the main UI includes a link into the design lab.

Example:

```python
html = Path("host/static/index.html").read_text(encoding="utf-8")
self.assertIn("/design-lab/index.html", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_design_lab.DesignLabEntryPointTests -v`
Expected: FAIL because the main UI has no design-lab entry link

- [ ] **Step 3: Write minimal implementation**

Add one low-risk entry point in the current UI, for example:

```html
<a class="pill" href="/design-lab/index.html">Design Lab</a>
```

Keep the existing layout intact. This is an entry link, not a redesign.

- [ ] **Step 4: Run targeted verification**

Run: `python3 -m unittest tests.test_agent_loop tests.test_design_lab tests.test_web_ui -v`
Expected: PASS

- [ ] **Step 5: Run full suite**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 6: Run browser QA**

Start the UI:

```bash
./scripts/start_web_ui.sh
RUN_ID="$(find runs -mindepth 1 -maxdepth 1 -type d | head -n 1 | xargs -n1 basename)"
echo "$RUN_ID"
```

Open and verify:

```bash
xdg-open "http://127.0.0.1:8765/design-lab/index.html?run_id=${RUN_ID}"
xdg-open "http://127.0.0.1:8765/design-lab/design-consultation.html?run_id=${RUN_ID}"
xdg-open "http://127.0.0.1:8765/design-lab/ui-ux-pro-max.html?run_id=${RUN_ID}"
xdg-open "http://127.0.0.1:8765/design-lab/penpot-uiux-design.html?run_id=${RUN_ID}"
```

Manual checklist:
- all three pages load
- switching variants preserves `run_id`
- empty/error states are legible when data is missing
- self-modification is visually stronger than generic file changes
- the main UI still works unchanged aside from the new entry link

- [ ] **Step 7: Commit**

Skip in this workspace: `/home/vimalinx/Research/Marathon` is not a Git repository.
