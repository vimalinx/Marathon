# <Feature Name> Active Plan

Copy this file to `docs/plans/YYYY-MM-DD-topic.md` before editing. Keep the template itself unchanged.

**Status:** active
**Owner:** <human or agent>
**Branch / Worktree:** <branch name or worktree path>
**Last Updated:** YYYY-MM-DD
**Related Design:** `docs/plans/YYYY-MM-DD-topic-design.md` or `none`

**Goal:** One sentence describing the user-visible outcome.

**Architecture:** One short paragraph describing the affected modules and why this slice belongs there.

**Verification:** List the exact commands that will be used to prove the work.

- `python3 -m pytest <target> -q`
- `<browser smoke check command or manual route list>`

**Out Of Scope:**

- Explicitly list what this plan is not doing.

---

## Current Slice

**Why now:** Why this slice is the right next move.

**Stop condition:** The concrete condition that makes this slice done.

## Task 1: <Task Name>

**Files:**

- Modify: `<path>`
- Create: `<path>`
- Test: `<path>`

**Status:** pending

**Step 1:** Describe the first concrete edit or test setup.

**Step 2:** Describe the implementation action.

**Step 3:** Describe the verification step.

## Task 2: <Task Name>

**Files:**

- Modify: `<path>`
- Test: `<path>`

**Status:** pending

**Step 1:** Describe the first concrete edit or test setup.

**Step 2:** Describe the implementation action.

**Step 3:** Describe the verification step.

## Decision Log

- YYYY-MM-DD: Record any boundary, naming, or architecture decision that future sessions must inherit.

## Session Log

### YYYY-MM-DD HH:MM

- Context loaded:
- Changes made:
- Verification run:
- Next step:

Add one block per meaningful session. Keep it short and factual.

## Open Questions

- Record only real blockers or decisions that still need confirmation.

## Done Definition

- The targeted behavior is implemented.
- The listed verification commands passed.
- The plan and decision log reflect the final shape.
