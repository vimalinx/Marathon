#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_CWD = Path("/workspace/sandbox")


def configured_cwd() -> Path:
    raw = os.environ.get("MARATHON_SANDBOX", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_CWD


def fail(message: str, **extra: object) -> None:
    payload = {"ok": False, "error": message}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(1)


def ok(**payload: object) -> None:
    body = {"ok": True}
    body.update(payload)
    print(json.dumps(body, ensure_ascii=False))


def read_action() -> dict[str, object]:
    raw = sys.stdin.read().strip()
    if not raw:
        fail("expected JSON payload on stdin")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        fail("invalid JSON payload", detail=str(exc))
    if not isinstance(payload, dict):
        fail("top-level JSON payload must be an object")
    return payload


def resolve_cwd() -> Path:
    candidate = configured_cwd()
    if candidate.is_dir():
        return candidate
    try:
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate
    except OSError:
        return Path.cwd()


def main() -> None:
    action = read_action()
    argv = action.get("argv")
    timeout = int(action.get("timeout", 30))

    if not isinstance(argv, list) or not argv:
        fail("argv must be a non-empty list")

    env = os.environ.copy()
    env["PATH"] = env.get("PATH", "")
    cwd = resolve_cwd()

    try:
        completed = subprocess.run(
            [str(part) for part in argv],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        ok(
            argv=argv,
            cwd=str(cwd),
            timeout=True,
            returncode=None,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
        )
        return

    ok(
        argv=argv,
        cwd=str(cwd),
        timeout=False,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


if __name__ == "__main__":
    main()
