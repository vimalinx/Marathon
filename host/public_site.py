#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT_DIR / 'runs'
CONTAINER_STATE_DIR = ROOT_DIR / 'state' / 'containers'
CONTAINER_BLOG_DIR = ROOT_DIR / 'state' / 'container_blogs'
AGENT_ACCOUNT_DIR = ROOT_DIR / 'state' / 'agent_accounts'
STATIC_SITE_DIR = ROOT_DIR / 'host' / 'static' / 'site'
FAVICON_FILE = ROOT_DIR / 'host' / 'static' / 'favicon.svg'


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return []
    payloads: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def read_text(path: Path, *, max_chars: int = 2000) -> str | None:
    if not path.exists():
        return None
    try:
        value = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None
    if len(value) <= max_chars:
        return value
    return value[-max_chars:]


def compact_text_preview(text: str | None, *, limit: int = 280) -> str | None:
    if not text:
        return None
    compact = ' '.join(str(text).split())
    if not compact:
        return None
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + '…'


def first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def sanitize_public_account(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    result = dict(payload)
    result.pop('auth_token', None)
    return result


def normalize_blog_post(payload: dict[str, Any] | None, *, container: str | None = None, run_id: str | None = None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    event = str(payload.get('event') or payload.get('type') or '').strip()
    has_round_shape = payload.get('round') is not None and any(
        key in payload for key in ('done', 'next', 'thought', 'summary', 'error')
    )
    if event not in {'round_completed', 'round_post'} and not has_round_shape:
        return None
    return {
        'type': 'round_post',
        'container': payload.get('container') or container,
        'run_id': payload.get('run_id') or run_id,
        'round': payload.get('round'),
        'summary': payload.get('summary'),
        'done': payload.get('done') or payload.get('summary'),
        'next': payload.get('next'),
        'thought': payload.get('thought'),
        'ts': payload.get('ts'),
        'stdout_tail': payload.get('stdout_tail'),
        'stderr_tail': payload.get('stderr_tail'),
    }


def normalize_agent_post(payload: dict[str, Any] | None, *, handle: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    if payload.get('round') is None and not any(key in payload for key in ('done', 'next', 'thought', 'summary')):
        return None
    return {
        'agent_handle': handle,
        'post_id': payload.get('post_id'),
        'container': payload.get('container'),
        'run_id': payload.get('run_id'),
        'round': payload.get('round'),
        'summary': payload.get('summary'),
        'done': payload.get('done') or payload.get('summary'),
        'next': payload.get('next'),
        'thought': payload.get('thought'),
        'instance_id': payload.get('instance_id'),
        'ts': payload.get('ts'),
    }


def read_run_posts(run_id: str, *, container: str | None = None) -> list[dict[str, Any]]:
    run_dir = RUNS_DIR / run_id
    direct = [
        normalized
        for normalized in (
            normalize_blog_post(payload, container=container, run_id=run_id)
            for payload in read_jsonl(run_dir / 'blog.jsonl')
        )
        if normalized is not None
    ]
    if direct:
        return direct
    if container:
        archive_path = CONTAINER_BLOG_DIR / f'{container}.jsonl'
        return [
            normalized
            for normalized in (
                normalize_blog_post(payload, container=container, run_id=run_id)
                for payload in read_jsonl(archive_path)
                if str(payload.get('run_id') or '') == run_id
            )
            if normalized is not None
        ]
    return []


def read_agent_account(handle: str) -> dict[str, Any] | None:
    return sanitize_public_account(read_json(AGENT_ACCOUNT_DIR / f'{handle}.json'))


def read_agent_posts(handle: str) -> list[dict[str, Any]]:
    posts = [
        normalized
        for normalized in (
            normalize_agent_post(payload, handle=handle)
            for payload in read_jsonl(AGENT_ACCOUNT_DIR / f'{handle}.posts.jsonl')
        )
        if normalized is not None
    ]
    return list(reversed(posts))


def list_public_accounts() -> list[dict[str, Any]]:
    ensure_dir(AGENT_ACCOUNT_DIR)
    items: list[dict[str, Any]] = []
    for path in sorted(AGENT_ACCOUNT_DIR.glob('*.json')):
        if path.name.endswith('.meta.json'):
            continue
        account = sanitize_public_account(read_json(path))
        if not isinstance(account, dict):
            continue
        handle = str(account.get('agent_handle') or '').strip()
        if not handle:
            continue
        posts = read_agent_posts(handle)
        latest_post = posts[0] if posts else None
        items.append(
            {
                **account,
                'latest_post': latest_post,
                'latest_preview': compact_text_preview(
                    first_text(
                        (latest_post or {}).get('done'),
                        (latest_post or {}).get('next'),
                        (latest_post or {}).get('thought'),
                        (latest_post or {}).get('summary'),
                    ),
                    limit=220,
                ),
                'post_count': len(posts),
            }
        )
    items.sort(key=lambda item: str(item.get('updated_at') or item.get('created_at') or ''), reverse=True)
    return items


def summarize_public_run(run_dir: Path) -> dict[str, Any]:
    host_run = read_json(run_dir / 'host_run.json') or {}
    status = read_json(run_dir / 'status.json') or {}
    ui_launch = read_json(run_dir / 'ui_launch.json') or {}
    latest_action = read_json(run_dir / 'latest_action.json') or {}
    container = first_text(host_run.get('container'), ui_launch.get('container'))
    agent_handle = first_text(ui_launch.get('agent_handle'))
    if not agent_handle and container:
        container_meta = read_json(CONTAINER_STATE_DIR / f'{container}.json') or {}
        agent_handle = first_text(container_meta.get('agent_handle'))

    posts = read_run_posts(run_dir.name, container=container)
    latest_post = posts[-1] if posts else None
    latest_response_text = read_text(run_dir / 'latest_response.txt', max_chars=1600)
    preview = compact_text_preview(
        first_text(
            (latest_post or {}).get('done'),
            (latest_post or {}).get('summary'),
            latest_action.get('done'),
            latest_action.get('summary'),
            status.get('last_done'),
            status.get('last_summary'),
            latest_response_text,
        ),
        limit=320,
    )
    summary = compact_text_preview(
        first_text(
            status.get('last_summary'),
            latest_action.get('summary'),
            status.get('last_done'),
            latest_action.get('done'),
            (latest_post or {}).get('done'),
            latest_response_text,
        ),
        limit=560,
    )
    state = str(status.get('state') or 'unknown').lower()
    updated_at = first_text(status.get('updated_at'), (latest_post or {}).get('ts'), ui_launch.get('started_at'))
    round_count = len(posts)
    completed_rounds = status.get('completed_rounds')
    if isinstance(completed_rounds, int) and completed_rounds > round_count:
        round_count = completed_rounds

    account = read_agent_account(agent_handle) if agent_handle else None
    title_bits = [bit for bit in [account.get('display_name') if account else None, container, run_dir.name] if bit]
    return {
        'public_run_id': run_dir.name,
        'run_id': run_dir.name,
        'title': ' · '.join(title_bits) if title_bits else run_dir.name,
        'container': container,
        'agent_handle': agent_handle,
        'agent_display_name': account.get('display_name') if account else None,
        'state': state,
        'is_live': state == 'running',
        'mode': first_text(host_run.get('mode'), ui_launch.get('mode')) or 'task',
        'updated_at': updated_at,
        'round_count': round_count,
        'preview': preview,
        'summary': summary,
    }


def list_public_runs() -> list[dict[str, Any]]:
    ensure_dir(RUNS_DIR)
    runs = [summarize_public_run(path) for path in RUNS_DIR.iterdir() if path.is_dir()]
    runs.sort(key=lambda item: str(item.get('updated_at') or ''), reverse=True)
    return runs


def home_payload() -> dict[str, Any]:
    runs = list_public_runs()
    accounts = list_public_accounts()
    live_runs = [run for run in runs if run.get('is_live')]
    completed_runs = [run for run in runs if not run.get('is_live')]
    featured_runs = completed_runs[:4] if completed_runs else runs[:4]
    return {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'featured_runs': featured_runs,
        'latest_completed_runs': completed_runs[:24],
        'live_runs': live_runs[:12],
        'accounts': accounts[:24],
        'run_count': len(runs),
        'account_count': len(accounts),
    }


def run_payload(run_id: str) -> dict[str, Any]:
    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f'run not found: {run_id}')
    summary = summarize_public_run(run_dir)
    posts = read_run_posts(run_id, container=summary.get('container'))
    timeline = []
    for post in posts:
        timeline.append(
            {
                'round': post.get('round'),
                'done': compact_text_preview(post.get('done'), limit=700),
                'next': compact_text_preview(post.get('next'), limit=700),
                'thought': compact_text_preview(post.get('thought'), limit=700),
                'summary': compact_text_preview(post.get('summary'), limit=700),
                'ts': post.get('ts'),
            }
        )
    return {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'summary': summary,
        'readable': {
            'title': summary.get('title'),
            'summary': summary.get('summary') or summary.get('preview') or '还没有可公开的摘要。',
            'status': summary.get('state'),
            'updated_at': summary.get('updated_at'),
        },
        'timeline': timeline,
    }


def agent_payload(handle: str) -> dict[str, Any]:
    account = read_agent_account(handle)
    if not isinstance(account, dict):
        raise FileNotFoundError(f'agent account not found: {handle}')
    posts = read_agent_posts(handle)
    runs = [run for run in list_public_runs() if run.get('agent_handle') == handle]
    return {
        'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'account': account,
        'recent_posts': posts[:24],
        'completed_runs': [run for run in runs if not run.get('is_live')][:24],
        'live_runs': [run for run in runs if run.get('is_live')][:12],
    }


def run_asset_name(run_id: str) -> str:
    return f'{quote(run_id, safe="")}.json'


def agent_asset_name(handle: str) -> str:
    return f'{quote(handle, safe="")}.json'


def export_github_pages(output_dir: Path) -> dict[str, Any]:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    ensure_dir(output_dir)
    if not STATIC_SITE_DIR.exists():
        raise FileNotFoundError(f'missing static site assets: {STATIC_SITE_DIR}')
    shutil.copytree(STATIC_SITE_DIR, output_dir, dirs_exist_ok=True)
    if FAVICON_FILE.exists():
        shutil.copy2(FAVICON_FILE, output_dir / 'favicon.svg')
    (output_dir / '.nojekyll').write_text('\n', encoding='utf-8')

    home = home_payload()
    write_json(output_dir / 'data' / 'site-home.json', home)
    write_json(
        output_dir / 'data' / 'live.json',
        {
            'generated_at': home['generated_at'],
            'live_runs': home['live_runs'],
        },
    )

    all_runs = list_public_runs()
    for run in all_runs:
        write_json(output_dir / 'data' / 'runs' / run_asset_name(str(run['public_run_id'])), run_payload(str(run['public_run_id'])))

    accounts = list_public_accounts()
    for account in accounts:
        handle = str(account.get('agent_handle') or '').strip()
        if not handle:
            continue
        write_json(output_dir / 'data' / 'agents' / agent_asset_name(handle), agent_payload(handle))

    return {
        'ok': True,
        'output_dir': str(output_dir),
        'generated_at': home['generated_at'],
        'run_count': len(all_runs),
        'account_count': len(accounts),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Export Marathon public snapshot for GitHub Pages')
    parser.add_argument('--output-dir', default=str(ROOT_DIR / 'build' / 'github-pages'))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = export_github_pages(Path(args.output_dir))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
