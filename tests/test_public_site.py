import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import host.public_site as public_site


def make_run(
    runs_dir: Path,
    run_id: str,
    *,
    container: str,
    state: str,
    updated_at: str,
    done: str,
    next_text: str,
    thought: str,
    agent_handle: str | None = None,
) -> None:
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True)
    (run_dir / 'host_run.json').write_text(
        json.dumps({'container': container, 'mode': 'task', 'started_at': updated_at}, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    (run_dir / 'ui_launch.json').write_text(
        json.dumps({'container': container, 'agent_handle': agent_handle, 'started_at': updated_at}, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    (run_dir / 'status.json').write_text(
        json.dumps(
            {
                'state': state,
                'completed_rounds': 1,
                'last_done': done,
                'last_next': next_text,
                'last_thought': thought,
                'last_summary': done,
                'updated_at': updated_at,
            },
            ensure_ascii=False,
        )
        + '\n',
        encoding='utf-8',
    )
    (run_dir / 'latest_action.json').write_text(
        json.dumps({'done': done, 'next': next_text, 'thought': thought, 'summary': done}, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    (run_dir / 'blog.jsonl').write_text(
        json.dumps(
            {
                'type': 'round_post',
                'container': container,
                'run_id': run_id,
                'round': 1,
                'done': done,
                'next': next_text,
                'thought': thought,
                'ts': updated_at,
            },
            ensure_ascii=False,
        )
        + '\n',
        encoding='utf-8',
    )


class PublicSitePayloadTests(unittest.TestCase):
    def test_home_payload_separates_live_completed_and_accounts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runs_dir = root / 'runs'
            accounts_dir = root / 'agent_accounts'
            container_state_dir = root / 'containers'
            blog_dir = root / 'container_blogs'
            runs_dir.mkdir()
            accounts_dir.mkdir()
            container_state_dir.mkdir()
            blog_dir.mkdir()

            make_run(
                runs_dir,
                'run-completed',
                container='sandbox-a',
                state='completed',
                updated_at='2026-04-02T10:00:00+0800',
                done='completed result',
                next_text='archive it',
                thought='close the loop',
                agent_handle='writer-1',
            )
            make_run(
                runs_dir,
                'run-live',
                container='sandbox-b',
                state='running',
                updated_at='2026-04-02T11:00:00+0800',
                done='still running',
                next_text='keep iterating',
                thought='work in progress',
                agent_handle='writer-1',
            )
            (accounts_dir / 'writer-1.json').write_text(
                json.dumps(
                    {
                        'agent_account_id': 'agent-1',
                        'agent_handle': 'writer-1',
                        'display_name': 'Writer One',
                        'bio': 'Writes run notes.',
                        'auth_token': 'secret-token',
                        'created_at': '2026-04-02T09:00:00+0800',
                        'updated_at': '2026-04-02T11:00:00+0800',
                    },
                    ensure_ascii=False,
                )
                + '\n',
                encoding='utf-8',
            )
            (accounts_dir / 'writer-1.posts.jsonl').write_text(
                json.dumps(
                    {
                        'agent_handle': 'writer-1',
                        'run_id': 'run-completed',
                        'round': 1,
                        'done': 'completed result',
                        'next': 'archive it',
                        'thought': 'close the loop',
                        'ts': '2026-04-02T10:00:00+0800',
                    },
                    ensure_ascii=False,
                )
                + '\n',
                encoding='utf-8',
            )

            with mock.patch.object(public_site, 'RUNS_DIR', runs_dir), mock.patch.object(
                public_site, 'AGENT_ACCOUNT_DIR', accounts_dir
            ), mock.patch.object(public_site, 'CONTAINER_STATE_DIR', container_state_dir), mock.patch.object(
                public_site, 'CONTAINER_BLOG_DIR', blog_dir
            ):
                payload = public_site.home_payload()

        self.assertEqual(payload['run_count'], 2)
        self.assertEqual(len(payload['live_runs']), 1)
        self.assertEqual(payload['live_runs'][0]['public_run_id'], 'run-live')
        self.assertEqual(payload['latest_completed_runs'][0]['public_run_id'], 'run-completed')
        self.assertEqual(payload['accounts'][0]['agent_handle'], 'writer-1')
        self.assertNotIn('auth_token', payload['accounts'][0])

    def test_run_payload_returns_readable_layer_and_timeline(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runs_dir = root / 'runs'
            accounts_dir = root / 'agent_accounts'
            container_state_dir = root / 'containers'
            blog_dir = root / 'container_blogs'
            runs_dir.mkdir()
            accounts_dir.mkdir()
            container_state_dir.mkdir()
            blog_dir.mkdir()

            make_run(
                runs_dir,
                'run-detail',
                container='sandbox-a',
                state='completed',
                updated_at='2026-04-02T10:00:00+0800',
                done='drafted a summary',
                next_text='publish the result',
                thought='focus on the readable slice',
                agent_handle='writer-1',
            )

            with mock.patch.object(public_site, 'RUNS_DIR', runs_dir), mock.patch.object(
                public_site, 'AGENT_ACCOUNT_DIR', accounts_dir
            ), mock.patch.object(public_site, 'CONTAINER_STATE_DIR', container_state_dir), mock.patch.object(
                public_site, 'CONTAINER_BLOG_DIR', blog_dir
            ):
                payload = public_site.run_payload('run-detail')

        self.assertEqual(payload['summary']['public_run_id'], 'run-detail')
        self.assertEqual(payload['readable']['status'], 'completed')
        self.assertEqual(len(payload['timeline']), 1)
        self.assertIn('drafted a summary', payload['timeline'][0]['done'])

    def test_agent_payload_exposes_public_account_recent_posts_and_runs(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runs_dir = root / 'runs'
            accounts_dir = root / 'agent_accounts'
            container_state_dir = root / 'containers'
            blog_dir = root / 'container_blogs'
            runs_dir.mkdir()
            accounts_dir.mkdir()
            container_state_dir.mkdir()
            blog_dir.mkdir()

            make_run(
                runs_dir,
                'run-agent',
                container='sandbox-a',
                state='completed',
                updated_at='2026-04-02T10:00:00+0800',
                done='completed result',
                next_text='archive it',
                thought='close the loop',
                agent_handle='writer-1',
            )
            (accounts_dir / 'writer-1.json').write_text(
                json.dumps(
                    {
                        'agent_account_id': 'agent-1',
                        'agent_handle': 'writer-1',
                        'display_name': 'Writer One',
                        'bio': 'Writes run notes.',
                        'auth_token': 'secret-token',
                        'created_at': '2026-04-02T09:00:00+0800',
                        'updated_at': '2026-04-02T11:00:00+0800',
                    },
                    ensure_ascii=False,
                )
                + '\n',
                encoding='utf-8',
            )
            (accounts_dir / 'writer-1.posts.jsonl').write_text(
                json.dumps(
                    {
                        'agent_handle': 'writer-1',
                        'run_id': 'run-agent',
                        'round': 1,
                        'done': 'completed result',
                        'next': 'archive it',
                        'thought': 'close the loop',
                        'ts': '2026-04-02T10:00:00+0800',
                    },
                    ensure_ascii=False,
                )
                + '\n',
                encoding='utf-8',
            )

            with mock.patch.object(public_site, 'RUNS_DIR', runs_dir), mock.patch.object(
                public_site, 'AGENT_ACCOUNT_DIR', accounts_dir
            ), mock.patch.object(public_site, 'CONTAINER_STATE_DIR', container_state_dir), mock.patch.object(
                public_site, 'CONTAINER_BLOG_DIR', blog_dir
            ):
                payload = public_site.agent_payload('writer-1')

        self.assertEqual(payload['account']['agent_handle'], 'writer-1')
        self.assertNotIn('auth_token', payload['account'])
        self.assertEqual(len(payload['recent_posts']), 1)
        self.assertEqual(payload['completed_runs'][0]['public_run_id'], 'run-agent')


class PublicSiteExportTests(unittest.TestCase):
    def test_export_github_pages_writes_assets_and_data_snapshots(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            runs_dir = root / 'runs'
            accounts_dir = root / 'agent_accounts'
            container_state_dir = root / 'containers'
            blog_dir = root / 'container_blogs'
            static_dir = root / 'site-assets'
            output_dir = root / 'build' / 'github-pages'
            runs_dir.mkdir()
            accounts_dir.mkdir()
            container_state_dir.mkdir()
            blog_dir.mkdir()
            static_dir.mkdir()

            for name in ('index.html', 'run.html', 'agent.html', 'live.html', 'site.css', 'site.js'):
                (static_dir / name).write_text(name, encoding='utf-8')

            make_run(
                runs_dir,
                'run-export',
                container='sandbox-a',
                state='completed',
                updated_at='2026-04-02T10:00:00+0800',
                done='exported result',
                next_text='ship it',
                thought='use GitHub Pages',
                agent_handle='writer-1',
            )
            (accounts_dir / 'writer-1.json').write_text(
                json.dumps(
                    {
                        'agent_account_id': 'agent-1',
                        'agent_handle': 'writer-1',
                        'display_name': 'Writer One',
                        'bio': 'Writes run notes.',
                        'created_at': '2026-04-02T09:00:00+0800',
                        'updated_at': '2026-04-02T11:00:00+0800',
                    },
                    ensure_ascii=False,
                )
                + '\n',
                encoding='utf-8',
            )

            with mock.patch.object(public_site, 'RUNS_DIR', runs_dir), mock.patch.object(
                public_site, 'AGENT_ACCOUNT_DIR', accounts_dir
            ), mock.patch.object(public_site, 'CONTAINER_STATE_DIR', container_state_dir), mock.patch.object(
                public_site, 'CONTAINER_BLOG_DIR', blog_dir
            ), mock.patch.object(public_site, 'STATIC_SITE_DIR', static_dir), mock.patch.object(
                public_site, 'FAVICON_FILE', static_dir / 'site.css'
            ):
                result = public_site.export_github_pages(output_dir)
                self.assertTrue(result['ok'])
                self.assertTrue((output_dir / 'index.html').exists())
                self.assertTrue((output_dir / 'run.html').exists())
                self.assertTrue((output_dir / 'agent.html').exists())
                self.assertTrue((output_dir / 'live.html').exists())
                self.assertTrue((output_dir / 'site.css').exists())
                self.assertTrue((output_dir / 'site.js').exists())
                self.assertTrue((output_dir / '.nojekyll').exists())
                self.assertTrue((output_dir / 'data' / 'site-home.json').exists())
                self.assertTrue((output_dir / 'data' / 'live.json').exists())
                self.assertTrue((output_dir / 'data' / 'runs' / public_site.run_asset_name('run-export')).exists())
                self.assertTrue((output_dir / 'data' / 'agents' / public_site.agent_asset_name('writer-1')).exists())
