import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest


ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT_DIR / "scripts" / "prune_container_state.sh"


def write_state_meta(path: Path, *, container_name: str, ipv4_address: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "container_name": container_name,
                "network_mode": "bridge-static",
                "bridge_name": "virbr0",
                "bridge_cidr": "192.168.122.1/24",
                "ipv4_address": ipv4_address,
                "ipv4_gateway": "192.168.122.1",
            }
        ),
        encoding="utf-8",
    )


class PruneContainerStateScriptTests(unittest.TestCase):
    def test_script_exists_and_is_shell_valid(self) -> None:
        self.assertTrue(SCRIPT_PATH.exists(), "expected prune helper script to exist")
        subprocess.run(["bash", "-n", str(SCRIPT_PATH)], check=True)

    def test_dry_run_reports_stale_state_without_deleting(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            state_dir = tmp_path / "state" / "containers"
            container_root = tmp_path / "var" / "lib" / "lxc"
            container_root.mkdir(parents=True)
            (container_root / "live").mkdir()

            stale_meta = state_dir / "ghost.json"
            live_meta = state_dir / "live.json"
            write_state_meta(stale_meta, container_name="ghost", ipv4_address="192.168.122.236/24")
            write_state_meta(live_meta, container_name="live", ipv4_address="192.168.122.237/24")

            completed = subprocess.run(
                ["bash", str(SCRIPT_PATH)],
                cwd=str(ROOT_DIR),
                env={
                    **os.environ,
                    "MARATHON_CONTAINER_STATE_DIR": str(state_dir),
                    "MARATHON_LXC_ROOT": str(container_root),
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(stale_meta.exists())
            self.assertTrue(live_meta.exists())
            self.assertIn(f"would-remove ghost 192.168.122.236/24 {stale_meta}", completed.stdout)
            self.assertIn("stale_count=1 removed_count=0 dry_run=1", completed.stdout)

    def test_apply_removes_only_stale_state(self) -> None:
        with TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            state_dir = tmp_path / "state" / "containers"
            container_root = tmp_path / "var" / "lib" / "lxc"
            container_root.mkdir(parents=True)
            (container_root / "live").mkdir()

            stale_meta = state_dir / "ghost.json"
            live_meta = state_dir / "live.json"
            write_state_meta(stale_meta, container_name="ghost", ipv4_address="192.168.122.236/24")
            write_state_meta(live_meta, container_name="live", ipv4_address="192.168.122.237/24")

            completed = subprocess.run(
                ["bash", str(SCRIPT_PATH), "--apply"],
                cwd=str(ROOT_DIR),
                env={
                    **os.environ,
                    "MARATHON_CONTAINER_STATE_DIR": str(state_dir),
                    "MARATHON_LXC_ROOT": str(container_root),
                },
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(stale_meta.exists())
            self.assertTrue(live_meta.exists())
            self.assertIn(f"removed ghost 192.168.122.236/24 {stale_meta}", completed.stdout)
            self.assertIn("stale_count=1 removed_count=1 dry_run=0", completed.stdout)


if __name__ == "__main__":
    unittest.main()
