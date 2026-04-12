from __future__ import annotations

import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import host.github_pages_sync as github_pages_sync


class GitHubPagesSyncConfigTests(unittest.TestCase):
    def test_write_config_persists_under_state_root(self) -> None:
        with TemporaryDirectory() as tmpdir:
            state_root = Path(tmpdir) / 'state'
            repo_path = Path('/home/vimalinx/Research/Marathon')
            config = github_pages_sync.write_config(repo_path, state_root=state_root)

            config_path = state_root / 'github_pages_sync' / 'marathon.json'
            self.assertTrue(config_path.exists())
            self.assertEqual(config['publish_branch'], 'gh-pages')
            self.assertEqual(config['timer_calendar'], 'hourly')

    def test_rendered_units_include_hourly_timer_and_runner_script(self) -> None:
        config = {
            'slug': 'marathon',
            'repo_path': '/home/vimalinx/Research/Marathon',
            'publish_branch': 'gh-pages',
            'timer_calendar': 'hourly',
        }
        service_text = github_pages_sync.render_systemd_service(config, root_dir=Path('/opt/marathon'))
        timer_text = github_pages_sync.render_systemd_timer(config)

        self.assertIn('Description=Marathon GitHub Pages sync for marathon', service_text)
        self.assertIn('/opt/marathon/scripts/run_github_pages_sync_once.sh /home/vimalinx/Research/Marathon', service_text)
        self.assertIn('OnCalendar=hourly', timer_text)
        self.assertIn('Unit=marathon-pages-sync-marathon.service', timer_text)


class GitHubPagesSyncScriptTests(unittest.TestCase):
    def test_run_script_exists_shell_valid_and_calls_module_runner(self) -> None:
        script_path = Path('scripts/run_github_pages_sync_once.sh')
        self.assertTrue(script_path.exists())
        subprocess.run(['bash', '-n', str(script_path)], check=True)
        script = script_path.read_text(encoding='utf-8')
        self.assertIn('python3 -m host.github_pages_sync --config "${CONFIG_PATH}"', script)

    def test_setup_script_exists_and_installs_user_units(self) -> None:
        script_path = Path('scripts/setup_github_pages_sync.sh')
        self.assertTrue(script_path.exists())
        subprocess.run(['bash', '-n', str(script_path)], check=True)
        script = script_path.read_text(encoding='utf-8')
        self.assertIn('systemctl --user daemon-reload', script)
        self.assertIn('systemctl --user enable --now "${TIMER_NAME}"', script)
        self.assertIn('run_github_pages_sync_once.sh', script)


class GitHubPagesSyncRunnerTests(unittest.TestCase):
    def test_sync_once_exports_commits_and_pushes_to_publish_branch(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            repo_path = root / 'repo'
            bare_remote = root / 'remote.git'
            state_root = root / 'state'
            repo_path.mkdir()

            subprocess.run(['git', 'init', '-b', 'main'], cwd=repo_path, check=True, capture_output=True, text=True)
            subprocess.run(['git', 'config', 'user.name', 'Test User'], cwd=repo_path, check=True, capture_output=True, text=True)
            subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=repo_path, check=True, capture_output=True, text=True)
            (repo_path / 'README.md').write_text('source repo\n', encoding='utf-8')
            subprocess.run(['git', 'add', 'README.md'], cwd=repo_path, check=True, capture_output=True, text=True)
            subprocess.run(['git', 'commit', '-m', 'initial'], cwd=repo_path, check=True, capture_output=True, text=True)
            subprocess.run(['git', 'init', '--bare', str(bare_remote)], check=True, capture_output=True, text=True)
            subprocess.run(['git', 'remote', 'add', 'origin', str(bare_remote)], cwd=repo_path, check=True, capture_output=True, text=True)
            subprocess.run(['git', 'push', '-u', 'origin', 'main'], cwd=repo_path, check=True, capture_output=True, text=True)

            config = github_pages_sync.write_config(repo_path, state_root=state_root)
            config_path = Path(str(config['config_path']))

            staging_output = Path(str(config['staging_output_path']))

            def fake_export(output_dir: Path) -> dict[str, object]:
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / 'index.html').write_text('snapshot home', encoding='utf-8')
                (output_dir / '.nojekyll').write_text('\n', encoding='utf-8')
                return {'ok': True, 'output_dir': str(output_dir), 'run_count': 1, 'account_count': 0}

            with mock.patch.object(github_pages_sync, 'PROJECT_ROOT', repo_path), mock.patch.object(
                github_pages_sync.public_site, 'export_github_pages', side_effect=fake_export
            ):
                result = github_pages_sync.sync_once(config_path)

            self.assertTrue(result['ok'])
            self.assertTrue(result['changed'])

            probe = subprocess.run(
                ['git', '--git-dir', str(bare_remote), 'show', 'gh-pages:index.html'],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn('snapshot home', probe.stdout)


if __name__ == '__main__':
    unittest.main()
