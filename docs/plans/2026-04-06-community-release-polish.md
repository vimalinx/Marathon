# Community Release Polish Active Plan

**Status:** completed
**Owner:** Codex
**Branch / Worktree:** current workspace
**Last Updated:** 2026-04-06
**Related Design:** none

**Goal:** Add the collaboration and release-facing repository scaffolding needed after the initial public `v0.1` baseline is ready.

**Architecture:** This slice stays in repository metadata and docs. It adds GitHub issue templates, a PR template, a changelog skeleton, and a lightweight release process note so outside contributors have a clear intake and release path without changing runtime behavior.

**Verification:**

- Manual file presence/content check for `.github/ISSUE_TEMPLATE/*`, `.github/pull_request_template.md`, `CHANGELOG.md`, and `RELEASING.md`

**Out Of Scope:**

- Runtime behavior changes
- CI behavior beyond the basic test workflow
- Maintainer roster or governance model

---

## Current Slice

**Why now:** The repository is now close to public-release shape. The remaining value is in making contribution and release workflows legible to outside users.

**Stop condition:** The repo contains usable issue/PR intake templates plus a basic changelog and release checklist.

## Task 1: Add contributor intake templates

**Files:**

- Create: `.github/ISSUE_TEMPLATE/bug_report.md`
- Create: `.github/ISSUE_TEMPLATE/feature_request.md`
- Create: `.github/ISSUE_TEMPLATE/config.yml`
- Create: `.github/pull_request_template.md`

**Status:** completed

## Task 2: Add release-facing docs

**Files:**

- Create: `CHANGELOG.md`
- Create: `RELEASING.md`

**Status:** completed

## Session Log

### 2026-04-06 12:30

- Context loaded: existing `.github/` state and the completed open-source release plan.
- Changes made: added issue templates, PR template, changelog skeleton, and a lightweight releasing guide.
- Verification run: manual file presence/content review only; no code paths changed.
- Next step: none required for this slice.
