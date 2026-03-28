import json
import os
import http.client
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest import mock

import container.agent_loop as agent_loop


class BuildMessagesTests(unittest.TestCase):
    def test_build_messages_includes_task_prompt_and_feedback(self) -> None:
        messages = agent_loop.build_messages(
            system_prompt="rules",
            round_index=3,
            task_prompt="repair the sandbox",
            feedback_bundle={
                "recent_rounds": [{"round": 2, "done": "listed files", "next": "inspect README", "thought": "need context"}],
                "last_action": {
                    "done": "list files",
                    "next": "inspect git",
                    "thought": "need more context",
                    "argv": ["bash", "-lc", "ls"],
                },
                "last_tool_result": {"returncode": 0, "stdout": "a\nb\n", "stderr": ""},
                "sandbox_state": {"sandbox_tree": "./a\n./b", "sandbox_git_status": "?? a"},
            },
        )
        payload = json.loads(messages[1]["content"])
        self.assertEqual(payload["task_prompt"], "repair the sandbox")
        self.assertEqual(payload["recent_rounds"][0]["round"], 2)
        self.assertEqual(payload["recent_rounds"][0]["done"], "listed files")
        self.assertEqual(payload["last_action"]["thought"], "need more context")
        self.assertIn("sandbox_state", payload)

    def test_build_messages_trims_large_feedback(self) -> None:
        messages = agent_loop.build_messages(
            system_prompt="rules",
            round_index=1,
            task_prompt="repair",
            feedback_bundle={
                "recent_rounds": [{"round": 1, "done": "z" * 5000, "next": "", "thought": ""}],
                "last_action": {"done": "q" * 5000, "next": "", "thought": ""},
                "last_tool_result": {"stdout": "x" * 5000, "stderr": ""},
                "sandbox_state": {"sandbox_tree": "y" * 5000, "sandbox_git_status": ""},
            },
        )
        payload = json.loads(messages[1]["content"])
        self.assertLess(len(payload["last_tool_result"]["stdout"]), 5000)
        self.assertLess(len(payload["sandbox_state"]["sandbox_tree"]), 5000)
        self.assertLess(len(payload["last_action"]["done"]), 5000)
        self.assertLess(len(payload["recent_rounds"][0]["done"]), 5000)


class BuildFeedbackBundleTests(unittest.TestCase):
    def test_feedback_bundle_uses_recent_rounds_and_latest_result(self) -> None:
        bundle = agent_loop.build_feedback_bundle(
            round_index=4,
            state_before={"sandbox_tree": "./a", "sandbox_git_status": "?? a"},
            latest_action={"done": "inspect", "next": "modify", "thought": "safe first"},
            latest_tool_result={"returncode": 0, "stdout": "ok", "stderr": ""},
            recent_rounds=[
                {"event": "round_completed", "round": 1, "done": "one", "next": "two", "thought": "three"},
                {"event": "round_completed", "round": 2, "done": "two", "next": "three", "thought": "four"},
                {"event": "round_failed", "round": 3, "error": "boom"},
            ],
        )
        self.assertEqual(len(bundle["recent_rounds"]), 3)
        self.assertEqual(bundle["last_tool_result"]["returncode"], 0)
        self.assertEqual(bundle["last_action"]["done"], "inspect")


class ValidateActionTests(unittest.TestCase):
    def test_validate_action_requires_done_next_and_thought(self) -> None:
        action = agent_loop.validate_action(
            {
                "done": "checked files",
                "next": "open README",
                "thought": "need repo context",
                "argv": ["bash", "-lc", "ls"],
                "timeout": "30",
            }
        )

        self.assertEqual(action["timeout"], 30)
        self.assertEqual(action["summary"], "checked files")

    def test_validate_action_rejects_missing_required_text(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing non-empty next"):
            agent_loop.validate_action(
                {
                    "done": "checked files",
                    "next": "",
                    "thought": "need repo context",
                    "argv": ["bash", "-lc", "ls"],
                    "timeout": 30,
                }
            )


class ResolveRuntimePathsTests(unittest.TestCase):
    def test_resolve_runtime_paths_uses_env_overrides(self) -> None:
        with TemporaryDirectory() as tmpdir:
            sandbox = Path(tmpdir) / "sandbox"
            log_root = Path(tmpdir) / "logs"
            prompt = Path(tmpdir) / "prompt.txt"
            tool = Path(tmpdir) / "tool.py"
            with mock.patch.dict(
                os.environ,
                {
                    "MARATHON_SANDBOX": str(sandbox),
                    "MARATHON_LOG_ROOT": str(log_root),
                    "MARATHON_PROMPT_FILE": str(prompt),
                    "MARATHON_TOOL_FILE": str(tool),
                },
                clear=False,
            ):
                paths = agent_loop.resolve_runtime_paths()
        self.assertEqual(paths["sandbox"], sandbox)
        self.assertEqual(paths["log_root"], log_root)
        self.assertEqual(paths["prompt_file"], prompt)
        self.assertEqual(paths["tool_file"], tool)


class CollectStateTests(unittest.TestCase):
    def test_collect_state_includes_prompt_and_loop_source(self) -> None:
        expected_loop_source = Path(agent_loop.__file__).read_text(encoding="utf-8", errors="replace")
        with TemporaryDirectory() as tmpdir:
            prompt_file = Path(tmpdir) / "prompt.txt"
            sandbox_dir = Path(tmpdir) / "sandbox"
            prompt_file.write_text("SYSTEM PROMPT", encoding="utf-8")
            sandbox_dir.mkdir()
            with mock.patch.dict(
                os.environ,
                {
                    "MARATHON_PROMPT_FILE": str(prompt_file),
                    "MARATHON_SANDBOX": str(sandbox_dir),
                },
                clear=False,
            ):
                state = agent_loop.collect_state()

        self.assertEqual(state["prompt_source"], "SYSTEM PROMPT")
        self.assertEqual(state["loop_source"], expected_loop_source)


class CallModelTests(unittest.TestCase):
    class _FakeResponse:
        def __init__(self, *, payload: dict[str, object] | None = None, error: Exception | None = None) -> None:
            self.payload = payload
            self.error = error

        def __enter__(self) -> "CallModelTests._FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            if self.error is not None:
                raise self.error
            return json.dumps(self.payload).encode("utf-8")

    def test_call_model_retries_after_incomplete_read(self) -> None:
        responses = [
            self._FakeResponse(error=http.client.IncompleteRead(b'{"choices":[{"message":{"content":"partial')),
            self._FakeResponse(payload={"choices": [{"message": {"content": "{\"cmd\":\"pwd\"}"}}]}),
        ]
        with mock.patch.object(agent_loop.urllib.request, "urlopen", side_effect=responses) as urlopen:
            with mock.patch.object(agent_loop.time, "sleep") as sleep:
                content, payload = agent_loop.call_model(
                    "https://example.com/v1",
                    "test-key",
                    "gpt-5.4",
                    [{"role": "user", "content": "hi"}],
                    agent_loop.load_model_settings(""),
                )

        self.assertEqual(content, "{\"cmd\":\"pwd\"}")
        self.assertEqual(payload["choices"][0]["message"]["content"], "{\"cmd\":\"pwd\"}")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once()


if __name__ == "__main__":
    unittest.main()
