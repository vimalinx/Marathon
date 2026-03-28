#!/usr/bin/env bash

set -euo pipefail

BASE_NAME="${1:-marathon-base}"
DISTRO="${DISTRO:-ubuntu}"
RELEASE="${RELEASE:-noble}"
ARCH="${ARCH:-amd64}"
MEMORY_LIMIT="${MEMORY_LIMIT:-2147483648}"
CPU_MAX="${CPU_MAX:-200000 100000}"
PIDS_MAX="${PIDS_MAX:-512}"
DISABLE_NETWORK="${DISABLE_NETWORK:-0}"
BRIDGE_NAME="${BRIDGE_NAME:-}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LXC_DIR="/var/lib/lxc/${BASE_NAME}"
ROOTFS_DIR="${LXC_DIR}/rootfs"
STATE_DIR="${ROOT_DIR}/state/containers"
META_FILE="${STATE_DIR}/${BASE_NAME}.json"

choose_bridge() {
  if [[ -n "${BRIDGE_NAME}" ]]; then
    if ! ip link show "${BRIDGE_NAME}" >/dev/null 2>&1; then
      return 1
    fi
    echo "${BRIDGE_NAME}"
    return 0
  fi
  if ip link show lxcbr0 >/dev/null 2>&1; then
    echo "lxcbr0"
    return 0
  fi
  if ip link show virbr0 >/dev/null 2>&1; then
    echo "virbr0"
    return 0
  fi
}

suggest_static_ip_json() {
  local container_name="$1"
  local bridge_cidr="$2"
  python3 "${ROOT_DIR}/host/lxc_network.py" suggest-static-ip \
    --container-name "${container_name}" \
    --bridge-cidr "${bridge_cidr}" \
    --state-dir "${STATE_DIR}"
}

write_guest_netplan() {
  local network_mode="$1"
  python3 "${ROOT_DIR}/host/lxc_network.py" render-netplan \
    --network-mode "${network_mode}" \
    | sudo -n tee "${ROOTFS_DIR}/etc/netplan/10-lxc.yaml" >/dev/null
}

write_meta() {
  local network_mode="$1"
  local bridge_name="$2"
  local bridge_cidr="$3"
  local ipv4_address="$4"
  local ipv4_gateway="$5"
  mkdir -p "${STATE_DIR}"
  python3 - <<PY2
import json
from pathlib import Path
payload = {
    "container_name": ${BASE_NAME@Q},
    "network_mode": ${network_mode@Q},
    "bridge_name": ${bridge_name@Q},
    "bridge_cidr": ${bridge_cidr@Q},
    "ipv4_address": ${ipv4_address@Q},
    "ipv4_gateway": ${ipv4_gateway@Q},
}
Path(${META_FILE@Q}).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY2
}

if ! command -v lxc-create >/dev/null 2>&1; then
  echo "missing lxc-create" >&2
  exit 1
fi

if [[ -d "${LXC_DIR}" ]]; then
  echo "container ${BASE_NAME} already exists at ${LXC_DIR}" >&2
  exit 1
fi

sudo -n lxc-create -n "${BASE_NAME}" -t download -- -d "${DISTRO}" -r "${RELEASE}" -a "${ARCH}"

sudo -n tee -a "${LXC_DIR}/config" >/dev/null <<EOF2
lxc.apparmor.profile = generated
lxc.apparmor.allow_nesting = 1
lxc.cap.drop = sys_module mac_admin mac_override sys_time sys_rawio
lxc.mount.auto = proc:mixed sys:ro cgroup:mixed
lxc.cgroup2.memory.max = ${MEMORY_LIMIT}
lxc.cgroup2.cpu.max = ${CPU_MAX}
lxc.cgroup2.pids.max = ${PIDS_MAX}
EOF2

NETWORK_MODE=""
NETWORK_BRIDGE=""
BRIDGE_CIDR=""
IPV4_ADDRESS=""
IPV4_GATEWAY=""

if [[ "${DISABLE_NETWORK}" == "1" ]]; then
  NETWORK_MODE="empty"
  sudo -n tee -a "${LXC_DIR}/config" >/dev/null <<EOF2
lxc.net.0.type = empty
EOF2
else
  NETWORK_BRIDGE="$(choose_bridge || true)"
  if [[ -n "${BRIDGE_NAME}" && -z "${NETWORK_BRIDGE}" ]]; then
    echo "requested bridge ${BRIDGE_NAME} was not found" >&2
    sudo -n lxc-destroy -n "${BASE_NAME}" >/dev/null 2>&1 || true
    exit 1
  fi
  if [[ -z "${NETWORK_BRIDGE}" ]]; then
    echo "no stable bridge found; creating ${BASE_NAME} with empty network" >&2
    NETWORK_MODE="empty"
    sudo -n tee -a "${LXC_DIR}/config" >/dev/null <<EOF2
lxc.net.0.type = empty
EOF2
  elif [[ "${NETWORK_BRIDGE}" == "lxcbr0" ]]; then
    NETWORK_MODE="bridge-dhcp"
  fi
  if [[ -n "${NETWORK_BRIDGE}" && "${NETWORK_BRIDGE}" != "lxcbr0" ]]; then
    BRIDGE_CIDR="$(ip -4 addr show "${NETWORK_BRIDGE}" | awk '/inet / {print $2; exit}')"
    if [[ -z "${BRIDGE_CIDR}" ]]; then
      echo "bridge ${NETWORK_BRIDGE} has no IPv4 address" >&2
      sudo -n lxc-destroy -n "${BASE_NAME}" >/dev/null 2>&1 || true
      exit 1
    fi
    IP_JSON="$(suggest_static_ip_json "${BASE_NAME}" "${BRIDGE_CIDR}")"
    mapfile -t IP_INFO < <(python3 - "${IP_JSON}" <<'PY2'
import json
import sys
payload = json.loads(sys.argv[1])
print(payload["ipv4_address"])
print(payload["ipv4_gateway"])
PY2
)
    IPV4_ADDRESS="${IP_INFO[0]}"
    IPV4_GATEWAY="${IP_INFO[1]}"
    NETWORK_MODE="bridge-static"
    sudo -n tee -a "${LXC_DIR}/config" >/dev/null <<EOF2
lxc.net.0.type = veth
lxc.net.0.link = ${NETWORK_BRIDGE}
lxc.net.0.flags = up
lxc.net.0.ipv4.address = ${IPV4_ADDRESS}
lxc.net.0.ipv4.gateway = ${IPV4_GATEWAY}
EOF2
  fi
fi

write_meta "${NETWORK_MODE}" "${NETWORK_BRIDGE}" "${BRIDGE_CIDR}" "${IPV4_ADDRESS}" "${IPV4_GATEWAY}"

sudo -n lxc-start -n "${BASE_NAME}"
sleep 5

sudo -n lxc-attach -n "${BASE_NAME}" -- bash -lc 'rm -f /etc/resolv.conf && printf "nameserver 1.1.1.1\nnameserver 8.8.8.8\n" > /etc/resolv.conf'
sudo -n lxc-attach -n "${BASE_NAME}" -- bash -lc 'apt-get update && apt-get install -y python3 git'
sudo -n lxc-attach -n "${BASE_NAME}" -- mkdir -p /opt/marathon /workspace/sandbox /workspace/runtime-log
write_guest_netplan "${NETWORK_MODE}"
cat "${ROOT_DIR}/container/agent_tools.py" | sudo -n lxc-attach -n "${BASE_NAME}" -- tee /opt/marathon/agent_tools.py >/dev/null
cat "${ROOT_DIR}/container/agent_loop.py" | sudo -n lxc-attach -n "${BASE_NAME}" -- tee /opt/marathon/agent_loop.py >/dev/null
cat "${ROOT_DIR}/prompts/minimal_system.txt" | sudo -n lxc-attach -n "${BASE_NAME}" -- tee /opt/marathon/minimal_system.txt >/dev/null
sudo -n lxc-attach -n "${BASE_NAME}" -- chmod +x /opt/marathon/agent_tools.py /opt/marathon/agent_loop.py

sudo -n lxc-attach -n "${BASE_NAME}" -- bash -lc 'cd /workspace/sandbox && git init && git config user.name marathon-agent && git config user.email marathon@local'
sudo -n lxc-attach -n "${BASE_NAME}" -- bash -lc 'cat > /workspace/sandbox/START.txt <<"EOF2"
You are running inside this container.
Your only built-in external capability is command execution through /opt/marathon/agent_tools.py.
Your agent loop also lives here at /opt/marathon/agent_loop.py.
You may inspect or modify both files yourself.
EOF2'
sudo -n lxc-attach -n "${BASE_NAME}" -- bash -lc 'cd /workspace/sandbox && git add -A && git commit -m "seed sandbox"'

sudo -n lxc-stop -n "${BASE_NAME}"

echo "created base container: ${BASE_NAME}"
echo "network mode: ${NETWORK_MODE}"
if [[ -n "${NETWORK_BRIDGE}" ]]; then
  echo "bridge: ${NETWORK_BRIDGE}"
fi
if [[ -n "${IPV4_ADDRESS}" ]]; then
  echo "ipv4: ${IPV4_ADDRESS} via ${IPV4_GATEWAY}"
fi
