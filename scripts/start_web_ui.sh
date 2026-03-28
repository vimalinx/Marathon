#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
SESSION_NAME="${MARATHON_UI_SESSION:-marathon-web-ui}"
HOST="${MARATHON_UI_HOST:-127.0.0.1}"
PORT="${MARATHON_UI_PORT:-8765}"
FOREGROUND="${1:-}"

mkdir -p "${ROOT_DIR}/state"

if [[ "${FOREGROUND}" == "--foreground" ]]; then
  exec python3 -m host.web_ui --host "${HOST}" --port "${PORT}"
fi

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is required for background mode; run with --foreground or install tmux" >&2
  exit 1
fi

if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
  tmux kill-session -t "${SESSION_NAME}"
fi

LOG_FILE="${ROOT_DIR}/state/web-ui.log"
CMD="cd ${ROOT_DIR@Q} && exec env PYTHONPATH=${PYTHONPATH@Q} MARATHON_UI_HOST=${HOST@Q} MARATHON_UI_PORT=${PORT@Q} python3 -m host.web_ui --host ${HOST@Q} --port ${PORT@Q} >> ${LOG_FILE@Q} 2>&1"

tmux new-session -d -s "${SESSION_NAME}" "${CMD}"
printf '%s\n' "${SESSION_NAME}" > "${ROOT_DIR}/state/web-ui.tmux-session"

echo "Marathon Web UI started in tmux session ${SESSION_NAME}"
echo "URL: http://${HOST}:${PORT}"
echo "Log: ${LOG_FILE}"
echo "Attach: tmux attach -t ${SESSION_NAME}"
