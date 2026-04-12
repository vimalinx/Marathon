#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable

import container.agent_loop as agent_loop
import host.host_nightly as host_nightly
import host.ingest_api as ingest_api
import host.model_env as model_env

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_HOST_RUNS_ROOT = PROJECT_ROOT / "host-runs"
DEFAULT_PROMPT_FILE = PROJECT_ROOT / "prompts" / "minimal_system.txt"
DEFAULT_TOOL_FILE = PROJECT_ROOT / "container" / "agent_tools.py"

model_env.load_model_env_defaults()


RoundExecutor = Callable[..., dict[str, object]]


def now_timestamp() -> datetime:
    return datetime.now().astimezone()


@contextmanager
def runtime_env(*, repo_path: Path, run_dir: Path, prompt_file: Path, tool_file: Path):
    keys = {
        "MARATHON_SANDBOX": str(repo_path),
        "MARATHON_LOG_ROOT": str(run_dir.parent),
        "MARATHON_PROMPT_FILE": str(prompt_file),
        "MARATHON_TOOL_FILE": str(tool_file),
    }
    previous = {key: os.environ.get(key) for key in keys}
    os.environ.update(keys)
    try:
        yield
    finally:
        for key, old_value in previous.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def update_status(run_dir: Path, payload: dict[str, object]) -> None:
    ingest_api.write_run_payload(
        {"run_id": run_dir.name, "status": payload},
        runs_dir=run_dir.parent,
    )


def write_round_artifacts(
    *,
    run_dir: Path,
    round_index: int,
    round_result: dict[str, object],
    committed: bool,
) -> None:
    action = round_result.get("action", {})
    tool_result = round_result.get("tool_result", {})
    state_before = round_result.get("state_before", {})
    state_after = round_result.get("state_after", {})
    response_text = str(round_result.get("response_text", ""))

    ingest_api.append_round_posts_payload(
        {
            "run_id": run_dir.name,
            "posts": [
                {
                    "round": round_index,
                    "summary": round_result.get("summary"),
                    "done": action.get("done") or action.get("summary"),
                    "next": action.get("next"),
                    "thought": action.get("thought"),
                    "argv": action.get("argv"),
                    "timeout": action.get("timeout"),
                    "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                }
            ],
        },
        runs_dir=run_dir.parent,
    )

    artifacts: list[dict[str, object]] = [
        {"round": round_index, "name": "action.json", "content": action},
        {"round": round_index, "name": "tool_result.json", "content": tool_result},
        {"round": round_index, "name": "state_before.json", "content": state_before},
        {"round": round_index, "name": "state_after.json", "content": state_after},
        {"round": round_index, "name": "commit.json", "content": {"committed": committed, "summary": round_result.get("summary", "")}},
        {"name": "latest_tool_result.json", "content": tool_result},
        {"name": "latest_state_before.json", "content": state_before},
        {"name": "latest_state_after.json", "content": state_after},
        {"name": "latest_response.txt", "content": response_text},
        {"round": round_index, "name": "response.txt", "content": response_text},
    ]

    request_payload = round_result.get("request")
    if request_payload is not None:
        artifacts.append({"round": round_index, "name": "request.json", "content": request_payload})

    raw_response = round_result.get("raw_response")
    if raw_response is not None:
        artifacts.append({"round": round_index, "name": "response_raw.json", "content": raw_response})

    ingest_api.write_artifacts_payload(
        {"run_id": run_dir.name, "artifacts": artifacts},
        runs_dir=run_dir.parent,
    )


def execute_agent_round(
    *,
    repo_path: Path,
    run_dir: Path,
    round_index: int,
    config: dict[str, object],
) -> dict[str, object]:
    api_key = str(config.get("api_key") or os.environ.get("MARATHON_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError("missing MARATHON_API_KEY")

    prompt_file = Path(str(config.get("prompt_file") or DEFAULT_PROMPT_FILE)).expanduser()
    tool_file = Path(str(config.get("tool_file") or DEFAULT_TOOL_FILE)).expanduser()
    task_prompt = str(config.get("task_prompt") or os.environ.get("MARATHON_TASK_PROMPT", agent_loop.DEFAULT_TASK_PROMPT))
    model = str(config.get("model") or os.environ.get("MARATHON_MODEL", agent_loop.DEFAULT_MODEL))
    base_url = str(config.get("base_url") or os.environ.get("MARATHON_BASE_URL", agent_loop.DEFAULT_BASE_URL))
    model_settings_json = str(config.get("model_settings_json") or os.environ.get("MARATHON_MODEL_SETTINGS_JSON", ""))
    system_prompt = prompt_file.read_text(encoding="utf-8")
    model_settings = agent_loop.load_model_settings(model_settings_json)

    with runtime_env(repo_path=repo_path, run_dir=run_dir, prompt_file=prompt_file, tool_file=tool_file):
        state_before = agent_loop.collect_state()
        latest_action = agent_loop.read_json(run_dir / "latest_action.json")
        latest_tool_result = agent_loop.read_json(run_dir / "latest_tool_result.json")
        feedback_bundle = agent_loop.build_feedback_bundle(
            round_index=round_index,
            state_before=state_before,
            latest_action=latest_action,
            latest_tool_result=latest_tool_result,
            recent_rounds=agent_loop.read_recent_events(run_dir / "events.jsonl"),
        )
        messages = agent_loop.build_messages(system_prompt, round_index, task_prompt, feedback_bundle)
        response_text, raw_response = agent_loop.call_model(base_url, api_key, model, messages, model_settings)
        action = agent_loop.extract_json_object(response_text)
        tool_result = agent_loop.run_tool(action)
        state_after = agent_loop.collect_state()

    return {
        "summary": str(action.get("summary", "")),
        "request": {"messages": messages, "model_settings": model_settings},
        "response_text": response_text,
        "raw_response": raw_response,
        "action": action,
        "tool_result": tool_result,
        "state_before": state_before,
        "state_after": state_after,
    }


def run_host_nightly(
    config: dict[str, object],
    *,
    host_runs_root: Path | None = None,
    run_id: str | None = None,
    now_fn: Callable[[], datetime] = now_timestamp,
    round_executor: RoundExecutor | None = None,
) -> dict[str, object]:
    repo_path = Path(str(config["repo_path"])).expanduser().resolve()
    slug = str(config.get("slug") or host_nightly.slugify_repo_path(repo_path))
    deadline = host_nightly.parse_deadline_time(str(config.get("deadline_time") or "08:00:00"))
    started_at = now_fn()
    branch_name = host_nightly.nightly_branch_name(started_at)
    run_id = run_id or started_at.strftime("nightly-%Y%m%d-%H%M%S")
    host_runs_root = (host_runs_root or DEFAULT_HOST_RUNS_ROOT).expanduser()
    run_dir = host_runs_root / slug / run_id
    host_nightly.ensure_dir(run_dir / "rounds")

    executor = round_executor or (
        lambda *, repo_path, run_dir, round_index: execute_agent_round(
            repo_path=repo_path,
            run_dir=run_dir,
            round_index=round_index,
            config=config,
        )
    )

    metadata: dict[str, object] = {
        "run_id": run_id,
        "slug": slug,
        "repo_path": str(repo_path),
        "branch_name": branch_name,
        "started_at": started_at.isoformat(),
        "deadline_time": deadline.isoformat(),
        "runtime": "host-nightly",
    }
    ingest_api.write_run_payload({"run_id": run_id, "run": metadata}, runs_dir=run_dir.parent)
    update_status(
        run_dir,
        {
            **metadata,
            "state": "starting",
            "completed_rounds": 0,
            "updated_at": started_at.isoformat(),
        },
    )
    ingest_api.append_events_payload(
        {
            "run_id": run_id,
            "events": [{"event": "run_started", "run_id": run_id, "repo_path": str(repo_path), "ts": time.time()}],
        },
        runs_dir=run_dir.parent,
    )

    default_branch: str | None = None
    checkpointed_dirty = False
    completed_rounds = 0
    state = "running"
    error_message = ""

    try:
        host_nightly.git_fetch_origin(repo_path)
        if host_nightly.repo_has_uncommitted_changes(repo_path):
            current_branch = host_nightly.current_branch_name(repo_path)
            if not current_branch:
                raise RuntimeError("cannot checkpoint dirty workspace from detached HEAD")
            host_nightly.checkpoint_dirty_workspace(repo_path)
            checkpointed_dirty = True
            start_point = "HEAD"
        else:
            default_branch = host_nightly.read_default_branch(repo_path)
            start_point = f"origin/{default_branch}"

        host_nightly.create_branch(repo_path, branch_name, start_point)
        metadata["default_branch"] = default_branch
        metadata["checkpointed_dirty"] = checkpointed_dirty
        ingest_api.write_run_payload({"run_id": run_id, "run": metadata}, runs_dir=run_dir.parent)

        if host_nightly.should_stop_for_deadline(started_at, deadline=deadline):
            state = "stopped_by_deadline"
        else:
            while True:
                round_index = completed_rounds + 1
                round_result = executor(repo_path=repo_path, run_dir=run_dir, round_index=round_index)
                summary = str(round_result.get("summary", "")).strip()
                committed = host_nightly.commit_all_changes(
                    repo_path,
                    host_nightly.format_round_commit_message(round_index, summary),
                )
                write_round_artifacts(
                    run_dir=run_dir,
                    round_index=round_index,
                    round_result=round_result,
                    committed=committed,
                )
                completed_rounds = round_index
                ingest_api.append_events_payload(
                    {
                        "run_id": run_id,
                        "events": [
                            {
                                "event": "round_completed",
                                "round": round_index,
                                "summary": summary,
                                "committed": committed,
                                "ts": time.time(),
                            }
                        ],
                    },
                    runs_dir=run_dir.parent,
                )
                update_status(
                    run_dir,
                    {
                        **metadata,
                        "state": "running",
                        "completed_rounds": completed_rounds,
                        "updated_at": now_fn().isoformat(),
                    },
                )
                if host_nightly.should_stop_for_deadline(now_fn(), deadline=deadline):
                    state = "stopped_by_deadline"
                    break
    except Exception as exc:
        state = "failed"
        error_message = str(exc)
        ingest_api.append_events_payload(
            {
                "run_id": run_id,
                "events": [{"event": "run_failed", "error": error_message, "ts": time.time()}],
            },
            runs_dir=run_dir.parent,
        )
        raise
    finally:
        final_status = {
            **metadata,
            "state": state,
            "completed_rounds": completed_rounds,
            "updated_at": now_fn().isoformat(),
        }
        if error_message:
            final_status["error"] = error_message
        update_status(run_dir, final_status)
        ingest_api.append_events_payload(
            {
                "run_id": run_id,
                "events": [
                    {
                        "event": "run_finished",
                        "state": state,
                        "completed_rounds": completed_rounds,
                        "ts": time.time(),
                    }
                ],
            },
            runs_dir=run_dir.parent,
        )

    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "state": state,
        "completed_rounds": completed_rounds,
        "branch_name": branch_name,
    }


def load_config(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("config must decode to an object")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one Marathon host-nightly session against a Git repo")
    parser.add_argument("--config", required=True, help="Path to a host project config JSON file")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--host-runs-root", default=str(DEFAULT_HOST_RUNS_ROOT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(Path(args.config).expanduser())
    try:
        result = run_host_nightly(
            config,
            host_runs_root=Path(args.host_runs_root).expanduser(),
            run_id=args.run_id or None,
        )
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
