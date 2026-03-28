#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, time
from pathlib import Path

DEFAULT_DEADLINE = time(hour=8, minute=0, second=0)
DEFAULT_START_TIME = time(hour=0, minute=30, second=0)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_ROOT = PROJECT_ROOT / "state"
DEFAULT_HOST_PROJECTS_ROOT = DEFAULT_STATE_ROOT / "host_projects"


def run(argv: list[str], *, cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=check,
    )


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: object) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: object) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def slugify_repo_path(repo_path: Path) -> str:
    source = repo_path.name.strip() or repo_path.resolve().name.strip() or "repo"
    slug = re.sub(r"[^a-z0-9]+", "-", source.lower()).strip("-")
    return slug or "repo"


def nightly_branch_name(now: datetime) -> str:
    return f"marathon/nightly-{now.strftime('%Y%m%d-%H%M%S')}"


def dirty_checkpoint_message() -> str:
    return "chore(marathon): checkpoint dirty workspace before nightly run"


def should_stop_for_deadline(now: datetime, *, deadline: time = DEFAULT_DEADLINE) -> bool:
    return now.time() >= deadline


def parse_deadline_time(raw_value: str | None) -> time:
    value = (raw_value or "").strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"invalid deadline time: {raw_value!r}")


def host_project_config_path(repo_path: Path, *, state_root: Path | None = None, slug: str | None = None) -> Path:
    state_root = state_root or DEFAULT_STATE_ROOT
    project_slug = slug or slugify_repo_path(repo_path)
    return state_root / "host_projects" / f"{project_slug}.json"


def load_host_project_config(config_path: Path) -> dict[str, object]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid host project config: {config_path}")
    return payload


def write_host_project_config(
    repo_path: Path,
    *,
    state_root: Path | None = None,
    slug: str | None = None,
    start_time: str = "00:30:00",
    deadline_time: str = "08:00:00",
) -> dict[str, object]:
    resolved_repo = repo_path.expanduser().resolve()
    project_slug = slug or slugify_repo_path(resolved_repo)
    config_path = host_project_config_path(resolved_repo, state_root=state_root, slug=project_slug)
    existing = load_host_project_config(config_path) if config_path.exists() else {}
    config = dict(existing)
    config.update(
        {
            "slug": project_slug,
            "repo_path": str(resolved_repo),
            "start_time": parse_deadline_time(str(existing.get("start_time") or start_time)).strftime("%H:%M:%S"),
            "deadline_time": parse_deadline_time(str(existing.get("deadline_time") or deadline_time)).strftime("%H:%M:%S"),
            "config_path": str(config_path),
        }
    )
    write_json(config_path, config)
    return config


def systemd_unit_base_name(slug: str) -> str:
    return f"marathon-nightly-{slug}"


def escape_systemd_exec_arg(value: str) -> str:
    return value.replace("\\", "\\\\").replace(" ", "\\ ")


def render_systemd_service(config: dict[str, object], *, root_dir: Path) -> str:
    slug = str(config["slug"])
    repo_path = escape_systemd_exec_arg(str(config["repo_path"]))
    runner = escape_systemd_exec_arg(str((root_dir / "scripts" / "run_host_nightly_once.sh").resolve()))
    working_dir = str(root_dir.resolve())
    return (
        "[Unit]\n"
        f"Description=Marathon nightly runner for {slug}\n"
        "After=network-online.target\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"WorkingDirectory={working_dir}\n"
        f"ExecStart={runner} {repo_path}\n"
    )


def render_systemd_timer(config: dict[str, object]) -> str:
    slug = str(config["slug"])
    start_time = parse_deadline_time(str(config.get("start_time") or DEFAULT_START_TIME.strftime("%H:%M:%S"))).strftime("%H:%M:%S")
    unit_name = f"{systemd_unit_base_name(slug)}.service"
    return (
        "[Unit]\n"
        f"Description=Daily Marathon nightly timer for {slug}\n"
        "\n"
        "[Timer]\n"
        f"OnCalendar=*-*-* {start_time}\n"
        "Persistent=true\n"
        f"Unit={unit_name}\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )


def current_branch_name(repo_path: Path) -> str:
    completed = run(["git", "-C", str(repo_path), "branch", "--show-current"])
    return completed.stdout.strip()


def read_default_branch(repo_path: Path) -> str:
    completed = run(
        ["git", "-C", str(repo_path), "symbolic-ref", "--short", "refs/remotes/origin/HEAD"]
    )
    branch_ref = completed.stdout.strip()
    if not branch_ref.startswith("origin/"):
        raise RuntimeError(f"unexpected origin HEAD ref: {branch_ref}")
    return branch_ref.removeprefix("origin/")


def repo_has_uncommitted_changes(repo_path: Path) -> bool:
    completed = run(["git", "-C", str(repo_path), "status", "--porcelain"], check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or "failed to read git status")
    return bool(completed.stdout.strip())


def git_fetch_origin(repo_path: Path) -> None:
    run(["git", "-C", str(repo_path), "fetch", "origin"])


def checkpoint_dirty_workspace(repo_path: Path) -> None:
    run(["git", "-C", str(repo_path), "add", "-A"])
    run(["git", "-C", str(repo_path), "commit", "-m", dirty_checkpoint_message()])


def create_branch(repo_path: Path, branch_name: str, start_point: str) -> None:
    run(["git", "-C", str(repo_path), "checkout", "-b", branch_name, start_point])


def format_round_commit_message(round_index: int, summary: str) -> str:
    safe_summary = re.sub(r"\s+", " ", summary).strip()[:100] or "no-summary"
    return f"marathon(round {round_index:03d}): {safe_summary}"


def commit_all_changes(repo_path: Path, message: str) -> bool:
    if not repo_has_uncommitted_changes(repo_path):
        return False
    run(["git", "-C", str(repo_path), "add", "-A"])
    run(["git", "-C", str(repo_path), "commit", "-m", message])
    return True
