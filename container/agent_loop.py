#!/usr/bin/env python3

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = ""
DEFAULT_MODEL = "gpt-5.4"
DEFAULT_TASK_PROMPT = (
    "Inspect the sandbox, identify the most useful next step, "
    "and improve the workspace incrementally while preserving an observable state."
)
DEFAULT_LOG_ROOT = Path("/workspace/runtime-log")
DEFAULT_SANDBOX = Path("/workspace/sandbox")
DEFAULT_PROMPT_FILE = Path("/opt/marathon/minimal_system.txt")
DEFAULT_TOOL_FILE = Path("/opt/marathon/agent_tools.py")
DEFAULT_MODEL_SETTINGS = {
    "temperature": 0.7,
    "request_timeout_seconds": 120.0,
    "request_max_attempts": 3,
    "request_retry_delay_seconds": 1.0,
    "extra_body": {},
}
MAX_FEEDBACK_TEXT_CHARS = 2000
ACTION_TEXT_FIELDS = ("done", "next", "thought")
INVALID_MODEL_RESPONSE_RETRIES = 3


def resolve_log_root() -> Path:
    raw = os.environ.get("MARATHON_LOG_ROOT", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_LOG_ROOT


def resolve_sandbox_dir() -> Path:
    raw = os.environ.get("MARATHON_SANDBOX", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_SANDBOX


def resolve_prompt_file() -> Path:
    raw = os.environ.get("MARATHON_PROMPT_FILE", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_PROMPT_FILE


def resolve_tool_file() -> Path:
    raw = os.environ.get("MARATHON_TOOL_FILE", "").strip()
    return Path(raw).expanduser() if raw else DEFAULT_TOOL_FILE


def resolve_runtime_paths() -> dict[str, Path]:
    return {
        "log_root": resolve_log_root(),
        "sandbox": resolve_sandbox_dir(),
        "prompt_file": resolve_prompt_file(),
        "tool_file": resolve_tool_file(),
    }


def run_command(argv: list[str], *, input_text: str | None = None, cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        input=input_text,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
        check=check,
    )


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: object) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def read_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def init_git_repo(path: Path, *, name: str, email: str) -> None:
    ensure_dir(path)
    if not (path / ".git").exists():
        run_command(["git", "init", str(path)], check=True)
    run_command(["git", "-C", str(path), "config", "user.name", name], check=False)
    run_command(["git", "-C", str(path), "config", "user.email", email], check=False)


def git_commit(path: Path, message: str) -> dict[str, object]:
    run_command(["git", "-C", str(path), "add", "-A"], check=False)
    completed = run_command(["git", "-C", str(path), "commit", "--allow-empty", "-m", message], check=False)
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def collect_state() -> dict[str, object]:
    sandbox_dir = resolve_sandbox_dir()
    ensure_dir(sandbox_dir)
    sandbox_tree = run_command([
        "bash",
        "-lc",
        f"cd {shlex.quote(str(sandbox_dir))} && find . -maxdepth 3 \\( -type f -o -type d \\) | sort | sed -n '1,200p'",
    ])
    sandbox_status = run_command(["bash", "-lc", f"cd {shlex.quote(str(sandbox_dir))} && git status --short || true"])
    prompt_file = resolve_prompt_file()
    tool_file = resolve_tool_file()
    loop_file = Path(__file__).resolve()
    prompt_source = prompt_file.read_text(encoding="utf-8", errors="replace") if prompt_file.exists() else ""
    tool_source = tool_file.read_text(encoding="utf-8", errors="replace") if tool_file.exists() else ""
    loop_source = loop_file.read_text(encoding="utf-8", errors="replace") if loop_file.exists() else ""
    return {
        "sandbox_tree": sandbox_tree.stdout,
        "sandbox_git_status": sandbox_status.stdout,
        "prompt_source": prompt_source,
        "tool_source": tool_source,
        "loop_source": loop_source,
    }


def compact_line(value: object, *, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def derive_action_summary(action: dict[str, object], *, limit: int = 160) -> str:
    for field in ACTION_TEXT_FIELDS:
        text = str(action.get(field) or "").strip()
        if text:
            return compact_line(text, limit=limit)
    return "no-summary"


def extract_commit_hash(commit_result: dict[str, object]) -> str | None:
    text = "\n".join(
        part for part in (str(commit_result.get("stdout") or ""), str(commit_result.get("stderr") or "")) if part
    )
    match = re.search(r"\[.+? ([0-9a-f]{7,40})\]", text)
    if match:
        return match.group(1)
    return None


def commit_sandbox(round_index: int, action: dict[str, object]) -> dict[str, object]:
    sandbox_dir = resolve_sandbox_dir()
    ensure_dir(sandbox_dir)
    safe_summary = derive_action_summary(action, limit=100)
    return git_commit(sandbox_dir, f"round {round_index}: {safe_summary}")


def extract_json_object(raw_text: str) -> dict[str, object]:
    stripped = raw_text.strip()
    if not stripped:
        raise ValueError("empty model response")
    try:
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    if start == -1:
        raise ValueError("no JSON object found")
    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(stripped)):
        char = stripped[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                candidate = stripped[start : index + 1]
                payload = json.loads(candidate)
                if isinstance(payload, dict):
                    return payload
                break
    raise ValueError("failed to parse JSON object")


def validate_action(payload: dict[str, object]) -> dict[str, object]:
    normalized = dict(payload)
    for field in ACTION_TEXT_FIELDS:
        value = str(normalized.get(field) or "").strip()
        if not value:
            raise ValueError(f"action missing non-empty {field}")
        normalized[field] = value

    argv = normalized.get("argv")
    if not isinstance(argv, list) or not argv:
        raise ValueError("action argv must be a non-empty list")
    normalized["argv"] = [str(part) for part in argv]

    timeout_raw = normalized.get("timeout", 30)
    try:
        timeout = int(timeout_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("action timeout must be an integer") from exc
    if timeout <= 0:
        raise ValueError("action timeout must be positive")
    normalized["timeout"] = timeout

    normalized["summary"] = derive_action_summary(normalized)
    return normalized


def load_model_settings(raw_text: str) -> dict[str, object]:
    settings = dict(DEFAULT_MODEL_SETTINGS)
    if not raw_text:
        return settings
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid MARATHON_MODEL_SETTINGS_JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("MARATHON_MODEL_SETTINGS_JSON must decode to an object")

    extra_body = payload.get("extra_body")
    if extra_body is None:
        payload["extra_body"] = {}
    elif not isinstance(extra_body, dict):
        raise ValueError("model settings extra_body must be an object")

    settings.update(payload)
    return settings


def call_model(base_url: str, api_key: str, model: str, messages: list[dict[str, str]], model_settings: dict[str, object]) -> tuple[str, dict[str, object]]:
    url = base_url.rstrip("/") + "/chat/completions"
    body: dict[str, object] = {
        "model": model,
        "messages": messages,
    }

    if model_settings.get("reasoning_effort"):
        body["reasoning_effort"] = model_settings["reasoning_effort"]
    if model_settings.get("temperature") is not None:
        body["temperature"] = model_settings["temperature"]
    if model_settings.get("top_p") is not None:
        body["top_p"] = model_settings["top_p"]
    if model_settings.get("max_completion_tokens") is not None:
        body["max_completion_tokens"] = model_settings["max_completion_tokens"]
    if model_settings.get("extra_body"):
        body.update(model_settings["extra_body"])

    timeout_seconds = float(model_settings.get("request_timeout_seconds") or DEFAULT_MODEL_SETTINGS["request_timeout_seconds"])
    max_attempts = max(1, int(model_settings.get("request_max_attempts") or DEFAULT_MODEL_SETTINGS["request_max_attempts"]))
    retry_delay_seconds = float(
        model_settings.get("request_retry_delay_seconds") or DEFAULT_MODEL_SETTINGS["request_retry_delay_seconds"]
    )
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    transient_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read().decode("utf-8")
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"model HTTP error {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, http.client.RemoteDisconnected, http.client.IncompleteRead) as exc:
            transient_error = exc
            if attempt >= max_attempts:
                raise RuntimeError(f"model request failed after {max_attempts} attempts: {exc}") from exc
            time.sleep(retry_delay_seconds)
    else:
        raise RuntimeError(f"model request failed after {max_attempts} attempts: {transient_error}")
    payload = json.loads(raw)
    content = payload["choices"][0]["message"]["content"]
    return content, payload


class InvalidModelResponseError(ValueError):
    def __init__(self, message: str, *, attempts: list[dict[str, object]]) -> None:
        super().__init__(message)
        self.attempts = attempts


def usage_int(value: object) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def normalize_token_usage(payload: dict[str, object] | None) -> dict[str, int]:
    usage = payload.get("usage") if isinstance(payload, dict) else None
    if not isinstance(usage, dict):
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    return {
        "prompt_tokens": usage_int(usage.get("prompt_tokens")),
        "completion_tokens": usage_int(usage.get("completion_tokens")),
        "total_tokens": usage_int(usage.get("total_tokens")),
    }


def add_token_usage_counts(current: dict[str, int], update: dict[str, int]) -> dict[str, int]:
    return {
        "prompt_tokens": current.get("prompt_tokens", 0) + update.get("prompt_tokens", 0),
        "completion_tokens": current.get("completion_tokens", 0) + update.get("completion_tokens", 0),
        "total_tokens": current.get("total_tokens", 0) + update.get("total_tokens", 0),
    }


def accumulate_token_usage(current: dict[str, int], payload: dict[str, object] | None) -> dict[str, int]:
    usage = normalize_token_usage(payload)
    return {
        "prompt_tokens": current.get("prompt_tokens", 0) + usage["prompt_tokens"],
        "completion_tokens": current.get("completion_tokens", 0) + usage["completion_tokens"],
        "total_tokens": current.get("total_tokens", 0) + usage["total_tokens"],
    }


def stop_reason_for_limits(
    *,
    elapsed_seconds: int,
    token_usage: dict[str, int],
    max_runtime_seconds: int | None,
    max_total_tokens: int | None,
) -> str | None:
    if max_runtime_seconds and elapsed_seconds >= max_runtime_seconds:
        return "max_runtime_seconds"
    if max_total_tokens and token_usage.get("total_tokens", 0) >= max_total_tokens:
        return "max_total_tokens"
    return None


def request_validated_action_with_retry(
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    model_settings: dict[str, object],
    *,
    invalid_response_retries: int = INVALID_MODEL_RESPONSE_RETRIES,
) -> dict[str, object]:
    invalid_attempts: list[dict[str, object]] = []
    round_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    last_error: ValueError | None = None

    for attempt in range(1, invalid_response_retries + 2):
        response_text, raw_response = call_model(base_url, api_key, model, messages, model_settings)
        usage = normalize_token_usage(raw_response)
        round_usage = add_token_usage_counts(round_usage, usage)
        try:
            action = validate_action(extract_json_object(response_text))
            return {
                "response_text": response_text,
                "raw_response": raw_response,
                "action": action,
                "round_usage": round_usage,
                "invalid_attempts": invalid_attempts,
            }
        except ValueError as exc:
            last_error = exc
            invalid_attempts.append(
                {
                    "attempt": attempt,
                    "error": str(exc),
                    "response_text": response_text,
                    "raw_response": raw_response,
                    "usage": usage,
                    "ts": iso_now(),
                }
            )
            if attempt > invalid_response_retries:
                raise InvalidModelResponseError(str(exc), attempts=invalid_attempts) from exc

    raise InvalidModelResponseError(str(last_error or "invalid model response"), attempts=invalid_attempts)


def persist_invalid_response_attempt(round_dir: Path, events_file: Path, *, round_index: int, attempt_payload: dict[str, object]) -> None:
    attempt = int(attempt_payload.get("attempt") or 0)
    suffix = f"{attempt:02d}"
    (round_dir / f"response.invalid-{suffix}.txt").write_text(str(attempt_payload.get("response_text") or ""), encoding="utf-8")
    write_json(round_dir / f"response.invalid-{suffix}.raw.json", attempt_payload.get("raw_response") or {})
    append_jsonl(
        events_file,
        {
            "event": "model_response_invalid",
            "round": round_index,
            "attempt": attempt,
            "error": attempt_payload.get("error"),
            "prompt_tokens": ((attempt_payload.get("usage") or {}) if isinstance(attempt_payload.get("usage"), dict) else {}).get("prompt_tokens"),
            "completion_tokens": ((attempt_payload.get("usage") or {}) if isinstance(attempt_payload.get("usage"), dict) else {}).get("completion_tokens"),
            "total_tokens": ((attempt_payload.get("usage") or {}) if isinstance(attempt_payload.get("usage"), dict) else {}).get("total_tokens"),
            "ts": attempt_payload.get("ts") or iso_now(),
        },
    )


def run_tool(action: dict[str, object]) -> dict[str, object]:
    completed = run_command(["python3", str(resolve_tool_file())], input_text=json.dumps(action, ensure_ascii=False))
    try:
        parsed = json.loads(completed.stdout.strip() or "{}")
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": "tool returned invalid JSON",
            "raw_stdout": completed.stdout,
            "raw_stderr": completed.stderr,
            "host_returncode": completed.returncode,
        }
    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "error": "tool returned non-object JSON",
            "raw_stdout": completed.stdout,
            "raw_stderr": completed.stderr,
            "host_returncode": completed.returncode,
        }
    parsed["host_returncode"] = completed.returncode
    if completed.stderr:
        parsed["host_stderr"] = completed.stderr
    return parsed


def trim_text(value: object, *, limit: int = MAX_FEEDBACK_TEXT_CHARS) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit]


def summarize_recent_rounds(recent_rounds: list[dict[str, object]], *, limit: int = 5) -> list[dict[str, object]]:
    summarized: list[dict[str, object]] = []
    for item in recent_rounds:
        if not isinstance(item, dict):
            continue
        event = item.get("event")
        if event in {"round_completed", "round_post"}:
            summarized.append(
                {
                    "round": item.get("round"),
                    "done": item.get("done") or item.get("summary"),
                    "next": item.get("next"),
                    "thought": item.get("thought"),
                    "returncode": item.get("returncode"),
                    "tool_ok": item.get("tool_ok"),
                }
            )
        elif event == "round_failed":
            summarized.append(
                {
                    "round": item.get("round"),
                    "error": item.get("error"),
                    "failed": True,
                }
            )
    return summarized[-limit:]


def read_recent_events(path: Path, *, limit: int = 5) -> list[dict[str, object]]:
    if not path.exists():
        return []
    events: list[dict[str, object]] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events[-limit:]


def build_feedback_bundle(
    *,
    round_index: int,
    state_before: dict[str, object],
    latest_action: dict[str, object] | None,
    latest_tool_result: dict[str, object] | None,
    recent_rounds: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "current_round": round_index,
        "recent_rounds": summarize_recent_rounds(recent_rounds),
        "last_action": latest_action or {},
        "last_tool_result": latest_tool_result or {},
        "sandbox_state": {
            "sandbox_tree": state_before.get("sandbox_tree", ""),
            "sandbox_git_status": state_before.get("sandbox_git_status", ""),
        },
    }


def build_messages(
    system_prompt: str,
    round_index: int,
    task_prompt: str,
    feedback_bundle: dict[str, object],
) -> list[dict[str, str]]:
    last_action = feedback_bundle.get("last_action")
    if not isinstance(last_action, dict):
        last_action = {}

    last_tool_result = feedback_bundle.get("last_tool_result")
    if not isinstance(last_tool_result, dict):
        last_tool_result = {}

    sandbox_state = feedback_bundle.get("sandbox_state")
    if not isinstance(sandbox_state, dict):
        sandbox_state = {}

    payload = {
        "round": round_index,
        "task_prompt": task_prompt,
        "recent_rounds": [
            {
                **recent_round,
                "done": trim_text(recent_round.get("done")),
                "next": trim_text(recent_round.get("next")),
                "thought": trim_text(recent_round.get("thought")),
                "error": trim_text(recent_round.get("error")),
            }
            for recent_round in (feedback_bundle.get("recent_rounds") or [])
            if isinstance(recent_round, dict)
        ],
        "last_action": {
            **last_action,
            "done": trim_text(last_action.get("done")),
            "next": trim_text(last_action.get("next")),
            "thought": trim_text(last_action.get("thought")),
        },
        "last_tool_result": {
            **last_tool_result,
            "stdout": trim_text(last_tool_result.get("stdout")),
            "stderr": trim_text(last_tool_result.get("stderr")),
        },
        "sandbox_state": {
            **sandbox_state,
            "sandbox_tree": trim_text(sandbox_state.get("sandbox_tree")),
            "sandbox_git_status": trim_text(sandbox_state.get("sandbox_git_status")),
        },
        "instruction": "Continue the task and output JSON with done, next, thought, argv, timeout only.",
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def update_status(status_file: Path, payload: dict[str, object]) -> None:
    write_json(status_file, payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Minimal agent loop running inside the LXC container")
    parser.add_argument("--run-id", default=os.environ.get("RUN_ID", time.strftime("run-%Y%m%d-%H%M%S")))
    parser.add_argument("--log-root", default=str(resolve_log_root()))
    parser.add_argument("--prompt-file", default=str(resolve_prompt_file()))
    parser.add_argument("--model", default=os.environ.get("MARATHON_MODEL", DEFAULT_MODEL))
    parser.add_argument("--base-url", default=os.environ.get("MARATHON_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--api-key", default=os.environ.get("MARATHON_API_KEY", ""))
    parser.add_argument("--task-prompt", default=os.environ.get("MARATHON_TASK_PROMPT", DEFAULT_TASK_PROMPT))
    parser.add_argument("--model-settings-json", default=os.environ.get("MARATHON_MODEL_SETTINGS_JSON", ""))
    parser.add_argument("--max-rounds", type=int, default=int(os.environ.get("MAX_ROUNDS", "0")))
    parser.add_argument("--sleep-seconds", type=float, default=float(os.environ.get("ROUND_SLEEP_SECONDS", "1")))
    parser.add_argument("--max-runtime-seconds", type=int, default=int(os.environ.get("MAX_RUNTIME_SECONDS", "0")))
    parser.add_argument("--max-total-tokens", type=int, default=int(os.environ.get("MAX_TOTAL_TOKENS", "0")))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.api_key:
        print("missing MARATHON_API_KEY", file=sys.stderr)
        sys.exit(2)
    if not args.base_url:
        print("missing MARATHON_BASE_URL", file=sys.stderr)
        sys.exit(2)

    log_root = Path(args.log_root)
    sandbox_dir = resolve_sandbox_dir()
    tool_file = resolve_tool_file()
    run_dir = log_root / args.run_id
    rounds_dir = run_dir / "rounds"
    ensure_dir(rounds_dir)
    ensure_dir(sandbox_dir)

    init_git_repo(run_dir, name=os.environ.get("MARATHON_GIT_NAME", "marathon-agent"), email=os.environ.get("MARATHON_GIT_EMAIL", "marathon@local"))
    init_git_repo(sandbox_dir, name=os.environ.get("MARATHON_GIT_NAME", "marathon-agent"), email=os.environ.get("MARATHON_GIT_EMAIL", "marathon@local"))

    system_prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    model_settings = load_model_settings(args.model_settings_json)
    max_runtime_seconds = args.max_runtime_seconds if args.max_runtime_seconds > 0 else None
    max_total_tokens = args.max_total_tokens if args.max_total_tokens > 0 else None
    status_file = run_dir / "status.json"
    events_file = run_dir / "events.jsonl"
    pid_file = run_dir / "agent.pid"
    live_summary_file = run_dir / "latest_action.json"
    live_result_file = run_dir / "latest_tool_result.json"
    live_before_file = run_dir / "latest_state_before.json"
    live_after_file = run_dir / "latest_state_after.json"
    live_response_file = run_dir / "latest_response.txt"
    live_round_file = run_dir / "latest_round.json"
    blog_file = run_dir / "blog.jsonl"

    pid_file.write_text(str(os.getpid()) + "\n", encoding="utf-8")

    metadata = {
        "run_id": args.run_id,
        "started_at": iso_now(),
        "model": args.model,
        "base_url": args.base_url,
        "task_prompt": args.task_prompt,
        "context_mode": "none",
        "tool_mode": "single-exec",
        "runtime": "inside-container",
        "prompt_file": args.prompt_file,
        "tool_file": str(tool_file),
        "sandbox_dir": str(sandbox_dir),
        "model_settings": model_settings,
        "max_runtime_seconds": max_runtime_seconds,
        "max_total_tokens": max_total_tokens,
    }
    token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    write_json(run_dir / "run.json", metadata)
    update_status(
        status_file,
        {
            **metadata,
            "state": "running",
            "completed_rounds": 0,
            "pid": os.getpid(),
            "token_usage_prompt": 0,
            "token_usage_completion": 0,
            "token_usage_total": 0,
            "elapsed_seconds": 0,
            "updated_at": iso_now(),
        },
    )
    append_jsonl(events_file, {"event": "run_started", "run_id": args.run_id, "pid": os.getpid(), "ts": iso_now()})
    git_commit(run_dir, "run initialized")

    round_index = 1
    completed_rounds = 0
    started_monotonic = time.monotonic()
    stop_reason = None
    try:
        while args.max_rounds == 0 or round_index <= args.max_rounds:
            elapsed_seconds = max(0, int(time.monotonic() - started_monotonic))
            stop_reason = stop_reason_for_limits(
                elapsed_seconds=elapsed_seconds,
                token_usage=token_usage,
                max_runtime_seconds=max_runtime_seconds,
                max_total_tokens=max_total_tokens,
            )
            if stop_reason:
                append_jsonl(
                    events_file,
                    {
                        "event": "run_budget_reached",
                        "round": completed_rounds,
                        "stop_reason": stop_reason,
                        "elapsed_seconds": elapsed_seconds,
                        "token_usage_total": token_usage["total_tokens"],
                        "ts": iso_now(),
                    },
                )
                break

            if (run_dir / "STOP").exists():
                update_status(
                    status_file,
                    {
                        **metadata,
                        "state": "stopping",
                        "completed_rounds": completed_rounds,
                        "pid": os.getpid(),
                        "token_usage_prompt": token_usage["prompt_tokens"],
                        "token_usage_completion": token_usage["completion_tokens"],
                        "token_usage_total": token_usage["total_tokens"],
                        "elapsed_seconds": elapsed_seconds,
                        "stop_reason": "stop_requested",
                        "updated_at": iso_now(),
                    },
                )
                stop_reason = "stop_requested"
                break

            round_dir = rounds_dir / f"{round_index:04d}"
            ensure_dir(round_dir)
            state_before = collect_state()
            latest_action = read_json(live_summary_file)
            latest_tool_result = read_json(live_result_file)
            feedback_bundle = build_feedback_bundle(
                round_index=round_index,
                state_before=state_before,
                latest_action=latest_action,
                latest_tool_result=latest_tool_result,
                recent_rounds=read_recent_events(events_file),
            )
            messages = build_messages(
                system_prompt,
                round_index,
                args.task_prompt,
                feedback_bundle,
            )
            response_text = ""
            raw_response: dict[str, object] = {}
            action: dict[str, object] = {}
            tool_result: dict[str, object] = {}
            sandbox_commit: dict[str, object] = {}
            state_after: dict[str, object] = {}
            round_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            invalid_response_attempts: list[dict[str, object]] = []

            try:
                action_request = request_validated_action_with_retry(
                    args.base_url,
                    args.api_key,
                    args.model,
                    messages,
                    model_settings,
                )
                response_text = str(action_request["response_text"])
                raw_response = action_request["raw_response"] if isinstance(action_request["raw_response"], dict) else {}
                action = action_request["action"] if isinstance(action_request["action"], dict) else {}
                round_usage = action_request["round_usage"] if isinstance(action_request["round_usage"], dict) else round_usage
                invalid_response_attempts = (
                    action_request["invalid_attempts"] if isinstance(action_request["invalid_attempts"], list) else []
                )
                for invalid_attempt in invalid_response_attempts:
                    if isinstance(invalid_attempt, dict):
                        persist_invalid_response_attempt(round_dir, events_file, round_index=round_index, attempt_payload=invalid_attempt)
                token_usage = add_token_usage_counts(token_usage, round_usage)
                tool_result = run_tool(action)
                sandbox_commit = commit_sandbox(round_index, action)
                state_after = collect_state()

                write_json(round_dir / "request.json", {"messages": messages, "model_settings": model_settings})
                (round_dir / "response.txt").write_text(response_text, encoding="utf-8")
                write_json(round_dir / "response_raw.json", raw_response)
                write_json(round_dir / "action.json", action)
                write_json(round_dir / "tool_result.json", tool_result)
                write_json(round_dir / "state_before.json", state_before)
                write_json(round_dir / "state_after.json", state_after)
                write_json(round_dir / "sandbox_commit.json", sandbox_commit)
                write_json(live_summary_file, action)
                write_json(live_result_file, tool_result)
                write_json(live_before_file, state_before)
                write_json(live_after_file, state_after)
                live_response_file.write_text(response_text, encoding="utf-8")

                round_post = {
                    "type": "round_post",
                    "run_id": args.run_id,
                    "round": round_index,
                    "summary": action.get("summary"),
                    "done": action.get("done"),
                    "next": action.get("next"),
                    "thought": action.get("thought"),
                    "argv": action.get("argv"),
                    "timeout": action.get("timeout"),
                    "prompt_tokens": round_usage["prompt_tokens"],
                    "completion_tokens": round_usage["completion_tokens"],
                    "total_tokens": round_usage["total_tokens"],
                    "tool_ok": tool_result.get("ok"),
                    "returncode": tool_result.get("returncode"),
                    "stdout_tail": trim_text(tool_result.get("stdout"), limit=4000),
                    "stderr_tail": trim_text(tool_result.get("stderr"), limit=4000),
                    "sandbox_commit": extract_commit_hash(sandbox_commit),
                    "ts": iso_now(),
                }
                event = {
                    "event": "round_completed",
                    **round_post,
                }
                append_jsonl(events_file, event)
                append_jsonl(blog_file, round_post)
                write_json(live_round_file, round_post)
                completed_rounds = round_index
                elapsed_seconds = max(0, int(time.monotonic() - started_monotonic))
                update_status(
                    status_file,
                    {
                        **metadata,
                        "state": "running",
                        "completed_rounds": completed_rounds,
                        "pid": os.getpid(),
                        "last_round": round_index,
                        "last_done": action.get("done"),
                        "last_next": action.get("next"),
                        "last_thought": action.get("thought"),
                        "last_summary": action.get("summary"),
                        "last_argv": action.get("argv"),
                        "last_returncode": tool_result.get("returncode"),
                        "token_usage_prompt": token_usage["prompt_tokens"],
                        "token_usage_completion": token_usage["completion_tokens"],
                        "token_usage_total": token_usage["total_tokens"],
                        "elapsed_seconds": elapsed_seconds,
                        "updated_at": iso_now(),
                    },
                )
                git_commit(run_dir, f"round {round_index}")
                print(json.dumps(round_post, ensure_ascii=False), flush=True)
            except Exception as exc:
                if isinstance(exc, InvalidModelResponseError):
                    invalid_response_attempts = exc.attempts
                    for invalid_attempt in invalid_response_attempts:
                        if isinstance(invalid_attempt, dict):
                            persist_invalid_response_attempt(round_dir, events_file, round_index=round_index, attempt_payload=invalid_attempt)
                    if invalid_response_attempts:
                        last_invalid = invalid_response_attempts[-1]
                        live_response_file.write_text(str(last_invalid.get("response_text") or ""), encoding="utf-8")
                        round_usage = invalid_response_attempts[-1].get("usage") if isinstance(invalid_response_attempts[-1].get("usage"), dict) else round_usage
                        accumulated_invalid_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                        for invalid_attempt in invalid_response_attempts:
                            usage = invalid_attempt.get("usage") if isinstance(invalid_attempt.get("usage"), dict) else {}
                            accumulated_invalid_usage = add_token_usage_counts(accumulated_invalid_usage, usage)  # type: ignore[arg-type]
                        token_usage = add_token_usage_counts(token_usage, accumulated_invalid_usage)
                error_payload = {"round": round_index, "error": str(exc)}
                write_json(round_dir / "error.json", error_payload)
                append_jsonl(events_file, {"event": "round_failed", **error_payload, "ts": iso_now()})
                update_status(
                    status_file,
                    {
                        **metadata,
                        "state": "failed",
                        "completed_rounds": completed_rounds,
                        "failed_round": round_index,
                        "error": str(exc),
                        "pid": os.getpid(),
                        "token_usage_prompt": token_usage["prompt_tokens"],
                        "token_usage_completion": token_usage["completion_tokens"],
                        "token_usage_total": token_usage["total_tokens"],
                        "elapsed_seconds": max(0, int(time.monotonic() - started_monotonic)),
                        "updated_at": iso_now(),
                    },
                )
                git_commit(run_dir, f"round {round_index} failed")
                raise

            stop_reason = stop_reason_for_limits(
                elapsed_seconds=elapsed_seconds,
                token_usage=token_usage,
                max_runtime_seconds=max_runtime_seconds,
                max_total_tokens=max_total_tokens,
            )
            if stop_reason:
                append_jsonl(
                    events_file,
                    {
                        "event": "run_budget_reached",
                        "round": completed_rounds,
                        "stop_reason": stop_reason,
                        "elapsed_seconds": elapsed_seconds,
                        "token_usage_total": token_usage["total_tokens"],
                        "ts": iso_now(),
                    },
                )
                break

            round_index += 1
            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)
    except KeyboardInterrupt:
        append_jsonl(events_file, {"event": "keyboard_interrupt", "ts": time.time()})
        update_status(
            status_file,
            {
                **metadata,
                "state": "interrupted",
                "completed_rounds": completed_rounds,
                "pid": os.getpid(),
                "token_usage_prompt": token_usage["prompt_tokens"],
                "token_usage_completion": token_usage["completion_tokens"],
                "token_usage_total": token_usage["total_tokens"],
                "elapsed_seconds": max(0, int(time.monotonic() - started_monotonic)),
                "updated_at": iso_now(),
            },
        )
        git_commit(run_dir, "run interrupted")
        raise

    final_state = "stopped" if (run_dir / "STOP").exists() else "completed"
    update_status(
        status_file,
        {
            **metadata,
            "state": final_state,
            "completed_rounds": completed_rounds,
            "pid": os.getpid(),
            "token_usage_prompt": token_usage["prompt_tokens"],
            "token_usage_completion": token_usage["completion_tokens"],
            "token_usage_total": token_usage["total_tokens"],
            "elapsed_seconds": max(0, int(time.monotonic() - started_monotonic)),
            "stop_reason": stop_reason,
            "updated_at": iso_now(),
        },
    )
    append_jsonl(
        events_file,
        {
            "event": "run_finished",
            "state": final_state,
            "completed_rounds": completed_rounds,
            "stop_reason": stop_reason,
            "token_usage_total": token_usage["total_tokens"],
            "ts": iso_now(),
        },
    )
    git_commit(run_dir, f"run {final_state}")


if __name__ == "__main__":
    main()
