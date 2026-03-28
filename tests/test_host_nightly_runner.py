from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

import host.host_nightly as host_nightly
import host.host_nightly_runner as host_nightly_runner


def run(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True, check=True)


class SequenceClock:
    def __init__(self, *values: datetime) -> None:
        self._values = list(values)
        self._last = values[-1]

    def __call__(self) -> datetime:
        if self._values:
            self._last = self._values.pop(0)
        return self._last


class HostNightlyRunnerTests(unittest.TestCase):
    def create_remote_repo(self, root: Path) -> Path:
        remote = root / "remote.git"
        repo = root / "repo"
        run(["git", "init", "--bare", "--initial-branch=main", str(remote)])
        run(["git", "clone", str(remote), str(repo)])
        run(["git", "-C", str(repo), "config", "user.name", "tester"])
        run(["git", "-C", str(repo), "config", "user.email", "tester@example.com"])
        (repo / "README.md").write_text("hello\n", encoding="utf-8")
        run(["git", "-C", str(repo), "add", "README.md"])
        run(["git", "-C", str(repo), "commit", "-m", "seed"])
        run(["git", "-C", str(repo), "push", "-u", "origin", "main"])
        run(["git", "-C", str(repo), "remote", "set-head", "origin", "-a"])
        return repo

    def test_run_host_nightly_writes_run_metadata_under_host_runs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = self.create_remote_repo(root)
            clock = SequenceClock(datetime(2026, 3, 19, 1, 0, 0), datetime(2026, 3, 19, 8, 0, 0))
            result = host_nightly_runner.run_host_nightly(
                {"slug": "repo", "repo_path": str(repo), "deadline_time": "08:00:00"},
                host_runs_root=root / "host-runs",
                run_id="night-1",
                now_fn=clock,
                round_executor=self.write_round_change,
            )

            run_dir = root / "host-runs" / "repo" / "night-1"
            self.assertEqual(result["run_dir"], str(run_dir))
            self.assertTrue((run_dir / "run.json").exists())
            self.assertTrue((run_dir / "status.json").exists())
            status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(status["state"], "stopped_by_deadline")
            self.assertEqual(status["completed_rounds"], 1)

    def test_run_host_nightly_creates_checkpoint_commit_when_repo_is_dirty(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = self.create_remote_repo(root)
            (repo / "README.md").write_text("dirty\n", encoding="utf-8")
            clock = SequenceClock(datetime(2026, 3, 19, 1, 0, 0), datetime(2026, 3, 19, 8, 0, 0))

            host_nightly_runner.run_host_nightly(
                {"slug": "repo", "repo_path": str(repo), "deadline_time": "08:00:00"},
                host_runs_root=root / "host-runs",
                run_id="night-2",
                now_fn=clock,
                round_executor=self.noop_round,
            )

            message = run(
                ["git", "-C", str(repo), "log", "main", "-1", "--pretty=%s"]
            ).stdout.strip()
            self.assertEqual(message, host_nightly.dirty_checkpoint_message())

    def test_run_host_nightly_creates_fresh_nightly_branch_from_default_branch(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = self.create_remote_repo(root)
            branch_time = datetime(2026, 3, 19, 1, 2, 3)
            clock = SequenceClock(branch_time, datetime(2026, 3, 19, 8, 0, 0))

            host_nightly_runner.run_host_nightly(
                {"slug": "repo", "repo_path": str(repo), "deadline_time": "08:00:00"},
                host_runs_root=root / "host-runs",
                run_id="night-3",
                now_fn=clock,
                round_executor=self.noop_round,
            )

            branch = host_nightly.nightly_branch_name(branch_time)
            current_branch = run(["git", "-C", str(repo), "branch", "--show-current"]).stdout.strip()
            nightly_head = run(["git", "-C", str(repo), "rev-parse", branch]).stdout.strip()
            main_head = run(["git", "-C", str(repo), "rev-parse", "origin/main"]).stdout.strip()
            self.assertEqual(current_branch, branch)
            self.assertEqual(nightly_head, main_head)

    def test_run_host_nightly_stops_with_deadline_state(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo = self.create_remote_repo(root)
            clock = SequenceClock(datetime(2026, 3, 19, 7, 59, 59), datetime(2026, 3, 19, 8, 0, 0))

            result = host_nightly_runner.run_host_nightly(
                {"slug": "repo", "repo_path": str(repo), "deadline_time": "08:00:00"},
                host_runs_root=root / "host-runs",
                run_id="night-4",
                now_fn=clock,
                round_executor=self.noop_round,
            )

            self.assertEqual(result["state"], "stopped_by_deadline")
            self.assertEqual(result["completed_rounds"], 1)

    def noop_round(
        self,
        *,
        repo_path: Path,
        run_dir: Path,
        round_index: int,
    ) -> dict[str, object]:
        return {
            "summary": f"noop {round_index}",
            "action": {"summary": f"noop {round_index}", "argv": ["bash", "-lc", "pwd"], "timeout": 30},
            "tool_result": {"ok": True, "returncode": 0, "stdout": "", "stderr": ""},
            "state_before": {},
            "state_after": {},
            "response_text": "{}",
        }

    def write_round_change(
        self,
        *,
        repo_path: Path,
        run_dir: Path,
        round_index: int,
    ) -> dict[str, object]:
        target = repo_path / "README.md"
        target.write_text(f"updated {round_index}\n", encoding="utf-8")
        return {
            "summary": f"update readme {round_index}",
            "action": {"summary": f"update readme {round_index}", "argv": ["bash", "-lc", "printf updated"], "timeout": 30},
            "tool_result": {"ok": True, "returncode": 0, "stdout": "", "stderr": ""},
            "state_before": {},
            "state_after": {},
            "response_text": "{}",
        }


if __name__ == "__main__":
    unittest.main()
