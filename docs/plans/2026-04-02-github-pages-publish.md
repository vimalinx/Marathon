# GitHub Pages Snapshot Publish Active Plan

**Status:** completed
**Owner:** Codex
**Branch / Worktree:** current workspace
**Last Updated:** 2026-04-02
**Related Design:** `docs/plans/2026-04-02-github-pages-publish-design.md`

**Goal:** Export the current Marathon public-facing data into a static snapshot and let this machine push it to `gh-pages` on an hourly timer.

**Architecture:** Add a file-only projection/export module that reads `runs/` and `state/` without touching LXC or Web UI runtime APIs. Pair that exporter with a small static frontend under `host/static/site/`, then add a host-side `gh-pages` sync runner plus `systemd --user` timer scripts.

**Verification:** List the exact commands that will be used to prove the work.

- `python3 -m pytest tests/test_public_site.py -q`
- `python3 -m pytest tests/test_web_ui.py tests/test_public_site.py -q`
- `python3 scripts/export_github_pages.py --output-dir build/github-pages`

**Out Of Scope:**

- Live public APIs under `/site`
- Human votes, nominations, reactions
- Runtime operator controls on the public Pages site

---

## Current Slice

**Why now:** The repo already has enough run and identity data to publish a useful static feed. GitHub Pages is the shortest path to a durable public surface.

**Stop condition:** A local export produces a complete static site bundle and the repo contains a host-side hourly sync path that can push the snapshot to `gh-pages`.

## Task 1: Add the Pages projection and export module

**Files:**

- Create: `host/public_site.py`
- Create: `tests/test_public_site.py`

**Status:** completed

**Step 1:** Add failing tests for public home, run detail, agent detail, and static export.

**Step 2:** Implement file-based projection helpers and a static export entrypoint.

**Step 3:** Run the new test file and a local export.

## Task 2: Add the static GitHub Pages frontend

**Files:**

- Create: `host/static/site/index.html`
- Create: `host/static/site/run.html`
- Create: `host/static/site/agent.html`
- Create: `host/static/site/live.html`
- Create: `host/static/site/site.css`
- Create: `host/static/site/site.js`

**Status:** completed

**Step 1:** Add minimal desktop-first public pages that load exported JSON.

**Step 2:** Keep the visual language aligned with the current repo rather than inventing a new brand.

**Step 3:** Verify the exported bundle contains the expected pages and assets.

## Task 3: Add the host-side hourly sync path

**Files:**

- Create: `host/github_pages_sync.py`
- Create: `scripts/run_github_pages_sync_once.sh`
- Create: `scripts/setup_github_pages_sync.sh`
- Modify: `README.md`

**Status:** completed

**Step 1:** Add a script wrapper for local/manual export.

**Step 2:** Add a host-side sync runner that exports, commits, and pushes to `gh-pages`.

**Step 3:** Add a `systemd --user` setup script for hourly execution and document the repo/Pages prerequisites.

## Decision Log

- 2026-04-02: GitHub Pages publish is a static snapshot product slice, not the same thing as the future live `Marathon Site`.
- 2026-04-02: Export must be file-only so GitHub Actions can build it without LXC or local runtime dependencies.
- 2026-04-02: Hourly publish should push a prepared static snapshot to `gh-pages` from the local machine instead of relying on GitHub Actions to reconstruct local runtime state.

## Session Log

### 2026-04-02 21:00

- Context loaded: README, PLAYBOOK, current public-site design/plan, Web UI structure, current state files.
- Changes made: Added a dedicated GitHub Pages design doc and active plan.
- Verification run: none yet
- Next step: implement `host/public_site.py`, static site assets, and the Pages workflow.

### 2026-04-02 22:30

- Context loaded: existing `runs/` and `state/agent_accounts/` data shapes, current Web UI helper structure.
- Changes made: added `host/public_site.py`, a static public-site frontend under `host/static/site/`, `scripts/export_github_pages.py`, a Pages workflow, and README documentation.
- Verification run:
  - `python3 -m pytest tests/test_public_site.py -q`
  - `python3 -m pytest tests/test_web_ui.py tests/test_public_site.py -q`
  - `python3 scripts/export_github_pages.py --output-dir build/github-pages`
- Next step: enable GitHub Pages in the GitHub repository settings and decide whether to auto-push runtime state from the local Marathon host.

### 2026-04-02 23:05

- Context loaded: current GitHub Pages export path, host nightly timer pattern, and local git remote state.
- Changes made: added `host/github_pages_sync.py`, one-shot and setup scripts for hourly `gh-pages` sync, updated README, and changed the Pages workflow to manual-only so branch-based publish is the default path.
- Verification run:
  - `python3 -m pytest tests/test_github_pages_sync.py -q`
  - `python3 -m pytest tests/test_public_site.py tests/test_github_pages_sync.py tests/test_host_nightly_scripts.py -q`
  - `bash scripts/run_github_pages_sync_once.sh` -> confirmed clear failure because this local repo has no `origin`
- Next step: point `origin` at the GitHub repo, configure Pages to serve `gh-pages`, then run `./scripts/setup_github_pages_sync.sh`.

## Open Questions

- None for the current implementation slice. The remaining dependency is repository configuration outside this workspace: `origin` and GitHub Pages branch source.

## Done Definition

- The targeted behavior is implemented.
- The listed verification commands passed.
- The plan and decision log reflect the final shape.
