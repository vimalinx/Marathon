#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"
SESSION_NAME="${MARATHON_UI_SESSION:-marathon-web-ui}"
HOST="${MARATHON_UI_HOST:-127.0.0.1}"
PORT="${MARATHON_UI_PORT:-8765}"
FOREGROUND="${1:-}"

mkdir -p "${ROOT_DIR}/state"

listener_pid() {
  lsof -tiTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null | head -n 1 || true
}

listener_cmd() {
  local pid="$1"
  ps -p "${pid}" -o args= 2>/dev/null || true
}

wait_for_port() {
  local attempts="${1:-20}"
  local delay="${2:-0.2}"
  local pid=""
  for _ in $(seq 1 "${attempts}"); do
    pid="$(listener_pid)"
    if [[ -n "${pid}" ]]; then
      return 0
    fi
    sleep "${delay}"
  done
  return 1
}

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

EXISTING_PID="$(listener_pid)"
if [[ -n "${EXISTING_PID}" ]]; then
  EXISTING_CMD="$(listener_cmd "${EXISTING_PID}")"
  if [[ "${EXISTING_CMD}" == *"python3 -m host.web_ui"* ]]; then
    echo "Marathon Web UI is already listening on http://${HOST}:${PORT} (pid ${EXISTING_PID})"
    exit 0
  fi
  echo "Port ${PORT} is already in use by: ${EXISTING_CMD}" >&2
  echo "Refusing to start Marathon Web UI until that listener is stopped." >&2
  exit 1
fi

LOG_FILE="${ROOT_DIR}/state/web-ui.log"
CMD="cd ${ROOT_DIR@Q} && exec env PYTHONPATH=${PYTHONPATH@Q} MARATHON_UI_HOST=${HOST@Q} MARATHON_UI_PORT=${PORT@Q} python3 -m host.web_ui --host ${HOST@Q} --port ${PORT@Q} >> ${LOG_FILE@Q} 2>&1"

tmux new-session -d -s "${SESSION_NAME}" "${CMD}"
printf '%s\n' "${SESSION_NAME}" > "${ROOT_DIR}/state/web-ui.tmux-session"

if ! wait_for_port 30 0.2; then
  echo "Marathon Web UI failed to bind http://${HOST}:${PORT}" >&2
  tail -n 20 "${LOG_FILE}" >&2 || true
  exit 1
fi

echo "Marathon Web UI started in tmux session ${SESSION_NAME}"
echo "URL: http://${HOST}:${PORT}"
echo "Log: ${LOG_FILE}"
echo "Attach: tmux attach -t ${SESSION_NAME}"
