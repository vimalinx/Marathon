#!/usr/bin/env bash

set -euo pipefail

USER_NAME="${1:-$(id -un)}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUDOERS_FILE="/etc/sudoers.d/marathon-lxc"
TEMP_FILE="$(mktemp)"

cleanup() {
  rm -f "${TEMP_FILE}"
}

trap cleanup EXIT

if [[ "${PROJECT_DIR}" =~ [[:space:]] ]]; then
  echo "project path contains whitespace; cannot generate a safe sudoers command match" >&2
  exit 1
fi

RULE="${USER_NAME} ALL=(root) NOPASSWD: /usr/bin/lxc-create, /usr/bin/lxc-start, /usr/bin/lxc-stop, /usr/bin/lxc-destroy, /usr/bin/lxc-attach, /usr/bin/lxc-info, /usr/bin/lxc-ls, /usr/bin/lxc-copy, /usr/bin/tee, /usr/bin/python3 ${PROJECT_DIR}/host/lxc_network.py *"

printf '%s\n' "${RULE}" > "${TEMP_FILE}"
visudo -cf "${TEMP_FILE}"
echo "requesting sudo to install ${SUDOERS_FILE}" >&2
sudo -v
sudo cp "${TEMP_FILE}" "${SUDOERS_FILE}"
sudo chmod 440 "${SUDOERS_FILE}"
sudo visudo -cf "${SUDOERS_FILE}"

printf 'installed %s for user %s\n' "${SUDOERS_FILE}" "${USER_NAME}"
