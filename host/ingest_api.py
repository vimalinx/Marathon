#!/usr/bin/env python3

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT_DIR / 'runs'
NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$')

TOP_LEVEL_TEXT_ARTIFACTS = {
    'latest_response.txt',
    'live.stdout',
    'live.stderr',
    'supervisor.stdout',
    'supervisor.stderr',
}
TOP_LEVEL_JSON_ARTIFACTS = {
    'latest_tool_result.json',
    'latest_state_before.json',
    'latest_state_after.json',
}
ROUND_TEXT_ARTIFACTS = {
    'response.txt',
    'response.invalid-01.txt',
    'response.invalid-02.txt',
    'response.invalid-03.txt',
    'response.invalid-04.txt',
}
ROUND_JSON_ARTIFACTS = {
    'request.json',
    'response_raw.json',
    'action.json',
    'tool_result.json',
    'state_before.json',
    'state_after.json',
    'commit.json',
    'error.json',
    'response.invalid-01.raw.json',
    'response.invalid-02.raw.json',
    'response.invalid-03.raw.json',
    'response.invalid-04.raw.json',
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + '\n')


def require_run_id(value: str) -> str:
    text = str(value or '').strip()
    if not NAME_RE.fullmatch(text):
        raise ValueError(f'invalid run id: {text}')
    return text


def parse_round(value: Any) -> int:
    round_num = int(value)
    if round_num <= 0:
        raise ValueError('round must be positive')
    return round_num


def run_dir(run_id: str, *, runs_dir: Path = RUNS_DIR) -> Path:
    return runs_dir / require_run_id(run_id)


def normalize_event(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError('event payload must be an object')
    normalized = dict(payload)
    normalized.setdefault('ts', time.strftime('%Y-%m-%dT%H:%M:%S%z'))
    return normalized


def normalize_round_post(payload: dict[str, Any], *, run_id: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError('round post must be an object')
    round_num = parse_round(payload.get('round'))
    normalized = dict(payload)
    normalized['type'] = str(payload.get('type') or 'round_post')
    normalized['run_id'] = str(payload.get('run_id') or run_id)
    normalized['round'] = round_num
    normalized.setdefault('ts', time.strftime('%Y-%m-%dT%H:%M:%S%z'))
    if not any(normalized.get(key) for key in ('done', 'next', 'thought', 'summary', 'error')):
        raise ValueError('round post must include at least one of done, next, thought, summary, or error')
    return normalized


def artifact_path(run_id: str, artifact: dict[str, Any], *, runs_dir: Path = RUNS_DIR) -> Path:
    name = str(artifact.get('name') or '').strip()
    if not name:
        raise ValueError('artifact name is required')
    if artifact.get('round') is None:
        if name in TOP_LEVEL_TEXT_ARTIFACTS or name in TOP_LEVEL_JSON_ARTIFACTS:
            return run_dir(run_id, runs_dir=runs_dir) / name
        raise ValueError(f'unsupported top-level artifact: {name}')
    round_num = parse_round(artifact.get('round'))
    if name in ROUND_TEXT_ARTIFACTS or name in ROUND_JSON_ARTIFACTS:
        return run_dir(run_id, runs_dir=runs_dir) / 'rounds' / f'{round_num:04d}' / name
    raise ValueError(f'unsupported round artifact: {name}')


def write_run_payload(payload: dict[str, Any], *, runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError('request body must be an object')
    run_id = require_run_id(str(payload.get('run_id') or ''))
    target_dir = run_dir(run_id, runs_dir=runs_dir)
    ensure_dir(target_dir)
    written: list[str] = []
    for key, filename in (
        ('run', 'run.json'),
        ('host_run', 'host_run.json'),
        ('ui_launch', 'ui_launch.json'),
        ('status', 'status.json'),
        ('launch', 'launch.json'),
    ):
        if key not in payload:
            continue
        value = payload.get(key)
        if not isinstance(value, dict):
            raise ValueError(f'{key} must be an object')
        write_json(target_dir / filename, value)
        written.append(filename)
    if not written:
        raise ValueError('no writable run payload provided')
    return {'ok': True, 'run_id': run_id, 'written': written}


def append_events_payload(payload: dict[str, Any], *, runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    run_id = require_run_id(str(payload.get('run_id') or ''))
    target_dir = run_dir(run_id, runs_dir=runs_dir)
    ensure_dir(target_dir)
    items = payload.get('events')
    if items is None:
        single = payload.get('event')
        items = [single] if isinstance(single, dict) else []
    if not isinstance(items, list) or not items:
        raise ValueError('events must be a non-empty list')
    count = 0
    for item in items:
        normalized = normalize_event(item)
        append_jsonl(target_dir / 'events.jsonl', normalized)
        count += 1
    return {'ok': True, 'run_id': run_id, 'appended': count}


def append_round_posts_payload(payload: dict[str, Any], *, runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    run_id = require_run_id(str(payload.get('run_id') or ''))
    target_dir = run_dir(run_id, runs_dir=runs_dir)
    ensure_dir(target_dir)
    items = payload.get('posts')
    if items is None:
        single = payload.get('post')
        items = [single] if isinstance(single, dict) else []
    if not isinstance(items, list) or not items:
        raise ValueError('posts must be a non-empty list')

    latest_post: dict[str, Any] | None = None
    count = 0
    for item in items:
        normalized = normalize_round_post(item, run_id=run_id)
        append_jsonl(target_dir / 'blog.jsonl', normalized)
        latest_post = normalized
        count += 1

    if latest_post is not None:
        write_json(target_dir / 'latest_round.json', latest_post)
        latest_action = {
            'summary': latest_post.get('summary'),
            'done': latest_post.get('done') or latest_post.get('summary'),
            'next': latest_post.get('next'),
            'thought': latest_post.get('thought'),
            'argv': latest_post.get('argv'),
            'timeout': latest_post.get('timeout'),
        }
        write_json(target_dir / 'latest_action.json', latest_action)
    return {'ok': True, 'run_id': run_id, 'appended': count}


def write_artifacts_payload(payload: dict[str, Any], *, runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    run_id = require_run_id(str(payload.get('run_id') or ''))
    target_dir = run_dir(run_id, runs_dir=runs_dir)
    ensure_dir(target_dir)
    items = payload.get('artifacts')
    if items is None:
        single = payload.get('artifact')
        items = [single] if isinstance(single, dict) else []
    if not isinstance(items, list) or not items:
        raise ValueError('artifacts must be a non-empty list')

    written: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('artifact must be an object')
        path = artifact_path(run_id, item, runs_dir=runs_dir)
        name = path.name
        if name.endswith('.json'):
            content = item.get('content')
            if not isinstance(content, (dict, list)):
                raise ValueError(f'json artifact {name} must use object or array content')
            write_json(path, content)
        else:
            content = item.get('content')
            if not isinstance(content, str):
                raise ValueError(f'text artifact {name} must use string content')
            ensure_dir(path.parent)
            path.write_text(content, encoding='utf-8')
        written.append(str(path.relative_to(target_dir)))
    return {'ok': True, 'run_id': run_id, 'written': written}
