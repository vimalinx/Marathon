from __future__ import annotations

import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

import host.host_nightly as host_nightly


class HostNightlyConfigTests(unittest.TestCase):
    def test_write_host_project_config_persists_under_state_host_projects(self) -> None:
        with TemporaryDirectory() as tmpdir:
            state_root = Path(tmpdir) / "state"
            repo_path = Path("/home/vimalinx/Projects/My App")
            config = host_nightly.write_host_project_config(
                repo_path,
                state_root=state_root,
            )

            config_path = state_root / "host_projects" / "my-app.json"
            self.assertEqual(config["slug"], "my-app")
            self.assertTrue(config_path.exists())
            persisted = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["repo_path"], str(repo_path))
            self.assertEqual(persisted["deadline_time"], "08:00:00")

    def test_systemd_unit_base_name_uses_project_slug(self) -> None:
        self.assertEqual(host_nightly.systemd_unit_base_name("my-app"), "marathon-nightly-my-app")

    def test_write_host_project_config_preserves_existing_schedule(self) -> None:
        with TemporaryDirectory() as tmpdir:
            state_root = Path(tmpdir) / "state"
            config_path = state_root / "host_projects" / "my-app.json"
            host_nightly.write_json(
                config_path,
                {
                    "slug": "my-app",
                    "repo_path": "/home/vimalinx/Projects/My App",
                    "start_time": "01:15:00",
                    "deadline_time": "09:30:00",
                },
            )

            config = host_nightly.write_host_project_config(
                Path("/home/vimalinx/Projects/My App"),
                state_root=state_root,
            )

            self.assertEqual(config["start_time"], "01:15:00")
            self.assertEqual(config["deadline_time"], "09:30:00")

    def test_rendered_units_include_repo_path_and_one_shot_runner(self) -> None:
        config = {
            "slug": "my-app",
            "repo_path": "/home/vimalinx/Projects/My App",
            "start_time": "00:30:00",
            "deadline_time": "08:00:00",
        }
        service_text = host_nightly.render_systemd_service(config, root_dir=Path("/opt/marathon"))
        timer_text = host_nightly.render_systemd_timer(config)

        self.assertIn("Description=Marathon nightly runner for my-app", service_text)
        self.assertIn("/opt/marathon/scripts/run_host_nightly_once.sh /home/vimalinx/Projects/My\\ App", service_text)
        self.assertIn("WorkingDirectory=/opt/marathon", service_text)
        self.assertIn("OnCalendar=*-*-* 00:30:00", timer_text)
        self.assertIn("Unit=marathon-nightly-my-app.service", timer_text)


class HostNightlyScriptTests(unittest.TestCase):
    def test_run_host_nightly_once_script_exists_shell_valid_and_calls_runner(self) -> None:
        script_path = Path("scripts/run_host_nightly_once.sh")
        self.assertTrue(script_path.exists(), "expected one-shot runner script to exist")
        subprocess.run(["bash", "-n", str(script_path)], check=True)
        script = script_path.read_text(encoding="utf-8")
        self.assertIn('python3 "${ROOT_DIR}/host/host_nightly_runner.py"', script)
        self.assertIn('--config "${CONFIG_PATH}"', script)

    def test_setup_host_nightly_script_exists_and_installs_user_units(self) -> None:
        script_path = Path("scripts/setup_host_nightly.sh")
        self.assertTrue(script_path.exists(), "expected setup script to exist")
        subprocess.run(["bash", "-n", str(script_path)], check=True)
        script = script_path.read_text(encoding="utf-8")
        self.assertIn('systemctl --user daemon-reload', script)
        self.assertIn('systemctl --user enable --now "${TIMER_NAME}"', script)
        self.assertIn('scripts/run_host_nightly_once.sh', script)

    def test_readme_mentions_host_nightly_scripts(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")
        self.assertIn("./scripts/setup_host_nightly.sh <repo_path>", readme)
        self.assertIn("./scripts/run_host_nightly_once.sh <repo_path>", readme)


if __name__ == "__main__":
    unittest.main()
