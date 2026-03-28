#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
from typing import Mapping, Sequence

MANAGED_NET0_KEYS = {
    "lxc.net.0.type",
    "lxc.net.0.link",
    "lxc.net.0.flags",
    "lxc.net.0.ipv4.address",
    "lxc.net.0.ipv4.gateway",
}


def parse_link_names(ip_br_output: str) -> list[str]:
    names: list[str] = []
    for raw_line in ip_br_output.splitlines():
        parts = raw_line.split()
        if parts:
            names.append(parts[0])
    return names


def choose_preferred_bridge(available_links: Sequence[str], explicit_bridge: str = "") -> str:
    explicit_bridge = explicit_bridge.strip()
    if explicit_bridge:
        return explicit_bridge
    for candidate in ("lxcbr0", "virbr0"):
        if candidate in available_links:
            return candidate
    return ""


def detect_veth_support(
    *,
    kernel_release: str | None = None,
    modules_root: Path = Path("/lib/modules"),
    sys_module_root: Path = Path("/sys/module"),
) -> dict[str, str | bool]:
    release = kernel_release or os.uname().release
    if (sys_module_root / "veth").exists():
        return {"available": True, "reason": "", "kernel_release": release}

    release_dir = modules_root / release
    if not release_dir.exists():
        installed = sorted(path.name for path in modules_root.iterdir() if path.is_dir()) if modules_root.exists() else []
        installed_desc = ", ".join(str(modules_root / name) for name in installed) if installed else f"no directories under {modules_root}"
        return {
            "available": False,
            "reason": f"kernel/modules mismatch: running {release} but only {installed_desc} exists",
            "kernel_release": release,
        }

    matches = list(release_dir.rglob("veth.ko*"))
    if matches:
        return {"available": True, "reason": "", "kernel_release": release}

    return {
        "available": False,
        "reason": f"veth module missing under {release_dir}",
        "kernel_release": release,
    }


def read_meta_file(path: Path) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def container_definition_exists(
    payload: Mapping[str, object],
    *,
    path: Path,
    container_root: Path,
) -> bool:
    if not container_root.exists():
        return True
    container_name = str(payload.get("container_name") or path.stem).strip()
    if not container_name:
        return True
    return (container_root / container_name).is_dir()


def used_ipv4_addresses(
    state_dir: Path,
    *,
    bridge_cidr: str,
    container_root: Path | None = None,
) -> set[ipaddress.IPv4Address]:
    try:
        bridge_interface = ipaddress.ip_interface(bridge_cidr)
    except ValueError:
        return set()

    used: set[ipaddress.IPv4Address] = set()
    if not state_dir.exists():
        return used

    for path in state_dir.glob("*.json"):
        payload = read_meta_file(path)
        if not payload:
            continue
        if container_root is not None and not container_definition_exists(payload, path=path, container_root=container_root):
            continue
        raw = str(payload.get("ipv4_address") or "").strip()
        if not raw:
            continue
        try:
            address_interface = ipaddress.ip_interface(raw)
        except ValueError:
            continue
        if address_interface.network == bridge_interface.network:
            used.add(address_interface.ip)
    return used


def rotated[T](items: Sequence[T], start_index: int) -> list[T]:
    if not items:
        return []
    offset = start_index % len(items)
    return list(items[offset:]) + list(items[:offset])


def network_offset_candidates(
    network: ipaddress.IPv4Network,
    *,
    offsets: Sequence[int],
) -> list[ipaddress.IPv4Address]:
    candidates: list[ipaddress.IPv4Address] = []
    for offset in offsets:
        candidate = network.network_address + offset
        if candidate in network and candidate != network.broadcast_address:
            candidates.append(candidate)
    return candidates


def suggest_static_ipv4(
    container_name: str,
    bridge_cidr: str,
    *,
    state_dir: Path,
    container_root: Path = Path("/var/lib/lxc"),
) -> dict[str, str]:
    bridge_interface = ipaddress.ip_interface(bridge_cidr)
    network = bridge_interface.network
    gateway = bridge_interface.ip
    reserved = used_ipv4_addresses(state_dir, bridge_cidr=bridge_cidr, container_root=container_root)
    reserved.add(gateway)

    preferred = network_offset_candidates(network, offsets=range(200, 240))
    fallback = network_offset_candidates(network, offsets=range(10, 200))
    seed = sum(container_name.encode("utf-8"))
    ordered = rotated(preferred, seed) + fallback

    for candidate in ordered:
        if candidate in reserved:
            continue
        return {
            "ipv4_address": f"{candidate}/{network.prefixlen}",
            "ipv4_gateway": str(gateway),
        }

    raise ValueError(f"no available IPv4 addresses in {network}")


def resolve_container_network(
    meta: Mapping[str, object] | None,
    *,
    available_links: Sequence[str],
    allow_empty_fallback: bool,
    veth_support: Mapping[str, object] | None = None,
) -> dict[str, str]:
    payload = meta or {}
    network_mode = str(payload.get("network_mode") or "").strip()
    bridge_name = str(payload.get("bridge_name") or "").strip()
    bridge_cidr = str(payload.get("bridge_cidr") or "").strip()
    ipv4_address = str(payload.get("ipv4_address") or "").strip()
    ipv4_gateway = str(payload.get("ipv4_gateway") or "").strip()

    resolved = {
        "network_mode": network_mode,
        "bridge_name": bridge_name,
        "bridge_cidr": bridge_cidr,
        "ipv4_address": ipv4_address,
        "ipv4_gateway": ipv4_gateway,
    }
    available = set(available_links)

    if network_mode in {"", "empty"}:
        return resolved

    veth_diagnostic = veth_support or detect_veth_support()
    if network_mode in {"bridge-static", "bridge-dhcp"} and not bool(veth_diagnostic.get("available")):
        warning = str(veth_diagnostic.get("reason") or "veth is unavailable on this host")
        if not allow_empty_fallback:
            return {**resolved, "error": warning}
        return {
            "network_mode": "empty",
            "bridge_name": "",
            "bridge_cidr": "",
            "ipv4_address": "",
            "ipv4_gateway": "",
            "warning": warning,
        }

    if network_mode == "bridge-static":
        if bridge_name and bridge_name in available:
            return resolved
        warning = f"bridge-static network requires missing bridge: {bridge_name or 'unknown'}"
    elif network_mode == "bridge-dhcp":
        required_bridge = bridge_name or "lxcbr0"
        if required_bridge in available:
            resolved["bridge_name"] = required_bridge
            return resolved
        warning = f"bridge-dhcp network requires missing bridge: {required_bridge}"
    else:
        return resolved

    if not allow_empty_fallback:
        return {**resolved, "error": warning}
    return {
        "network_mode": "empty",
        "bridge_name": "",
        "bridge_cidr": "",
        "ipv4_address": "",
        "ipv4_gateway": "",
        "warning": warning,
    }


def render_net0_lines(
    *,
    network_mode: str,
    bridge_name: str = "",
    ipv4_address: str = "",
    ipv4_gateway: str = "",
) -> list[str]:
    if network_mode == "empty":
        return ["lxc.net.0.type = empty"]
    if network_mode == "bridge-static":
        return [
            "lxc.net.0.type = veth",
            f"lxc.net.0.link = {bridge_name}",
            "lxc.net.0.flags = up",
            f"lxc.net.0.ipv4.address = {ipv4_address}",
            f"lxc.net.0.ipv4.gateway = {ipv4_gateway}",
        ]
    return []


def rewrite_net0_config_text(
    config_text: str,
    *,
    network_mode: str,
    bridge_name: str = "",
    ipv4_address: str = "",
    ipv4_gateway: str = "",
) -> str:
    kept_lines: list[str] = []
    for raw_line in config_text.splitlines():
        key = raw_line.split("=", 1)[0].strip()
        if key in MANAGED_NET0_KEYS:
            continue
        kept_lines.append(raw_line)
    final_lines = kept_lines + render_net0_lines(
        network_mode=network_mode,
        bridge_name=bridge_name,
        ipv4_address=ipv4_address,
        ipv4_gateway=ipv4_gateway,
    )
    return "\n".join(final_lines).rstrip() + "\n"


def rewrite_config_file(
    path: Path,
    *,
    network_mode: str,
    bridge_name: str = "",
    ipv4_address: str = "",
    ipv4_gateway: str = "",
) -> None:
    current = path.read_text(encoding="utf-8")
    updated = rewrite_net0_config_text(
        current,
        network_mode=network_mode,
        bridge_name=bridge_name,
        ipv4_address=ipv4_address,
        ipv4_gateway=ipv4_gateway,
    )
    path.write_text(updated, encoding="utf-8")


def render_guest_netplan(network_mode: str) -> str:
    if network_mode == "bridge-static":
        return (
            "network:\n"
            "  version: 2\n"
            "  ethernets:\n"
            "    eth0:\n"
            "      dhcp4: false\n"
            "      dhcp6: false\n"
        )
    if network_mode == "bridge-dhcp":
        return (
            "network:\n"
            "  version: 2\n"
            "  ethernets:\n"
            "    eth0:\n"
            "      dhcp4: true\n"
            "      dhcp-identifier: mac\n"
        )
    return (
        "network:\n"
        "  version: 2\n"
        "  ethernets: {}\n"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LXC network helpers for Marathon")
    subparsers = parser.add_subparsers(dest="command", required=True)

    rewrite = subparsers.add_parser("rewrite-config")
    rewrite.add_argument("--path", required=True)
    rewrite.add_argument("--network-mode", required=True)
    rewrite.add_argument("--bridge-name", default="")
    rewrite.add_argument("--ipv4-address", default="")
    rewrite.add_argument("--ipv4-gateway", default="")

    suggest = subparsers.add_parser("suggest-static-ip")
    suggest.add_argument("--container-name", required=True)
    suggest.add_argument("--bridge-cidr", required=True)
    suggest.add_argument("--state-dir", required=True)
    suggest.add_argument("--container-root", default="/var/lib/lxc")

    render = subparsers.add_parser("render-netplan")
    render.add_argument("--network-mode", required=True)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "rewrite-config":
        rewrite_config_file(
            Path(args.path),
            network_mode=args.network_mode,
            bridge_name=args.bridge_name,
            ipv4_address=args.ipv4_address,
            ipv4_gateway=args.ipv4_gateway,
        )
    elif args.command == "suggest-static-ip":
        payload = suggest_static_ipv4(
            args.container_name,
            args.bridge_cidr,
            state_dir=Path(args.state_dir),
            container_root=Path(args.container_root),
        )
        print(json.dumps(payload, ensure_ascii=False))
    elif args.command == "render-netplan":
        print(render_guest_netplan(args.network_mode), end="")


if __name__ == "__main__":
    main()
