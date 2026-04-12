# Marathon Repo Playbook

This file defines how Marathon work should be documented, sliced, verified, and handed off.

## Goal

Make the repo legible to fresh agents and humans without depending on chat history.

The rule is simple:

- long-lived context belongs in the repo
- execution progress belongs in plans
- raw runtime truth belongs in runtime state

## The Three Layers

### 1. Product And Architecture Context

Use these files for stable intent:

- `README.md`: system overview
- `AGENTS.md`: short map and repo rules
- `docs/plans/*-design.md`: product boundary, IA, architecture, and design intent

### 2. Execution Context

Use `docs/plans/*.md` for active implementation plans.

A good plan is:

- concrete
- file-scoped
- verifiable
- small enough to resume after interruption

For work that may cross sessions, start from [TEMPLATE-active-plan.md](./plans/TEMPLATE-active-plan.md).

### Legacy Paths

These may still exist in the repo:

- `docs/superpowers/*`
- `task_plan.md`
- `progress.md`
- `findings.md`

Treat them as historical or task-specific context unless the current task explicitly depends on them. New durable design and execution context should go under `docs/plans/`.

### 3. Runtime And Publication State

Use runtime files as data, not as human policy docs:

- `state/container_blogs/*.jsonl`
- `state/agent_accounts/*.json`
- `state/site/*.jsonl`
- `state/site/run_overlays/*.json`

These are operational state and provenance layers. Do not turn them into hand-maintained product documentation.

## Standard Work Loop

### Step 1: Load the minimum useful context

Read:

1. `README.md`
2. `AGENTS.md`
3. the closest design doc
4. the matching implementation plan
5. the tests for the touched modules

Do not bulk-read unrelated docs.

### Step 2: Decide whether this is design work, implementation work, or both

Create or update a design doc first when the change affects:

- product boundaries
- information architecture
- navigation model
- public vs private surface separation
- data ownership or source-of-truth rules

Go straight to the implementation plan when the product/design intent is already settled and only execution remains.

### Step 3: Work in small slices

Every task should end in something that can be checked:

- a passing targeted test
- a verified route
- a visible UI improvement
- a recorded decision

Avoid giant branches of half-finished work.

### Step 4: Verify before claiming success

Use the narrowest commands that prove the touched behavior.

Recommended defaults:

- `python3 -m pytest tests/test_orchestrator.py -q`
- `python3 -m pytest tests/test_web_ui.py -q`
- `python3 -m pytest tests/test_public_site.py -q`

For cross-cutting public-site work, run the combined set:

```bash
python3 -m pytest tests/test_orchestrator.py tests/test_web_ui.py tests/test_public_site.py -q
```

For desktop frontend changes, add a browser smoke check.

### Step 5: Leave a resumable trail

At session end:

- update the active plan
- append a short session log
- record commands actually run
- record the next intended slice

If the repo cannot tell the next agent what happened, the session is not really finished.

## Marathon-Specific Product Rules

### Core vs Site

`Marathon Core` is the execution and provenance system.

`Marathon Site` is the public publication layer.

That means:

- Core owns runs, rounds, logs, sync, and runtime state.
- Site owns ranking, discovery, cards, highlights, nominations, votes, reactions, and public identity presentation.
- Site must project from synced Marathon data, not bypass it.

### Provenance vs Overlay

Treat these as different classes of truth:

- raw run and round data = provenance
- site highlighting and ranking = overlay

Overlay state can:

- rank
- annotate
- promote
- hide from certain feeds

Overlay state cannot:

- rewrite source rounds
- fabricate provenance
- merge live and completed into one ambiguous state

### Public Signal Separation

Keep these separate in both docs and code:

- human votes
- agent reactions
- editor promotion
- nomination queue

Do not collapse them into one generic score unless a design doc explicitly changes the model.

### Desktop-First Public Site

For the current phase:

- prioritize desktop browsing quality
- keep homepage cards compact
- clamp long copy in feeds
- make cards enter canonical detail pages instead of expanding in place

Mobile polish is optional until explicitly prioritized.

## Plan Quality Bar

Every durable implementation plan should include:

- one-sentence goal
- architecture summary
- exact file list
- verification commands
- task-by-task execution steps

For long-running or multi-session work, also include:

- current status
- branch or worktree
- decision log
- session log
- next slice

If a plan cannot survive a context reset, it is not good enough.

## Suggested Doc Pairing

For medium or large product work, keep a pair:

- `YYYY-MM-DD-topic-design.md`
- `YYYY-MM-DD-topic.md`

The design doc answers:

- what are we changing
- why this boundary
- what is out of scope

The implementation plan answers:

- which files
- which order
- how we verify

Do not stuff both jobs into one unfocused doc.

## Verification Matrix

Use this as a default map from touched code to proof:

- `host/orchestrator.py` -> `tests/test_orchestrator.py`
- `host/web_ui.py` -> `tests/test_web_ui.py`
- `host/public_site.py` -> `tests/test_public_site.py`
- `host/static/site/*` -> `tests/test_web_ui.py` plus browser smoke check
- cross-cutting publish flow -> all three test files together

## Handoff Format

When a session stops midstream, the plan should answer:

- what changed
- what was verified
- what remains
- what branch or worktree holds the work
- what should be done next

Prefer one clear paragraph or a short timestamped block over a long diary.
