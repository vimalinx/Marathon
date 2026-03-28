#!/usr/bin/env bash

set -euo pipefail

BASE_NAME="${1:-marathon-base}"
RUN_NAME="${RUN_NAME:-marathon-$(date +%Y%m%d-%H%M%S)}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
DEFAULT_MODEL="gpt-5.4"
DEFAULT_BASE_URL="http://49.235.88.239:3000/v1"

source "${ROOT_DIR}/scripts/load_model_env.sh"

"${ROOT_DIR}/scripts/clone_container.sh" "${BASE_NAME}" "${RUN_NAME}" --start

cleanup() {
  if [[ "${KEEP_CONTAINER:-0}" != "1" ]]; then
    sudo -n lxc-stop -n "${RUN_NAME}" >/dev/null 2>&1 || true
    sudo -n lxc-destroy -n "${RUN_NAME}" >/dev/null 2>&1 || true
    rm -f "${ROOT_DIR}/state/containers/${RUN_NAME}.json"
  fi
}

trap cleanup EXIT

python3 "${ROOT_DIR}/host/orchestrator.py"   --container "${RUN_NAME}"   --runs-dir "${ROOT_DIR}/runs"   --model "${MARATHON_MODEL:-${DEFAULT_MODEL}}"   --base-url "${MARATHON_BASE_URL:-${DEFAULT_BASE_URL}}"   --api-key "${MARATHON_API_KEY:-}"   --max-rounds "${MAX_ROUNDS:-0}"   --sleep-seconds "${ROUND_SLEEP_SECONDS:-1}"
