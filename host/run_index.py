#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT_DIR / 'runs'
CONTAINER_BLOG_DIR = ROOT_DIR / 'state' / 'container_blogs'
AGENT_ACCOUNT_DIR = ROOT_DIR / 'state' / 'agent_accounts'
DB_PATH = ROOT_DIR / 'state' / 'run_index.sqlite3'
MAX_TEXT_PREVIEW = 16000

_INDEX_LOCK = threading.Lock()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_text(path: Path, *, max_chars: int | None = None) -> str | None:
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None
    if max_chars is None or len(content) <= max_chars:
        return content
    return content[-max_chars:]


def read_json(path: Path) -> dict[str, Any] | None:
    text = read_text(path)
    if text is None:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    text = read_text(path)
    if text is None:
        return []
    items: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def encode_json(payload: Any) -> str | None:
    if payload is None:
        return None
    return json.dumps(payload, ensure_ascii=False)


def decode_json(text: str | None) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str):
            text = value.strip()
            if text:
                return text
    return None


def compact_text_preview(text: str | None, *, limit: int = 280) -> str | None:
    if not text:
        return None
    compact = ' '.join(str(text).split())
    if not compact:
        return None
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + '…'


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
        'prompt_tokens': payload.get('prompt_tokens'),
        'completion_tokens': payload.get('completion_tokens'),
        'total_tokens': payload.get('total_tokens'),
        'tool_ok': payload.get('tool_ok'),
        'returncode': payload.get('returncode'),
        'stdout_tail': payload.get('stdout_tail'),
        'stderr_tail': payload.get('stderr_tail'),
        'sandbox_commit': payload.get('sandbox_commit'),
        'ts': payload.get('ts'),
        'failed': bool(payload.get('failed')),
        'error': payload.get('error'),
    }


def normalize_recent_round(payload: dict[str, Any]) -> dict[str, Any] | None:
    event = payload.get('event')
    if event in {'round_completed', 'round_post'}:
        return normalize_blog_post(payload, container=payload.get('container'), run_id=payload.get('run_id'))
    if event == 'round_failed':
        return {
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
            'error': payload.get('error'),
        }
    return None


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


def sanitize_public_account(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    result = dict(payload)
    result.pop('auth_token', None)
    return result


def maybe_int(value: Any) -> int | None:
    if value in (None, '', 'max'):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def pid_is_running(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def read_pid(path: Path) -> int | None:
    text = read_text(path)
    if text is None:
        return None
    try:
        return int(text.strip())
    except (TypeError, ValueError):
        return None


def run_signature(run_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(run_dir.rglob('*')):
        if '.git' in path.parts:
            continue
        relative = path.relative_to(run_dir)
        stat = path.stat()
        digest.update(str(relative).encode('utf-8', errors='replace'))
        digest.update(str(stat.st_size).encode('utf-8'))
        digest.update(str(stat.st_mtime_ns).encode('utf-8'))
    return digest.hexdigest()


def source_signature(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(str(path).encode('utf-8', errors='replace'))
        if not path.exists():
            digest.update(b'missing')
            continue
        stat = path.stat()
        digest.update(str(stat.st_size).encode('utf-8'))
        digest.update(str(stat.st_mtime_ns).encode('utf-8'))
    return digest.hexdigest()


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
    latest_response_text = read_text(run_dir / 'latest_response.txt', max_chars=1200)
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
        or compact_text_preview(latest_response_text, limit=1200),
    }


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


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    ensure_dir(db_path.parent)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        '''
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            container TEXT,
            state TEXT,
            updated_at TEXT,
            completed_rounds INTEGER,
            supervisor_running INTEGER,
            signature TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            host_run_json TEXT,
            status_json TEXT,
            launch_json TEXT,
            ui_launch_json TEXT,
            latest_action_json TEXT,
            latest_tool_result_json TEXT,
            latest_state_before_json TEXT,
            latest_state_after_json TEXT,
            latest_round_json TEXT,
            latest_response_text TEXT,
            latest_round_error_text TEXT,
            live_stdout_tail TEXT,
            live_stderr_tail TEXT,
            supervisor_stdout_tail TEXT,
            supervisor_stderr_tail TEXT,
            events_tail TEXT
        );

        CREATE TABLE IF NOT EXISTS round_posts (
            run_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            round INTEGER,
            ts TEXT,
            failed INTEGER NOT NULL DEFAULT 0,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (run_id, seq),
            FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS events (
            run_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            event TEXT,
            round INTEGER,
            ts TEXT,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (run_id, seq),
            FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS artifacts (
            run_id TEXT NOT NULL,
            artifact_key TEXT NOT NULL,
            round_num INTEGER,
            attempt INTEGER,
            text_blob TEXT,
            raw_json_text TEXT,
            path TEXT,
            PRIMARY KEY (run_id, artifact_key, path),
            FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS container_blogs (
            container_name TEXT PRIMARY KEY,
            signature TEXT NOT NULL,
            meta_json TEXT,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS container_blog_posts (
            container_name TEXT NOT NULL,
            seq INTEGER NOT NULL,
            ts TEXT,
            round INTEGER,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (container_name, seq),
            FOREIGN KEY (container_name) REFERENCES container_blogs(container_name) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS agent_accounts (
            agent_handle TEXT PRIMARY KEY,
            signature TEXT NOT NULL,
            account_json TEXT NOT NULL,
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS agent_posts (
            agent_handle TEXT NOT NULL,
            seq INTEGER NOT NULL,
            ts TEXT,
            round INTEGER,
            raw_json TEXT NOT NULL,
            PRIMARY KEY (agent_handle, seq),
            FOREIGN KEY (agent_handle) REFERENCES agent_accounts(agent_handle) ON DELETE CASCADE
        );
        '''
    )
    conn.commit()


def reindex_run(conn: sqlite3.Connection, run_dir: Path) -> None:
    summary = summarize_run(run_dir)
    signature = run_signature(run_dir)
    host_run = read_json(run_dir / 'host_run.json')
    status = read_json(run_dir / 'status.json')
    launch = read_json(run_dir / 'launch.json')
    ui_launch = read_json(run_dir / 'ui_launch.json')
    latest_action = read_json(run_dir / 'latest_action.json')
    latest_tool_result = read_json(run_dir / 'latest_tool_result.json')
    latest_state_before = read_json(run_dir / 'latest_state_before.json')
    latest_state_after = read_json(run_dir / 'latest_state_after.json')
    latest_round = read_json(run_dir / 'latest_round.json')
    latest_response_text = read_text(run_dir / 'latest_response.txt')
    live_stdout_tail = read_text(run_dir / 'live.stdout')
    live_stderr_tail = read_text(run_dir / 'live.stderr')
    supervisor_stdout_tail = read_text(run_dir / 'supervisor.stdout')
    supervisor_stderr_tail = read_text(run_dir / 'supervisor.stderr')
    events_tail = read_text(run_dir / 'events.jsonl')
    latest_error = latest_round_error_text(run_dir)
    invalid_artifacts = list_invalid_response_artifacts(run_dir)

    conn.execute('DELETE FROM runs WHERE run_id = ?', (run_dir.name,))
    conn.execute('DELETE FROM round_posts WHERE run_id = ?', (run_dir.name,))
    conn.execute('DELETE FROM events WHERE run_id = ?', (run_dir.name,))
    conn.execute('DELETE FROM artifacts WHERE run_id = ?', (run_dir.name,))

    conn.execute(
        '''
        INSERT INTO runs (
            run_id, container, state, updated_at, completed_rounds, supervisor_running, signature, summary_json,
            host_run_json, status_json, launch_json, ui_launch_json, latest_action_json, latest_tool_result_json,
            latest_state_before_json, latest_state_after_json, latest_round_json, latest_response_text,
            latest_round_error_text, live_stdout_tail, live_stderr_tail, supervisor_stdout_tail,
            supervisor_stderr_tail, events_tail
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            run_dir.name,
            summary.get('container'),
            summary.get('state'),
            summary.get('updated_at'),
            summary.get('completed_rounds'),
            1 if summary.get('supervisor_running') else 0,
            signature,
            encode_json(summary),
            encode_json(host_run),
            encode_json(status),
            encode_json(launch),
            encode_json(ui_launch),
            encode_json(latest_action),
            encode_json(latest_tool_result),
            encode_json(latest_state_before),
            encode_json(latest_state_after),
            encode_json(latest_round),
            latest_response_text,
            latest_error,
            live_stdout_tail,
            live_stderr_tail,
            supervisor_stdout_tail,
            supervisor_stderr_tail,
            events_tail,
        ),
    )

    for seq, payload in enumerate(read_jsonl(run_dir / 'blog.jsonl')):
        normalized = normalize_blog_post(payload, container=summary.get('container'), run_id=run_dir.name)
        if normalized is None:
            continue
        conn.execute(
            'INSERT INTO round_posts (run_id, seq, round, ts, failed, raw_json) VALUES (?, ?, ?, ?, ?, ?)',
            (
                run_dir.name,
                seq,
                normalized.get('round'),
                normalized.get('ts'),
                1 if normalized.get('failed') else 0,
                encode_json(normalized),
            ),
        )

    for seq, payload in enumerate(read_jsonl(run_dir / 'events.jsonl')):
        conn.execute(
            'INSERT INTO events (run_id, seq, event, round, ts, raw_json) VALUES (?, ?, ?, ?, ?, ?)',
            (
                run_dir.name,
                seq,
                payload.get('event'),
                payload.get('round'),
                payload.get('ts'),
                encode_json(payload) or '{}',
            ),
        )

    for artifact in invalid_artifacts:
        conn.execute(
            '''
            INSERT INTO artifacts (run_id, artifact_key, round_num, attempt, text_blob, raw_json_text, path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                run_dir.name,
                'invalid_response',
                artifact.get('round') if isinstance(artifact.get('round'), int) else None,
                maybe_int(artifact.get('attempt')),
                artifact.get('text'),
                artifact.get('raw_json_text'),
                artifact.get('text_path'),
            ),
        )

    if latest_error:
        conn.execute(
            '''
            INSERT INTO artifacts (run_id, artifact_key, round_num, attempt, text_blob, raw_json_text, path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                run_dir.name,
                'round_error',
                None,
                None,
                latest_error,
                None,
                None,
            ),
        )


def ensure_index_current(
    db_path: Path = DB_PATH,
    runs_dir: Path = RUNS_DIR,
    container_blog_dir: Path = CONTAINER_BLOG_DIR,
    agent_account_dir: Path = AGENT_ACCOUNT_DIR,
) -> None:
    with _INDEX_LOCK:
        conn = connect(db_path)
        try:
            init_schema(conn)
            ensure_dir(runs_dir)
            indexed = {
                row['run_id']: row['signature']
                for row in conn.execute('SELECT run_id, signature FROM runs')
            }
            present_runs: set[str] = set()
            for run_dir in sorted((path for path in runs_dir.iterdir() if path.is_dir()), key=lambda p: p.name):
                present_runs.add(run_dir.name)
                signature = run_signature(run_dir)
                if indexed.get(run_dir.name) == signature:
                    continue
                reindex_run(conn, run_dir)
            stale = set(indexed) - present_runs
            for run_id in stale:
                conn.execute('DELETE FROM runs WHERE run_id = ?', (run_id,))
            reindex_container_blogs(conn, container_blog_dir=container_blog_dir)
            reindex_agent_accounts(conn, agent_account_dir=agent_account_dir)
            conn.commit()
        finally:
            conn.close()


def reindex_container_blogs(conn: sqlite3.Connection, container_blog_dir: Path = CONTAINER_BLOG_DIR) -> None:
    ensure_dir(container_blog_dir)
    indexed = {
        row['container_name']: row['signature']
        for row in conn.execute('SELECT container_name, signature FROM container_blogs')
    }
    present: set[str] = set()
    for blog_path in sorted(container_blog_dir.glob('*.jsonl')):
        container_name = blog_path.stem
        meta_path = container_blog_dir / f'{container_name}.meta.json'
        signature = source_signature([blog_path, meta_path])
        present.add(container_name)
        if indexed.get(container_name) == signature:
            continue
        posts = []
        for payload in read_jsonl(blog_path):
            normalized = normalize_blog_post(payload, container=container_name, run_id=payload.get('run_id'))
            if normalized is not None:
                posts.append(normalized)
        meta = read_json(meta_path) or {}
        conn.execute('DELETE FROM container_blogs WHERE container_name = ?', (container_name,))
        conn.execute('DELETE FROM container_blog_posts WHERE container_name = ?', (container_name,))
        conn.execute(
            'INSERT INTO container_blogs (container_name, signature, meta_json, updated_at) VALUES (?, ?, ?, ?)',
            (
                container_name,
                signature,
                encode_json(meta),
                meta.get('updated_at') or ((posts[-1].get('ts') if posts else None)),
            ),
        )
        for seq, payload in enumerate(posts):
            conn.execute(
                'INSERT INTO container_blog_posts (container_name, seq, ts, round, raw_json) VALUES (?, ?, ?, ?, ?)',
                (container_name, seq, payload.get('ts'), payload.get('round'), encode_json(payload) or '{}'),
            )
    stale = set(indexed) - present
    for container_name in stale:
        conn.execute('DELETE FROM container_blogs WHERE container_name = ?', (container_name,))


def reindex_agent_accounts(conn: sqlite3.Connection, agent_account_dir: Path = AGENT_ACCOUNT_DIR) -> None:
    ensure_dir(agent_account_dir)
    indexed = {
        row['agent_handle']: row['signature']
        for row in conn.execute('SELECT agent_handle, signature FROM agent_accounts')
    }
    present: set[str] = set()
    for account_path in sorted(agent_account_dir.glob('*.json')):
        if account_path.name.endswith('.meta.json'):
            continue
        handle = account_path.stem
        posts_path = agent_account_dir / f'{handle}.posts.jsonl'
        signature = source_signature([account_path, posts_path])
        present.add(handle)
        if indexed.get(handle) == signature:
            continue
        account = sanitize_public_account(read_json(account_path))
        if not isinstance(account, dict):
            continue
        posts = []
        for payload in read_jsonl(posts_path):
            normalized = normalize_agent_post(payload, agent_handle=handle)
            if normalized is not None:
                posts.append(normalized)
        conn.execute('DELETE FROM agent_accounts WHERE agent_handle = ?', (handle,))
        conn.execute('DELETE FROM agent_posts WHERE agent_handle = ?', (handle,))
        conn.execute(
            'INSERT INTO agent_accounts (agent_handle, signature, account_json, updated_at) VALUES (?, ?, ?, ?)',
            (
                handle,
                signature,
                encode_json(account) or '{}',
                account.get('updated_at') or account.get('created_at'),
            ),
        )
        for seq, payload in enumerate(posts):
            conn.execute(
                'INSERT INTO agent_posts (agent_handle, seq, ts, round, raw_json) VALUES (?, ?, ?, ?, ?)',
                (handle, seq, payload.get('ts'), payload.get('round'), encode_json(payload) or '{}'),
            )
    stale = set(indexed) - present
    for handle in stale:
        conn.execute('DELETE FROM agent_accounts WHERE agent_handle = ?', (handle,))


def list_run_summaries(
    db_path: Path = DB_PATH,
    runs_dir: Path = RUNS_DIR,
    container_blog_dir: Path = CONTAINER_BLOG_DIR,
    agent_account_dir: Path = AGENT_ACCOUNT_DIR,
) -> list[dict[str, Any]]:
    ensure_index_current(
        db_path=db_path,
        runs_dir=runs_dir,
        container_blog_dir=container_blog_dir,
        agent_account_dir=agent_account_dir,
    )
    conn = connect(db_path)
    try:
        rows = conn.execute('SELECT summary_json FROM runs ORDER BY updated_at DESC, run_id DESC').fetchall()
        items = []
        for row in rows:
            payload = decode_json(row['summary_json'])
            if isinstance(payload, dict):
                items.append(payload)
        return items
    finally:
        conn.close()


def get_run_payload(
    run_id: str,
    db_path: Path = DB_PATH,
    runs_dir: Path = RUNS_DIR,
    container_blog_dir: Path = CONTAINER_BLOG_DIR,
    agent_account_dir: Path = AGENT_ACCOUNT_DIR,
) -> dict[str, Any]:
    ensure_index_current(
        db_path=db_path,
        runs_dir=runs_dir,
        container_blog_dir=container_blog_dir,
        agent_account_dir=agent_account_dir,
    )
    conn = connect(db_path)
    try:
        row = conn.execute('SELECT * FROM runs WHERE run_id = ?', (run_id,)).fetchone()
        if row is None:
            raise FileNotFoundError(f'run not found: {run_id}')

        round_rows = conn.execute('SELECT raw_json FROM round_posts WHERE run_id = ? ORDER BY seq DESC', (run_id,)).fetchall()
        event_rows = conn.execute('SELECT raw_json FROM events WHERE run_id = ? ORDER BY seq DESC LIMIT 60', (run_id,)).fetchall()
        artifact_rows = conn.execute(
            '''
            SELECT round_num, attempt, text_blob, raw_json_text, path
            FROM artifacts
            WHERE run_id = ? AND artifact_key = 'invalid_response'
            ORDER BY round_num DESC, attempt DESC
            ''',
            (run_id,),
        ).fetchall()

        blog_posts = []
        for round_row in round_rows:
            payload = decode_json(round_row['raw_json'])
            if isinstance(payload, dict):
                blog_posts.append(payload)

        recent_rounds = []
        for event_row in event_rows:
            payload = decode_json(event_row['raw_json'])
            if isinstance(payload, dict):
                normalized = normalize_recent_round(payload)
                if normalized is not None:
                    recent_rounds.append(normalized)

        invalid_response_artifacts = [
            {
                'round': artifact_row['round_num'],
                'attempt': artifact_row['attempt'],
                'text': artifact_row['text_blob'],
                'raw_json_text': artifact_row['raw_json_text'],
                'text_path': artifact_row['path'],
            }
            for artifact_row in artifact_rows
        ]

        return {
            'summary': decode_json(row['summary_json']) or {},
            'host_run': decode_json(row['host_run_json']),
            'status': decode_json(row['status_json']),
            'launch': decode_json(row['launch_json']),
            'ui_launch': decode_json(row['ui_launch_json']),
            'latest_action': decode_json(row['latest_action_json']),
            'latest_tool_result': decode_json(row['latest_tool_result_json']),
            'latest_state_before': decode_json(row['latest_state_before_json']),
            'latest_state_after': decode_json(row['latest_state_after_json']),
            'latest_round': decode_json(row['latest_round_json']),
            'latest_response_text': row['latest_response_text'],
            'latest_round_error_text': row['latest_round_error_text'],
            'recent_rounds': recent_rounds,
            'blog_posts': blog_posts,
            'events_tail': row['events_tail'],
            'live_stdout_tail': row['live_stdout_tail'],
            'live_stderr_tail': row['live_stderr_tail'],
            'supervisor_stdout_tail': row['supervisor_stdout_tail'],
            'supervisor_stderr_tail': row['supervisor_stderr_tail'],
            'invalid_response_artifacts': invalid_response_artifacts,
        }
    finally:
        conn.close()


def get_container_blog_payload(
    container_name: str,
    *,
    limit: int | None = None,
    db_path: Path = DB_PATH,
    runs_dir: Path = RUNS_DIR,
    container_blog_dir: Path = CONTAINER_BLOG_DIR,
    agent_account_dir: Path = AGENT_ACCOUNT_DIR,
) -> dict[str, Any]:
    ensure_index_current(
        db_path=db_path,
        runs_dir=runs_dir,
        container_blog_dir=container_blog_dir,
        agent_account_dir=agent_account_dir,
    )
    conn = connect(db_path)
    try:
        row = conn.execute('SELECT meta_json, updated_at FROM container_blogs WHERE container_name = ?', (container_name,)).fetchone()
        meta = decode_json(row['meta_json']) if row is not None else {}
        post_rows = conn.execute(
            'SELECT raw_json FROM container_blog_posts WHERE container_name = ? ORDER BY seq DESC',
            (container_name,),
        ).fetchall()
        posts = []
        for post_row in post_rows:
            payload = decode_json(post_row['raw_json'])
            if isinstance(payload, dict):
                posts.append(payload)
        if limit is not None:
            posts = posts[:limit]
        meta_dict = meta if isinstance(meta, dict) else {}
        return {
            'container': container_name,
            'blog_posts': posts,
            'latest_blog_post': posts[0] if posts else None,
            'blog_meta': {
                **meta_dict,
                'container': container_name,
                'post_count': meta_dict.get('post_count', len(posts)),
                'updated_at': meta_dict.get('updated_at') or (posts[0].get('ts') if posts else None),
            },
        }
    finally:
        conn.close()


def get_agent_account_payload(
    handle: str,
    *,
    limit: int | None = None,
    db_path: Path = DB_PATH,
    runs_dir: Path = RUNS_DIR,
    container_blog_dir: Path = CONTAINER_BLOG_DIR,
    agent_account_dir: Path = AGENT_ACCOUNT_DIR,
) -> dict[str, Any]:
    ensure_index_current(
        db_path=db_path,
        runs_dir=runs_dir,
        container_blog_dir=container_blog_dir,
        agent_account_dir=agent_account_dir,
    )
    conn = connect(db_path)
    try:
        row = conn.execute('SELECT account_json FROM agent_accounts WHERE agent_handle = ?', (handle,)).fetchone()
        if row is None:
            raise FileNotFoundError(f'agent account not found: {handle}')
        account = decode_json(row['account_json'])
        if not isinstance(account, dict):
            raise FileNotFoundError(f'agent account not found: {handle}')
        post_rows = conn.execute(
            'SELECT raw_json FROM agent_posts WHERE agent_handle = ? ORDER BY seq DESC',
            (handle,),
        ).fetchall()
        posts = []
        for post_row in post_rows:
            payload = decode_json(post_row['raw_json'])
            if isinstance(payload, dict):
                posts.append(payload)
        if limit is not None:
            posts = posts[:limit]
        latest_post = posts[0] if posts else None
        return {
            'account': account,
            'posts': posts,
            'latest_post': latest_post,
            'latest_preview': preview_from_payload(latest_post, limit=600),
            'post_count': len(posts),
        }
    finally:
        conn.close()


def list_agent_accounts_payload(
    db_path: Path = DB_PATH,
    runs_dir: Path = RUNS_DIR,
    container_blog_dir: Path = CONTAINER_BLOG_DIR,
    agent_account_dir: Path = AGENT_ACCOUNT_DIR,
) -> dict[str, Any]:
    ensure_index_current(
        db_path=db_path,
        runs_dir=runs_dir,
        container_blog_dir=container_blog_dir,
        agent_account_dir=agent_account_dir,
    )
    conn = connect(db_path)
    try:
        account_rows = conn.execute('SELECT agent_handle, account_json FROM agent_accounts').fetchall()
        accounts = []
        for account_row in account_rows:
            handle = account_row['agent_handle']
            detail = get_agent_account_payload(
                handle,
                db_path=db_path,
                runs_dir=runs_dir,
                container_blog_dir=container_blog_dir,
                agent_account_dir=agent_account_dir,
            )
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
        return {'accounts': accounts}
    finally:
        conn.close()
