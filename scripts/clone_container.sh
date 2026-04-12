#!/usr/bin/env bash

set -euo pipefail

SOURCE_NAME="${1:?source container name required}"
TARGET_NAME="${2:?target container name required}"
START_AFTER="${3:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${ROOT_DIR}/state/containers"
SOURCE_META="${STATE_DIR}/${SOURCE_NAME}.json"
TARGET_META="${STATE_DIR}/${TARGET_NAME}.json"
TARGET_CONFIG="/var/lib/lxc/${TARGET_NAME}/config"
TARGET_ROOTFS="/var/lib/lxc/${TARGET_NAME}/rootfs"

bridge_exists() {
  local bridge_name="$1"
  [[ -n "${bridge_name}" ]] && ip link show "${bridge_name}" >/dev/null 2>&1
}

rewrite_network_config() {
  local config_path="$1"
  local network_mode="$2"
  local bridge_name="${3:-}"
  local ipv4_address="${4:-}"
  local ipv4_gateway="${5:-}"
  sudo -n python3 "${ROOT_DIR}/host/lxc_network.py" rewrite-config \
    --path "${config_path}" \
    --network-mode "${network_mode}" \
    --bridge-name "${bridge_name}" \
    --ipv4-address "${ipv4_address}" \
    --ipv4-gateway "${ipv4_gateway}"
}

suggest_static_ip_json() {
  local target_name="$1"
  local bridge_cidr="$2"
  python3 "${ROOT_DIR}/host/lxc_network.py" suggest-static-ip \
    --container-name "${target_name}" \
    --bridge-cidr "${bridge_cidr}" \
    --state-dir "${STATE_DIR}"
}

write_guest_netplan() {
  local network_mode="$1"
  python3 "${ROOT_DIR}/host/lxc_network.py" render-netplan \
    --network-mode "${network_mode}" \
    | sudo -n tee "${TARGET_ROOTFS}/etc/netplan/10-lxc.yaml" >/dev/null
}

sudo -n lxc-copy -n "${SOURCE_NAME}" -N "${TARGET_NAME}"
mkdir -p "${STATE_DIR}"

if [[ -f "${SOURCE_META}" ]]; then
  mapfile -t META_INFO < <(python3 - "$SOURCE_META" <<'PY2'
import json
import sys
with open(sys.argv[1], 'r', encoding='utf-8') as handle:
    payload = json.load(handle)
print(payload.get('network_mode', ''))
print(payload.get('bridge_name', ''))
print(payload.get('bridge_cidr', ''))
print(payload.get('ipv4_gateway', ''))
print(json.dumps(payload.get('agent_settings') or {}, ensure_ascii=False))
print(payload.get('agent_settings_updated_at', ''))
PY2
)
  NETWORK_MODE="${META_INFO[0]}"
  BRIDGE_NAME="${META_INFO[1]}"
  BRIDGE_CIDR="${META_INFO[2]}"
  IPV4_GATEWAY="${META_INFO[3]}"
  AGENT_SETTINGS_JSON="${META_INFO[4]}"
  AGENT_SETTINGS_UPDATED_AT="${META_INFO[5]}"
  TARGET_IPV4=""
  NETWORK_WARNING=""

  if [[ "${NETWORK_MODE}" == "bridge-static" && -n "${BRIDGE_NAME}" && -n "${BRIDGE_CIDR}" ]]; then
    if bridge_exists "${BRIDGE_NAME}"; then
      IP_JSON="$(suggest_static_ip_json "${TARGET_NAME}" "${BRIDGE_CIDR}")"
      mapfile -t IP_INFO < <(python3 - "${IP_JSON}" <<'PY2'
import json
import sys
payload = json.loads(sys.argv[1])
print(payload["ipv4_address"])
print(payload["ipv4_gateway"])
PY2
)
      TARGET_IPV4="${IP_INFO[0]}"
      IPV4_GATEWAY="${IP_INFO[1]}"
      rewrite_network_config "${TARGET_CONFIG}" "${NETWORK_MODE}" "${BRIDGE_NAME}" "${TARGET_IPV4}" "${IPV4_GATEWAY}"
    else
      NETWORK_WARNING="source bridge ${BRIDGE_NAME} is missing; cloned container will use empty network"
      NETWORK_MODE="empty"
      BRIDGE_NAME=""
      BRIDGE_CIDR=""
      IPV4_GATEWAY=""
      rewrite_network_config "${TARGET_CONFIG}" "${NETWORK_MODE}"
    fi
  elif [[ "${NETWORK_MODE}" == "bridge-dhcp" ]]; then
    DHCP_BRIDGE="${BRIDGE_NAME:-lxcbr0}"
    if ! bridge_exists "${DHCP_BRIDGE}"; then
      NETWORK_WARNING="source bridge ${DHCP_BRIDGE} is missing; cloned container will use empty network"
      NETWORK_MODE="empty"
      BRIDGE_NAME=""
      BRIDGE_CIDR=""
      IPV4_GATEWAY=""
      rewrite_network_config "${TARGET_CONFIG}" "${NETWORK_MODE}"
    fi
  fi

  write_guest_netplan "${NETWORK_MODE}"

  python3 - <<PY2
import json
from pathlib import Path
payload = {
    'container_name': ${TARGET_NAME@Q},
    'network_mode': ${NETWORK_MODE@Q},
    'bridge_name': ${BRIDGE_NAME@Q},
    'bridge_cidr': ${BRIDGE_CIDR@Q},
    'ipv4_address': ${TARGET_IPV4@Q},
    'ipv4_gateway': ${IPV4_GATEWAY@Q},
}
agent_settings = json.loads(${AGENT_SETTINGS_JSON@Q} or '{}')
if isinstance(agent_settings, dict) and agent_settings:
    payload['agent_settings'] = agent_settings
if ${AGENT_SETTINGS_UPDATED_AT@Q}:
    payload['agent_settings_updated_at'] = ${AGENT_SETTINGS_UPDATED_AT@Q}
Path(${TARGET_META@Q}).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding='utf-8')
PY2
  if [[ -n "${NETWORK_WARNING}" ]]; then
    echo "${NETWORK_WARNING}" >&2
  fi
fi

if [[ "${START_AFTER}" == "--start" ]]; then
  sudo -n lxc-start -n "${TARGET_NAME}"
fi
