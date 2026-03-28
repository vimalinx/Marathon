#!/usr/bin/env bash

set -euo pipefail

REPO_PATH="${1:?usage: $0 <repo_path>}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_ROOT="${MARATHON_STATE_ROOT:-${ROOT_DIR}/state}"
HOST_RUNS_ROOT="${MARATHON_HOST_RUNS_ROOT:-${ROOT_DIR}/host-runs}"

export PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

CONFIG_PATH="$(
  python3 -c 'import sys; from pathlib import Path; import host.host_nightly as host_nightly; config = host_nightly.write_host_project_config(Path(sys.argv[1]), state_root=Path(sys.argv[2])); print(config["config_path"])' \
    "${REPO_PATH}" \
    "${STATE_ROOT}"
)"

exec python3 "${ROOT_DIR}/host/host_nightly_runner.py" \
  --config "${CONFIG_PATH}" \
  --host-runs-root "${HOST_RUNS_ROOT}"
