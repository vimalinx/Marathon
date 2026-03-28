#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${MARATHON_CONTAINER_STATE_DIR:-${ROOT_DIR}/state/containers}"
CONTAINER_ROOT="${MARATHON_LXC_ROOT:-/var/lib/lxc}"

export PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

exec python3 "${ROOT_DIR}/host/prune_container_state.py" \
  --state-dir "${STATE_DIR}" \
  --container-root "${CONTAINER_ROOT}" \
  "$@"
