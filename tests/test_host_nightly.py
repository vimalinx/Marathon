from datetime import datetime
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

import host.host_nightly as host_nightly


def run(argv: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=str(cwd) if cwd else None, capture_output=True, text=True, check=True)


class HostNightlyHelpersTests(unittest.TestCase):
    def test_slugify_repo_path_uses_readable_repo_name(self) -> None:
        slug = host_nightly.slugify_repo_path(Path("/home/vimalinx/Projects/My App.repo"))
        self.assertEqual(slug, "my-app-repo")

    def test_nightly_branch_name_formats_timestamp(self) -> None:
        branch = host_nightly.nightly_branch_name(datetime(2026, 3, 19, 23, 0, 5))
        self.assertEqual(branch, "marathon/nightly-20260319-230005")

    def test_dirty_checkpoint_message_is_explicit(self) -> None:
        self.assertEqual(
            host_nightly.dirty_checkpoint_message(),
            "chore(marathon): checkpoint dirty workspace before nightly run",
        )

    def test_should_stop_for_deadline_at_or_after_eight(self) -> None:
        self.assertFalse(host_nightly.should_stop_for_deadline(datetime(2026, 3, 19, 7, 59, 59)))
        self.assertTrue(host_nightly.should_stop_for_deadline(datetime(2026, 3, 19, 8, 0, 0)))


class HostNightlyGitTests(unittest.TestCase):
    def test_read_default_branch_uses_origin_head(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
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

            self.assertEqual(host_nightly.read_default_branch(repo), "main")

    def test_repo_has_uncommitted_changes_detects_dirty_workspace(self) -> None:
        with TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir) / "repo"
            run(["git", "init", "--initial-branch=main", str(repo)])
            run(["git", "-C", str(repo), "config", "user.name", "tester"])
            run(["git", "-C", str(repo), "config", "user.email", "tester@example.com"])
            (repo / "README.md").write_text("hello\n", encoding="utf-8")
            run(["git", "-C", str(repo), "add", "README.md"])
            run(["git", "-C", str(repo), "commit", "-m", "seed"])
            self.assertFalse(host_nightly.repo_has_uncommitted_changes(repo))
            (repo / "README.md").write_text("changed\n", encoding="utf-8")
            self.assertTrue(host_nightly.repo_has_uncommitted_changes(repo))


if __name__ == "__main__":
    unittest.main()
