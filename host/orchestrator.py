#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import host.model_env as model_env

model_env.load_model_env_defaults()

DEFAULT_BASE_URL = model_env.default_base_url()
DEFAULT_MODEL = model_env.default_model()
DEFAULT_TASK_PROMPT = (
    'Inspect the sandbox, identify the most useful next step, '
    'and improve the workspace incrementally while preserving an observable state.'
)
DEFAULT_PROMPT_SOURCE = Path(__file__).resolve().parent.parent / 'prompts' / 'minimal_system.txt'
DEFAULT_PROMPT_TARGET = '/opt/marathon/minimal_system.txt'
CONTAINER_BLOG_DIR = Path(__file__).resolve().parent.parent / 'state' / 'container_blogs'
CONTAINER_STATE_DIR = Path(__file__).resolve().parent.parent / 'state' / 'containers'
AGENT_ACCOUNT_DIR = Path(__file__).resolve().parent.parent / 'state' / 'agent_accounts'
DEFAULT_SYNC_FILES = [
    'run.json',
    'status.json',
    'events.jsonl',
    'blog.jsonl',
    'latest_action.json',
    'latest_tool_result.json',
    'latest_state_before.json',
    'latest_state_after.json',
    'latest_response.txt',
    'latest_round.json',
    'live.stdout',
    'live.stderr',
    'agent.pid',
]


def run_host_command(argv: list[str], *, input_text: str | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, input=input_text, capture_output=True, text=True, check=check)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def append_jsonl(path: Path, payload: object) -> None:
    with path.open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + '\n')


def read_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    payloads: list[dict[str, object]] = []
    for raw_line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        if not raw_line.strip():
            continue
        try:
            payload = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def container_state_path(name: str) -> Path:
    return CONTAINER_STATE_DIR / f'{name}.json'


def agent_account_path(handle: str) -> Path:
    return AGENT_ACCOUNT_DIR / f'{handle}.json'


def agent_account_posts_path(handle: str) -> Path:
    return AGENT_ACCOUNT_DIR / f'{handle}.posts.jsonl'


def read_container_state_meta(name: str) -> dict[str, object]:
    return read_json(container_state_path(name)) or {}


def read_agent_account(handle: str) -> dict[str, object] | None:
    return read_json(agent_account_path(handle))


def init_git_repo(path: Path) -> None:
    ensure_dir(path)
    if not (path / '.git').exists():
        run_host_command(['git', 'init', str(path)], check=True)
    run_host_command(['git', '-C', str(path), 'config', 'user.name', os.environ.get('MARATHON_GIT_NAME', 'marathon-host')], check=False)
    run_host_command(['git', '-C', str(path), 'config', 'user.email', os.environ.get('MARATHON_GIT_EMAIL', 'marathon@local')], check=False)


def git_commit(path: Path, message: str) -> dict[str, object]:
    run_host_command(['git', '-C', str(path), 'add', '-A'], check=False)
    completed = run_host_command(['git', '-C', str(path), 'commit', '--allow-empty', '-m', message], check=False)
    return {'returncode': completed.returncode, 'stdout': completed.stdout, 'stderr': completed.stderr}


def lxc_attach(container: str, command: list[str], *, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return run_host_command(['sudo', '-n', 'lxc-attach', '-n', container, '--', *command], input_text=input_text, check=False)


def read_container_file(container: str, path: str) -> str | None:
    completed = lxc_attach(container, ['bash', '-lc', f'cat {shlex.quote(path)}'])
    if completed.returncode != 0:
        return None
    return completed.stdout


def write_container_file(container: str, path: str, content: str) -> dict[str, object]:
    command = f'mkdir -p {shlex.quote(str(Path(path).parent))} && cat > {shlex.quote(path)}'
    completed = lxc_attach(container, ['bash', '-lc', command], input_text=content)
    return {'ok': completed.returncode == 0, 'stdout': completed.stdout, 'stderr': completed.stderr, 'path': path}


def write_container_stop(container: str, path: str) -> None:
    lxc_attach(container, ['bash', '-lc', f'mkdir -p {shlex.quote(str(Path(path).parent))} && touch {shlex.quote(path)}'])


def is_agent_running(container: str, pid_file: str) -> bool:
    command = (
        f'if [ ! -f {shlex.quote(pid_file)} ]; then exit 1; fi; '
        f'pid=$(cat {shlex.quote(pid_file)}); '
        'kill -0 "$pid" 2>/dev/null'
    )
    completed = lxc_attach(container, ['bash', '-lc', command])
    return completed.returncode == 0


def parse_base_url_endpoint(base_url: str) -> tuple[str, int]:
    parsed = urlparse(base_url)
    if not parsed.hostname:
        raise ValueError(f'invalid base URL: {base_url}')
    if parsed.port is not None:
        return parsed.hostname, parsed.port
    return parsed.hostname, 443 if parsed.scheme == 'https' else 80


def wait_for_container_base_url(
    container: str,
    base_url: str,
    *,
    attempts: int = 20,
    sleep_seconds: float = 1.0,
) -> bool:
    host, port = parse_base_url_endpoint(base_url)
    probe = (
        'import socket; '
        f'sock = socket.create_connection(({host!r}, {port}), timeout=2); '
        'sock.close()'
    )
    for attempt in range(attempts):
        completed = lxc_attach(container, ['python3', '-c', probe])
        if completed.returncode == 0:
            return True
        if attempt + 1 < attempts:
            time.sleep(sleep_seconds)
    return False


def start_agent(
    container: str,
    *,
    run_id: str,
    model: str,
    base_url: str,
    api_key: str,
    task_prompt: str,
    model_settings_json: str,
    max_rounds: int,
    sleep_seconds: float,
) -> dict[str, object]:
    run_dir = f'/workspace/runtime-log/{run_id}'
    pid_path = f'{run_dir}/agent.pid'
    launcher = """
import os
import subprocess
import sys

run_dir = sys.argv[1]
pid_path = sys.argv[2]
env = os.environ.copy()
env.update(
    {
        'RUN_ID': sys.argv[3],
        'MARATHON_MODEL': sys.argv[4],
        'MARATHON_BASE_URL': sys.argv[5],
        'MARATHON_API_KEY': sys.argv[6],
        'MARATHON_TASK_PROMPT': sys.argv[7],
        'MARATHON_MODEL_SETTINGS_JSON': sys.argv[8],
        'MAX_ROUNDS': sys.argv[9],
        'ROUND_SLEEP_SECONDS': sys.argv[10],
    }
)
os.makedirs(run_dir, exist_ok=True)
stdout_path = os.path.join(run_dir, 'live.stdout')
stderr_path = os.path.join(run_dir, 'live.stderr')
with open(stdout_path, 'a', encoding='utf-8') as stdout_handle, open(stderr_path, 'a', encoding='utf-8') as stderr_handle:
    process = subprocess.Popen(
        ['python3', '/opt/marathon/agent_loop.py'],
        cwd=run_dir,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=stdout_handle,
        stderr=stderr_handle,
        start_new_session=True,
        text=True,
    )
with open(pid_path, 'w', encoding='utf-8') as handle:
    handle.write(f'{process.pid}\\n')
"""
    command = [
        'python3',
        '-c',
        launcher,
        run_dir,
        pid_path,
        run_id,
        model,
        base_url,
        api_key,
        task_prompt,
        model_settings_json,
        str(max_rounds),
        str(sleep_seconds),
    ]
    completed = lxc_attach(container, command)
    return {
        'returncode': completed.returncode,
        'stdout': completed.stdout,
        'stderr': completed.stderr,
        'run_id': run_id,
        'pid_file': pid_path,
    }


def sync_prompt_to_container(container: str, prompt_source: Path, prompt_target: str) -> dict[str, object]:
    if not prompt_source.exists():
        return {'ok': False, 'error': f'prompt source missing: {prompt_source}'}
    prompt_text = prompt_source.read_text(encoding='utf-8')
    result = write_container_file(container, prompt_target, prompt_text)
    result['source'] = str(prompt_source)
    result['bytes'] = len(prompt_text.encode('utf-8'))
    return result


def sync_files(container: str, container_run_dir: str, host_run_dir: Path) -> None:
    for filename in DEFAULT_SYNC_FILES:
        content = read_container_file(container, f'{container_run_dir}/{filename}')
        if content is None:
            continue
        (host_run_dir / filename).write_text(content, encoding='utf-8')


def parse_round_value(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def sync_container_blog_archive(container: str, run_id: str, host_run_dir: Path) -> dict[str, object]:
    ensure_dir(CONTAINER_BLOG_DIR)
    source_path = host_run_dir / 'blog.jsonl'
    archive_path = CONTAINER_BLOG_DIR / f'{container}.jsonl'
    meta_path = CONTAINER_BLOG_DIR / f'{container}.meta.json'

    meta = read_json(meta_path) or {'container': container, 'post_count': 0, 'runs': {}}
    runs_meta = meta.get('runs')
    if not isinstance(runs_meta, dict):
        runs_meta = {}

    run_meta = runs_meta.get(run_id)
    if not isinstance(run_meta, dict):
        run_meta = {}
    last_round = parse_round_value(run_meta.get('last_round')) or 0

    appended = 0
    latest_round = last_round
    latest_ts = None

    for payload in read_jsonl(source_path):
        round_value = parse_round_value(payload.get('round'))
        if round_value is None or round_value <= last_round:
            continue
        post = dict(payload)
        post.setdefault('type', 'round_post')
        post.setdefault('container', container)
        post.setdefault('run_id', run_id)
        append_jsonl(archive_path, post)
        appended += 1
        latest_round = round_value
        ts_value = post.get('ts')
        if isinstance(ts_value, str) and ts_value.strip():
            latest_ts = ts_value.strip()

    if appended:
        runs_meta[run_id] = {
            'last_round': latest_round,
            'updated_at': latest_ts,
        }
        meta.update(
            {
                'container': container,
                'post_count': int(meta.get('post_count') or 0) + appended,
                'latest_run_id': run_id,
                'latest_round': latest_round,
                'updated_at': latest_ts or meta.get('updated_at') or time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                'runs': runs_meta,
            }
        )
        write_json(meta_path, meta)

    return {
        'container': container,
        'run_id': run_id,
        'appended': appended,
        'latest_round': latest_round if appended else last_round,
        'updated_at': latest_ts,
        'archive_path': str(archive_path),
    }


def sync_container_blog_to_agent_account(container: str, run_id: str, host_run_dir: Path) -> dict[str, object]:
    state_meta = read_container_state_meta(container)
    raw_handle = str(state_meta.get('agent_handle') or '').strip()
    if not raw_handle:
        return {
            'container': container,
            'run_id': run_id,
            'bound': False,
            'appended': 0,
        }

    ensure_dir(CONTAINER_BLOG_DIR)
    meta_path = CONTAINER_BLOG_DIR / f'{container}.meta.json'
    meta = read_json(meta_path) or {'container': container, 'post_count': 0, 'runs': {}}
    now = time.strftime('%Y-%m-%dT%H:%M:%S%z')

    agent_binding = meta.get('agent_binding')
    if not isinstance(agent_binding, dict) or agent_binding.get('agent_handle') != raw_handle:
        agent_binding = {
            'agent_handle': raw_handle,
            'bound_at': now,
            'updated_at': now,
            'last_account_sync_run_id': None,
            'last_account_sync_round': 0,
            'last_account_sync_at': None,
            'runs': {},
        }

    runs_meta = agent_binding.get('runs')
    if not isinstance(runs_meta, dict):
        runs_meta = {}
    run_meta = runs_meta.get(run_id)
    if not isinstance(run_meta, dict):
        run_meta = {}
    last_round = parse_round_value(run_meta.get('last_round')) or 0

    account = read_agent_account(raw_handle)
    if not isinstance(account, dict):
        agent_binding.update({'updated_at': now, 'last_error': f'agent account not found: {raw_handle}', 'runs': runs_meta})
        meta['agent_binding'] = agent_binding
        write_json(meta_path, meta)
        return {
            'container': container,
            'run_id': run_id,
            'bound': True,
            'agent_handle': raw_handle,
            'appended': 0,
            'error': f'agent account not found: {raw_handle}',
        }

    instance_id = str(account.get('instance_id') or '').strip()
    if not instance_id:
        agent_binding.update({'updated_at': now, 'last_error': f'agent account missing instance_id: {raw_handle}', 'runs': runs_meta})
        meta['agent_binding'] = agent_binding
        write_json(meta_path, meta)
        return {
            'container': container,
            'run_id': run_id,
            'bound': True,
            'agent_handle': raw_handle,
            'appended': 0,
            'error': f'agent account missing instance_id: {raw_handle}',
        }

    appended = 0
    latest_round = last_round
    latest_ts = None
    for payload in read_jsonl(host_run_dir / 'blog.jsonl'):
        round_value = parse_round_value(payload.get('round'))
        if round_value is None or round_value <= last_round:
            continue

        post = {
            'agent_handle': raw_handle,
            'post_id': payload.get('post_id') or f'{raw_handle}-{run_id}-{round_value}',
            'container': payload.get('container') or container,
            'run_id': payload.get('run_id') or run_id,
            'round': round_value,
            'summary': payload.get('summary'),
            'done': payload.get('done') or payload.get('summary'),
            'next': payload.get('next'),
            'thought': payload.get('thought'),
            'instance_id': instance_id,
            'ts': payload.get('ts') or now,
        }
        if not any(post.get(key) for key in ('done', 'next', 'thought', 'summary')):
            continue
        ensure_dir(AGENT_ACCOUNT_DIR)
        append_jsonl(agent_account_posts_path(raw_handle), post)
        appended += 1
        latest_round = round_value
        ts_value = post.get('ts')
        if isinstance(ts_value, str) and ts_value.strip():
            latest_ts = ts_value.strip()

    if appended:
        account['updated_at'] = latest_ts or now
        write_json(agent_account_path(raw_handle), account)
        runs_meta[run_id] = {
            'last_round': latest_round,
            'updated_at': latest_ts or now,
        }
        agent_binding.update(
            {
                'agent_handle': raw_handle,
                'updated_at': latest_ts or now,
                'last_account_sync_run_id': run_id,
                'last_account_sync_round': latest_round,
                'last_account_sync_at': latest_ts or now,
                'last_error': None,
                'runs': runs_meta,
            }
        )
        meta['agent_binding'] = agent_binding
        write_json(meta_path, meta)

    return {
        'container': container,
        'run_id': run_id,
        'bound': True,
        'agent_handle': raw_handle,
        'appended': appended,
        'latest_round': latest_round if appended else last_round,
        'updated_at': latest_ts,
    }


def parse_completed_rounds(status_text: str | None) -> int:
    if not status_text:
        return -1
    try:
        payload = json.loads(status_text)
    except json.JSONDecodeError:
        return -1
    if not isinstance(payload, dict):
        return -1
    value = payload.get('completed_rounds', -1)
    return int(value) if isinstance(value, int) else -1


def parse_state(status_text: str | None) -> str:
    if not status_text:
        return 'unknown'
    try:
        payload = json.loads(status_text)
    except json.JSONDecodeError:
        return 'unknown'
    if not isinstance(payload, dict):
        return 'unknown'
    state = payload.get('state', 'unknown')
    return state if isinstance(state, str) else 'unknown'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Host supervisor for the in-container Marathon agent')
    parser.add_argument('--container', required=True, help='LXC container name')
    parser.add_argument('--runs-dir', default='runs', help='Host directory for mirrored run logs')
    parser.add_argument('--run-id', default='', help='Optional explicit run id')
    parser.add_argument('--model', default=os.environ.get('MARATHON_MODEL', DEFAULT_MODEL))
    parser.add_argument('--base-url', default=os.environ.get('MARATHON_BASE_URL', DEFAULT_BASE_URL))
    parser.add_argument('--api-key', default=os.environ.get('MARATHON_API_KEY', ''))
    parser.add_argument('--task-prompt', default=os.environ.get('MARATHON_TASK_PROMPT', DEFAULT_TASK_PROMPT))
    parser.add_argument('--model-settings-json', default=os.environ.get('MARATHON_MODEL_SETTINGS_JSON', '{}'))
    parser.add_argument('--prompt-source', default=str(DEFAULT_PROMPT_SOURCE))
    parser.add_argument('--prompt-target', default=DEFAULT_PROMPT_TARGET)
    parser.add_argument('--max-rounds', type=int, default=int(os.environ.get('MAX_ROUNDS', '0')), help='0 means infinite')
    parser.add_argument('--sleep-seconds', type=float, default=float(os.environ.get('ROUND_SLEEP_SECONDS', '1')))
    parser.add_argument('--sync-interval', type=float, default=float(os.environ.get('MARATHON_SYNC_INTERVAL', '2')))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.api_key:
        print('missing --api-key or MARATHON_API_KEY', file=sys.stderr)
        sys.exit(2)

    run_id = args.run_id or time.strftime('run-%Y%m%d-%H%M%S')
    host_run_dir = Path(args.runs_dir) / run_id
    ensure_dir(host_run_dir)
    init_git_repo(host_run_dir)

    prompt_source = Path(args.prompt_source)
    prompt_text = prompt_source.read_text(encoding='utf-8') if prompt_source.exists() else ''
    if prompt_text:
        (host_run_dir / 'prompt.txt').write_text(prompt_text, encoding='utf-8')

    metadata = {
        'run_id': run_id,
        'container': args.container,
        'model': args.model,
        'base_url': args.base_url,
        'task_prompt': args.task_prompt,
        'model_settings': json.loads(args.model_settings_json or '{}'),
        'started_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'max_rounds': args.max_rounds,
        'sleep_seconds': args.sleep_seconds,
        'sync_interval': args.sync_interval,
        'runtime': 'agent-inside-container',
        'prompt_source': str(prompt_source),
        'prompt_target': args.prompt_target,
    }
    write_json(host_run_dir / 'host_run.json', metadata)

    prompt_sync = sync_prompt_to_container(args.container, prompt_source, args.prompt_target)
    write_json(host_run_dir / 'prompt_sync.json', prompt_sync)
    git_commit(host_run_dir, 'prompt synced')
    if not prompt_sync.get('ok'):
        print(json.dumps({'event': 'prompt_sync_failed', **prompt_sync}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    if not wait_for_container_base_url(args.container, args.base_url):
        print(
            json.dumps(
                {
                    'event': 'base_url_connectivity_failed',
                    'container': args.container,
                    'base_url': args.base_url,
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    launch = start_agent(
        args.container,
        run_id=run_id,
        model=args.model,
        base_url=args.base_url,
        api_key=args.api_key,
        task_prompt=args.task_prompt,
        model_settings_json=args.model_settings_json or '{}',
        max_rounds=args.max_rounds,
        sleep_seconds=args.sleep_seconds,
    )
    write_json(host_run_dir / 'launch.json', launch)
    git_commit(host_run_dir, 'run launched')
    if launch['returncode'] != 0:
        print(json.dumps({'event': 'launch_failed', **launch}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

    container_run_dir = f'/workspace/runtime-log/{run_id}'
    stop_file = f'{container_run_dir}/STOP'
    pid_file = f'{container_run_dir}/agent.pid'
    last_committed_round = -1
    stop_sent = False

    try:
        while True:
            if (host_run_dir / 'STOP').exists() and not stop_sent:
                write_container_stop(args.container, stop_file)
                stop_sent = True

            sync_files(args.container, container_run_dir, host_run_dir)
            sync_container_blog_archive(args.container, run_id, host_run_dir)
            sync_container_blog_to_agent_account(args.container, run_id, host_run_dir)
            status_text = (host_run_dir / 'status.json').read_text(encoding='utf-8') if (host_run_dir / 'status.json').exists() else None
            completed_rounds = parse_completed_rounds(status_text)
            state = parse_state(status_text)

            if completed_rounds > last_committed_round:
                git_commit(host_run_dir, f'round {completed_rounds}')
                last_committed_round = completed_rounds
                print(json.dumps({'event': 'host_synced', 'round': completed_rounds, 'state': state}, ensure_ascii=False), flush=True)

            running = is_agent_running(args.container, pid_file)
            if not running and state in {'completed', 'stopped', 'failed', 'interrupted'}:
                break
            if not running and state == 'unknown':
                break
            time.sleep(max(args.sync_interval, 0.2))
    except KeyboardInterrupt:
        if not stop_sent:
            write_container_stop(args.container, stop_file)
        print('stop requested on host', file=sys.stderr)

    sync_files(args.container, container_run_dir, host_run_dir)
    sync_container_blog_archive(args.container, run_id, host_run_dir)
    sync_container_blog_to_agent_account(args.container, run_id, host_run_dir)
    final_status = (host_run_dir / 'status.json').read_text(encoding='utf-8') if (host_run_dir / 'status.json').exists() else None
    git_commit(host_run_dir, f'run finished: {parse_state(final_status)}')


if __name__ == '__main__':
    main()
