#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import host.public_site as public_site

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_ROOT = PROJECT_ROOT / 'state'
DEFAULT_PAGES_SYNC_ROOT = DEFAULT_STATE_ROOT / 'github_pages_sync'
DEFAULT_PUBLISH_BRANCH = 'gh-pages'
DEFAULT_TIMER_CALENDAR = 'hourly'


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
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def load_config(config_path: Path) -> dict[str, Any]:
    payload = json.loads(config_path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'invalid GitHub Pages sync config: {config_path}')
    return payload


def slugify_repo_path(repo_path: Path) -> str:
    source = repo_path.name.strip() or repo_path.resolve().name.strip() or 'repo'
    slug = ''.join(ch.lower() if ch.isalnum() else '-' for ch in source)
    slug = '-'.join(part for part in slug.split('-') if part)
    return slug or 'repo'


def config_path_for(repo_path: Path, *, state_root: Path | None = None, slug: str | None = None) -> Path:
    state_root = state_root or DEFAULT_STATE_ROOT
    repo_slug = slug or slugify_repo_path(repo_path)
    return state_root / 'github_pages_sync' / f'{repo_slug}.json'


def write_config(
    repo_path: Path,
    *,
    state_root: Path | None = None,
    slug: str | None = None,
    publish_branch: str = DEFAULT_PUBLISH_BRANCH,
    timer_calendar: str = DEFAULT_TIMER_CALENDAR,
) -> dict[str, Any]:
    resolved_repo = repo_path.expanduser().resolve()
    state_root = state_root or DEFAULT_STATE_ROOT
    repo_slug = slug or slugify_repo_path(resolved_repo)
    config_path = config_path_for(resolved_repo, state_root=state_root, slug=repo_slug)
    existing = load_config(config_path) if config_path.exists() else {}
    deploy_root = state_root / 'github_pages_sync' / repo_slug
    config = dict(existing)
    config.update(
        {
            'slug': repo_slug,
            'repo_path': str(resolved_repo),
            'publish_branch': str(existing.get('publish_branch') or publish_branch),
            'timer_calendar': str(existing.get('timer_calendar') or timer_calendar),
            'deploy_clone_path': str(Path(existing.get('deploy_clone_path') or (deploy_root / 'deploy-clone')).resolve()),
            'staging_output_path': str(Path(existing.get('staging_output_path') or (deploy_root / 'staging-site')).resolve()),
            'config_path': str(config_path),
        }
    )
    write_json(config_path, config)
    return config


def systemd_unit_base_name(slug: str) -> str:
    return f'marathon-pages-sync-{slug}'


def escape_systemd_exec_arg(value: str) -> str:
    return value.replace('\\', '\\\\').replace(' ', '\\ ')


def render_systemd_service(config: dict[str, Any], *, root_dir: Path) -> str:
    slug = str(config['slug'])
    repo_path = escape_systemd_exec_arg(str(config['repo_path']))
    runner = escape_systemd_exec_arg(str((root_dir / 'scripts' / 'run_github_pages_sync_once.sh').resolve()))
    working_dir = str(root_dir.resolve())
    return (
        '[Unit]\n'
        f'Description=Marathon GitHub Pages sync for {slug}\n'
        'After=network-online.target\n'
        '\n'
        '[Service]\n'
        'Type=oneshot\n'
        f'WorkingDirectory={working_dir}\n'
        f'ExecStart={runner} {repo_path}\n'
    )


def render_systemd_timer(config: dict[str, Any]) -> str:
    slug = str(config['slug'])
    timer_calendar = str(config.get('timer_calendar') or DEFAULT_TIMER_CALENDAR).strip() or DEFAULT_TIMER_CALENDAR
    unit_name = f'{systemd_unit_base_name(slug)}.service'
    return (
        '[Unit]\n'
        f'Description=Hourly Marathon GitHub Pages sync timer for {slug}\n'
        '\n'
        '[Timer]\n'
        f'OnCalendar={timer_calendar}\n'
        'Persistent=true\n'
        f'Unit={unit_name}\n'
        '\n'
        '[Install]\n'
        'WantedBy=timers.target\n'
    )


def pages_commit_message(now: datetime | None = None) -> str:
    current = now or datetime.now()
    return f'chore(pages): update snapshot {current.strftime("%Y-%m-%d %H:%M:%S")}'


def git_origin_url(repo_path: Path) -> str:
    completed = run(['git', '-C', str(repo_path), 'remote', 'get-url', 'origin'], check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            'git origin remote is missing; add a GitHub remote before enabling hourly Pages sync'
        )
    value = completed.stdout.strip()
    if not value:
        raise RuntimeError(
            'git origin remote is empty; point origin at the GitHub repository before enabling hourly Pages sync'
        )
    return value


def remote_branch_exists(repo_path: Path, branch: str) -> bool:
    completed = run(['git', 'ls-remote', '--heads', 'origin', branch], cwd=repo_path, check=False)
    return completed.returncode == 0 and bool(completed.stdout.strip())


def local_branch_exists(repo_path: Path, branch: str) -> bool:
    completed = run(['git', 'show-ref', '--verify', f'refs/heads/{branch}'], cwd=repo_path, check=False)
    return completed.returncode == 0


def configure_deploy_clone(deploy_clone_path: Path, *, source_repo: Path, origin_url: str) -> None:
    if (deploy_clone_path / '.git').exists():
        run(['git', 'remote', 'set-url', 'origin', origin_url], cwd=deploy_clone_path)
        return
    if deploy_clone_path.exists():
        shutil.rmtree(deploy_clone_path)
    ensure_dir(deploy_clone_path.parent)
    run(['git', 'clone', str(source_repo), str(deploy_clone_path)])
    run(['git', 'remote', 'set-url', 'origin', origin_url], cwd=deploy_clone_path)
    run(['git', 'config', 'user.name', 'Marathon Pages Sync'], cwd=deploy_clone_path)
    run(['git', 'config', 'user.email', 'marathon-pages@local'], cwd=deploy_clone_path)


def checkout_publish_branch(deploy_clone_path: Path, publish_branch: str) -> None:
    run(['git', 'fetch', 'origin'], cwd=deploy_clone_path, check=False)
    if remote_branch_exists(deploy_clone_path, publish_branch):
        if local_branch_exists(deploy_clone_path, publish_branch):
            run(['git', 'checkout', publish_branch], cwd=deploy_clone_path)
        else:
            run(['git', 'checkout', '-B', publish_branch, f'origin/{publish_branch}'], cwd=deploy_clone_path)
        run(['git', 'reset', '--hard', f'origin/{publish_branch}'], cwd=deploy_clone_path)
        return
    if local_branch_exists(deploy_clone_path, publish_branch):
        run(['git', 'checkout', publish_branch], cwd=deploy_clone_path)
        return
    run(['git', 'checkout', '--orphan', publish_branch], cwd=deploy_clone_path)


def clear_checkout_dir(deploy_clone_path: Path) -> None:
    for item in deploy_clone_path.iterdir():
        if item.name == '.git':
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def copy_tree_contents(source_dir: Path, target_dir: Path) -> None:
    for item in source_dir.iterdir():
        destination = target_dir / item.name
        if item.is_dir():
            shutil.copytree(item, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(item, destination)


def has_changes(repo_path: Path) -> bool:
    completed = run(['git', 'status', '--porcelain'], cwd=repo_path, check=False)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or 'failed to read git status')
    return bool(completed.stdout.strip())


def sync_once(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    repo_path = Path(str(config['repo_path'])).resolve()
    if repo_path != PROJECT_ROOT:
        raise RuntimeError('GitHub Pages sync currently supports the Marathon repo root only')
    publish_branch = str(config.get('publish_branch') or DEFAULT_PUBLISH_BRANCH)
    deploy_clone_path = Path(str(config['deploy_clone_path'])).resolve()
    staging_output_path = Path(str(config['staging_output_path'])).resolve()
    origin_url = git_origin_url(repo_path)

    configure_deploy_clone(deploy_clone_path, source_repo=repo_path, origin_url=origin_url)
    checkout_publish_branch(deploy_clone_path, publish_branch)
    clear_checkout_dir(deploy_clone_path)

    export_result = public_site.export_github_pages(staging_output_path)
    copy_tree_contents(staging_output_path, deploy_clone_path)

    run(['git', 'add', '-A'], cwd=deploy_clone_path)
    if not has_changes(deploy_clone_path):
        return {
            'ok': True,
            'changed': False,
            'publish_branch': publish_branch,
            'deploy_clone_path': str(deploy_clone_path),
            'export': export_result,
        }

    message = pages_commit_message()
    run(['git', 'commit', '-m', message], cwd=deploy_clone_path)
    push = run(['git', 'push', '-u', 'origin', publish_branch], cwd=deploy_clone_path)
    return {
        'ok': True,
        'changed': True,
        'publish_branch': publish_branch,
        'deploy_clone_path': str(deploy_clone_path),
        'commit_message': message,
        'push_stdout': push.stdout,
        'push_stderr': push.stderr,
        'export': export_result,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Sync the Marathon GitHub Pages snapshot to origin')
    parser.add_argument('--config', required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = sync_once(Path(args.config).resolve())
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
