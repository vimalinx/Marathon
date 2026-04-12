# Security Policy

## Reporting

Do not open public issues for vulnerabilities that could expose:

- API keys or tokens
- local network access
- host command execution paths
- container breakout paths

Use the repository's private maintainer contact path if available. If none is configured yet, disclose minimally and avoid publishing exploit details until maintainers can coordinate a fix.

## Relevant Surfaces

Security-sensitive areas include:

- `host/web_ui.py`
- `host/orchestrator.py`
- `container/agent_loop.py`
- scripts that start, stop, clone, or destroy containers

## Operational Notes

- The operator UI is intended to bind to localhost.
- The project assumes `sudo -n` for LXC control; review trust boundaries carefully.
- Never commit real credentials or local env files.
- If you enable external ingestion writers, set `MARATHON_INGEST_TOKEN` so `/api/ingest/*` is not left anonymous.
