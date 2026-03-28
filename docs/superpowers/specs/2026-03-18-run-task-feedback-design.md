# Run Task And Feedback Loop Design

## Goal

Make Marathon's in-container agent stop behaving like a stateless command generator.

The first iteration should add two concrete capabilities:

1. Each run can carry its own explicit task prompt.
2. Each round sent to the model includes recent execution feedback and current sandbox state.

## Current Problem

Today the container agent only sends two messages to the model: the global system prompt and a tiny user payload containing the round number. The model does not see the previous command result, recent round summaries, or the current sandbox state when choosing the next action.

That creates three practical failures:

1. The agent has no working memory across rounds.
2. The task is implicit and weak because the default prompt is effectively "play freely."
3. The host UI can launch runs, but it cannot define a concrete per-run objective.

## Non-Goals

This iteration will not add:

- Long-term memory or vector search
- A planner / executor split
- Multiple tools beyond the existing single command executor
- Autonomous prompt optimization
- Full conversation history replay

## Recommended Approach

Use a run-scoped task prompt plus a compact feedback bundle generated from the most recent run artifacts.

The global prompt should stay responsible for role, boundaries, and output format. The concrete objective should move into run metadata so different runs can pursue different tasks without rewriting the global prompt file. Each round should construct a structured user message that includes the task, current round number, recent round history, the latest tool result, and a snapshot of sandbox state.

This keeps the current architecture intact:

- Host still launches and mirrors runs.
- Container agent still executes exactly one JSON action per round.
- The only semantic change is that the model finally sees enough context to continue work intentionally.

## Alternatives Considered

### 1. Global Prompt Only

Put a stronger default mission into `prompts/minimal_system.txt` and leave run metadata unchanged.

This is cheaper to implement but fails the main product need: different runs cannot carry different goals, and state continuity remains weak.

### 2. Full Memory / Planner Layer

Add persistent task state, explicit planning artifacts, and a richer control loop.

This would likely improve performance more than the recommended approach, but it is a much larger redesign and would blur whether the first improvement came from basic state feedback or from a new runtime architecture.

## Design

### 1. Run-Scoped Task Prompt

Add a new `task_prompt` field to run launch flows.

Sources:

- `POST /api/runs/start`
- `POST /api/containers/<name>/launch-agent`
- direct host supervisor launch metadata

Behavior:

- If the caller supplies `task_prompt`, use it for that run.
- If omitted or blank, use a repository-defined default task prompt.
- Persist the resolved task prompt into run metadata on both host and container sides.

The task prompt must be treated as data for a run, not as part of the global system prompt file.

### 2. Global Prompt Responsibility Shift

Revise `prompts/minimal_system.txt` so it does not carry the concrete mission. It should define:

- The runtime identity
- The fact that the agent runs inside the container
- The single-command-per-round constraint
- The strict JSON output contract
- The expectation that the model should use provided task and feedback context

This separates permanent rules from per-run intent.

### 3. Feedback Bundle Construction

Add a context-building step inside `container/agent_loop.py` before each model call.

The bundle should include:

- `task_prompt`
- `round`
- `recent_rounds`: a compact list of the last few round outcomes
- `last_action`: latest `summary`, `argv`, and return code when available
- `last_tool_result`: trimmed stdout/stderr and timeout information
- `sandbox_state`: current file tree preview and git status
- `guidance`: reminder to continue the task incrementally and output only one JSON action

The bundle should be serialized as one structured JSON object inside the user message.

### 4. Context Size Limits

Feedback must be bounded so the loop stays stable.

Recommended limits for the first version:

- Include at most the latest 5 completed or failed rounds
- Trim stdout/stderr previews to a fixed character limit
- Trim sandbox tree and git status to existing preview lengths or lower

If an artifact is missing, represent that explicitly with `null` or an empty string instead of raising.

### 5. Message Construction

`build_messages()` should return:

1. The revised system prompt
2. A single user message containing the structured round context

The user message should remain deterministic and machine-oriented. Avoid natural-language wrapping around the JSON payload.

### 6. Host Metadata And UI

The host side should surface and preserve the task prompt.

Changes:

- Extend model/run resolution to accept `task_prompt`
- Write the resolved task into `host_run.json`
- Expose task prompt in run detail payloads
- Add a task input field in the Web UI for new runs and "launch agent in existing container"

The UI should prefill the field with the default task prompt so the user sees what will happen even if they do not customize it.

### 7. Default Task Prompt

Add a small default task prompt constant on the host side and/or in shared metadata handling. The default should be explicit and pragmatic, for example:

"Inspect the sandbox, identify the most useful next step, and improve the workspace incrementally while preserving a runnable, observable state."

The exact wording can be tuned during implementation, but it should describe a real goal instead of "随便玩."

## Data Flow

1. User starts a run or launches an agent from the Web UI.
2. Host resolves model settings and task prompt.
3. Host writes launch metadata and starts the supervisor.
4. Container agent writes run metadata including `task_prompt`.
5. Before each round, the agent collects current sandbox state and recent run artifacts.
6. The agent sends system prompt plus structured round context to the model.
7. The model returns one JSON action.
8. The tool executes the action.
9. The agent records results and uses them as feedback in the next round.

## Error Handling

- Missing task prompt: resolve to the default task prompt.
- Missing prior artifacts: continue with empty feedback fields.
- Oversized stdout/stderr: trim before message construction.
- Invalid old log entries: skip them rather than failing the run.
- Model still returns invalid JSON: preserve current failure behavior.

This iteration should improve continuity without weakening the existing fail-fast behavior for invalid model output.

## File Impact

Expected code changes:

- Modify `container/agent_loop.py`
- Modify `host/orchestrator.py`
- Modify `host/web_ui.py`
- Modify `host/static/index.html`
- Modify `prompts/minimal_system.txt`
- Add tests, likely under `tests/`

## Testing Strategy

Add focused tests around context construction instead of trying to integration-test LXC behavior in the first pass.

Minimum coverage:

1. `build_messages()` includes the resolved task prompt.
2. `build_messages()` includes recent action/result/state feedback.
3. Missing history still produces a valid message.
4. Context trimming keeps previews bounded.
5. Host-side task prompt resolution uses the default when omitted.

Prefer stdlib-friendly Python tests if no existing test runner is present.

## Risks

### Prompt Drift

Adding too much raw feedback can make the model less consistent. The fix is aggressive truncation and a simple message schema.

### UI / Host / Container Schema Drift

The same `task_prompt` concept will cross several files. Keep the field name identical everywhere to avoid accidental mismatch.

### False Sense Of Memory

This is still not long-term memory. It only gives the model enough short-horizon continuity to continue work sensibly.

## Success Criteria

The change is successful when:

- A user can launch two runs with different task prompts without editing the global prompt file.
- The round payload sent to the model contains recent run feedback and current sandbox state.
- The agent can continue from the previous round's outcome instead of acting as if each round is brand new.
- Existing JSON action execution behavior remains unchanged.
