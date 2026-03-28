#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import host.lxc_network as lxc_network

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_DIR = PROJECT_ROOT / "state" / "containers"
DEFAULT_CONTAINER_ROOT = Path("/var/lib/lxc")


def list_stale_state_files(state_dir: Path, *, container_root: Path) -> list[dict[str, str]]:
    if not state_dir.exists():
        return []
    if not container_root.exists():
        raise FileNotFoundError(f"container root does not exist: {container_root}")

    stale_entries: list[dict[str, str]] = []
    for path in sorted(state_dir.glob("*.json")):
        payload = lxc_network.read_meta_file(path)
        if not payload:
            continue
        if lxc_network.container_definition_exists(payload, path=path, container_root=container_root):
            continue
        stale_entries.append(
            {
                "path": str(path),
                "container_name": str(payload.get("container_name") or path.stem).strip(),
                "ipv4_address": str(payload.get("ipv4_address") or "").strip(),
            }
        )
    return stale_entries


def prune_stale_state_files(
    state_dir: Path,
    *,
    container_root: Path,
    apply: bool,
) -> tuple[list[dict[str, str]], int]:
    stale_entries = list_stale_state_files(state_dir, container_root=container_root)
    removed_count = 0

    for entry in stale_entries:
        action = "would-remove"
        path = Path(entry["path"])
        if apply:
            try:
                path.unlink()
            except FileNotFoundError:
                action = "already-missing"
            else:
                action = "removed"
                removed_count += 1
        print(f"{action} {entry['container_name']} {entry['ipv4_address']} {entry['path']}")

    return stale_entries, removed_count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prune stale Marathon container state files")
    parser.add_argument("--state-dir", default=str(DEFAULT_STATE_DIR))
    parser.add_argument("--container-root", default=str(DEFAULT_CONTAINER_ROOT))
    parser.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        stale_entries, removed_count = prune_stale_state_files(
            Path(args.state_dir),
            container_root=Path(args.container_root),
            apply=bool(args.apply),
        )
    except FileNotFoundError as exc:
        print(str(exc), flush=True)
        return 1

    print(
        f"stale_count={len(stale_entries)} removed_count={removed_count} dry_run={0 if args.apply else 1}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
