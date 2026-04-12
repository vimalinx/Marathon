# Invalid Model Response Retry Active Plan

**Status:** completed
**Owner:** Codex
**Branch / Worktree:** current workspace
**Last Updated:** 2026-04-04
**Related Design:** none

**Goal:** Retry once when a model returns malformed action JSON, and persist enough raw response evidence to debug repeated failures.

**Architecture:** The change stays inside `container/agent_loop.py`. The loop should treat malformed or schema-invalid model action payloads as a model-response failure class, not an immediate terminal run failure, and should retry one additional model request before marking the round failed. Invalid attempts should leave raw response artifacts and event markers. Tests live in `tests/test_agent_loop.py`.

**Verification:**

- `python3 -m pytest tests/test_agent_loop.py -q`

**Out Of Scope:**

- Provider-specific prompt tuning
- Changing the public UI copy
- Multi-retry backoff strategies beyond one extra attempt

---

## Current Slice

**Why now:** A recent `glm-5.1` run failed on round 12 due to malformed JSON with an invalid backslash escape. The system currently treats that as terminal even though a one-time retry is low-risk and directly aligned with the user's request.

**Stop condition:** Invalid model action JSON triggers exactly one extra model request, raw failed responses are recorded, and targeted tests pass.

## Task 1: Add one-shot invalid-response retry in the agent loop

**Files:**

- Modify: `container/agent_loop.py`
- Test: `tests/test_agent_loop.py`

**Status:** completed

## Decision Log

- 2026-04-04: Retry applies only to model-response parsing/validation failures, not to tool failures or arbitrary runtime exceptions.

## Session Log

### 2026-04-04 09:00

- Context loaded: latest failing run metadata, `live.stderr`, `events.jsonl`, current JSON extraction code, and existing agent loop tests.
- Changes made: none yet
- Verification run: none yet
- Next step: implement retry helper plus invalid-response event/artifact persistence.

### 2026-04-04 09:20

- Context loaded: confirmed latest `glm-5.1` run failed on round 12 due to `Invalid \escape` in model-returned JSON-like content.
- Changes made: added one-shot retry for invalid model action payloads, persisted invalid response attempts as round artifacts plus `model_response_invalid` events, and ensured failed invalid responses still update `latest_response.txt` for host-side debugging.
- Verification run:
  - `python3 -m pytest tests/test_agent_loop.py -q`
- Next step: none required; the new behavior will apply on the next launched run after container sync.

## Open Questions

- None blocking.
