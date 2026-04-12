from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import host.orchestrator as orchestrator


class ParseArgsTests(unittest.TestCase):
    def test_parse_args_accepts_task_prompt(self) -> None:
        argv = [
            "orchestrator.py",
            "--container",
            "sandbox-1",
            "--api-key",
            "test-key",
            "--task-prompt",
            "repair the sandbox incrementally",
        ]
        with mock.patch.object(sys, "argv", argv):
            args = orchestrator.parse_args()
        self.assertEqual(args.task_prompt, "repair the sandbox incrementally")

    def test_parse_args_accepts_runtime_budget_flags(self) -> None:
        argv = [
            "orchestrator.py",
            "--container",
            "sandbox-1",
            "--api-key",
            "test-key",
            "--max-runtime-seconds",
            "900",
            "--max-total-tokens",
            "12000",
        ]
        with mock.patch.object(sys, "argv", argv):
            args = orchestrator.parse_args()
        self.assertEqual(args.max_runtime_seconds, 900)
        self.assertEqual(args.max_total_tokens, 12000)


class BaseUrlConnectivityTests(unittest.TestCase):
    def test_wait_for_container_base_url_retries_until_connectivity_succeeds(self) -> None:
        attempts = [
            subprocess.CompletedProcess(args=["python3"], returncode=1, stdout="", stderr="not ready"),
            subprocess.CompletedProcess(args=["python3"], returncode=0, stdout="", stderr=""),
        ]
        with mock.patch.object(orchestrator, "lxc_attach", side_effect=attempts) as attach:
            with mock.patch.object(orchestrator.time, "sleep") as sleep:
                ready = orchestrator.wait_for_container_base_url(
                    "sandbox-1",
                    "http://192.168.122.1:18080/v1",
                    attempts=2,
                    sleep_seconds=0.25,
                )
        self.assertTrue(ready)
        self.assertEqual(attach.call_count, 2)
        command = attach.call_args_list[0].args[1]
        self.assertEqual(command[:2], ["python3", "-c"])
        self.assertIn("socket.create_connection", command[2])
        sleep.assert_called_once_with(0.25)


class StartAgentLaunchTests(unittest.TestCase):
    def test_start_agent_uses_python_launcher_instead_of_shell_backgrounding(self) -> None:
        completed = subprocess.CompletedProcess(args=["python3"], returncode=0, stdout="", stderr="")

        with mock.patch.object(orchestrator, "lxc_attach", return_value=completed) as attach:
            result = orchestrator.start_agent(
                "sandbox-1",
                run_id="run-1",
                model="gpt-5.4",
                base_url="https://example.com/v1",
                api_key="test-key",
                task_prompt="explore freely",
                model_settings_json='{"reasoning_effort":"high"}',
                max_rounds=0,
                sleep_seconds=1.0,
                max_runtime_seconds=600,
                max_total_tokens=12000,
            )

        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["pid_file"], "/workspace/runtime-log/run-1/agent.pid")
        command = attach.call_args.args[1]
        self.assertEqual(command[:2], ["python3", "-c"])
        self.assertIn("subprocess.Popen", command[2])
        self.assertIn("/opt/marathon/agent_loop.py", command[2])
        self.assertIn("explore freely", command)
        self.assertIn('{"reasoning_effort":"high"}', command)
        self.assertIn("MAX_RUNTIME_SECONDS", command[2])
        self.assertIn("MAX_TOTAL_TOKENS", command[2])
        self.assertIn("600", command)
        self.assertIn("12000", command)


class ContainerBlogArchiveTests(unittest.TestCase):
    def test_sync_container_blog_archive_appends_new_posts_once(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / "runs" / "run-1"
            run_dir.mkdir(parents=True)
            (run_dir / "blog.jsonl").write_text(
                "\n".join(
                    [
                        '{"type":"round_post","run_id":"run-1","round":1,"done":"one","next":"two","thought":"three","ts":"2026-03-26T12:00:00+0800"}',
                        '{"type":"round_post","run_id":"run-1","round":2,"done":"two","next":"three","thought":"four","ts":"2026-03-26T12:01:00+0800"}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            blog_dir = root / "state" / "container_blogs"

            with mock.patch.object(orchestrator, "CONTAINER_BLOG_DIR", blog_dir):
                first = orchestrator.sync_container_blog_archive("sandbox-1", "run-1", run_dir)
                second = orchestrator.sync_container_blog_archive("sandbox-1", "run-1", run_dir)

            archive_path = blog_dir / "sandbox-1.jsonl"
            meta_path = blog_dir / "sandbox-1.meta.json"
            archive_lines = archive_path.read_text(encoding="utf-8").splitlines()
            meta = orchestrator.read_json(meta_path)

            self.assertEqual(first["appended"], 2)
            self.assertEqual(second["appended"], 0)
            self.assertTrue(archive_path.exists())
            self.assertTrue(meta_path.exists())
            self.assertEqual(len(archive_lines), 2)
            self.assertIsNotNone(meta)
            self.assertEqual(meta["latest_round"], 2)
            self.assertEqual(meta["post_count"], 2)


class SyncRoundArtifactsTests(unittest.TestCase):
    def test_sync_files_mirrors_invalid_response_artifacts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            host_run_dir = Path(tmpdir) / "run-1"
            host_run_dir.mkdir(parents=True)
            (host_run_dir / "status.json").write_text(
                '{"completed_rounds": 3, "failed_round": 4}\n',
                encoding="utf-8",
            )

            def fake_read(container: str, path: str) -> str | None:
                if path.endswith("/status.json"):
                    return '{"completed_rounds": 3, "failed_round": 4}\n'
                if path.endswith("/rounds/0004/response.invalid-01.txt"):
                    return "bad raw response"
                if path.endswith("/rounds/0004/response.invalid-01.raw.json"):
                    return '{"choices":[]}\n'
                if path.endswith("/rounds/0004/error.json"):
                    return '{"round":4,"error":"bad json"}\n'
                return None

            with mock.patch.object(orchestrator, "read_container_file", side_effect=fake_read):
                orchestrator.sync_files("sandbox-1", "/workspace/runtime-log/run-1", host_run_dir)

            self.assertEqual(
                (host_run_dir / "rounds" / "0004" / "response.invalid-01.txt").read_text(encoding="utf-8"),
                "bad raw response",
            )
            self.assertIn(
                "bad json",
                (host_run_dir / "rounds" / "0004" / "error.json").read_text(encoding="utf-8"),
            )


class ContainerAccountMirrorTests(unittest.TestCase):
    def test_sync_container_blog_to_agent_account_appends_new_posts_once(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / "runs" / "run-1"
            run_dir.mkdir(parents=True)
            (run_dir / "blog.jsonl").write_text(
                "\n".join(
                    [
                        '{"type":"round_post","run_id":"run-1","round":1,"done":"one","next":"two","thought":"three","ts":"2026-03-27T10:00:00+0800"}',
                        '{"type":"round_post","run_id":"run-1","round":2,"done":"two","next":"three","thought":"four","ts":"2026-03-27T10:01:00+0800"}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            blog_dir = root / "state" / "container_blogs"
            container_state_dir = root / "state" / "containers"
            account_dir = root / "state" / "agent_accounts"
            blog_dir.mkdir(parents=True)
            container_state_dir.mkdir(parents=True)
            account_dir.mkdir(parents=True)

            (container_state_dir / "sandbox-1.json").write_text(
                '{"container_name":"sandbox-1","agent_handle":"writer-1"}\n',
                encoding="utf-8",
            )
            (account_dir / "writer-1.json").write_text(
                '{"agent_account_id":"agent-writer-1","agent_handle":"writer-1","display_name":"Writer One","instance_id":"writer-1-main","auth_token":"secret-token","created_at":"2026-03-27T09:00:00+0800","updated_at":"2026-03-27T09:10:00+0800"}\n',
                encoding="utf-8",
            )

            with mock.patch.object(orchestrator, "CONTAINER_BLOG_DIR", blog_dir), mock.patch.object(
                orchestrator, "CONTAINER_STATE_DIR", container_state_dir
            ), mock.patch.object(orchestrator, "AGENT_ACCOUNT_DIR", account_dir):
                first = orchestrator.sync_container_blog_to_agent_account("sandbox-1", "run-1", run_dir)
                second = orchestrator.sync_container_blog_to_agent_account("sandbox-1", "run-1", run_dir)

            posts = orchestrator.read_jsonl(account_dir / "writer-1.posts.jsonl")
            meta = orchestrator.read_json(blog_dir / "sandbox-1.meta.json")

        self.assertEqual(first["appended"], 2)
        self.assertEqual(second["appended"], 0)
        self.assertEqual(len(posts), 2)
        self.assertEqual(posts[0]["instance_id"], "writer-1-main")
        self.assertEqual(meta["agent_binding"]["agent_handle"], "writer-1")
        self.assertEqual(meta["agent_binding"]["last_account_sync_round"], 2)

    def test_sync_container_blog_to_agent_account_skips_when_unbound(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / "runs" / "run-1"
            run_dir.mkdir(parents=True)
            (run_dir / "blog.jsonl").write_text(
                '{"type":"round_post","run_id":"run-1","round":1,"done":"one","next":"two","thought":"three","ts":"2026-03-27T10:00:00+0800"}\n',
                encoding="utf-8",
            )

            blog_dir = root / "state" / "container_blogs"
            container_state_dir = root / "state" / "containers"
            account_dir = root / "state" / "agent_accounts"
            blog_dir.mkdir(parents=True)
            container_state_dir.mkdir(parents=True)
            account_dir.mkdir(parents=True)
            (container_state_dir / "sandbox-1.json").write_text('{"container_name":"sandbox-1"}\n', encoding="utf-8")

            with mock.patch.object(orchestrator, "CONTAINER_BLOG_DIR", blog_dir), mock.patch.object(
                orchestrator, "CONTAINER_STATE_DIR", container_state_dir
            ), mock.patch.object(orchestrator, "AGENT_ACCOUNT_DIR", account_dir):
                result = orchestrator.sync_container_blog_to_agent_account("sandbox-1", "run-1", run_dir)

        self.assertFalse(result["bound"])
        self.assertEqual(result["appended"], 0)
        self.assertFalse((account_dir / "writer-1.posts.jsonl").exists())


class MainConnectivityTests(unittest.TestCase):
    def test_main_waits_for_container_connectivity_before_launching_agent(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            prompt = root / "prompt.txt"
            prompt.write_text("rules\n", encoding="utf-8")
            runs_dir = root / "runs"
            argv = [
                "orchestrator.py",
                "--container",
                "sandbox-1",
                "--runs-dir",
                str(runs_dir),
                "--run-id",
                "run-1",
                "--api-key",
                "test-key",
                "--base-url",
                "http://192.168.122.1:18080/v1",
                "--prompt-source",
                str(prompt),
            ]
            call_order: list[str] = []

            with mock.patch.object(sys, "argv", argv):
                with mock.patch.object(orchestrator, "init_git_repo"):
                    with mock.patch.object(orchestrator, "sync_prompt_to_container", return_value={"ok": True}):
                        with mock.patch.object(orchestrator, "git_commit", return_value={"returncode": 0}):
                            with mock.patch.object(
                                orchestrator,
                                "wait_for_container_base_url",
                                side_effect=lambda *args, **kwargs: call_order.append("wait") or True,
                            ) as wait_for_connectivity:
                                with mock.patch.object(
                                    orchestrator,
                                    "start_agent",
                                    side_effect=lambda *args, **kwargs: call_order.append("start")
                                    or {
                                        "returncode": 1,
                                        "stdout": "",
                                        "stderr": "launch failed",
                                        "run_id": "run-1",
                                        "pid_file": "/workspace/runtime-log/run-1/agent.pid",
                                    },
                                ):
                                    with self.assertRaises(SystemExit) as raised:
                                        orchestrator.main()

        self.assertEqual(raised.exception.code, 1)
        self.assertEqual(call_order[:2], ["wait", "start"])
        wait_for_connectivity.assert_called_once_with("sandbox-1", "http://192.168.122.1:18080/v1")


if __name__ == "__main__":
    unittest.main()
