#!/usr/bin/env bash

set -euo pipefail

REPO_PATH="${1:?usage: $0 <repo_path>}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_ROOT="${MARATHON_STATE_ROOT:-${ROOT_DIR}/state}"
USER_SYSTEMD_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/systemd/user"

export PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl is not available on this host" >&2
  exit 1
fi

mkdir -p "${USER_SYSTEMD_DIR}"

CONFIG_PATH="$(
  python3 -c 'import sys; from pathlib import Path; import host.host_nightly as host_nightly; config = host_nightly.write_host_project_config(Path(sys.argv[1]), state_root=Path(sys.argv[2])); print(config["config_path"])' \
    "${REPO_PATH}" \
    "${STATE_ROOT}"
)"

UNIT_BASE="$(
  python3 -c 'import sys; from pathlib import Path; import host.host_nightly as host_nightly; config = host_nightly.load_host_project_config(Path(sys.argv[1])); print(host_nightly.systemd_unit_base_name(str(config["slug"])))' \
    "${CONFIG_PATH}"
)"

SERVICE_NAME="${UNIT_BASE}.service"
TIMER_NAME="${UNIT_BASE}.timer"
SERVICE_PATH="${USER_SYSTEMD_DIR}/${SERVICE_NAME}"
TIMER_PATH="${USER_SYSTEMD_DIR}/${TIMER_NAME}"

# The rendered service points at scripts/run_host_nightly_once.sh for execution.
python3 -c 'import sys; from pathlib import Path; import host.host_nightly as host_nightly; config = host_nightly.load_host_project_config(Path(sys.argv[1])); sys.stdout.write(host_nightly.render_systemd_service(config, root_dir=Path(sys.argv[2])))' \
  "${CONFIG_PATH}" \
  "${ROOT_DIR}" \
  > "${SERVICE_PATH}"

python3 -c 'import sys; from pathlib import Path; import host.host_nightly as host_nightly; config = host_nightly.load_host_project_config(Path(sys.argv[1])); sys.stdout.write(host_nightly.render_systemd_timer(config))' \
  "${CONFIG_PATH}" \
  > "${TIMER_PATH}"

if ! systemctl --user daemon-reload; then
  echo "systemctl --user daemon-reload failed" >&2
  exit 1
fi

systemctl --user enable --now "${TIMER_NAME}"

echo "installed ${SERVICE_NAME} and ${TIMER_NAME}"
