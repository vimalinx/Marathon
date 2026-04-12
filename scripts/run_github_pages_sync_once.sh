#!/usr/bin/env bash

set -euo pipefail

REPO_PATH="${1:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -z "${REPO_PATH}" ]]; then
  REPO_PATH="${ROOT_DIR}"
fi
STATE_ROOT="${MARATHON_STATE_ROOT:-${ROOT_DIR}/state}"

export PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

CONFIG_PATH="$(
  python3 -c 'import sys; from pathlib import Path; import host.github_pages_sync as sync; config = sync.write_config(Path(sys.argv[1]), state_root=Path(sys.argv[2])); print(config["config_path"])' \
    "${REPO_PATH}" \
    "${STATE_ROOT}"
)"

exec python3 -m host.github_pages_sync --config "${CONFIG_PATH}"
