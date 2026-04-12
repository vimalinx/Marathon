# AGENTS.md

This file is a map, not an encyclopedia. Keep it short, stable, and point deeper decisions into repo docs.

## What This Repo Is

Marathon currently has two product surfaces:

- `Marathon Core`: the local runtime system for container runs, host orchestration, nightly execution, logs, and provenance.
- `Marathon Site`: the public-facing publication layer that projects real Marathon runs into a browseable network.

Do not blur these two surfaces together by accident.

## Read First

For any non-trivial change, load context in this order:

1. `README.md`
2. `docs/PLAYBOOK.md`
3. the relevant `docs/plans/*-design.md`
4. the matching implementation plan in `docs/plans/*.md`
5. the tests around the touched area

## Repo Map

- `container/`: agent runtime inside the sandbox
- `host/orchestrator.py`: host-side sync and run observation
- `host/host_nightly*.py`: host-nightly execution path for real repos
- `host/web_ui.py`: local operator console and API surface
- `host/public_site.py`: public-site projection layer
- `host/static/site/*`: desktop-first public site frontend
- `tests/`: behavior source of truth for code changes
- `docs/plans/`: primary home for active design docs and executable implementation plans
- `docs/superpowers/`: historical planning/spec material; do not use as the default location for new work
- `state/`: runtime data and public-site overlay state

## Hard Product Boundaries

### Marathon Core

- Owns execution, rounds, raw logs, sync, container state, and nightly runs.
- Raw run data is provenance. Treat it as the most trusted layer.

### Marathon Site

- Owns discovery, presentation, highlighting, voting, nominations, and reactions.
- Must project from real synced Marathon data, not from free-floating community posts.
- Public editorial state belongs in `state/site/`, not in raw run archives.

## Hard Invariants

- Do not rewrite raw run or round history for editorial reasons.
- Keep `live` and `completed` as separate browsing surfaces.
- Keep `human votes` and `agent reactions` as separate signals.
- Keep public overlays additive. They may rank, annotate, or hide; they must not falsify source provenance.
- For the public site, optimize desktop first unless a task explicitly requires mobile.
- Long content should clamp in list cards and expand only on canonical detail pages.

## Documentation Workflow

- If a change alters product shape, IA, or boundaries, create or update a `*-design.md` doc first.
- If work spans multiple concrete steps, create or update a matching implementation plan in `docs/plans/`.
- Prefer `docs/plans/` over legacy scratch files or `docs/superpowers/` when creating new durable context.
- Use `docs/plans/TEMPLATE-active-plan.md` when the work may span multiple sessions or agents.
- Keep the repo as the record system. Do not leave critical decisions only in chat.

## Plan Naming

- Design doc: `docs/plans/YYYY-MM-DD-topic-design.md`
- Execution plan: `docs/plans/YYYY-MM-DD-topic.md`

Keep plan titles stable once execution starts. Update the contents, not the filename, unless the scope actually changed.

## Verification Expectations

- Run targeted `pytest` for touched backend modules.
- Run `tests/test_web_ui.py` for route or static frontend changes.
- Run `tests/test_public_site.py` for public-site projection changes.
- Run a browser smoke check for meaningful UI changes before calling the work done.

## Handoff Standard

Before ending a session:

- update the active plan or relevant design doc if the scope changed
- record the verification commands actually run
- note any unresolved risk or next slice
- leave enough context that a fresh agent can continue from the repo alone
