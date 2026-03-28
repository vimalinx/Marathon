#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION_NAME="${MARATHON_UI_SESSION:-marathon-web-ui}"

if tmux has-session -t "${SESSION_NAME}" 2>/dev/null; then
  tmux kill-session -t "${SESSION_NAME}"
  echo "Stopped tmux session ${SESSION_NAME}"
else
  echo "No tmux session named ${SESSION_NAME}"
fi
