# Release Helpers Active Plan

**Status:** completed
**Owner:** Codex
**Branch / Worktree:** current workspace
**Last Updated:** 2026-04-07
**Related Design:** none

**Goal:** Add small release-maintenance helpers after the repository became publishable: remove duplicated test scaffolding and provide a simple script for printing release notes by version.

**Architecture:** This slice is repo-maintenance only. It touches `tests/test_web_ui.py` to remove duplicate test-class definitions and adds a lightweight shell helper in `scripts/` to surface versioned release notes files without changing runtime code.

**Verification:**

- `python3 -m pytest tests/test_web_ui.py -q`
- `bash -n scripts/show_release_notes.sh`

**Out Of Scope:**

- Release tagging
- Publishing to GitHub

---

## Current Slice

**Why now:** The release pipeline is largely ready, so the next best step is eliminating maintenance confusion and smoothing the release operator workflow.

**Stop condition:** There is only one model-connectivity test class in `tests/test_web_ui.py`, and a maintainer can print the `v0.1.0` release notes with a single script command.

## Task 1: Remove duplicate release-adjacent test scaffolding

**Files:**

- Modify: `tests/test_web_ui.py`

**Status:** completed

## Task 2: Add release-notes helper script

**Files:**

- Create: `scripts/show_release_notes.sh`

**Status:** completed

## Session Log

### 2026-04-07 00:00

- Context loaded: current release docs, `scripts/`, and `tests/test_web_ui.py`.
- Changes made: removed duplicated model-connectivity test class and added a release-notes helper script.
- Verification run:
  - `python3 -m pytest tests/test_web_ui.py -q`
  - `bash -n scripts/show_release_notes.sh`
- Next step: none required.
