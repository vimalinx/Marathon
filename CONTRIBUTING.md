# Contributing

Thanks for contributing to Marathon.

## Start Here

Read these first:

1. [README.md](./README.md)
2. [docs/PLAYBOOK.md](./docs/PLAYBOOK.md)
3. the relevant design/plan doc in `docs/plans/`

## Working Rules

- Keep `Marathon Core` and `Marathon Site` boundaries explicit.
- Treat raw run history as provenance, not editable presentation data.
- Prefer small, verifiable slices over broad mixed-scope changes.
- Update durable repo docs when product shape, IA, or execution flow changes.

## Verification

Run the narrowest proof for the files you touched.

Common commands:

```bash
python3 -m pytest tests/test_web_ui.py -q
python3 -m pytest tests/test_orchestrator.py -q
python3 -m pytest tests/test_public_site.py -q
python3 -m pytest -q
```

For operator UI changes, also do a browser smoke check.

## Pull Requests

Include:

- the user-visible outcome
- verification commands actually run
- remaining risks or follow-up work

## Experimental Areas

The repo contains experimental surfaces such as `design-lab` and parts of the public-site snapshot flow. Unless your task explicitly targets those areas, prefer `Marathon Core` fixes and docs work first.
