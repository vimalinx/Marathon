# Run Task Feedback Loop Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add run-scoped task prompts and short-horizon execution feedback so Marathon's agent can continue work across rounds with a concrete objective.

**Architecture:** Keep the existing host-orchestrator-container structure intact. Add a `task_prompt` field to run launch metadata, thread it through host and container runtime files, and change the model input builder in `container/agent_loop.py` to include bounded recent feedback and current sandbox state. Extend the Web UI to collect this field and revise the global system prompt so it defines rules, not a specific mission.

**Tech Stack:** Python 3 stdlib, HTML/CSS/vanilla JavaScript, `unittest`, LXC host scripts

---

## File Structure

- Modify: `container/agent_loop.py`
  Responsibility: run metadata, context assembly, bounded feedback bundle, model message construction.
- Modify: `host/orchestrator.py`
  Responsibility: pass resolved `task_prompt` into container runtime and mirror it into host-side metadata.
- Modify: `host/web_ui.py`
  Responsibility: define default task prompt, resolve per-run task input, expose task prompt in API payloads.
- Modify: `host/static/index.html`
  Responsibility: add task prompt inputs to launch forms and send them to the backend.
- Modify: `prompts/minimal_system.txt`
  Responsibility: define runtime rules and JSON contract without owning the per-run mission.
- Create: `tests/test_agent_loop.py`
  Responsibility: verify message construction, history trimming, and feedback inclusion.
- Create: `tests/test_web_ui.py`
  Responsibility: verify host-side task prompt resolution and defaulting behavior.

## Chunk 1: Runtime Context Plumbing

### Task 1: Add Host-Side Task Prompt Resolution Tests

**Files:**
- Create: `tests/test_web_ui.py`
- Modify: `host/web_ui.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest
import host.web_ui as web_ui


class ResolveTaskPromptTests(unittest.TestCase):
    def test_resolve_task_prompt_uses_default_when_blank(self):
        self.assertEqual(
            web_ui.resolve_task_prompt({"task_prompt": "   "}),
            web_ui.DEFAULT_TASK_PROMPT,
        )

    def test_resolve_task_prompt_preserves_explicit_value(self):
        self.assertEqual(
            web_ui.resolve_task_prompt({"task_prompt": "inspect project and improve docs"}),
            "inspect project and improve docs",
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_web_ui -v`
Expected: FAIL with `AttributeError` or import-time failure because `resolve_task_prompt` and `DEFAULT_TASK_PROMPT` do not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add a default task prompt constant and helper in `host/web_ui.py`.

```python
DEFAULT_TASK_PROMPT = (
    "Inspect the sandbox, identify the most useful next step, "
    "and improve the workspace incrementally while preserving an observable state."
)


def resolve_task_prompt(payload: dict[str, Any]) -> str:
    raw = str(payload.get('task_prompt') or '').strip()
    return raw or DEFAULT_TASK_PROMPT
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_web_ui -v`
Expected: PASS for both task prompt resolution cases.

- [ ] **Step 5: Commit**

If this directory becomes a git repository:

```bash
git add tests/test_web_ui.py host/web_ui.py
git commit -m "test: cover host task prompt resolution"
```

### Task 2: Thread `task_prompt` Through Host Launch Metadata

**Files:**
- Modify: `host/web_ui.py`
- Modify: `host/orchestrator.py`
- Test: `tests/test_web_ui.py`

- [ ] **Step 1: Write the failing test**

Extend `tests/test_web_ui.py` with a behavior test for resolved run config.

```python
class ResolveRunLaunchPayloadTests(unittest.TestCase):
    def test_resolved_launch_payload_includes_task_prompt(self):
        payload = {"task_prompt": "repair the sandbox incrementally"}
        self.assertEqual(
            web_ui.resolve_task_prompt(payload),
            "repair the sandbox incrementally",
        )
```

Also add a small helper-level test if you extract metadata-building behavior from `host/orchestrator.py`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_web_ui -v`
Expected: FAIL because launch flows do not yet store or pass `task_prompt`.

- [ ] **Step 3: Write minimal implementation**

Make these changes:

- In `host/web_ui.py`, include `task_prompt` in:
  - `launch_agent_for_container(...)`
  - `start_run(...)`
  - `run_detail(...)` response if present
- In `host/orchestrator.py`, add `--task-prompt` arg and include it in:
  - `host_run.json`
  - `start_agent(...)` environment variables

Implementation sketch:

```python
parser.add_argument('--task-prompt', default=os.environ.get('MARATHON_TASK_PROMPT', ''))

metadata = {
    ...
    'task_prompt': args.task_prompt,
}
```

```python
f'MARATHON_TASK_PROMPT={shlex.quote(task_prompt)} '
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_web_ui -v`
Expected: PASS with resolved `task_prompt` behavior intact.

- [ ] **Step 5: Commit**

If this directory becomes a git repository:

```bash
git add tests/test_web_ui.py host/web_ui.py host/orchestrator.py
git commit -m "feat: pass task prompts through host launch flow"
```

## Chunk 2: Container Feedback Bundle

### Task 3: Add Failing Tests For Agent Message Construction

**Files:**
- Create: `tests/test_agent_loop.py`
- Modify: `container/agent_loop.py`

- [ ] **Step 1: Write the failing test**

Create focused tests around a new helper, for example `build_round_context(...)` or an expanded `build_messages(...)`.

```python
import json
import unittest
import container.agent_loop as agent_loop


class BuildMessagesTests(unittest.TestCase):
    def test_build_messages_includes_task_prompt_and_feedback(self):
        messages = agent_loop.build_messages(
            system_prompt="rules",
            round_index=3,
            task_prompt="repair the sandbox",
            feedback_bundle={
                "recent_rounds": [{"round": 2, "summary": "listed files"}],
                "last_action": {"summary": "list files", "argv": ["bash", "-lc", "ls"]},
                "last_tool_result": {"returncode": 0, "stdout": "a\\nb\\n", "stderr": ""},
                "sandbox_state": {"sandbox_tree": "./a\\n./b", "sandbox_git_status": "?? a"},
            },
        )
        payload = json.loads(messages[1]["content"])
        self.assertEqual(payload["task_prompt"], "repair the sandbox")
        self.assertEqual(payload["recent_rounds"][0]["round"], 2)
        self.assertIn("sandbox_state", payload)

    def test_build_messages_trims_large_feedback(self):
        messages = agent_loop.build_messages(
            system_prompt="rules",
            round_index=1,
            task_prompt="repair",
            feedback_bundle={
                "recent_rounds": [],
                "last_action": {},
                "last_tool_result": {"stdout": "x" * 5000, "stderr": ""},
                "sandbox_state": {"sandbox_tree": "y" * 5000, "sandbox_git_status": ""},
            },
        )
        payload = json.loads(messages[1]["content"])
        self.assertLess(len(payload["last_tool_result"]["stdout"]), 5000)
        self.assertLess(len(payload["sandbox_state"]["sandbox_tree"]), 5000)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_agent_loop -v`
Expected: FAIL because `build_messages()` does not accept the extra parameters and no trimming helpers exist.

- [ ] **Step 3: Write minimal implementation**

In `container/agent_loop.py`:

- Add a `DEFAULT_TASK_PROMPT`
- Read `MARATHON_TASK_PROMPT` from args/env
- Add helpers to trim previews and normalize missing artifacts
- Expand `build_messages()` to accept `task_prompt` and `feedback_bundle`

Implementation sketch:

```python
def trim_text(value: str | None, *, limit: int) -> str:
    text = value or ""
    return text if len(text) <= limit else text[:limit]
```

```python
def build_messages(system_prompt, round_index, task_prompt, feedback_bundle):
    payload = {
        "round": round_index,
        "task_prompt": task_prompt,
        **feedback_bundle,
        "instruction": "Continue the task and output the next command JSON only.",
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_agent_loop -v`
Expected: PASS for task prompt inclusion and bounded preview behavior.

- [ ] **Step 5: Commit**

If this directory becomes a git repository:

```bash
git add tests/test_agent_loop.py container/agent_loop.py
git commit -m "test: cover agent feedback message construction"
```

### Task 4: Build Feedback From Recent Run Artifacts

**Files:**
- Modify: `container/agent_loop.py`
- Test: `tests/test_agent_loop.py`

- [ ] **Step 1: Write the failing test**

Extend `tests/test_agent_loop.py` with a helper-level test for a new function that builds feedback from recent files.

```python
class BuildFeedbackBundleTests(unittest.TestCase):
    def test_feedback_bundle_uses_recent_rounds_and_latest_result(self):
        bundle = agent_loop.build_feedback_bundle(
            round_index=4,
            state_before={"sandbox_tree": "./a", "sandbox_git_status": "?? a"},
            latest_action={"summary": "inspect"},
            latest_tool_result={"returncode": 0, "stdout": "ok", "stderr": ""},
            recent_rounds=[
                {"event": "round_completed", "round": 1, "summary": "one"},
                {"event": "round_completed", "round": 2, "summary": "two"},
                {"event": "round_failed", "round": 3, "error": "boom"},
            ],
        )
        self.assertEqual(len(bundle["recent_rounds"]), 3)
        self.assertEqual(bundle["last_tool_result"]["returncode"], 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_agent_loop -v`
Expected: FAIL because `build_feedback_bundle()` does not exist yet.

- [ ] **Step 3: Write minimal implementation**

Add focused helpers in `container/agent_loop.py`:

- `summarize_recent_rounds(...)`
- `build_feedback_bundle(...)`

Then use them in the main loop before `call_model(...)`.

Implementation sketch:

```python
feedback_bundle = build_feedback_bundle(
    round_index=round_index,
    state_before=state_before,
    latest_action=read_json_if_exists(live_summary_file),
    latest_tool_result=read_json_if_exists(live_result_file),
    recent_rounds=read_recent_events(events_file, limit=5),
)
messages = build_messages(system_prompt, round_index, args.task_prompt, feedback_bundle)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_agent_loop -v`
Expected: PASS with stable recent-round summarization and latest result inclusion.

- [ ] **Step 5: Commit**

If this directory becomes a git repository:

```bash
git add tests/test_agent_loop.py container/agent_loop.py
git commit -m "feat: add bounded agent feedback bundle"
```

## Chunk 3: UI And Prompt Integration

### Task 5: Add UI Task Prompt Inputs And API Wiring

**Files:**
- Modify: `host/static/index.html`
- Modify: `host/web_ui.py`
- Test: `tests/test_web_ui.py`

- [ ] **Step 1: Write the failing test**

Add a backend-facing test that `resolve_task_prompt()` and launch handlers accept explicit task data from request payloads.

```python
class LaunchPayloadTests(unittest.TestCase):
    def test_launch_payload_can_override_default_task_prompt(self):
        payload = {"task_prompt": "inspect and improve startup files"}
        self.assertEqual(web_ui.resolve_task_prompt(payload), "inspect and improve startup files")
```

This test overlaps intentionally with UI API wiring because the backend is the stable seam.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_web_ui -v`
Expected: FAIL until the request handlers thread `task_prompt` into launch calls.

- [ ] **Step 3: Write minimal implementation**

In `host/web_ui.py`:

- Resolve `task_prompt` in:
  - `/api/runs/start`
  - `/api/containers/<name>/launch-agent`
- Pass it into `start_run(...)` and `launch_agent_for_container(...)`

In `host/static/index.html`:

- Add a textarea or text input for task prompt in both launch forms
- Prefill it from the backend default task prompt or inline default text
- Include `task_prompt` in the JSON body sent by `fetch`

Implementation sketch:

```javascript
task_prompt: form.get('task_prompt'),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_web_ui -v`
Expected: PASS for backend launch payload resolution.

- [ ] **Step 5: Commit**

If this directory becomes a git repository:

```bash
git add tests/test_web_ui.py host/web_ui.py host/static/index.html
git commit -m "feat: add run task prompt inputs"
```

### Task 6: Revise Global Prompt And Run The Full Verification Set

**Files:**
- Modify: `prompts/minimal_system.txt`
- Modify: `container/agent_loop.py`
- Test: `tests/test_agent_loop.py`
- Test: `tests/test_web_ui.py`

- [ ] **Step 1: Write the failing test**

If the prompt text is validated in tests, add a small assertion around the new system prompt expectations. If not, treat the existing message-construction tests as the failing tests for this task and update them to require that task ownership lives in the user payload, not only the system prompt.

Example:

```python
self.assertEqual(payload["task_prompt"], "repair the sandbox")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_agent_loop tests.test_web_ui -v`
Expected: FAIL until the final prompt wording and message flow match the new design.

- [ ] **Step 3: Write minimal implementation**

Revise `prompts/minimal_system.txt` so it says, in effect:

- You are running inside the container
- Use the provided task and feedback context
- Output one JSON action only
- Do not emit Markdown or explanation

Also ensure `container/agent_loop.py` writes `task_prompt` into `run.json` metadata.

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_agent_loop tests.test_web_ui -v`
Expected: PASS for all focused tests.

- [ ] **Step 5: Run broader smoke verification**

Run: `python3 -m unittest discover -s tests -v`
Expected: PASS with all discovered tests green.

- [ ] **Step 6: Commit**

If this directory becomes a git repository:

```bash
git add prompts/minimal_system.txt container/agent_loop.py tests/test_agent_loop.py tests/test_web_ui.py
git commit -m "feat: add run task prompts and feedback loop"
```

## Notes

- Current workspace is not a git repository, so commit steps are conditional until version control exists.
- If `host/static/index.html` becomes hard to edit cleanly, keep changes minimal and localized rather than restructuring the page.
- Stop and reassess if the feedback bundle starts pulling in too much raw log text; the first version should stay aggressively bounded.
