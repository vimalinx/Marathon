#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION_NAME="${MARATHON_UI_SESSION:-marathon-web-ui}"
PORT="${MARATHON_UI_PORT:-8765}"

listener_pid() {
  lsof -tiTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null | head -n 1 || true
}

listener_cmd() {
  local pid="$1"
  ps -p "${pid}" -o args= 2>/dev/null || true
}

if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
  tmux kill-session -t "${SESSION_NAME}"
  echo "Stopped tmux session ${SESSION_NAME}"
else
  echo "No tmux session named ${SESSION_NAME}"
fi

PID="$(listener_pid)"
if [[ -n "${PID}" ]]; then
  CMD="$(listener_cmd "${PID}")"
  if [[ "${CMD}" == *"python3 -m host.web_ui"* ]]; then
    kill "${PID}" 2>/dev/null || true
    echo "Stopped Marathon Web UI listener pid ${PID}"
  fi
fi
