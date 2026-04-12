# Changelog

All notable changes to this project should be recorded in this file.

## Unreleased

- No unreleased entries yet.

## v0.1.0 - 2026-04-06

Initial public open-source release centered on `Marathon Core`.

### Added

- Operator Web UI for container-first local orchestration
- Runtime budget controls for rounds, pacing, wall-clock time, and total token usage
- Model configuration persistence plus connectivity testing from the UI
- Manual retry controls for failed runs and core container lifecycle actions in the detail view
- Invalid model-response diagnostics and host-visible retry evidence
- Public-release scaffolding:
  - MIT license
  - contributing guide
  - security policy
  - code of conduct
  - GitHub issue templates
  - pull request template
  - basic GitHub Actions test workflow

### Changed

- Removed repository-level hardcoded provider defaults; `MARATHON_BASE_URL` and `MARATHON_API_KEY` must now be provided explicitly
- Hardened Web UI startup so port conflicts fail loudly instead of looking like a successful launch
- Clarified release scope: `Marathon Core` is the primary supported public surface for `v0.1`

### Experimental

These surfaces remain available but are still more experimental than `Marathon Core`:

- `Marathon Site`
- `design-lab`
- GitHub Pages snapshot publishing flow
