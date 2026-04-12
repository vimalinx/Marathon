#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import mimetypes
import os
import re
import secrets
import shlex
import signal
import subprocess
import sys
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import urllib.error
import urllib.request

import host.lxc_network as lxc_network
import host.model_env as model_env
import host.ingest_api as ingest_api
import host.run_index as run_index

ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / 'host' / 'static'
RUNS_DIR = ROOT_DIR / 'runs'
PROMPT_FILE = ROOT_DIR / 'prompts' / 'minimal_system.txt'
MODEL_PROFILES_FILE = ROOT_DIR / 'state' / 'model_profiles.json'
CONTAINER_STATE_DIR = ROOT_DIR / 'state' / 'containers'
CONTAINER_BLOG_DIR = ROOT_DIR / 'state' / 'container_blogs'
AGENT_ACCOUNT_DIR = ROOT_DIR / 'state' / 'agent_accounts'
CONTAINER_SETTINGS_BACKUP_DIR = ROOT_DIR / 'state' / 'container_settings_backups'

model_env.load_model_env_defaults()

DEFAULT_BASE_URL = model_env.default_base_url()
DEFAULT_MODEL = model_env.default_model()
DEFAULT_TASK_PROMPT = (
    'Inspect the sandbox, identify the most useful next step, '
    'and improve the workspace incrementally while preserving an observable state.'
)
FREEPLAY_TASK_PROMPT = (
    'You are alone in a fresh sandbox. Explore the environment, inspect the tools and prompt '
    'you were given, decide your own direction, and keep playing inside the sandbox. Prefer '
    'self-directed experimentation, preserve observability, and keep making concrete changes or '
    'observations instead of stopping for approval.'
)
NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$')
MAX_TEXT_PREVIEW = 16000
STATIC_ROUTE_ALIASES = {
    '/index.html': 'index.html',
    '/favicon.ico': 'favicon.svg',
    '/sandboxes': 'sandboxes.html',
    '/sandboxes/': 'sandboxes.html',
    '/sandboxes.html': 'sandboxes.html',
    '/container': 'container.html',
    '/container/': 'container.html',
    '/container.html': 'container.html',
    '/new': 'new.html',
    '/new/': 'new.html',
    '/new.html': 'new.html',
    '/agents': 'agents.html',
    '/agents/': 'agents.html',
    '/agents.html': 'agents.html',
    '/agent': 'agent.html',
    '/agent/': 'agent.html',
    '/agent.html': 'agent.html',
    '/design-lab': 'design-lab/index.html',
    '/design-lab/': 'design-lab/index.html',
}


def run_host_command(argv: list[str], *, input_text: str | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        input=input_text,
        capture_output=True,
        text=True,
        check=check,
        cwd=str(ROOT_DIR),
    )


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + '\n')


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def read_text(path: Path, *, max_chars: int = MAX_TEXT_PREVIEW) -> str | None:
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None
    if len(content) <= max_chars:
        return content
    return content[-max_chars:]


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


def first_non_null(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def api_key_fingerprint(value: str | None) -> str | None:
    token = str(value or '').strip()
    if not token:
        return None
    return hashlib.sha256(token.encode('utf-8')).hexdigest()[:16]


def preview_from_payload(payload: dict[str, Any] | None, *, limit: int = 280) -> str | None:
    if not isinstance(payload, dict):
        return None
    return compact_text_preview(
        first_text(
            payload.get('done'),
            payload.get('next'),
            payload.get('thought'),
            payload.get('summary'),
            payload.get('error'),
        ),
        limit=limit,
    )


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
        'argv': payload.get('argv'),
        'timeout': payload.get('timeout'),
        'tool_ok': payload.get('tool_ok'),
        'returncode': payload.get('returncode'),
        'stdout_tail': payload.get('stdout_tail'),
        'stderr_tail': payload.get('stderr_tail'),
        'sandbox_commit': payload.get('sandbox_commit'),
        'ts': payload.get('ts'),
    }


def container_blog_path(name: str) -> Path:
    return CONTAINER_BLOG_DIR / f'{name}.jsonl'


def container_blog_meta_path(name: str) -> Path:
    return CONTAINER_BLOG_DIR / f'{name}.meta.json'


def read_blog_posts(path: Path, *, limit: int | None = None, container: str | None = None, run_id: str | None = None) -> list[dict[str, Any]]:
    posts = [
        normalized
        for normalized in (
            normalize_blog_post(payload, container=container, run_id=run_id)
            for payload in read_jsonl(path)
        )
        if normalized is not None
    ]
    if limit is not None:
        posts = posts[-limit:]
    return list(reversed(posts))


def read_container_blog_meta(name: str) -> dict[str, Any]:
    return read_json(container_blog_meta_path(name)) or {}


def read_container_blog_posts(name: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    return read_blog_posts(container_blog_path(name), limit=limit, container=name)


def container_blog_payload(name: str, *, limit: int | None = None) -> dict[str, Any]:
    require_name(name, field='container name')
    try:
        return run_index.get_container_blog_payload(
            name,
            limit=limit,
            runs_dir=RUNS_DIR,
            container_blog_dir=CONTAINER_BLOG_DIR,
            agent_account_dir=AGENT_ACCOUNT_DIR,
        )
    except Exception:
        posts = read_container_blog_posts(name, limit=limit)
        meta = read_container_blog_meta(name)
        return {
            'container': name,
            'blog_posts': posts,
            'latest_blog_post': posts[0] if posts else None,
            'blog_meta': {
                **meta,
                'container': name,
                'post_count': meta.get('post_count', len(posts)),
                'updated_at': meta.get('updated_at') or (posts[0].get('ts') if posts else None),
            },
        }


def container_state_path(name: str) -> Path:
    return CONTAINER_STATE_DIR / f'{name}.json'


def write_container_state_meta(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    require_name(name, field='container name')
    ensure_dir(CONTAINER_STATE_DIR)
    normalized = dict(payload or {})
    normalized['container_name'] = str(normalized.get('container_name') or name).strip() or name
    write_json(container_state_path(name), normalized)
    return normalized


def agent_account_path(handle: str) -> Path:
    return AGENT_ACCOUNT_DIR / f'{handle}.json'


def agent_account_posts_path(handle: str) -> Path:
    return AGENT_ACCOUNT_DIR / f'{handle}.posts.jsonl'


def read_agent_account(handle: str) -> dict[str, Any] | None:
    require_name(handle, field='agent handle')
    payload = read_json(agent_account_path(handle))
    if not isinstance(payload, dict):
        return None
    if payload.get('agent_handle') != handle:
        payload['agent_handle'] = handle
    return payload


def public_agent_account(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {key: value for key, value in payload.items() if key != 'auth_token'}


def generate_agent_auth_token() -> str:
    return secrets.token_urlsafe(24)


def generate_agent_instance_id(handle: str) -> str:
    base = handle[:55]
    return require_name(f'{base}-{secrets.token_hex(4)}', field='instance id')


def bearer_token(value: str | None) -> str | None:
    text = str(value or '').strip()
    if not text:
        return None
    prefix = 'bearer '
    if text.lower().startswith(prefix):
        token = text[len(prefix):].strip()
        return token or None
    return None


def extract_agent_write_credentials(headers: Any, payload: dict[str, Any]) -> tuple[str | None, str | None]:
    auth_token = first_text(
        payload.get('auth_token'),
        headers.get('X-Agent-Token') if headers is not None else None,
        bearer_token(headers.get('Authorization')) if headers is not None else None,
    )
    instance_id = first_text(
        payload.get('instance_id'),
        headers.get('X-Agent-Instance') if headers is not None else None,
    )
    return auth_token, instance_id


def extract_ingest_token(headers: Any, payload: dict[str, Any]) -> str | None:
    return first_text(
        payload.get('ingest_token'),
        headers.get('X-Marathon-Ingest-Token') if headers is not None else None,
        bearer_token(headers.get('Authorization')) if headers is not None else None,
    )


def require_ingest_token(headers: Any, payload: dict[str, Any]) -> None:
    expected = str(os.environ.get('MARATHON_INGEST_TOKEN', '')).strip()
    if not expected:
        return
    provided = extract_ingest_token(headers, payload)
    if not provided:
        raise PermissionError('ingestion token required')
    if provided != expected:
        raise PermissionError('invalid ingestion token')


def normalize_agent_post(payload: dict[str, Any] | None, *, agent_handle: str) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    has_content = any(payload.get(key) for key in ('done', 'next', 'thought', 'summary', 'error'))
    if not has_content:
        return None
    return {
        'agent_handle': agent_handle,
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


def read_agent_account_posts(handle: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    require_name(handle, field='agent handle')
    posts = [
        normalized
        for normalized in (
            normalize_agent_post(payload, agent_handle=handle)
            for payload in read_jsonl(agent_account_posts_path(handle))
        )
        if normalized is not None
    ]
    if limit is not None:
        posts = posts[-limit:]
    return list(reversed(posts))


def agent_account_payload(handle: str, *, limit: int | None = None) -> dict[str, Any]:
    require_name(handle, field='agent handle')
    try:
        detail = run_index.get_agent_account_payload(
            handle,
            limit=limit,
            runs_dir=RUNS_DIR,
            container_blog_dir=CONTAINER_BLOG_DIR,
            agent_account_dir=AGENT_ACCOUNT_DIR,
        )
        return {
            'account': public_agent_account(detail.get('account')),
            'posts': detail.get('posts') or [],
            'latest_post': detail.get('latest_post'),
            'latest_preview': detail.get('latest_preview'),
            'post_count': detail.get('post_count', 0),
        }
    except FileNotFoundError:
        raise ValueError(f'agent account not found: {handle}')
    except Exception:
        account = read_agent_account(handle)
        if account is None:
            raise ValueError(f'agent account not found: {handle}')
        posts = read_agent_account_posts(handle, limit=limit)
        latest_post = posts[0] if posts else None
        return {
            'account': public_agent_account(account),
            'posts': posts,
            'latest_post': latest_post,
            'latest_preview': preview_from_payload(latest_post, limit=600),
            'post_count': len(posts),
        }


def list_agent_handles() -> list[str]:
    ensure_dir(AGENT_ACCOUNT_DIR)
    handles = [path.stem for path in AGENT_ACCOUNT_DIR.glob('*.json') if path.is_file() and not path.name.endswith('.posts.json')]
    return sorted(set(handles))


def agent_accounts_payload() -> dict[str, Any]:
    try:
        payload = run_index.list_agent_accounts_payload(
            runs_dir=RUNS_DIR,
            container_blog_dir=CONTAINER_BLOG_DIR,
            agent_account_dir=AGENT_ACCOUNT_DIR,
        )
        payload['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
        return payload
    except Exception:
        ensure_dir(AGENT_ACCOUNT_DIR)
        accounts: list[dict[str, Any]] = []
        for handle in list_agent_handles():
            try:
                detail = agent_account_payload(handle)
            except ValueError:
                continue
            account = detail['account']
            accounts.append(
                {
                    **account,
                    'latest_post': detail['latest_post'],
                    'latest_preview': detail['latest_preview'],
                    'post_count': detail['post_count'],
                }
            )
        accounts.sort(
            key=lambda item: (
                str((item.get('latest_post') or {}).get('ts') or item.get('updated_at') or item.get('created_at') or ''),
                item.get('agent_handle') or '',
            ),
            reverse=True,
        )
        return {'accounts': accounts, 'updated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z')}


def container_agent_binding_payload(name: str) -> dict[str, Any]:
    require_name(name, field='container name')
    meta = read_container_state_meta(name)
    blog_meta = read_container_blog_meta(name)
    raw_handle = first_text(meta.get('agent_handle'))
    if not raw_handle:
        return {
            'container': name,
            'agent_handle': None,
            'account': None,
            'account_url': None,
            'local_identity': f'local/{name}',
            'sync': blog_meta.get('agent_binding') if isinstance(blog_meta.get('agent_binding'), dict) else None,
        }

    handle = require_name(raw_handle, field='agent handle')
    account = read_agent_account(handle)
    sync = blog_meta.get('agent_binding') if isinstance(blog_meta.get('agent_binding'), dict) else None
    if isinstance(sync, dict) and sync.get('agent_handle') != handle:
        sync = None
    return {
        'container': name,
        'agent_handle': handle,
        'account': public_agent_account(account) if isinstance(account, dict) else None,
        'account_url': f'/agent?handle={handle}',
        'local_identity': f'local/{name}',
        'sync': sync,
    }


def initial_container_agent_binding_meta(name: str, agent_handle: str) -> dict[str, Any]:
    now = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    blog_meta = read_container_blog_meta(name)
    binding: dict[str, Any] = {
        'agent_handle': agent_handle,
        'bound_at': now,
        'updated_at': now,
        'last_account_sync_run_id': None,
        'last_account_sync_round': 0,
        'last_account_sync_at': None,
        'runs': {},
    }
    latest_run_id = first_text(blog_meta.get('latest_run_id'))
    latest_round = maybe_int(blog_meta.get('latest_round')) or 0
    if latest_run_id and latest_round > 0:
        binding['runs'] = {
            latest_run_id: {
                'last_round': latest_round,
                'updated_at': now,
                'seeded_at': now,
            }
        }
        binding['last_account_sync_run_id'] = latest_run_id
        binding['last_account_sync_round'] = latest_round
    return binding


def set_container_agent_binding(name: str, agent_handle: str | None) -> dict[str, Any]:
    require_name(name, field='container name')
    meta = read_container_state_meta(name)
    if agent_handle is None:
        meta.pop('agent_handle', None)
        write_container_state_meta(name, meta)
        blog_meta = read_container_blog_meta(name)
        if 'agent_binding' in blog_meta:
            blog_meta.pop('agent_binding', None)
            write_json(container_blog_meta_path(name), blog_meta)
        return container_agent_binding_payload(name)

    handle = require_name(agent_handle, field='agent handle')
    account = read_agent_account(handle)
    if account is None:
        raise ValueError(f'agent account not found: {handle}')

    meta['agent_handle'] = handle
    write_container_state_meta(name, meta)

    blog_meta = read_container_blog_meta(name)
    existing = blog_meta.get('agent_binding')
    if not isinstance(existing, dict) or existing.get('agent_handle') != handle:
        blog_meta['agent_binding'] = initial_container_agent_binding_meta(name, handle)
        write_json(container_blog_meta_path(name), blog_meta)

    return container_agent_binding_payload(name)


def resolve_start_run_agent_handle(
    base_name: str,
    agent_handle: str | None,
    *,
    explicit: bool = False,
) -> str | None:
    require_name(base_name, field='base container name')
    if explicit:
        return first_text(agent_handle)
    base_meta = read_container_state_meta(base_name)
    return first_text(agent_handle, base_meta.get('agent_handle'))


def register_agent_account(payload: dict[str, Any]) -> dict[str, Any]:
    raw_handle = str(payload.get('agent_handle') or payload.get('handle') or '').strip()
    handle = require_name(raw_handle, field='agent handle')
    now = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    existing = read_agent_account(handle) or {}
    has_existing_credentials = bool(first_text(existing.get('auth_token')) and first_text(existing.get('instance_id')))
    if existing and has_existing_credentials:
        raise FileExistsError(f'agent account already exists: {handle}')
    auth_token = first_text(existing.get('auth_token')) or generate_agent_auth_token()
    instance_id = require_name(
        first_text(payload.get('instance_id'), existing.get('instance_id')) or generate_agent_instance_id(handle),
        field='instance id',
    )
    account = {
        'agent_account_id': existing.get('agent_account_id') or str(payload.get('agent_account_id') or f'agent-{handle}'),
        'agent_handle': handle,
        'display_name': str(payload.get('display_name') or existing.get('display_name') or handle).strip() or handle,
        'bio': str(payload.get('bio') or existing.get('bio') or '').strip(),
        'default_model': str(payload.get('default_model') or existing.get('default_model') or '').strip(),
        'instance_id': instance_id,
        'auth_token': auth_token,
        'created_at': existing.get('created_at') or now,
        'updated_at': now,
    }
    ensure_dir(AGENT_ACCOUNT_DIR)
    write_json(agent_account_path(handle), account)
    return {
        'ok': True,
        'created': not bool(existing),
        'migrated_legacy_credentials': bool(existing) and not has_existing_credentials,
        'account': public_agent_account(account),
        'credentials': {
            'auth_token': auth_token,
            'instance_id': instance_id,
        },
    }


def append_agent_account_post(
    handle: str,
    payload: dict[str, Any],
    *,
    auth_token: str | None = None,
    instance_id: str | None = None,
) -> dict[str, Any]:
    require_name(handle, field='agent handle')
    account = read_agent_account(handle)
    if account is None:
        raise ValueError(f'agent account not found: {handle}')
    stored_auth_token = first_text(account.get('auth_token'))
    stored_instance_id = first_text(account.get('instance_id'))
    if not stored_auth_token or not stored_instance_id:
        raise PermissionError('agent account is missing write credentials; re-register it to mint them')
    provided_auth_token = first_text(auth_token, payload.get('auth_token'))
    provided_instance_id = first_text(instance_id, payload.get('instance_id'))
    if not provided_auth_token:
        raise PermissionError('auth token required')
    if provided_auth_token != stored_auth_token:
        raise PermissionError('invalid auth token')
    if not provided_instance_id:
        raise PermissionError('instance_id required')
    if provided_instance_id != stored_instance_id:
        raise PermissionError('invalid instance id')
    now = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    normalized = normalize_agent_post(
        {
            **payload,
            'instance_id': stored_instance_id,
            'post_id': payload.get('post_id') or f'{handle}-{int(time.time() * 1000)}',
            'ts': payload.get('ts') or now,
        },
        agent_handle=handle,
    )
    if normalized is None:
        raise ValueError('blog post must include at least one of done, next, thought, summary, or error')
    append_jsonl(agent_account_posts_path(handle), normalized)
    account['updated_at'] = normalized.get('ts') or now
    write_json(agent_account_path(handle), account)
    return {'ok': True, 'account': public_agent_account(account), 'post': normalized}


def resolve_static_asset_path(request_path: str) -> Path | None:
    if request_path in {'/', '/index.html'}:
        return STATIC_DIR / 'index.html'
    alias = STATIC_ROUTE_ALIASES.get(request_path)
    if alias is not None:
        relative_path = Path(alias)
    else:
        if not request_path.startswith('/') or request_path.startswith('/api/'):
            return None
        relative_name = request_path.removeprefix('/')
        if not relative_name:
            return None
        relative_path = Path(relative_name)
    asset_root = STATIC_DIR.resolve()
    resolved_path = (asset_root / relative_path).resolve()
    try:
        resolved_path.relative_to(asset_root)
    except ValueError:
        return None
    if not resolved_path.is_file():
        return None
    return resolved_path


def read_recent_rounds(path: Path, *, limit: int = 60) -> list[dict[str, Any]]:
    rounds: list[dict[str, Any]] = []
    for payload in read_jsonl(path):
        event = payload.get('event')
        if event in {'round_completed', 'round_post'}:
            normalized = normalize_blog_post(payload)
            if normalized is not None:
                rounds.append(normalized)
        elif event == 'round_failed':
            rounds.append(
                {
                    'round': payload.get('round'),
                    'summary': payload.get('error'),
                    'done': None,
                    'next': None,
                    'thought': None,
                    'argv': None,
                    'tool_ok': False,
                    'returncode': None,
                    'ts': payload.get('ts'),
                    'failed': True,
                }
            )
    return list(reversed(rounds[-limit:]))


TRACKED_SELF_MODIFICATION_SOURCES = (
    'prompt_source',
    'tool_source',
    'loop_source',
)


def derive_self_modification_summary(state_before: dict[str, Any] | None, state_after: dict[str, Any] | None) -> dict[str, Any]:
    before = state_before if isinstance(state_before, dict) else {}
    after = state_after if isinstance(state_after, dict) else {}
    categories = [
        field
        for field in TRACKED_SELF_MODIFICATION_SOURCES
        if before.get(field) is not None and after.get(field) is not None and before.get(field) != after.get(field)
    ]
    return {
        'observed': bool(categories),
        'categories': categories,
        'latest_category': categories[-1] if categories else None,
    }


def summarize_run_self_modification(
    run_dir: Path,
    latest_state_before: dict[str, Any] | None,
    latest_state_after: dict[str, Any] | None,
) -> dict[str, Any]:
    categories: list[str] = []
    latest_category = None
    latest_round = None
    count = 0
    newest_round_has_usable_observation = False

    rounds_dir = run_dir / 'rounds'
    if rounds_dir.exists():
        round_dirs = sorted(path for path in rounds_dir.iterdir() if path.is_dir())
        newest_round_dir = round_dirs[-1] if round_dirs else None
        for round_dir in round_dirs:
            round_summary = derive_self_modification_summary(
                read_json(round_dir / 'state_before.json'),
                read_json(round_dir / 'state_after.json'),
            )
            if not round_summary['observed']:
                continue
            count += 1
            for category in round_summary['categories']:
                if category not in categories:
                    categories.append(category)
            latest_category = round_summary['latest_category']
            latest_round = int(round_dir.name) if round_dir.name.isdigit() else latest_round
            if newest_round_dir is not None and round_dir == newest_round_dir:
                newest_round_has_usable_observation = True
    latest_summary = derive_self_modification_summary(latest_state_before, latest_state_after)
    should_use_latest_state_fallback = latest_summary['observed'] and (
        count == 0 or not newest_round_has_usable_observation
    )
    if should_use_latest_state_fallback:
        if count == 0:
            categories = list(latest_summary['categories'])
            count = 1
        else:
            for category in latest_summary['categories']:
                if category not in categories:
                    categories.append(category)
            count += 1
        latest_category = latest_summary['latest_category']
        latest_round = None

    return {
        'observed': count > 0,
        'categories': categories,
        'latest_category': latest_category,
        'latest_round': latest_round,
        'count': count,
    }


def derive_run_observation(
    summary: dict[str, Any],
    latest_state_before: dict[str, Any] | None,
    latest_state_after: dict[str, Any] | None,
    recent_rounds: list[dict[str, Any]],
    self_modification: dict[str, Any] | None,
) -> dict[str, Any]:
    _ = summary
    _ = latest_state_before
    _ = latest_state_after
    _ = recent_rounds
    return {
        'self_modification': self_modification or {
            'observed': False,
            'categories': [],
            'latest_category': None,
            'latest_round': None,
            'count': 0,
        }
    }


def pid_is_running(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_pid(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        return int(path.read_text(encoding='utf-8').strip())
    except (OSError, ValueError):
        return None


def require_name(value: str, *, field: str) -> str:
    if not NAME_RE.fullmatch(value):
        raise ValueError(f'invalid {field}: {value}')
    return value


def parse_int(value: Any, *, default: int) -> int:
    if value in (None, ''):
        return default
    return int(value)


def parse_float(value: Any, *, default: float) -> float:
    if value in (None, ''):
        return default
    return float(value)


def parse_non_negative_int(value: Any, *, default: int) -> int:
    parsed = parse_int(value, default=default)
    if parsed < 0:
        raise ValueError('value must be non-negative')
    return parsed


def parse_non_negative_float(value: Any, *, default: float) -> float:
    parsed = parse_float(value, default=default)
    if parsed < 0:
        raise ValueError('value must be non-negative')
    return parsed


def maybe_int(value: Any) -> int | None:
    if value in (None, '', 'max'):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def lxc_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return run_host_command(['sudo', '-n', *args], check=False)


def lxc_attach(container: str, command: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    require_name(container, field='container name')
    return run_host_command(['sudo', '-n', 'lxc-attach', '-n', container, '--', *command], input_text=input_text, check=False)


def read_container_state_meta(name: str) -> dict[str, Any]:
    return read_json(CONTAINER_STATE_DIR / f'{name}.json') or {}


def remove_container_state_meta(name: str) -> None:
    try:
        (CONTAINER_STATE_DIR / f'{name}.json').unlink()
    except FileNotFoundError:
        return


def list_host_links() -> list[str]:
    completed = run_host_command(['ip', '-br', 'link'], check=False)
    if completed.returncode != 0:
        return []
    return lxc_network.parse_link_names(completed.stdout)


def list_container_names() -> list[str]:
    names: list[str] = []
    listed = lxc_command(['lxc-ls', '-1'])
    if listed.returncode == 0:
        names = [line.strip() for line in listed.stdout.splitlines() if line.strip()]
    elif Path('/var/lib/lxc').exists():
        names = sorted(path.name for path in Path('/var/lib/lxc').iterdir() if path.is_dir())
    return sorted(set(names))


def get_container_info(name: str) -> dict[str, Any]:
    meta = read_container_state_meta(name)
    blog_meta = read_container_blog_meta(name)
    blog_posts = read_container_blog_posts(name, limit=1)
    latest_blog_post = blog_posts[0] if blog_posts else None
    info: dict[str, Any] = {
        'name': name,
        'state': 'UNKNOWN',
        'pid': None,
        'ips': [],
        'network_mode': meta.get('network_mode'),
        'bridge_name': meta.get('bridge_name'),
        'bridge_cidr': meta.get('bridge_cidr'),
        'ipv4_address': meta.get('ipv4_address'),
        'ipv4_gateway': meta.get('ipv4_gateway'),
        'agent_handle': meta.get('agent_handle'),
        'latest_blog_post': latest_blog_post,
        'latest_blog_preview': preview_from_payload(latest_blog_post, limit=600),
        'latest_blog_updated_at': (latest_blog_post or {}).get('ts') or blog_meta.get('updated_at'),
        'blog_post_count': blog_meta.get('post_count', len(blog_posts)),
    }
    completed = lxc_command(['lxc-info', '-n', name])
    if completed.returncode != 0:
        info['error'] = completed.stderr.strip() or completed.stdout.strip() or 'failed to inspect container'
        return info
    ips: list[str] = []
    for raw_line in completed.stdout.splitlines():
        if ':' not in raw_line:
            continue
        key, value = raw_line.split(':', 1)
        key = key.strip()
        value = value.strip()
        if key == 'State':
            info['state'] = value or 'UNKNOWN'
        elif key == 'PID':
            info['pid'] = int(value) if value.isdigit() else None
        elif key == 'IP' and value and value != '-':
            ips.append(value)
    info['ips'] = ips
    return info


def list_containers() -> list[dict[str, Any]]:
    return [get_container_info(name) for name in list_container_names()]


def read_container_runtime(name: str) -> dict[str, Any]:
    info = get_container_info(name)
    runtime: dict[str, Any] = {
        'name': info.get('name'),
        'state': info.get('state'),
        'pid': info.get('pid'),
        'ips': info.get('ips'),
        'network_mode': info.get('network_mode'),
        'bridge_name': info.get('bridge_name'),
        'bridge_cidr': info.get('bridge_cidr'),
        'ipv4_address': info.get('ipv4_address'),
        'ipv4_gateway': info.get('ipv4_gateway'),
        'memory_current_bytes': None,
        'memory_max_bytes': None,
        'memory_max_raw': None,
        'pids_current': None,
        'pids_max': None,
        'pids_max_raw': None,
        'cpu_usage_usec': None,
        'cpu_user_usec': None,
        'cpu_system_usec': None,
        'cpu_nr_periods': None,
        'cpu_nr_throttled': None,
        'cpu_throttled_usec': None,
        'cpu_max': None,
        'cpu_weight': None,
        'loadavg': None,
        'metrics_error': info.get('error'),
    }

    if info.get('state') != 'RUNNING':
        return runtime

    script = r'''
python3 - <<'INNER'
import json
from pathlib import Path

root = Path('/sys/fs/cgroup')


def read_first(names):
    for name in names:
        path = root / name
        try:
            return path.read_text(encoding='utf-8', errors='replace').strip()
        except OSError:
            continue
    return None


def parse_cpu_stat(text):
    payload = {}
    if not text:
        return payload
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            payload[parts[0]] = parts[1] if len(parts) == 2 else ' '.join(parts[1:])
    return payload


result = {
    'memory_current': read_first(['memory.current', 'memory/memory.usage_in_bytes']),
    'memory_max': read_first(['memory.max', 'memory/memory.limit_in_bytes']),
    'pids_current': read_first(['pids.current']),
    'pids_max': read_first(['pids.max']),
    'cpu_stat': parse_cpu_stat(read_first(['cpu.stat'])),
    'cpu_max': read_first(['cpu.max', 'cpu/cpu.cfs_quota_us']),
    'cpu_weight': read_first(['cpu.weight', 'cpu/cpu.shares']),
}
try:
    result['loadavg'] = Path('/proc/loadavg').read_text(encoding='utf-8', errors='replace').strip()
except OSError:
    result['loadavg'] = None
print(json.dumps(result, ensure_ascii=False))
INNER
'''
    completed = lxc_attach(name, ['bash', '-lc', script])
    if completed.returncode != 0:
        runtime['metrics_error'] = completed.stderr.strip() or completed.stdout.strip() or 'failed to read container metrics'
        return runtime

    try:
        payload = json.loads(completed.stdout.strip() or '{}')
    except json.JSONDecodeError:
        runtime['metrics_error'] = 'container metrics returned invalid JSON'
        return runtime

    if not isinstance(payload, dict):
        runtime['metrics_error'] = 'container metrics returned non-object JSON'
        return runtime

    cpu_stat = payload.get('cpu_stat') if isinstance(payload.get('cpu_stat'), dict) else {}
    runtime.update(
        {
            'memory_current_bytes': maybe_int(payload.get('memory_current')),
            'memory_max_bytes': maybe_int(payload.get('memory_max')),
            'memory_max_raw': payload.get('memory_max'),
            'pids_current': maybe_int(payload.get('pids_current')),
            'pids_max': maybe_int(payload.get('pids_max')),
            'pids_max_raw': payload.get('pids_max'),
            'cpu_usage_usec': maybe_int(cpu_stat.get('usage_usec') or cpu_stat.get('usage')),
            'cpu_user_usec': maybe_int(cpu_stat.get('user_usec') or cpu_stat.get('user')),
            'cpu_system_usec': maybe_int(cpu_stat.get('system_usec') or cpu_stat.get('system')),
            'cpu_nr_periods': maybe_int(cpu_stat.get('nr_periods')),
            'cpu_nr_throttled': maybe_int(cpu_stat.get('nr_throttled')),
            'cpu_throttled_usec': maybe_int(cpu_stat.get('throttled_usec') or cpu_stat.get('throttled_time')),
            'cpu_max': payload.get('cpu_max'),
            'cpu_weight': payload.get('cpu_weight'),
            'loadavg': payload.get('loadavg'),
            'metrics_error': None,
        }
    )
    return runtime


def write_container_file(container: str, path: str, content: str) -> dict[str, Any]:
    parent = str(Path(path).parent)
    command = f'mkdir -p {shlex.quote(parent)} && cat > {shlex.quote(path)}'
    completed = lxc_attach(container, ['bash', '-lc', command], input_text=content)
    return {
        'ok': completed.returncode == 0,
        'path': path,
        'stdout': completed.stdout,
        'stderr': completed.stderr,
    }


def sync_local_file_to_container(container: str, source: Path, target: str, *, executable: bool = False) -> dict[str, Any]:
    if not source.exists():
        return {'ok': False, 'path': target, 'error': f'missing source file: {source}'}
    result = write_container_file(container, target, source.read_text(encoding='utf-8'))
    result['source'] = str(source)
    result['bytes'] = source.stat().st_size
    if not result.get('ok'):
        return result
    if executable:
        chmod = lxc_attach(container, ['bash', '-lc', f'chmod +x {shlex.quote(target)}'])
        result['chmod_returncode'] = chmod.returncode
        if chmod.returncode != 0:
            result['ok'] = False
            result['stderr'] = (result.get('stderr') or '') + (chmod.stderr or chmod.stdout or '')
    return result


def ensure_container_running(name: str) -> dict[str, Any]:
    info = get_container_info(name)
    if info.get('state') == 'RUNNING':
        return {'ok': True, 'started': False, 'container': info}
    started = start_container(name)
    if not started.get('ok'):
        return {'ok': False, 'started': False, 'container': info, 'start': started}
    time.sleep(2)
    return {'ok': True, 'started': True, 'container': get_container_info(name), 'start': started}


def prepare_container_for_agent(container: str) -> dict[str, Any]:
    require_name(container, field='container name')
    running = ensure_container_running(container)
    if not running.get('ok'):
        return {'ok': False, 'step': 'start_container', **running}

    bootstrap_script = r'''
set -e
if ! command -v python3 >/dev/null 2>&1 || ! command -v git >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y python3 git
  else
    echo "python3 or git missing, and apt-get is unavailable" >&2
    exit 2
  fi
fi
mkdir -p /opt/marathon /workspace/sandbox /workspace/runtime-log
cd /workspace/sandbox
if [ ! -d .git ]; then
  git init
  git config user.name marathon-agent
  git config user.email marathon@local
fi
'''
    boot = lxc_attach(container, ['bash', '-lc', bootstrap_script])
    bootstrap = {'ok': boot.returncode == 0, 'stdout': boot.stdout, 'stderr': boot.stderr}
    if boot.returncode != 0:
        return {'ok': False, 'step': 'bootstrap', 'running': running, 'bootstrap': bootstrap}

    synced = [
        sync_local_file_to_container(container, ROOT_DIR / 'container' / 'agent_tools.py', '/opt/marathon/agent_tools.py', executable=True),
        sync_local_file_to_container(container, ROOT_DIR / 'container' / 'agent_loop.py', '/opt/marathon/agent_loop.py', executable=True),
        sync_local_file_to_container(container, PROMPT_FILE, '/opt/marathon/minimal_system.txt', executable=False),
    ]
    failed = next((item for item in synced if not item.get('ok')), None)
    if failed:
        return {'ok': False, 'step': 'sync_files', 'running': running, 'bootstrap': bootstrap, 'synced': synced, 'error': failed.get('error') or failed.get('stderr') or 'sync failed'}

    seed = lxc_attach(
        container,
        ['bash', '-lc', 'if [ ! -f /workspace/sandbox/START.txt ]; then cat > /workspace/sandbox/START.txt <<\'EOF\'\nYou are running inside this container.\nYour only built-in external capability is command execution through /opt/marathon/agent_tools.py.\nYour agent loop also lives here at /opt/marathon/agent_loop.py.\nYou may inspect or modify both files yourself.\nEOF\nfi'],
    )
    return {
        'ok': True,
        'running': running,
        'bootstrap': bootstrap,
        'synced': synced,
        'seeded': {'ok': seed.returncode == 0, 'stdout': seed.stdout, 'stderr': seed.stderr},
    }


def read_prompt_payload() -> dict[str, Any]:
    ensure_dir(PROMPT_FILE.parent)
    text = PROMPT_FILE.read_text(encoding='utf-8') if PROMPT_FILE.exists() else ''
    updated_at = None
    if PROMPT_FILE.exists():
        updated_at = time.strftime('%Y-%m-%dT%H:%M:%S%z', time.localtime(PROMPT_FILE.stat().st_mtime))
    return {'path': str(PROMPT_FILE), 'text': text, 'updated_at': updated_at}


def write_prompt_payload(text: str) -> dict[str, Any]:
    ensure_dir(PROMPT_FILE.parent)
    PROMPT_FILE.write_text(text, encoding='utf-8')
    return read_prompt_payload()


def parse_optional_int(value: Any, *, default: int | None = None) -> int | None:
    if value in (None, ''):
        return default
    return int(value)


def parse_optional_float(value: Any, *, default: float | None = None) -> float | None:
    if value in (None, ''):
        return default
    return float(value)


def parse_optional_non_negative_int(value: Any, *, default: int | None = None) -> int | None:
    parsed = parse_optional_int(value, default=default)
    if parsed is None:
        return None
    if parsed < 0:
        raise ValueError('value must be non-negative')
    return parsed


def parse_optional_non_negative_float(value: Any, *, default: float | None = None) -> float | None:
    parsed = parse_optional_float(value, default=default)
    if parsed is None:
        return None
    if parsed < 0:
        raise ValueError('value must be non-negative')
    return parsed


def normalize_extra_body(value: Any) -> dict[str, Any]:
    if value in (None, ''):
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        payload = json.loads(value or '{}')
        if not isinstance(payload, dict):
            raise ValueError('extra_body must decode to an object')
        return payload
    raise ValueError('extra_body must be an object or JSON string')


def container_settings_backup_path(name: str, timestamp: str) -> Path:
    require_name(name, field='container name')
    return CONTAINER_SETTINGS_BACKUP_DIR / name / f'{timestamp}.json'


def list_container_settings_backups(name: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    require_name(name, field='container name')
    backup_dir = CONTAINER_SETTINGS_BACKUP_DIR / name
    if not backup_dir.exists():
        return []
    paths = sorted((path for path in backup_dir.glob('*.json') if path.is_file()), reverse=True)
    if limit is not None:
        paths = paths[:limit]
    items: list[dict[str, Any]] = []
    for path in paths:
        items.append(
            {
                'name': path.name,
                'path': str(path),
                'updated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z', time.localtime(path.stat().st_mtime)),
                'bytes': path.stat().st_size,
            }
        )
    return items


def container_settings_backup_summary(name: str) -> dict[str, Any]:
    backups = list_container_settings_backups(name, limit=1)
    latest = backups[0] if backups else None
    backup_dir = CONTAINER_SETTINGS_BACKUP_DIR / name
    count = len([path for path in backup_dir.glob('*.json') if path.is_file()]) if backup_dir.exists() else 0
    return {
        'count': count,
        'latest': latest,
    }


def backup_container_state_meta(name: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    require_name(name, field='container name')
    source_path = container_state_path(name)
    if not source_path.exists():
        return None
    timestamp = time.strftime('%Y%m%d-%H%M%S')
    target_path = container_settings_backup_path(name, timestamp)
    ensure_dir(target_path.parent)
    write_json(target_path, payload)
    return {
        'name': target_path.name,
        'path': str(target_path),
        'updated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
    }


def normalize_container_agent_settings(payload: Any) -> dict[str, Any]:
    if payload in (None, ''):
        return {}
    if not isinstance(payload, dict):
        raise ValueError('agent_settings must be an object')

    normalized: dict[str, Any] = {}

    if first_text(payload.get('mode')):
        normalized['mode'] = resolve_run_mode({'mode': payload.get('mode')})

    for key in ('task_prompt', 'model', 'base_url', 'reasoning_effort'):
        value = first_text(payload.get(key))
        if value is not None:
            normalized[key] = value

    for key in ('temperature', 'top_p', 'request_timeout_seconds', 'request_retry_delay_seconds', 'sleep_seconds'):
        value = parse_optional_non_negative_float(payload.get(key), default=None)
        if value is not None:
            normalized[key] = value

    for key in ('max_completion_tokens', 'request_max_attempts', 'max_rounds', 'max_runtime_seconds', 'max_total_tokens'):
        value = parse_optional_non_negative_int(payload.get(key), default=None)
        if value is not None:
            normalized[key] = value

    if 'extra_body' in payload:
        normalized['extra_body'] = normalize_extra_body(payload.get('extra_body'))

    return normalized


def container_agent_settings_from_meta(meta: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(meta, dict):
        return {}
    raw = meta.get('agent_settings')
    if not isinstance(raw, dict):
        return {}
    try:
        return normalize_container_agent_settings(raw)
    except ValueError:
        return {}


def read_container_agent_settings(name: str) -> dict[str, Any]:
    require_name(name, field='container name')
    return container_agent_settings_from_meta(read_container_state_meta(name))


def merge_container_agent_settings(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    require_name(name, field='container name')
    saved = read_container_agent_settings(name)
    if not saved:
        return dict(payload)
    merged = dict(saved)
    merged.update(payload)
    return merged


def write_container_agent_settings(name: str, payload: dict[str, Any]) -> dict[str, Any]:
    require_name(name, field='container name')
    meta = read_container_state_meta(name)
    current = container_agent_settings_from_meta(meta)
    clear = bool(payload.get('clear'))
    source = payload.get('agent_settings') if 'agent_settings' in payload else payload
    updated = {} if clear else normalize_container_agent_settings(source)

    if current == updated:
        return {
            'ok': True,
            'container': name,
            'settings': updated,
            'backup': None,
            'backup_summary': container_settings_backup_summary(name),
            'updated_at': meta.get('agent_settings_updated_at'),
        }

    backup = backup_container_state_meta(name, meta) if meta else None
    if updated:
        meta['agent_settings'] = updated
        meta['agent_settings_updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    else:
        meta.pop('agent_settings', None)
        meta.pop('agent_settings_updated_at', None)

    write_container_state_meta(name, meta)
    return {
        'ok': True,
        'container': name,
        'settings': updated,
        'backup': backup,
        'backup_summary': container_settings_backup_summary(name),
        'updated_at': meta.get('agent_settings_updated_at'),
    }


def resolve_task_prompt(payload: dict[str, Any]) -> str:
    raw = str(payload.get('task_prompt') or '').strip()
    return raw or DEFAULT_TASK_PROMPT


def resolve_run_mode(payload: dict[str, Any]) -> str:
    raw = str(payload.get('mode') or 'task').strip().lower()
    if raw in {'task', 'freeplay'}:
        return raw
    raise ValueError(f'unsupported run mode: {raw}')


def apply_run_mode_defaults(payload: dict[str, Any], resolved: dict[str, Any]) -> dict[str, Any]:
    mode = resolve_run_mode(payload)
    result = dict(resolved)
    model_settings = dict(result['model_settings'])

    if mode == 'freeplay':
        result['task_prompt'] = FREEPLAY_TASK_PROMPT
        model_settings['reasoning_effort'] = 'high'
        model_settings['temperature'] = 0.7
        model_settings['request_timeout_seconds'] = 120.0
        model_settings['request_max_attempts'] = 10
        model_settings['request_retry_delay_seconds'] = 2.0
        model_settings['extra_body'] = model_settings.get('extra_body') or {}
    else:
        result['task_prompt'] = resolve_task_prompt(payload)

    result['max_rounds'] = parse_non_negative_int(payload.get('max_rounds'), default=0)
    result['sleep_seconds'] = parse_non_negative_float(payload.get('sleep_seconds'), default=1.0)
    result['max_runtime_seconds'] = parse_optional_non_negative_int(payload.get('max_runtime_seconds'), default=None)
    result['max_total_tokens'] = parse_optional_non_negative_int(payload.get('max_total_tokens'), default=None)
    result['mode'] = mode
    result['model_settings'] = model_settings
    return result


def normalize_model_profile(payload: Any, *, fallback_id: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError('model profile must be an object')
    profile_id = str(payload.get('id') or fallback_id).strip()
    require_name(profile_id, field='model profile id')
    label = str(payload.get('label') or profile_id).strip()
    model = str(payload.get('model') or '').strip()
    base_url = str(payload.get('base_url') or '').strip()
    return {
        'id': profile_id,
        'label': label or profile_id,
        'model': model,
        'base_url': base_url,
        'api_key': str(payload.get('api_key') or '').strip(),
        'reasoning_effort': str(payload.get('reasoning_effort') or '').strip(),
        'temperature': parse_optional_float(payload.get('temperature'), default=0.7),
        'top_p': parse_optional_float(payload.get('top_p'), default=None),
        'max_completion_tokens': parse_optional_int(payload.get('max_completion_tokens'), default=None),
        'request_timeout_seconds': parse_optional_float(payload.get('request_timeout_seconds'), default=120.0),
        'request_max_attempts': parse_optional_int(payload.get('request_max_attempts'), default=None),
        'request_retry_delay_seconds': parse_optional_float(payload.get('request_retry_delay_seconds'), default=None),
        'extra_body': normalize_extra_body(payload.get('extra_body')),
    }


def default_model_profiles_payload() -> dict[str, Any]:
    return {
        'path': str(MODEL_PROFILES_FILE),
        'default_profile_id': 'default',
        'profiles': [
            normalize_model_profile(
                {
                    'id': 'default',
                    'label': '默认配置',
                    'model': os.environ.get('MARATHON_MODEL', '').strip(),
                    'base_url': os.environ.get('MARATHON_BASE_URL', '').strip(),
                    'api_key': os.environ.get('MARATHON_API_KEY', ''),
                    'temperature': None,
                    'request_timeout_seconds': 120.0,
                    'extra_body': {},
                },
                fallback_id='default',
            )
        ],
        'updated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
    }


def refresh_default_model_profile_from_environment(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    profiles = payload.get('profiles')
    if not isinstance(profiles, list):
        return payload, False

    changed = False
    refreshed_profiles: list[dict[str, Any]] = []
    for item in profiles:
        if not isinstance(item, dict) or item.get('id') != 'default':
            refreshed_profiles.append(item)
            continue
        refreshed = dict(item)
        env_defaults = default_model_profiles_payload()['profiles'][0]
        for field in ('model', 'base_url', 'api_key'):
            env_value = str(env_defaults.get(field) or '').strip()
            if not env_value or refreshed.get(field) == env_value:
                continue
            refreshed[field] = env_value
            changed = True
        refreshed_profiles.append(refreshed)

    if not changed:
        return payload, False

    updated = dict(payload)
    updated['profiles'] = refreshed_profiles
    updated['updated_at'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    return updated, True


def normalize_model_profiles_payload(payload: dict[str, Any], *, updated_at: str | None = None) -> dict[str, Any]:
    raw_profiles = payload.get('profiles')
    if not isinstance(raw_profiles, list) or not raw_profiles:
        raise ValueError('profiles must be a non-empty array')

    profiles: list[dict[str, Any]] = []
    profile_ids: set[str] = set()
    for index, item in enumerate(raw_profiles, start=1):
        profile = normalize_model_profile(item, fallback_id=f'profile-{index}')
        if profile['id'] in profile_ids:
            raise ValueError(f'duplicate model profile id: {profile["id"]}')
        profile_ids.add(profile['id'])
        profiles.append(profile)

    default_profile_id = str(payload.get('default_profile_id') or profiles[0]['id']).strip()
    if default_profile_id not in profile_ids:
        raise ValueError(f'default profile not found: {default_profile_id}')

    return {
        'path': str(MODEL_PROFILES_FILE),
        'default_profile_id': default_profile_id,
        'profiles': profiles,
        'updated_at': updated_at or time.strftime('%Y-%m-%dT%H:%M:%S%z'),
    }


def write_model_profiles_payload(payload: dict[str, Any]) -> dict[str, Any]:
    ensure_dir(MODEL_PROFILES_FILE.parent)
    result = normalize_model_profiles_payload(payload)
    write_json(MODEL_PROFILES_FILE, result)
    return result


def read_model_profiles_payload() -> dict[str, Any]:
    ensure_dir(MODEL_PROFILES_FILE.parent)
    payload = read_json(MODEL_PROFILES_FILE)
    if payload is None:
        payload = default_model_profiles_payload()
        write_json(MODEL_PROFILES_FILE, payload)
        return payload
    normalized = normalize_model_profiles_payload(payload, updated_at=payload.get('updated_at') if isinstance(payload, dict) else None)
    refreshed, changed = refresh_default_model_profile_from_environment(normalized)
    if changed:
        write_json(MODEL_PROFILES_FILE, refreshed)
    return refreshed


def get_model_profile(profile_id: str | None) -> dict[str, Any]:
    payload = read_model_profiles_payload()
    target_id = str(profile_id or payload['default_profile_id']).strip()
    for profile in payload['profiles']:
        if profile['id'] == target_id:
            return profile
    raise ValueError(f'model profile not found: {target_id}')


def resolve_run_model_config(payload: dict[str, Any]) -> dict[str, Any]:
    profiles_payload = read_model_profiles_payload()
    profile_id = str(payload.get('profile_id') or profiles_payload['default_profile_id']).strip()
    profile = get_model_profile(profile_id)

    model = str(payload.get('model') or profile['model'] or DEFAULT_MODEL).strip()
    base_url = str(payload.get('base_url') or profile['base_url'] or DEFAULT_BASE_URL).strip()
    if not model:
        raise ValueError('missing model')
    if not base_url:
        raise ValueError('missing base_url')

    model_settings = {
        'profile_id': profile['id'],
        'profile_label': profile['label'],
        'reasoning_effort': str(payload.get('reasoning_effort') or profile.get('reasoning_effort') or '').strip(),
        'temperature': parse_optional_float(payload.get('temperature'), default=profile.get('temperature')),
        'top_p': parse_optional_float(payload.get('top_p'), default=profile.get('top_p')),
        'max_completion_tokens': parse_optional_int(payload.get('max_completion_tokens'), default=profile.get('max_completion_tokens')),
        'request_timeout_seconds': parse_optional_float(payload.get('request_timeout_seconds'), default=profile.get('request_timeout_seconds')),
        'request_max_attempts': parse_optional_int(payload.get('request_max_attempts'), default=profile.get('request_max_attempts')),
        'request_retry_delay_seconds': parse_optional_float(
            payload.get('request_retry_delay_seconds'),
            default=profile.get('request_retry_delay_seconds'),
        ),
        'extra_body': profile.get('extra_body') or {},
    }
    if 'extra_body' in payload:
        model_settings['extra_body'] = normalize_extra_body(payload.get('extra_body'))

    cleaned = {
        key: value
        for key, value in model_settings.items()
        if value not in (None, '') or key in {'profile_id', 'profile_label', 'extra_body'}
    }
    cleaned['extra_body'] = cleaned.get('extra_body') or {}
    api_key = str(payload.get('api_key') or profile.get('api_key') or os.environ.get('MARATHON_API_KEY', '')).strip()
    return {'model': model, 'base_url': base_url, 'api_key': api_key, 'model_settings': cleaned, 'profile': profile}


def test_model_connectivity(payload: dict[str, Any]) -> dict[str, Any]:
    resolved = resolve_run_model_config(payload)
    api_key = resolved['api_key']
    if not api_key:
        raise ValueError('missing API key')

    model_settings = dict(resolved['model_settings'])
    base_url = str(resolved['base_url']).rstrip('/')
    url = base_url + '/chat/completions'
    request_body: dict[str, Any] = {
        'model': resolved['model'],
        'messages': [
            {'role': 'system', 'content': 'Reply with a very short plain-text pong.'},
            {'role': 'user', 'content': 'ping'},
        ],
        'max_completion_tokens': min(
            parse_non_negative_int(model_settings.get('max_completion_tokens'), default=48),
            48,
        ),
    }
    if model_settings.get('reasoning_effort'):
        request_body['reasoning_effort'] = model_settings['reasoning_effort']
    if model_settings.get('temperature') is not None:
        request_body['temperature'] = model_settings['temperature']
    if model_settings.get('top_p') is not None:
        request_body['top_p'] = model_settings['top_p']
    if model_settings.get('extra_body'):
        request_body.update(model_settings['extra_body'])

    timeout_seconds = parse_non_negative_float(model_settings.get('request_timeout_seconds'), default=15.0)
    max_attempts = max(1, parse_non_negative_int(model_settings.get('request_max_attempts'), default=1))
    retry_delay_seconds = parse_non_negative_float(model_settings.get('request_retry_delay_seconds'), default=1.0)
    request = urllib.request.Request(
        url,
        data=json.dumps(request_body).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        },
        method='POST',
    )

    started = time.monotonic()
    raw = ''
    transient_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read().decode('utf-8')
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='replace')
            raise RuntimeError(f'model HTTP error {exc.code}: {detail}') from exc
        except (urllib.error.URLError, TimeoutError, http.client.RemoteDisconnected, http.client.IncompleteRead) as exc:
            transient_error = exc
            if attempt >= max_attempts:
                raise RuntimeError(f'model request failed after {max_attempts} attempts: {exc}') from exc
            time.sleep(retry_delay_seconds)
    else:
        raise RuntimeError(f'model request failed after {max_attempts} attempts: {transient_error}')

    latency_ms = int((time.monotonic() - started) * 1000)
    response_payload = json.loads(raw or '{}')
    if not isinstance(response_payload, dict):
        raise ValueError('model response was not a JSON object')
    choices = response_payload.get('choices')
    if not isinstance(choices, list) or not choices:
        raise ValueError('model response did not include choices')
    first_choice = choices[0] if isinstance(choices[0], dict) else {}
    message = first_choice.get('message') if isinstance(first_choice.get('message'), dict) else {}
    content = str(message.get('content') or '').strip()
    usage = response_payload.get('usage') if isinstance(response_payload.get('usage'), dict) else {}
    return {
        'ok': True,
        'model': resolved['model'],
        'base_url': base_url,
        'latency_ms': latency_ms,
        'preview': compact_text_preview(content, limit=160) or '模型已响应，但没有返回正文。',
        'response_model': response_payload.get('model') or resolved['model'],
        'usage': {
            'prompt_tokens': usage.get('prompt_tokens'),
            'completion_tokens': usage.get('completion_tokens'),
            'total_tokens': usage.get('total_tokens'),
        },
    }


def run_dir_for(run_id: str) -> Path:
    require_name(run_id, field='run id')
    return RUNS_DIR / run_id


def list_invalid_response_artifacts(run_dir: Path) -> list[dict[str, Any]]:
    rounds_dir = run_dir / 'rounds'
    if not rounds_dir.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(rounds_dir.glob('*/response.invalid-*.txt')):
        round_name = path.parent.name
        raw_path = path.with_suffix('.raw.json')
        items.append(
            {
                'round': int(round_name) if round_name.isdigit() else round_name,
                'attempt': path.stem.split('-')[-1],
                'text': read_text(path, max_chars=MAX_TEXT_PREVIEW),
                'raw_json_text': read_text(raw_path, max_chars=MAX_TEXT_PREVIEW),
                'text_path': str(path),
                'raw_path': str(raw_path),
            }
        )
    return items


def latest_round_error_text(run_dir: Path) -> str | None:
    rounds_dir = run_dir / 'rounds'
    if not rounds_dir.exists():
        return None
    candidates = sorted(rounds_dir.glob('*/error.json'))
    if not candidates:
        return None
    latest = candidates[-1]
    return read_text(latest, max_chars=MAX_TEXT_PREVIEW)


def summarize_run(run_dir: Path) -> dict[str, Any]:
    host_run = read_json(run_dir / 'host_run.json') or {}
    status = read_json(run_dir / 'status.json') or {}
    launch = read_json(run_dir / 'launch.json') or {}
    ui_launch = read_json(run_dir / 'ui_launch.json') or {}
    latest_action = read_json(run_dir / 'latest_action.json') or {}
    latest_action_done = first_text(latest_action.get('done'), latest_action.get('summary'))
    latest_action_next = first_text(latest_action.get('next'))
    latest_action_thought = first_text(latest_action.get('thought'))
    supervisor_pid = read_pid(run_dir / 'supervisor.pid')
    return {
        'run_id': run_dir.name,
        'container': host_run.get('container') or ui_launch.get('container'),
        'state': status.get('state', 'unknown'),
        'completed_rounds': status.get('completed_rounds', -1),
        'last_done': status.get('last_done') or latest_action_done,
        'last_next': status.get('last_next') or latest_action_next,
        'last_thought': status.get('last_thought') or latest_action_thought,
        'last_summary': status.get('last_summary'),
        'last_argv': status.get('last_argv'),
        'updated_at': status.get('updated_at') or host_run.get('started_at') or ui_launch.get('started_at'),
        'stopped_requested': (run_dir / 'STOP').exists(),
        'supervisor_pid': supervisor_pid,
        'supervisor_running': pid_is_running(supervisor_pid),
        'model': host_run.get('model') or ui_launch.get('model'),
        'base_url': host_run.get('base_url') or ui_launch.get('base_url'),
        'mode': host_run.get('mode') or ui_launch.get('mode') or 'task',
        'task_prompt': host_run.get('task_prompt') or ui_launch.get('task_prompt'),
        'sync_interval': host_run.get('sync_interval'),
        'max_runtime_seconds': status.get('max_runtime_seconds') or host_run.get('max_runtime_seconds') or ui_launch.get('max_runtime_seconds'),
        'max_total_tokens': status.get('max_total_tokens') or host_run.get('max_total_tokens') or ui_launch.get('max_total_tokens'),
        'token_usage_prompt': status.get('token_usage_prompt'),
        'token_usage_completion': status.get('token_usage_completion'),
        'token_usage_total': status.get('token_usage_total'),
        'elapsed_seconds': status.get('elapsed_seconds'),
        'stop_reason': status.get('stop_reason'),
        'launch_returncode': launch.get('returncode'),
        'latest_action_done': latest_action_done,
        'latest_action_next': latest_action_next,
        'latest_action_thought': latest_action_thought,
        'latest_action_summary': latest_action.get('summary') or preview_from_payload(latest_action, limit=160),
        'latest_response_preview': preview_from_payload(latest_action, limit=1200)
        or compact_text_preview(read_text(run_dir / 'latest_response.txt', max_chars=1200), limit=1200),
    }


def list_runs() -> list[dict[str, Any]]:
    try:
        return run_index.list_run_summaries(
            runs_dir=RUNS_DIR,
            container_blog_dir=CONTAINER_BLOG_DIR,
            agent_account_dir=AGENT_ACCOUNT_DIR,
        )
    except Exception:
        ensure_dir(RUNS_DIR)
        dirs = [path for path in RUNS_DIR.iterdir() if path.is_dir()]
        dirs.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        return [summarize_run(path) for path in dirs]


def runs_for_container(container_name: str) -> list[dict[str, Any]]:
    require_name(container_name, field='container name')
    return [run for run in list_runs() if run.get('container') == container_name]


def latest_run_summary_for_container(container_name: str) -> dict[str, Any] | None:
    runs = runs_for_container(container_name)
    return runs[0] if runs else None


def active_run_summary_for_container(container_name: str) -> dict[str, Any] | None:
    for run in runs_for_container(container_name):
        state = str(run.get('state') or '').lower()
        if run.get('supervisor_running') or state == 'running':
            return run
    return None


def container_detail(name: str) -> dict[str, Any]:
    require_name(name, field='container name')
    blog = container_blog_payload(name)
    return {
        'container': get_container_info(name),
        'container_runtime': read_container_runtime(name),
        'latest_run': latest_run_summary_for_container(name),
        'active_run': active_run_summary_for_container(name),
        'blog_posts': blog['blog_posts'],
        'latest_blog_post': blog['latest_blog_post'],
        'blog_meta': blog['blog_meta'],
        'agent_binding': container_agent_binding_payload(name),
        'saved_agent_settings': read_container_agent_settings(name),
        'agent_settings_updated_at': read_container_state_meta(name).get('agent_settings_updated_at'),
        'settings_backup_summary': container_settings_backup_summary(name),
    }

def run_detail(run_id: str) -> dict[str, Any]:
    run_dir = run_dir_for(run_id)
    try:
        indexed = run_index.get_run_payload(
            run_id,
            runs_dir=RUNS_DIR,
            container_blog_dir=CONTAINER_BLOG_DIR,
            agent_account_dir=AGENT_ACCOUNT_DIR,
        )
    except Exception:
        indexed = {}

    summary = indexed.get('summary') if isinstance(indexed.get('summary'), dict) else summarize_run(run_dir)
    latest_state_before = (
        indexed.get('latest_state_before')
        if isinstance(indexed.get('latest_state_before'), dict)
        else read_json(run_dir / 'latest_state_before.json')
    )
    latest_state_after = (
        indexed.get('latest_state_after')
        if isinstance(indexed.get('latest_state_after'), dict)
        else read_json(run_dir / 'latest_state_after.json')
    )
    recent_rounds = indexed.get('recent_rounds') if isinstance(indexed.get('recent_rounds'), list) else read_recent_rounds(run_dir / 'events.jsonl')
    self_modification = summarize_run_self_modification(run_dir, latest_state_before, latest_state_after)
    latest_round = (
        indexed.get('latest_round')
        if isinstance(indexed.get('latest_round'), dict)
        else normalize_blog_post(read_json(run_dir / 'latest_round.json'), container=summary.get('container'), run_id=run_id)
    )
    tool_source = None
    for candidate in (latest_state_after, latest_state_before):
        if isinstance(candidate, dict) and isinstance(candidate.get('tool_source'), str):
            tool_source = candidate.get('tool_source')
            break
    container_name = summary.get('container')
    invalid_response_artifacts = (
        indexed.get('invalid_response_artifacts')
        if isinstance(indexed.get('invalid_response_artifacts'), list)
        else list_invalid_response_artifacts(run_dir)
    )
    return {
        'summary': summary,
        'host_run': indexed.get('host_run') if isinstance(indexed.get('host_run'), dict) else read_json(run_dir / 'host_run.json'),
        'status': indexed.get('status') if isinstance(indexed.get('status'), dict) else read_json(run_dir / 'status.json'),
        'launch': indexed.get('launch') if isinstance(indexed.get('launch'), dict) else read_json(run_dir / 'launch.json'),
        'ui_launch': indexed.get('ui_launch') if isinstance(indexed.get('ui_launch'), dict) else read_json(run_dir / 'ui_launch.json'),
        'latest_action': indexed.get('latest_action') if isinstance(indexed.get('latest_action'), dict) else read_json(run_dir / 'latest_action.json'),
        'latest_tool_result': indexed.get('latest_tool_result') if isinstance(indexed.get('latest_tool_result'), dict) else read_json(run_dir / 'latest_tool_result.json'),
        'latest_state_before': latest_state_before,
        'latest_state_after': latest_state_after,
        'latest_round': latest_round,
        'latest_response_text': indexed.get('latest_response_text') if isinstance(indexed.get('latest_response_text'), str) else read_text(run_dir / 'latest_response.txt'),
        'latest_round_error_text': indexed.get('latest_round_error_text') if isinstance(indexed.get('latest_round_error_text'), str) else latest_round_error_text(run_dir),
        'invalid_response_artifacts': invalid_response_artifacts,
        'recent_rounds': recent_rounds,
        'blog_posts': indexed.get('blog_posts') if isinstance(indexed.get('blog_posts'), list) else read_blog_posts(run_dir / 'blog.jsonl', run_id=run_id, container=summary.get('container')),
        'observation': derive_run_observation(
            summary,
            latest_state_before,
            latest_state_after,
            recent_rounds,
            self_modification,
        ),
        'events_tail': indexed.get('events_tail') if isinstance(indexed.get('events_tail'), str) else read_text(run_dir / 'events.jsonl'),
        'live_stdout_tail': indexed.get('live_stdout_tail') if isinstance(indexed.get('live_stdout_tail'), str) else read_text(run_dir / 'live.stdout'),
        'live_stderr_tail': indexed.get('live_stderr_tail') if isinstance(indexed.get('live_stderr_tail'), str) else read_text(run_dir / 'live.stderr'),
        'supervisor_stdout_tail': indexed.get('supervisor_stdout_tail') if isinstance(indexed.get('supervisor_stdout_tail'), str) else read_text(run_dir / 'supervisor.stdout'),
        'supervisor_stderr_tail': indexed.get('supervisor_stderr_tail') if isinstance(indexed.get('supervisor_stderr_tail'), str) else read_text(run_dir / 'supervisor.stderr'),
        'tool_source': tool_source,
        'container_runtime': read_container_runtime(container_name) if isinstance(container_name, str) else None,
    }


def stop_host_process(pid: int | None) -> None:
    if not pid_is_running(pid):
        return
    os.kill(pid, signal.SIGTERM)


def stop_container(name: str) -> dict[str, Any]:
    require_name(name, field='container name')
    completed = lxc_command(['lxc-stop', '-n', name])
    return {'ok': completed.returncode == 0, 'stdout': completed.stdout, 'stderr': completed.stderr}


def start_container(name: str) -> dict[str, Any]:
    require_name(name, field='container name')
    preflight = lxc_network.resolve_container_network(
        read_container_state_meta(name),
        available_links=list_host_links(),
        allow_empty_fallback=True,
        veth_support=lxc_network.detect_veth_support(),
    )
    if preflight.get('warning'):
        return {
            'ok': False,
            'stdout': '',
            'stderr': f"{preflight['warning']}; existing container config was not modified",
            'preflight': preflight,
        }
    completed = lxc_command(['lxc-start', '-n', name])
    return {
        'ok': completed.returncode == 0,
        'stdout': completed.stdout,
        'stderr': completed.stderr,
        'preflight': preflight,
    }


def destroy_container(name: str) -> dict[str, Any]:
    require_name(name, field='container name')
    lxc_command(['lxc-stop', '-n', name])
    completed = lxc_command(['lxc-destroy', '-n', name])
    if completed.returncode == 0:
        remove_container_state_meta(name)
    return {'ok': completed.returncode == 0, 'stdout': completed.stdout, 'stderr': completed.stderr}


def clone_container(source_name: str, target_name: str, *, start: bool) -> dict[str, Any]:
    require_name(source_name, field='source container name')
    require_name(target_name, field='target container name')
    if source_name == target_name:
        raise ValueError('source and target names must differ')
    command = [str(ROOT_DIR / 'scripts' / 'clone_container.sh'), source_name, target_name]
    if start:
        command.append('--start')
    completed = subprocess.run(command, capture_output=True, text=True, cwd=str(ROOT_DIR), check=False)
    return {'ok': completed.returncode == 0, 'stdout': completed.stdout, 'stderr': completed.stderr, 'started': start}


def create_base_container(name: str, *, disable_network: bool) -> dict[str, Any]:
    require_name(name, field='container name')
    env = os.environ.copy()
    env['DISABLE_NETWORK'] = '1' if disable_network else '0'
    completed = subprocess.run(
        [str(ROOT_DIR / 'scripts' / 'create_base_container.sh'), name],
        capture_output=True,
        text=True,
        cwd=str(ROOT_DIR),
        env=env,
        check=False,
    )
    return {'ok': completed.returncode == 0, 'stdout': completed.stdout, 'stderr': completed.stderr}


def launch_supervisor(
    *,
    container: str,
    run_id: str,
    model: str,
    base_url: str,
    api_key: str,
    task_prompt: str,
    model_settings: dict[str, Any],
    max_rounds: int,
    sleep_seconds: float,
    max_runtime_seconds: int | None,
    max_total_tokens: int | None,
    agent_handle: str | None = None,
    mode: str = 'task',
) -> dict[str, Any]:
    require_name(container, field='container name')
    require_name(run_id, field='run id')
    if not api_key:
        raise ValueError('missing API key')
    run_dir = RUNS_DIR / run_id
    if run_dir.exists() and any(run_dir.iterdir()):
        raise ValueError(f'run directory already exists: {run_id}')
    ensure_dir(run_dir)
    compact_model_settings = {
        key: value
        for key, value in model_settings.items()
        if key not in {'profile_id', 'profile_label'}
    }
    command = [
        'python3',
        '-m',
        'host.orchestrator',
        '--container', container,
        '--runs-dir', str(RUNS_DIR),
        '--run-id', run_id,
        '--model', model,
        '--base-url', base_url,
        '--api-key', api_key,
        '--task-prompt', task_prompt,
        '--model-settings-json', json.dumps(compact_model_settings, ensure_ascii=True, separators=(',', ':')),
        '--max-rounds', str(max_rounds),
        '--sleep-seconds', str(sleep_seconds),
    ]
    if max_runtime_seconds is not None:
        command.extend(['--max-runtime-seconds', str(max_runtime_seconds)])
    if max_total_tokens is not None:
        command.extend(['--max-total-tokens', str(max_total_tokens)])
    stdout_path = run_dir / 'supervisor.stdout'
    stderr_path = run_dir / 'supervisor.stderr'
    with stdout_path.open('a', encoding='utf-8') as stdout_handle, stderr_path.open('a', encoding='utf-8') as stderr_handle:
        process = subprocess.Popen(
            command,
            cwd=str(ROOT_DIR),
            stdout=stdout_handle,
            stderr=stderr_handle,
            start_new_session=True,
            text=True,
        )
    (run_dir / 'supervisor.pid').write_text(f'{process.pid}\n', encoding='utf-8')
    write_json(
        run_dir / 'ui_launch.json',
        {
            'run_id': run_id,
            'container': container,
            'mode': mode,
            'model': model,
            'base_url': base_url,
            'task_prompt': task_prompt,
            'started_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'supervisor_pid': process.pid,
            'model_settings': model_settings,
            'api_key_fingerprint': api_key_fingerprint(api_key),
            'max_rounds': max_rounds,
            'sleep_seconds': sleep_seconds,
            'max_runtime_seconds': max_runtime_seconds,
            'max_total_tokens': max_total_tokens,
            'agent_handle': agent_handle,
        },
    )
    return {'ok': True, 'run_id': run_id, 'container': container, 'supervisor_pid': process.pid}


def launch_agent_for_container(
    container: str,
    *,
    model: str,
    base_url: str,
    api_key: str,
    task_prompt: str,
    model_settings: dict[str, Any],
    max_rounds: int,
    sleep_seconds: float,
    max_runtime_seconds: int | None,
    max_total_tokens: int | None,
    agent_handle: str | None = None,
    run_id: str | None = None,
    mode: str = 'task',
) -> dict[str, Any]:
    require_name(container, field='container name')
    if not api_key:
        raise ValueError('missing API key')

    resolved_agent_handle = first_text(agent_handle)
    if resolved_agent_handle:
        set_container_agent_binding(container, resolved_agent_handle)

    active = active_run_summary_for_container(container)
    if active is not None:
        return {
            'ok': True,
            'already_running': True,
            'launch': {
                'run_id': active['run_id'],
                'container': container,
                'supervisor_pid': active.get('supervisor_pid'),
            },
            'active_run': active,
        }

    prepared = prepare_container_for_agent(container)
    if not prepared.get('ok'):
        return {'ok': False, 'step': 'prepare_container', **prepared}

    final_run_id = run_id or f'{container}-{time.strftime("%Y%m%d-%H%M%S")}'
    launched = launch_supervisor(
        container=container,
        run_id=final_run_id,
        model=model,
        base_url=base_url,
        api_key=api_key,
        task_prompt=task_prompt,
        model_settings=model_settings,
        max_rounds=max_rounds,
        sleep_seconds=sleep_seconds,
        max_runtime_seconds=max_runtime_seconds,
        max_total_tokens=max_total_tokens,
        agent_handle=resolved_agent_handle,
        mode=mode,
    )
    return {'ok': True, 'prepared': prepared, 'launch': launched}


def stop_agent_for_container(container: str) -> dict[str, Any]:
    require_name(container, field='container name')
    active = active_run_summary_for_container(container)
    if active is None:
        raise ValueError(f'container has no active AI session: {container}')
    stopped = stop_run(active['run_id'])
    return {'ok': True, 'container': container, 'active_run': active, 'stop': stopped}


def retry_payload_from_run_detail(detail: dict[str, Any]) -> dict[str, Any]:
    summary = detail.get('summary') if isinstance(detail.get('summary'), dict) else {}
    host_run = detail.get('host_run') if isinstance(detail.get('host_run'), dict) else {}
    ui_launch = detail.get('ui_launch') if isinstance(detail.get('ui_launch'), dict) else {}
    ui_settings = ui_launch.get('model_settings') if isinstance(ui_launch.get('model_settings'), dict) else {}
    payload: dict[str, Any] = {
        'mode': first_text(ui_launch.get('mode'), host_run.get('mode'), summary.get('mode')) or 'task',
        'task_prompt': first_text(ui_launch.get('task_prompt'), host_run.get('task_prompt'), summary.get('task_prompt')) or DEFAULT_TASK_PROMPT,
        'model': first_text(ui_launch.get('model'), host_run.get('model'), summary.get('model')),
        'base_url': first_text(ui_launch.get('base_url'), host_run.get('base_url'), summary.get('base_url')),
        'profile_id': first_text(ui_settings.get('profile_id')),
        'reasoning_effort': first_text(ui_settings.get('reasoning_effort')),
        'temperature': first_non_null(ui_settings.get('temperature')),
        'top_p': first_non_null(ui_settings.get('top_p')),
        'max_completion_tokens': first_non_null(ui_settings.get('max_completion_tokens')),
        'request_timeout_seconds': first_non_null(ui_settings.get('request_timeout_seconds')),
        'request_max_attempts': first_non_null(ui_settings.get('request_max_attempts')),
        'request_retry_delay_seconds': first_non_null(ui_settings.get('request_retry_delay_seconds')),
        'extra_body': ui_settings.get('extra_body') if isinstance(ui_settings.get('extra_body'), dict) else {},
        'max_rounds': first_non_null(ui_launch.get('max_rounds'), host_run.get('max_rounds'), 0),
        'sleep_seconds': first_non_null(ui_launch.get('sleep_seconds'), host_run.get('sleep_seconds'), 1.0),
        'max_runtime_seconds': first_non_null(ui_launch.get('max_runtime_seconds'), host_run.get('max_runtime_seconds')),
        'max_total_tokens': first_non_null(ui_launch.get('max_total_tokens'), host_run.get('max_total_tokens')),
        'api_key_fingerprint': first_text(ui_launch.get('api_key_fingerprint'), host_run.get('api_key_fingerprint')),
    }
    resolved_agent_handle = first_text(ui_launch.get('agent_handle'), summary.get('agent_handle'))
    if resolved_agent_handle is not None:
        payload['agent_handle'] = resolved_agent_handle
    return payload


def retry_latest_run_for_container(container: str) -> dict[str, Any]:
    require_name(container, field='container name')
    active = active_run_summary_for_container(container)
    if active is not None:
        raise ValueError(f'container already has an active AI session: {container}')
    latest = latest_run_summary_for_container(container)
    if latest is None:
        raise ValueError(f'container has no previous run to retry: {container}')

    detail = run_detail(str(latest['run_id']))
    payload = retry_payload_from_run_detail(detail)
    resolved = apply_run_mode_defaults(payload, resolve_run_model_config(payload))
    expected_fingerprint = first_text(payload.get('api_key_fingerprint'))
    current_fingerprint = api_key_fingerprint(resolved.get('api_key'))
    if expected_fingerprint and current_fingerprint != expected_fingerprint:
        raise ValueError(
            'current API key does not match the original run configuration; update the model config explicitly before retrying'
        )
    agent_handle = first_text(payload.get('agent_handle'))
    launched = launch_agent_for_container(
        container,
        model=resolved['model'],
        base_url=resolved['base_url'],
        api_key=resolved['api_key'],
        task_prompt=resolved['task_prompt'],
        model_settings=resolved['model_settings'],
        max_rounds=resolved['max_rounds'],
        sleep_seconds=resolved['sleep_seconds'],
        max_runtime_seconds=resolved['max_runtime_seconds'],
        max_total_tokens=resolved['max_total_tokens'],
        agent_handle=agent_handle,
        mode=resolved['mode'],
    )
    return {
        'ok': bool(launched.get('ok')),
        'container': container,
        'retried_from_run_id': latest['run_id'],
        'retry_payload': payload,
        'resolved_mode': resolved['mode'],
        'launch': launched.get('launch'),
        'prepared': launched.get('prepared'),
        'already_running': launched.get('already_running', False),
        'error': launched.get('error'),
        'step': launched.get('step'),
    }


def restart_container(name: str) -> dict[str, Any]:
    require_name(name, field='container name')
    stopped = stop_container(name)
    if not stopped.get('ok'):
        return {'ok': False, 'container': name, 'stop': stopped}
    time.sleep(1)
    started = start_container(name)
    return {'ok': bool(started.get('ok')), 'container': name, 'stop': stopped, 'start': started}


def start_run(
    base_name: str,
    *,
    container_name: str,
    run_id: str,
    model: str,
    base_url: str,
    api_key: str,
    task_prompt: str,
    model_settings: dict[str, Any],
    max_rounds: int,
    sleep_seconds: float,
    max_runtime_seconds: int | None,
    max_total_tokens: int | None,
    agent_handle: str | None = None,
    agent_handle_explicit: bool = False,
    mode: str = 'task',
) -> dict[str, Any]:
    cloned = clone_container(base_name, container_name, start=True)
    if not cloned.get('ok'):
        return {'ok': False, 'step': 'clone_or_start', **cloned}
    try:
        resolved_agent_handle = resolve_start_run_agent_handle(
            base_name,
            agent_handle,
            explicit=agent_handle_explicit,
        )
        if resolved_agent_handle:
            set_container_agent_binding(container_name, resolved_agent_handle)
        launched = launch_agent_for_container(
            container_name,
            run_id=run_id,
            model=model,
            base_url=base_url,
            api_key=api_key,
            task_prompt=task_prompt,
            model_settings=model_settings,
            max_rounds=max_rounds,
            sleep_seconds=sleep_seconds,
            max_runtime_seconds=max_runtime_seconds,
            max_total_tokens=max_total_tokens,
            agent_handle=resolved_agent_handle,
            mode=mode,
        )
    except Exception as exc:
        destroy_container(container_name)
        return {'ok': False, 'step': 'launch_supervisor', 'error': str(exc)}
    if not launched.get('ok'):
        return {'ok': False, 'clone': cloned, **launched}
    return {
        'ok': True,
        'clone': cloned,
        'launch': launched.get('launch'),
        'prepared': launched.get('prepared'),
        'already_running': launched.get('already_running', False),
    }


def stop_run(run_id: str) -> dict[str, Any]:
    run_dir = run_dir_for(run_id)
    ensure_dir(run_dir)
    (run_dir / 'STOP').write_text('\n', encoding='utf-8')
    return {'ok': True, 'run_id': run_id, 'stop_file': str(run_dir / 'STOP')}


def destroy_run(run_id: str) -> dict[str, Any]:
    detail = run_detail(run_id)
    summary = detail['summary']
    container = summary.get('container')
    supervisor_pid = summary.get('supervisor_pid')
    result: dict[str, Any] = {'ok': True, 'run_id': run_id, 'container': container}
    stop_run(run_id)
    if isinstance(supervisor_pid, int):
        stop_host_process(supervisor_pid)
        result['supervisor_pid'] = supervisor_pid
    if isinstance(container, str):
        result['container_destroy'] = destroy_container(container)
    return result


def overview_payload() -> dict[str, Any]:
    return {
        'config': {
            'default_model': os.environ.get('MARATHON_MODEL', DEFAULT_MODEL),
            'default_base_url': os.environ.get('MARATHON_BASE_URL', DEFAULT_BASE_URL),
            'default_task_prompt': DEFAULT_TASK_PROMPT,
            'runs_dir': str(RUNS_DIR),
            'prompt_path': str(PROMPT_FILE),
            'model_profiles_path': str(MODEL_PROFILES_FILE),
        },
        'containers': list_containers(),
        'runs': list_runs(),
        'server_time': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
    }


class AppHandler(BaseHTTPRequestHandler):
    server_version = 'MarathonWebUI/0.2'

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write('%s - - [%s] %s\n' % (self.address_string(), self.log_date_time_string(), format % args))

    def send_json(self, payload: Any, *, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, content: str, *, content_type: str = 'text/plain; charset=utf-8', status: int = HTTPStatus.OK) -> None:
        body = content.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_static_asset(self, asset_path: Path) -> None:
        content_type, _ = mimetypes.guess_type(str(asset_path))
        self.send_text(
            asset_path.read_text(encoding='utf-8'),
            content_type=f'{content_type or "application/octet-stream"}; charset=utf-8',
        )

    def read_body(self) -> dict[str, Any]:
        raw_length = self.headers.get('Content-Length', '0')
        length = int(raw_length) if raw_length.isdigit() else 0
        raw = self.rfile.read(length) if length > 0 else b'{}'
        try:
            payload = json.loads(raw.decode('utf-8') or '{}')
        except json.JSONDecodeError as exc:
            raise ValueError(f'invalid JSON body: {exc}') from exc
        if not isinstance(payload, dict):
            raise ValueError('request body must be a JSON object')
        return payload

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == '/':
            index = (STATIC_DIR / 'index.html').read_text(encoding='utf-8')
            self.send_text(index, content_type='text/html; charset=utf-8')
            return
        asset_path = resolve_static_asset_path(parsed.path)
        if asset_path is not None:
            self.send_static_asset(asset_path)
            return
        if parsed.path == '/api/overview':
            self.send_json(overview_payload())
            return
        if parsed.path == '/api/prompt':
            self.send_json(read_prompt_payload())
            return
        if parsed.path == '/api/model-profiles':
            self.send_json(read_model_profiles_payload())
            return
        if parsed.path == '/api/agent-accounts':
            self.send_json(agent_accounts_payload())
            return
        if parsed.path.startswith('/api/agent-accounts/'):
            parts = [part for part in parsed.path.split('/') if part]
            if len(parts) == 3:
                handle = require_name(parts[2], field='agent handle')
                try:
                    self.send_json(agent_account_payload(handle))
                except Exception as exc:
                    self.send_json({'ok': False, 'error': str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
        if parsed.path.startswith('/api/containers/'):
            parts = [part for part in parsed.path.split('/') if part]
            if len(parts) == 4 and parts[3] == 'blog':
                name = require_name(parts[2], field='container name')
                try:
                    self.send_json(container_blog_payload(name))
                except Exception as exc:
                    self.send_json({'ok': False, 'error': str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            if len(parts) == 3:
                name = require_name(parts[2], field='container name')
                try:
                    self.send_json(container_detail(name))
                except Exception as exc:
                    self.send_json({'ok': False, 'error': str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
        if parsed.path.startswith('/api/runs/'):
            run_id = parsed.path.split('/')[-1]
            try:
                self.send_json(run_detail(run_id))
            except Exception as exc:
                self.send_json({'ok': False, 'error': str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self.send_json({'ok': False, 'error': 'not found'}, status=HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self.read_body()
            if parsed.path == '/api/prompt':
                text = payload.get('text')
                if not isinstance(text, str):
                    raise ValueError('prompt text must be a string')
                self.send_json({'ok': True, **write_prompt_payload(text)})
                return
            if parsed.path == '/api/model-profiles':
                self.send_json({'ok': True, **write_model_profiles_payload(payload)})
                return
            if parsed.path == '/api/model-connectivity-test':
                self.send_json(test_model_connectivity(payload))
                return
            if parsed.path == '/api/ingest/runs':
                require_ingest_token(self.headers, payload)
                self.send_json(ingest_api.write_run_payload(payload, runs_dir=RUNS_DIR))
                return
            if parsed.path == '/api/ingest/events':
                require_ingest_token(self.headers, payload)
                self.send_json(ingest_api.append_events_payload(payload, runs_dir=RUNS_DIR))
                return
            if parsed.path == '/api/ingest/round-posts':
                require_ingest_token(self.headers, payload)
                self.send_json(ingest_api.append_round_posts_payload(payload, runs_dir=RUNS_DIR))
                return
            if parsed.path == '/api/ingest/artifacts':
                require_ingest_token(self.headers, payload)
                self.send_json(ingest_api.write_artifacts_payload(payload, runs_dir=RUNS_DIR))
                return
            if parsed.path == '/api/agent-accounts/register':
                self.send_json(register_agent_account(payload), status=HTTPStatus.CREATED)
                return
            if parsed.path.startswith('/api/agent-accounts/') and parsed.path.endswith('/blog-posts'):
                handle = require_name(parsed.path.split('/')[-2], field='agent handle')
                auth_token, instance_id = extract_agent_write_credentials(self.headers, payload)
                self.send_json(
                    append_agent_account_post(handle, payload, auth_token=auth_token, instance_id=instance_id),
                    status=HTTPStatus.CREATED,
                )
                return
            if parsed.path.startswith('/api/containers/') and parsed.path.endswith('/agent-account'):
                name = require_name(parsed.path.split('/')[-2], field='container name')
                self.send_json(
                    {
                        'ok': True,
                        'binding': set_container_agent_binding(name, first_text(payload.get('agent_handle'))),
                    }
                )
                return
            if parsed.path.startswith('/api/containers/') and parsed.path.endswith('/settings'):
                name = require_name(parsed.path.split('/')[-2], field='container name')
                self.send_json(write_container_agent_settings(name, payload))
                return
            if parsed.path == '/api/base-containers':
                name = require_name(str(payload.get('name', '')).strip(), field='container name')
                disable_network = bool(payload.get('disable_network', False))
                self.send_json(create_base_container(name, disable_network=disable_network))
                return
            if parsed.path == '/api/containers/clone':
                source_name = require_name(str(payload.get('source_name', '')).strip(), field='source container name')
                target_name = require_name(str(payload.get('target_name', '')).strip(), field='target container name')
                self.send_json(clone_container(source_name, target_name, start=bool(payload.get('start', True))))
                return
            if parsed.path.startswith('/api/containers/') and parsed.path.endswith('/start'):
                name = require_name(parsed.path.split('/')[-2], field='container name')
                self.send_json(start_container(name))
                return
            if parsed.path.startswith('/api/containers/') and parsed.path.endswith('/stop'):
                name = require_name(parsed.path.split('/')[-2], field='container name')
                self.send_json(stop_container(name))
                return
            if parsed.path.startswith('/api/containers/') and parsed.path.endswith('/restart'):
                name = require_name(parsed.path.split('/')[-2], field='container name')
                self.send_json(restart_container(name))
                return
            if parsed.path.startswith('/api/containers/') and parsed.path.endswith('/destroy'):
                name = require_name(parsed.path.split('/')[-2], field='container name')
                self.send_json(destroy_container(name))
                return
            if parsed.path.startswith('/api/containers/') and parsed.path.endswith('/launch-agent'):
                name = require_name(parsed.path.split('/')[-2], field='container name')
                merged_payload = merge_container_agent_settings(name, payload)
                resolved = apply_run_mode_defaults(merged_payload, resolve_run_model_config(merged_payload))
                api_key = resolved['api_key']
                self.send_json(launch_agent_for_container(
                    name,
                    model=resolved['model'],
                    base_url=resolved['base_url'],
                    api_key=api_key,
                    task_prompt=resolved['task_prompt'],
                    model_settings=resolved['model_settings'],
                    max_rounds=resolved['max_rounds'],
                    sleep_seconds=resolved['sleep_seconds'],
                    max_runtime_seconds=resolved['max_runtime_seconds'],
                    max_total_tokens=resolved['max_total_tokens'],
                    agent_handle=first_text(payload.get('agent_handle')),
                    mode=resolved['mode'],
                ))
                return
            if parsed.path.startswith('/api/containers/') and parsed.path.endswith('/stop-agent'):
                name = require_name(parsed.path.split('/')[-2], field='container name')
                self.send_json(stop_agent_for_container(name))
                return
            if parsed.path.startswith('/api/containers/') and parsed.path.endswith('/retry-agent'):
                name = require_name(parsed.path.split('/')[-2], field='container name')
                self.send_json(retry_latest_run_for_container(name))
                return
            if parsed.path == '/api/runs/start':
                base_name = require_name(str(payload.get('base_name', '')).strip(), field='base container name')
                now = time.strftime('%Y%m%d-%H%M%S')
                container_name = str(payload.get('container_name') or f'marathon-{now}').strip()
                run_id = str(payload.get('run_id') or f'{container_name}-{now}').strip()
                require_name(run_id, field='run id')
                require_name(container_name, field='container name')
                merged_payload = merge_container_agent_settings(base_name, payload)
                resolved = apply_run_mode_defaults(merged_payload, resolve_run_model_config(merged_payload))
                api_key = resolved['api_key']
                agent_handle_explicit = 'agent_handle' in payload
                raw_agent_handle = payload.get('agent_handle') if agent_handle_explicit else None
                self.send_json(start_run(
                    base_name,
                    container_name=container_name,
                    run_id=run_id,
                    model=resolved['model'],
                    base_url=resolved['base_url'],
                    api_key=api_key,
                    task_prompt=resolved['task_prompt'],
                    model_settings=resolved['model_settings'],
                    max_rounds=resolved['max_rounds'],
                    sleep_seconds=resolved['sleep_seconds'],
                    max_runtime_seconds=resolved['max_runtime_seconds'],
                    max_total_tokens=resolved['max_total_tokens'],
                    agent_handle=raw_agent_handle if isinstance(raw_agent_handle, str) else None,
                    agent_handle_explicit=agent_handle_explicit,
                    mode=resolved['mode'],
                ))
                return
            if parsed.path.startswith('/api/runs/') and parsed.path.endswith('/stop'):
                run_id = require_name(parsed.path.split('/')[-2], field='run id')
                self.send_json(stop_run(run_id))
                return
            if parsed.path.startswith('/api/runs/') and parsed.path.endswith('/destroy'):
                run_id = require_name(parsed.path.split('/')[-2], field='run id')
                self.send_json(destroy_run(run_id))
                return
        except FileExistsError as exc:
            self.send_json({'ok': False, 'error': str(exc)}, status=HTTPStatus.CONFLICT)
            return
        except PermissionError as exc:
            self.send_json({'ok': False, 'error': str(exc)}, status=HTTPStatus.FORBIDDEN)
            return
        except ValueError as exc:
            self.send_json({'ok': False, 'error': str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            self.send_json({'ok': False, 'error': str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        self.send_json({'ok': False, 'error': 'not found'}, status=HTTPStatus.NOT_FOUND)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Marathon Web UI')
    parser.add_argument('--host', default=os.environ.get('MARATHON_UI_HOST', '127.0.0.1'))
    parser.add_argument('--port', type=int, default=int(os.environ.get('MARATHON_UI_PORT', '8765')))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_dir(RUNS_DIR)
    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    print(f'Marathon Web UI listening on http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('stopping web UI', file=sys.stderr)
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
