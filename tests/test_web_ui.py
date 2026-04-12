import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import json
import urllib.request
from contextlib import contextmanager
from threading import Thread

import host.web_ui as web_ui


@contextmanager
def serve_app() -> tuple[web_ui.ThreadingHTTPServer, str]:
    server = web_ui.ThreadingHTTPServer(("127.0.0.1", 0), web_ui.AppHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield server, f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class ResolveTaskPromptTests(unittest.TestCase):
    def test_resolve_task_prompt_uses_default_when_blank(self) -> None:
        self.assertEqual(
            web_ui.resolve_task_prompt({"task_prompt": "   "}),
            web_ui.DEFAULT_TASK_PROMPT,
        )

    def test_resolve_task_prompt_preserves_explicit_value(self) -> None:
        self.assertEqual(
            web_ui.resolve_task_prompt({"task_prompt": "inspect project and improve docs"}),
            "inspect project and improve docs",
        )


class ResolveRunModeTests(unittest.TestCase):
    def test_defaults_to_task_mode(self) -> None:
        self.assertEqual(web_ui.resolve_run_mode({}), "task")

    def test_accepts_freeplay_mode(self) -> None:
        self.assertEqual(web_ui.resolve_run_mode({"mode": "freeplay"}), "freeplay")

    def test_apply_run_mode_defaults_for_freeplay_sets_expected_defaults(self) -> None:
        resolved = web_ui.apply_run_mode_defaults(
            {"mode": "freeplay"},
            {
                "model": "gpt-5.4",
                "base_url": "https://example.com/v1",
                "api_key": "test-key",
                "model_settings": {"profile_id": "default", "profile_label": "默认配置", "extra_body": {}},
                "profile": {"id": "default"},
            },
        )

        self.assertEqual(resolved["mode"], "freeplay")
        self.assertEqual(resolved["task_prompt"], web_ui.FREEPLAY_TASK_PROMPT)
        self.assertEqual(resolved["max_rounds"], 0)
        self.assertEqual(resolved["sleep_seconds"], 1.0)
        self.assertEqual(resolved["model_settings"]["request_max_attempts"], 10)
        self.assertEqual(resolved["model_settings"]["request_retry_delay_seconds"], 2.0)

    def test_apply_run_mode_defaults_parses_runtime_budget_fields(self) -> None:
        resolved = web_ui.apply_run_mode_defaults(
            {
                "mode": "task",
                "task_prompt": "stay focused",
                "max_rounds": "5",
                "sleep_seconds": "2.5",
                "max_runtime_seconds": "600",
                "max_total_tokens": "12000",
            },
            {
                "model": "gpt-5.4",
                "base_url": "https://example.com/v1",
                "api_key": "test-key",
                "model_settings": {"profile_id": "default", "profile_label": "默认配置", "extra_body": {}},
                "profile": {"id": "default"},
            },
        )

        self.assertEqual(resolved["max_rounds"], 5)
        self.assertEqual(resolved["sleep_seconds"], 2.5)
        self.assertEqual(resolved["max_runtime_seconds"], 600)
        self.assertEqual(resolved["max_total_tokens"], 12000)


class ModelProfilesTests(unittest.TestCase):
    def test_read_model_profiles_payload_refreshes_default_profile_from_environment(self) -> None:
        with TemporaryDirectory() as tmpdir:
            profiles_file = Path(tmpdir) / "model_profiles.json"
            profiles_file.write_text(
                """{
  "path": "ignored",
  "default_profile_id": "default",
  "profiles": [
    {
      "id": "default",
      "label": "默认配置",
      "model": "gpt-5.4",
      "base_url": "http://49.235.88.239:3000/v1",
      "api_key": "old-key",
      "reasoning_effort": "",
      "temperature": 0.7,
      "top_p": null,
      "max_completion_tokens": null,
      "request_timeout_seconds": 120,
      "extra_body": {}
    }
  ],
  "updated_at": "2026-03-09T16:39:00+0800"
}
""",
                encoding="utf-8",
            )
            with mock.patch.object(web_ui, "MODEL_PROFILES_FILE", profiles_file):
                with mock.patch.dict(
                    web_ui.os.environ,
                    {
                        "MARATHON_BASE_URL": "https://example.com/v1",
                        "MARATHON_API_KEY": "new-key",
                        "MARATHON_MODEL": "gpt-5.4",
                    },
                    clear=False,
                ):
                    payload = web_ui.read_model_profiles_payload()

        self.assertEqual(payload["profiles"][0]["base_url"], "https://example.com/v1")
        self.assertEqual(payload["profiles"][0]["api_key"], "new-key")

    def test_resolve_run_model_config_accepts_runtime_override_fields(self) -> None:
        with TemporaryDirectory() as tmpdir:
            profiles_file = Path(tmpdir) / "model_profiles.json"
            profiles_file.write_text(
                """{
  "path": "ignored",
  "default_profile_id": "default",
  "profiles": [
    {
      "id": "default",
      "label": "默认配置",
      "model": "gpt-5.4",
      "base_url": "https://example.com/v1",
      "api_key": "profile-key",
      "reasoning_effort": "medium",
      "temperature": 0.7,
      "top_p": 0.9,
      "max_completion_tokens": 3200,
      "request_timeout_seconds": 120,
      "request_max_attempts": 3,
      "request_retry_delay_seconds": 1.0,
      "extra_body": {"provider":"default"}
    }
  ],
  "updated_at": "2026-03-09T16:39:00+0800"
}
""",
                encoding="utf-8",
            )
            with mock.patch.object(web_ui, "MODEL_PROFILES_FILE", profiles_file):
                resolved = web_ui.resolve_run_model_config(
                    {
                        "model": "gpt-5.4-mini",
                        "base_url": "https://alt.example.com/v1",
                        "api_key": "request-key",
                        "reasoning_effort": "high",
                        "temperature": "0.2",
                        "top_p": "0.8",
                        "max_completion_tokens": "6400",
                        "request_timeout_seconds": "180",
                        "request_max_attempts": "6",
                        "request_retry_delay_seconds": "3.5",
                        "extra_body": "{\"provider\":\"override\"}",
                    }
                )

        self.assertEqual(resolved["model"], "gpt-5.4-mini")
        self.assertEqual(resolved["base_url"], "https://alt.example.com/v1")
        self.assertEqual(resolved["api_key"], "request-key")
        self.assertEqual(resolved["model_settings"]["reasoning_effort"], "high")
        self.assertEqual(resolved["model_settings"]["temperature"], 0.2)
        self.assertEqual(resolved["model_settings"]["top_p"], 0.8)
        self.assertEqual(resolved["model_settings"]["max_completion_tokens"], 6400)
        self.assertEqual(resolved["model_settings"]["request_timeout_seconds"], 180.0)
        self.assertEqual(resolved["model_settings"]["request_max_attempts"], 6)
        self.assertEqual(resolved["model_settings"]["request_retry_delay_seconds"], 3.5)
        self.assertEqual(resolved["model_settings"]["extra_body"], {"provider": "override"})


class ModelConnectivityTests(unittest.TestCase):
    class _FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload

        def __enter__(self) -> "ModelConnectivityTests._FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def read(self) -> bytes:
            return json.dumps(self.payload).encode("utf-8")

    def test_test_model_connectivity_returns_latency_preview_and_usage(self) -> None:
        response = self._FakeResponse(
            {
                "model": "gpt-5.4",
                "choices": [{"message": {"content": "pong"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
            }
        )
        with mock.patch.object(
            web_ui,
            "resolve_run_model_config",
            return_value={
                "model": "gpt-5.4",
                "base_url": "https://example.com/v1",
                "api_key": "test-key",
                "model_settings": {
                    "reasoning_effort": "low",
                    "request_timeout_seconds": 5,
                    "request_max_attempts": 1,
                    "request_retry_delay_seconds": 1,
                    "extra_body": {},
                },
                "profile": {"id": "default"},
            },
        ), mock.patch.object(web_ui.urllib.request, "urlopen", return_value=response), mock.patch.object(
            web_ui.time, "monotonic", side_effect=[10.0, 10.12]
        ):
            result = web_ui.test_model_connectivity({"model": "gpt-5.4"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["response_model"], "gpt-5.4")
        self.assertEqual(result["preview"], "pong")
        self.assertEqual(result["usage"]["total_tokens"], 15)
        self.assertEqual(result["latency_ms"], 119)


class ContainerBlogPayloadTests(unittest.TestCase):
    def test_reads_container_blog_archive_with_latest_post_first(self) -> None:
        with TemporaryDirectory() as tmpdir:
            blog_dir = Path(tmpdir)
            (blog_dir / "sandbox-1.jsonl").write_text(
                "\n".join(
                    [
                        '{"type":"round_post","container":"sandbox-1","run_id":"run-1","round":1,"done":"one","next":"two","thought":"three","ts":"2026-03-26T12:00:00+0800"}',
                        '{"type":"round_post","container":"sandbox-1","run_id":"run-1","round":2,"done":"two","next":"three","thought":"four","ts":"2026-03-26T12:01:00+0800"}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (blog_dir / "sandbox-1.meta.json").write_text(
                '{"container":"sandbox-1","post_count":2,"updated_at":"2026-03-26T12:01:00+0800"}\n',
                encoding="utf-8",
            )

            with mock.patch.object(web_ui, "CONTAINER_BLOG_DIR", blog_dir):
                payload = web_ui.container_blog_payload("sandbox-1")

        self.assertEqual(payload["latest_blog_post"]["round"], 2)
        self.assertEqual(len(payload["blog_posts"]), 2)
        self.assertEqual(payload["blog_posts"][0]["done"], "two")
        self.assertEqual(payload["blog_meta"]["post_count"], 2)

    def test_run_detail_exposes_invalid_response_artifacts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / "runs" / "run-1"
            rounds_dir = run_dir / "rounds" / "0004"
            rounds_dir.mkdir(parents=True)
            (run_dir / "host_run.json").write_text(
                '{"container":"sandbox-1","mode":"task","started_at":"2026-04-05T10:00:00+0800"}\n',
                encoding="utf-8",
            )
            (run_dir / "status.json").write_text(
                '{"state":"failed","completed_rounds":3,"failed_round":4,"updated_at":"2026-04-05T10:05:00+0800"}\n',
                encoding="utf-8",
            )
            (rounds_dir / "response.invalid-01.txt").write_text('bad raw response', encoding="utf-8")
            (rounds_dir / "response.invalid-01.raw.json").write_text('{"choices":[]}\n', encoding="utf-8")
            (rounds_dir / "error.json").write_text('{"round":4,"error":"bad json"}\n', encoding="utf-8")

            with mock.patch.object(web_ui, "RUNS_DIR", root / "runs"):
                payload = web_ui.run_detail("run-1")

        self.assertEqual(len(payload["invalid_response_artifacts"]), 1)
        self.assertIn("bad raw response", payload["invalid_response_artifacts"][0]["text"])
        self.assertIn("bad json", payload["latest_round_error_text"])


class IngestionRouteTests(unittest.TestCase):
    def test_ingest_routes_write_run_truth_files(self) -> None:
        with TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs"
            runs_dir.mkdir()

            def post(base_url: str, path: str, payload: dict[str, object]) -> dict[str, object]:
                req = urllib.request.Request(
                    base_url + path,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req) as response:
                    return json.loads(response.read().decode("utf-8"))

            with mock.patch.object(web_ui, "RUNS_DIR", runs_dir), mock.patch.object(
                web_ui.run_index, "RUNS_DIR", runs_dir
            ), serve_app() as (_, base_url):
                run_result = post(
                    base_url,
                    "/api/ingest/runs",
                    {
                        "run_id": "run-ingest-1",
                        "host_run": {"container": "sandbox-1", "model": "gpt-5.4"},
                        "status": {"state": "running", "completed_rounds": 0},
                    },
                )
                events_result = post(
                    base_url,
                    "/api/ingest/events",
                    {
                        "run_id": "run-ingest-1",
                        "events": [{"event": "run_started", "ts": "2026-04-07T11:00:00+0800"}],
                    },
                )
                posts_result = post(
                    base_url,
                    "/api/ingest/round-posts",
                    {
                        "run_id": "run-ingest-1",
                        "posts": [
                            {
                                "round": 1,
                                "done": "checked sandbox",
                                "next": "open README",
                                "thought": "need context",
                                "argv": ["bash", "-lc", "pwd"],
                                "timeout": 30,
                            }
                        ],
                    },
                )
                artifacts_result = post(
                    base_url,
                    "/api/ingest/artifacts",
                    {
                        "run_id": "run-ingest-1",
                        "artifacts": [
                            {"name": "latest_response.txt", "content": "raw response text"},
                            {"round": 1, "name": "response.invalid-01.txt", "content": "bad json attempt"},
                            {"round": 1, "name": "response.invalid-01.raw.json", "content": {"choices": []}},
                        ],
                    },
                )

            run_dir = runs_dir / "run-ingest-1"
            self.assertTrue(run_result["ok"])
            self.assertEqual(events_result["appended"], 1)
            self.assertEqual(posts_result["appended"], 1)
            self.assertEqual(len(artifacts_result["written"]), 3)
            self.assertTrue((run_dir / "host_run.json").exists())
            self.assertTrue((run_dir / "status.json").exists())
            self.assertTrue((run_dir / "events.jsonl").exists())
            self.assertTrue((run_dir / "blog.jsonl").exists())
            self.assertTrue((run_dir / "latest_action.json").exists())
            self.assertEqual((run_dir / "latest_response.txt").read_text(encoding="utf-8"), "raw response text")
            self.assertEqual(
                (run_dir / "rounds" / "0001" / "response.invalid-01.txt").read_text(encoding="utf-8"),
                "bad json attempt",
            )

    def test_ingest_routes_require_token_when_configured(self) -> None:
        with TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir) / "runs"
            runs_dir.mkdir()

            def post(base_url: str, path: str, payload: dict[str, object], *, token: str | None = None) -> tuple[int, str]:
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["X-Marathon-Ingest-Token"] = token
                req = urllib.request.Request(
                    base_url + path,
                    data=json.dumps(payload).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req) as response:
                        return response.status, response.read().decode("utf-8")
                except urllib.error.HTTPError as error:
                    return error.code, error.read().decode("utf-8")

            with mock.patch.object(web_ui, "RUNS_DIR", runs_dir), mock.patch.object(
                web_ui.run_index, "RUNS_DIR", runs_dir
            ), mock.patch.dict(web_ui.os.environ, {"MARATHON_INGEST_TOKEN": "secret-ingest"}, clear=False), serve_app() as (_, base_url):
                missing_status, missing_body = post(
                    base_url,
                    "/api/ingest/runs",
                    {"run_id": "run-ingest-auth-1", "host_run": {"container": "sandbox-1"}},
                )
                wrong_status, wrong_body = post(
                    base_url,
                    "/api/ingest/runs",
                    {"run_id": "run-ingest-auth-1", "host_run": {"container": "sandbox-1"}},
                    token="wrong",
                )
                ok_status, ok_body = post(
                    base_url,
                    "/api/ingest/runs",
                    {"run_id": "run-ingest-auth-1", "host_run": {"container": "sandbox-1"}},
                    token="secret-ingest",
                )

            self.assertEqual(missing_status, 403)
            self.assertIn("ingestion token required", missing_body)
            self.assertEqual(wrong_status, 403)
            self.assertIn("invalid ingestion token", wrong_body)
            self.assertEqual(ok_status, 200)
            self.assertIn('"ok": true', ok_body)


class AgentAccountPayloadTests(unittest.TestCase):
    def test_reads_agent_account_with_latest_post_first(self) -> None:
        with TemporaryDirectory() as tmpdir:
            account_dir = Path(tmpdir)
            (account_dir / "writer-1.json").write_text(
                '{"agent_account_id":"agent-1","agent_handle":"writer-1","display_name":"Writer One","bio":"local test account","instance_id":"writer-1-main","auth_token":"secret-token","created_at":"2026-03-27T09:00:00+0800","updated_at":"2026-03-27T09:10:00+0800"}\n',
                encoding="utf-8",
            )
            (account_dir / "writer-1.posts.jsonl").write_text(
                "\n".join(
                    [
                        '{"agent_handle":"writer-1","round":1,"done":"first","next":"second","thought":"third","ts":"2026-03-27T09:01:00+0800"}',
                        '{"agent_handle":"writer-1","round":2,"done":"new","next":"later","thought":"more","ts":"2026-03-27T09:02:00+0800"}',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(web_ui, "AGENT_ACCOUNT_DIR", account_dir):
                payload = web_ui.agent_account_payload("writer-1")

        self.assertEqual(payload["account"]["agent_handle"], "writer-1")
        self.assertEqual(payload["account"]["instance_id"], "writer-1-main")
        self.assertNotIn("auth_token", payload["account"])
        self.assertEqual(payload["latest_post"]["round"], 2)
        self.assertEqual(payload["posts"][0]["done"], "new")
        self.assertEqual(payload["post_count"], 2)

    def test_lists_agent_accounts_with_latest_post_preview(self) -> None:
        with TemporaryDirectory() as tmpdir:
            account_dir = Path(tmpdir)
            (account_dir / "writer-1.json").write_text(
                '{"agent_account_id":"agent-1","agent_handle":"writer-1","display_name":"Writer One","instance_id":"writer-1-main","auth_token":"secret-token","created_at":"2026-03-27T09:00:00+0800","updated_at":"2026-03-27T09:10:00+0800"}\n',
                encoding="utf-8",
            )
            (account_dir / "writer-1.posts.jsonl").write_text(
                '{"agent_handle":"writer-1","round":3,"done":"latest entry","next":"later","thought":"more","ts":"2026-03-27T09:03:00+0800"}\n',
                encoding="utf-8",
            )

            with mock.patch.object(web_ui, "AGENT_ACCOUNT_DIR", account_dir):
                payload = web_ui.agent_accounts_payload()

        self.assertEqual(len(payload["accounts"]), 1)
        self.assertEqual(payload["accounts"][0]["agent_handle"], "writer-1")
        self.assertEqual(payload["accounts"][0]["instance_id"], "writer-1-main")
        self.assertNotIn("auth_token", payload["accounts"][0])
        self.assertEqual(payload["accounts"][0]["latest_post"]["round"], 3)
        self.assertIn("latest entry", payload["accounts"][0]["latest_preview"])


class AgentAccountWriteProtectionTests(unittest.TestCase):
    def test_register_agent_account_returns_public_account_and_private_credentials(self) -> None:
        with TemporaryDirectory() as tmpdir:
            account_dir = Path(tmpdir)
            with mock.patch.object(web_ui, "AGENT_ACCOUNT_DIR", account_dir):
                result = web_ui.register_agent_account(
                    {
                        "agent_handle": "writer-2",
                        "display_name": "Writer Two",
                        "default_model": "gpt-5.4",
                        "bio": "Writes experimental notes.",
                    }
                )

                saved = web_ui.read_json(account_dir / "writer-2.json")

        self.assertTrue(result["ok"])
        self.assertEqual(result["account"]["agent_handle"], "writer-2")
        self.assertIn("instance_id", result["account"])
        self.assertNotIn("auth_token", result["account"])
        self.assertTrue(result["credentials"]["auth_token"])
        self.assertEqual(result["credentials"]["instance_id"], result["account"]["instance_id"])
        self.assertEqual(saved["auth_token"], result["credentials"]["auth_token"])
        self.assertEqual(saved["instance_id"], result["credentials"]["instance_id"])

    def test_register_existing_account_with_credentials_is_rejected(self) -> None:
        with TemporaryDirectory() as tmpdir:
            account_dir = Path(tmpdir)
            (account_dir / "writer-3.json").write_text(
                '{"agent_account_id":"agent-writer-3","agent_handle":"writer-3","display_name":"Writer Three","instance_id":"writer-3-main","auth_token":"secret-token","created_at":"2026-03-27T09:00:00+0800","updated_at":"2026-03-27T09:10:00+0800"}\n',
                encoding="utf-8",
            )

            with mock.patch.object(web_ui, "AGENT_ACCOUNT_DIR", account_dir):
                with self.assertRaises(FileExistsError):
                    web_ui.register_agent_account({"agent_handle": "writer-3"})

    def test_register_existing_legacy_account_backfills_credentials_once(self) -> None:
        with TemporaryDirectory() as tmpdir:
            account_dir = Path(tmpdir)
            (account_dir / "writer-4.json").write_text(
                '{"agent_account_id":"agent-writer-4","agent_handle":"writer-4","display_name":"Writer Four","created_at":"2026-03-27T09:00:00+0800","updated_at":"2026-03-27T09:10:00+0800"}\n',
                encoding="utf-8",
            )

            with mock.patch.object(web_ui, "AGENT_ACCOUNT_DIR", account_dir):
                result = web_ui.register_agent_account({"agent_handle": "writer-4"})

        self.assertTrue(result["ok"])
        self.assertFalse(result["created"])
        self.assertTrue(result["migrated_legacy_credentials"])
        self.assertTrue(result["credentials"]["auth_token"])
        self.assertTrue(result["credentials"]["instance_id"])

    def test_append_agent_account_post_requires_matching_token_and_instance_id(self) -> None:
        with TemporaryDirectory() as tmpdir:
            account_dir = Path(tmpdir)
            (account_dir / "writer-5.json").write_text(
                '{"agent_account_id":"agent-writer-5","agent_handle":"writer-5","display_name":"Writer Five","instance_id":"writer-5-main","auth_token":"secret-token","created_at":"2026-03-27T09:00:00+0800","updated_at":"2026-03-27T09:10:00+0800"}\n',
                encoding="utf-8",
            )

            with mock.patch.object(web_ui, "AGENT_ACCOUNT_DIR", account_dir):
                with self.assertRaises(PermissionError):
                    web_ui.append_agent_account_post(
                        "writer-5",
                        {"round": 1, "done": "attempted write"},
                        auth_token="wrong-token",
                        instance_id="writer-5-main",
                    )

                with self.assertRaises(PermissionError):
                    web_ui.append_agent_account_post(
                        "writer-5",
                        {"round": 1, "done": "attempted write"},
                        auth_token="secret-token",
                        instance_id="writer-5-sidecar",
                    )

    def test_append_agent_account_post_persists_instance_id_for_valid_writer(self) -> None:
        with TemporaryDirectory() as tmpdir:
            account_dir = Path(tmpdir)
            (account_dir / "writer-6.json").write_text(
                '{"agent_account_id":"agent-writer-6","agent_handle":"writer-6","display_name":"Writer Six","instance_id":"writer-6-main","auth_token":"secret-token","created_at":"2026-03-27T09:00:00+0800","updated_at":"2026-03-27T09:10:00+0800"}\n',
                encoding="utf-8",
            )

            with mock.patch.object(web_ui, "AGENT_ACCOUNT_DIR", account_dir):
                result = web_ui.append_agent_account_post(
                    "writer-6",
                    {"round": 2, "done": "published note", "next": "continue"},
                    auth_token="secret-token",
                    instance_id="writer-6-main",
                )
                posts = web_ui.read_jsonl(account_dir / "writer-6.posts.jsonl")

        self.assertTrue(result["ok"])
        self.assertEqual(result["post"]["instance_id"], "writer-6-main")
        self.assertEqual(posts[0]["instance_id"], "writer-6-main")


class ContainerAgentBindingTests(unittest.TestCase):
    def test_set_container_agent_binding_persists_handle_and_returns_public_account(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            account_dir = root / "agent_accounts"
            state_dir = root / "containers"
            blog_dir = root / "container_blogs"
            account_dir.mkdir(parents=True)
            state_dir.mkdir(parents=True)
            blog_dir.mkdir(parents=True)
            (account_dir / "writer-1.json").write_text(
                '{"agent_account_id":"agent-writer-1","agent_handle":"writer-1","display_name":"Writer One","instance_id":"writer-1-main","auth_token":"secret-token","created_at":"2026-03-27T09:00:00+0800","updated_at":"2026-03-27T09:10:00+0800"}\n',
                encoding="utf-8",
            )
            (state_dir / "sandbox-1.json").write_text(
                '{"container_name":"sandbox-1","network_mode":"bridge-static"}\n',
                encoding="utf-8",
            )

            with mock.patch.object(web_ui, "AGENT_ACCOUNT_DIR", account_dir), mock.patch.object(
                web_ui, "CONTAINER_STATE_DIR", state_dir
            ), mock.patch.object(web_ui, "CONTAINER_BLOG_DIR", blog_dir):
                result = web_ui.set_container_agent_binding("sandbox-1", "writer-1")
                saved = web_ui.read_json(state_dir / "sandbox-1.json")

        self.assertEqual(saved["agent_handle"], "writer-1")
        self.assertEqual(result["agent_handle"], "writer-1")
        self.assertEqual(result["account"]["agent_handle"], "writer-1")
        self.assertNotIn("auth_token", result["account"])

    def test_set_container_agent_binding_none_clears_handle_and_sync_meta(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            account_dir = root / "agent_accounts"
            state_dir = root / "containers"
            blog_dir = root / "container_blogs"
            account_dir.mkdir(parents=True)
            state_dir.mkdir(parents=True)
            blog_dir.mkdir(parents=True)
            (state_dir / "sandbox-1.json").write_text(
                '{"container_name":"sandbox-1","agent_handle":"writer-1"}\n',
                encoding="utf-8",
            )
            (blog_dir / "sandbox-1.meta.json").write_text(
                '{"container":"sandbox-1","agent_binding":{"agent_handle":"writer-1","last_account_sync_round":2}}\n',
                encoding="utf-8",
            )

            with mock.patch.object(web_ui, "AGENT_ACCOUNT_DIR", account_dir), mock.patch.object(
                web_ui, "CONTAINER_STATE_DIR", state_dir
            ), mock.patch.object(web_ui, "CONTAINER_BLOG_DIR", blog_dir):
                result = web_ui.set_container_agent_binding("sandbox-1", None)
                saved = web_ui.read_json(state_dir / "sandbox-1.json")
                saved_blog_meta = web_ui.read_json(blog_dir / "sandbox-1.meta.json")

        self.assertNotIn("agent_handle", saved)
        self.assertNotIn("agent_binding", saved_blog_meta)
        self.assertIsNone(result["agent_handle"])
        self.assertIsNone(result["account"])

    def test_set_container_agent_binding_rejects_unknown_account(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            account_dir = root / "agent_accounts"
            state_dir = root / "containers"
            blog_dir = root / "container_blogs"
            account_dir.mkdir(parents=True)
            state_dir.mkdir(parents=True)
            blog_dir.mkdir(parents=True)
            (state_dir / "sandbox-1.json").write_text('{"container_name":"sandbox-1"}\n', encoding="utf-8")

            with mock.patch.object(web_ui, "AGENT_ACCOUNT_DIR", account_dir), mock.patch.object(
                web_ui, "CONTAINER_STATE_DIR", state_dir
            ), mock.patch.object(web_ui, "CONTAINER_BLOG_DIR", blog_dir):
                with self.assertRaises(ValueError):
                    web_ui.set_container_agent_binding("sandbox-1", "missing-account")


class ContainerAgentSettingsTests(unittest.TestCase):
    def test_write_container_agent_settings_creates_backup_before_update(self) -> None:
        with TemporaryDirectory() as tmpdir:
            container_dir = Path(tmpdir) / "containers"
            backup_dir = Path(tmpdir) / "backups"
            container_dir.mkdir()
            (container_dir / "sandbox-1.json").write_text(
                """{
  "container_name": "sandbox-1",
  "network_mode": "bridge-static",
  "agent_settings": {
    "max_rounds": 3,
    "sleep_seconds": 1.0
  }
}
""",
                encoding="utf-8",
            )

            with mock.patch.object(web_ui, "CONTAINER_STATE_DIR", container_dir), mock.patch.object(
                web_ui, "CONTAINER_SETTINGS_BACKUP_DIR", backup_dir
            ):
                result = web_ui.write_container_agent_settings(
                    "sandbox-1",
                    {"agent_settings": {"max_rounds": 8, "max_total_tokens": 16000}},
                )
                saved = web_ui.read_json(container_dir / "sandbox-1.json")

        self.assertTrue(result["ok"])
        self.assertIsNotNone(result["backup"])
        self.assertEqual(saved["agent_settings"]["max_rounds"], 8)
        self.assertEqual(saved["agent_settings"]["max_total_tokens"], 16000)
        self.assertEqual(saved["network_mode"], "bridge-static")
        self.assertEqual(result["backup_summary"]["count"], 1)

    def test_merge_container_agent_settings_keeps_explicit_request_values(self) -> None:
        with TemporaryDirectory() as tmpdir:
            container_dir = Path(tmpdir) / "containers"
            container_dir.mkdir()
            (container_dir / "sandbox-1.json").write_text(
                """{
  "container_name": "sandbox-1",
  "agent_settings": {
    "max_rounds": 7,
    "sleep_seconds": 2.0,
    "max_total_tokens": 9000,
    "model": "gpt-5.4"
  }
}
""",
                encoding="utf-8",
            )

            with mock.patch.object(web_ui, "CONTAINER_STATE_DIR", container_dir):
                merged = web_ui.merge_container_agent_settings(
                    "sandbox-1",
                    {"sleep_seconds": "0.5", "model": "gpt-5.4-mini"},
                )

        self.assertEqual(merged["max_rounds"], 7)
        self.assertEqual(merged["max_total_tokens"], 9000)
        self.assertEqual(merged["sleep_seconds"], "0.5")
        self.assertEqual(merged["model"], "gpt-5.4-mini")


class StartRunBindingInheritanceTests(unittest.TestCase):
    def test_start_run_inherits_base_agent_handle_when_omitted(self) -> None:
        with mock.patch.object(web_ui, "clone_container", return_value={"ok": True}) as clone_container, mock.patch.object(
            web_ui,
            "read_container_state_meta",
            side_effect=lambda name: {"agent_handle": "writer-1"} if name == "base-box" else {},
        ), mock.patch.object(web_ui, "set_container_agent_binding") as set_container_agent_binding, mock.patch.object(
            web_ui,
            "launch_agent_for_container",
            return_value={"ok": True, "launch": {"run_id": "run-1", "container": "child-box"}},
        ) as launch_agent_for_container:
            result = web_ui.start_run(
                "base-box",
                container_name="child-box",
                run_id="run-1",
                model="gpt-5.4",
                base_url="https://example.com/v1",
                api_key="test-key",
                task_prompt="inspect",
                model_settings={},
                max_rounds=0,
                sleep_seconds=1.0,
                max_runtime_seconds=None,
                max_total_tokens=None,
            )

        self.assertTrue(result["ok"])
        clone_container.assert_called_once_with("base-box", "child-box", start=True)
        set_container_agent_binding.assert_called_once_with("child-box", "writer-1")
        self.assertEqual(launch_agent_for_container.call_args.kwargs["agent_handle"], "writer-1")

    def test_start_run_respects_explicit_blank_agent_handle_without_inheriting(self) -> None:
        with mock.patch.object(web_ui, "clone_container", return_value={"ok": True}), mock.patch.object(
            web_ui,
            "read_container_state_meta",
            side_effect=lambda name: {"agent_handle": "writer-1"} if name == "base-box" else {},
        ), mock.patch.object(web_ui, "set_container_agent_binding") as set_container_agent_binding, mock.patch.object(
            web_ui,
            "launch_agent_for_container",
            return_value={"ok": True, "launch": {"run_id": "run-1", "container": "child-box"}},
        ) as launch_agent_for_container:
            result = web_ui.start_run(
                "base-box",
                container_name="child-box",
                run_id="run-1",
                model="gpt-5.4",
                base_url="https://example.com/v1",
                api_key="test-key",
                task_prompt="inspect",
                model_settings={},
                max_rounds=0,
                sleep_seconds=1.0,
                max_runtime_seconds=None,
                max_total_tokens=None,
                agent_handle="",
                agent_handle_explicit=True,
            )

        self.assertTrue(result["ok"])
        set_container_agent_binding.assert_not_called()
        self.assertIsNone(launch_agent_for_container.call_args.kwargs["agent_handle"])


class StartContainerTests(unittest.TestCase):
    def test_returns_preflight_error_when_static_bridge_is_missing(self) -> None:
        with mock.patch.object(
            web_ui,
            "read_container_state_meta",
            return_value={
                "network_mode": "bridge-static",
                "bridge_name": "br-ef44f54afd12",
                "bridge_cidr": "172.21.0.1/16",
                "ipv4_address": "172.21.0.228/16",
                "ipv4_gateway": "172.21.0.1",
            },
        ), mock.patch.object(web_ui, "list_host_links", return_value=["lo", "wlan0"]), mock.patch.object(
            web_ui.lxc_network,
            "detect_veth_support",
            return_value={"available": True, "reason": ""},
        ), mock.patch.object(
            web_ui,
            "lxc_command",
        ) as lxc_command:
            result = web_ui.start_container("marathon-base")

        self.assertFalse(result["ok"])
        self.assertEqual(result["preflight"]["network_mode"], "empty")
        self.assertIn("missing bridge", result["stderr"])
        lxc_command.assert_not_called()

    def test_returns_host_module_error_when_veth_is_unavailable(self) -> None:
        with mock.patch.object(
            web_ui,
            "read_container_state_meta",
            return_value={
                "network_mode": "bridge-static",
                "bridge_name": "virbr0",
                "bridge_cidr": "192.168.122.1/24",
                "ipv4_address": "192.168.122.20/24",
                "ipv4_gateway": "192.168.122.1",
            },
        ), mock.patch.object(web_ui, "list_host_links", return_value=["lo", "virbr0"]), mock.patch.object(
            web_ui.lxc_network,
            "detect_veth_support",
            return_value={"available": False, "reason": "kernel/modules mismatch: running 6.19.6-arch1-1 but only /lib/modules/6.19.8-arch1-1 exists"},
        ), mock.patch.object(web_ui, "lxc_command") as lxc_command:
            result = web_ui.start_container("marathon-base")

        self.assertFalse(result["ok"])
        self.assertEqual(result["preflight"]["network_mode"], "empty")
        self.assertIn("kernel/modules mismatch", result["stderr"])
        lxc_command.assert_not_called()


class RetryLatestRunTests(unittest.TestCase):
    def test_retry_latest_run_reuses_latest_run_configuration(self) -> None:
        detail = {
            "summary": {
                "run_id": "run-old",
                "container": "sandbox-1",
                "mode": "task",
                "model": "gpt-5.4",
                "base_url": "https://example.com/v1",
                "agent_handle": "writer-1",
            },
            "host_run": {
                "task_prompt": "repair repo",
                "max_rounds": 5,
                "sleep_seconds": 2.0,
                "max_runtime_seconds": 600,
                "max_total_tokens": 12000,
            },
            "ui_launch": {
                "mode": "task",
                "model": "gpt-5.4",
                "base_url": "https://example.com/v1",
                "task_prompt": "repair repo",
                "agent_handle": "writer-1",
                "model_settings": {
                    "profile_id": "default",
                    "profile_label": "默认配置",
                    "reasoning_effort": "high",
                    "temperature": 0.2,
                    "request_timeout_seconds": 120,
                    "request_max_attempts": 4,
                    "request_retry_delay_seconds": 2.0,
                    "extra_body": {},
                },
                "max_rounds": 5,
                "sleep_seconds": 2.0,
                "max_runtime_seconds": 600,
                "max_total_tokens": 12000,
            },
        }
        with mock.patch.object(web_ui, "active_run_summary_for_container", return_value=None), mock.patch.object(
            web_ui,
            "latest_run_summary_for_container",
            return_value={"run_id": "run-old", "container": "sandbox-1"},
        ), mock.patch.object(
            web_ui,
            "run_detail",
            return_value=detail,
        ), mock.patch.object(
            web_ui,
            "resolve_run_model_config",
            return_value={
                "model": "gpt-5.4",
                "base_url": "https://example.com/v1",
                "api_key": "test-key",
                "model_settings": {
                    "profile_id": "default",
                    "profile_label": "默认配置",
                    "reasoning_effort": "high",
                    "temperature": 0.2,
                    "request_timeout_seconds": 120,
                    "request_max_attempts": 4,
                    "request_retry_delay_seconds": 2.0,
                    "extra_body": {},
                },
                "profile": {"id": "default"},
            },
        ), mock.patch.object(
            web_ui,
            "launch_agent_for_container",
            return_value={"ok": True, "launch": {"run_id": "run-new", "container": "sandbox-1"}},
        ) as launch_agent_for_container:
            result = web_ui.retry_latest_run_for_container("sandbox-1")

        self.assertTrue(result["ok"])
        self.assertEqual(result["retried_from_run_id"], "run-old")
        self.assertEqual(launch_agent_for_container.call_args.kwargs["task_prompt"], "repair repo")
        self.assertEqual(launch_agent_for_container.call_args.kwargs["max_rounds"], 5)
        self.assertEqual(launch_agent_for_container.call_args.kwargs["max_runtime_seconds"], 600)
        self.assertEqual(launch_agent_for_container.call_args.kwargs["max_total_tokens"], 12000)
        self.assertEqual(launch_agent_for_container.call_args.kwargs["agent_handle"], "writer-1")

    def test_retry_latest_run_rejects_when_active_run_exists(self) -> None:
        with mock.patch.object(web_ui, "active_run_summary_for_container", return_value={"run_id": "run-live"}):
            with self.assertRaises(ValueError):
                web_ui.retry_latest_run_for_container("sandbox-1")

    def test_retry_latest_run_rejects_when_api_key_fingerprint_changes(self) -> None:
        detail = {
            "summary": {"run_id": "run-old", "container": "sandbox-1", "mode": "task"},
            "host_run": {"task_prompt": "repair repo"},
            "ui_launch": {
                "mode": "task",
                "model": "gpt-5.4",
                "base_url": "https://example.com/v1",
                "task_prompt": "repair repo",
                "api_key_fingerprint": "oldfingerprint",
                "model_settings": {"profile_id": "default", "profile_label": "默认配置", "extra_body": {}},
            },
        }
        with mock.patch.object(web_ui, "active_run_summary_for_container", return_value=None), mock.patch.object(
            web_ui,
            "latest_run_summary_for_container",
            return_value={"run_id": "run-old", "container": "sandbox-1"},
        ), mock.patch.object(
            web_ui,
            "run_detail",
            return_value=detail,
        ), mock.patch.object(
            web_ui,
            "resolve_run_model_config",
            return_value={
                "model": "gpt-5.4",
                "base_url": "https://example.com/v1",
                "api_key": "new-key",
                "model_settings": {"profile_id": "default", "profile_label": "默认配置", "extra_body": {}},
                "profile": {"id": "default"},
            },
        ):
            with self.assertRaises(ValueError):
                web_ui.retry_latest_run_for_container("sandbox-1")


class DestroyContainerTests(unittest.TestCase):
    def test_destroy_container_removes_state_meta_after_success(self) -> None:
        with TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)
            meta_path = state_dir / "sandbox-1.json"
            meta_path.write_text("{}", encoding="utf-8")
            with mock.patch.object(web_ui, "CONTAINER_STATE_DIR", state_dir):
                with mock.patch.object(
                    web_ui,
                    "lxc_command",
                    side_effect=[
                        mock.Mock(returncode=0, stdout="", stderr=""),
                        mock.Mock(returncode=0, stdout="", stderr=""),
                    ],
                ):
                    result = web_ui.destroy_container("sandbox-1")
                self.assertFalse(meta_path.exists())

        self.assertTrue(result["ok"])


class WebUiScriptTests(unittest.TestCase):
    def test_start_web_ui_script_defaults_to_localhost(self) -> None:
        script = Path("scripts/start_web_ui.sh").read_text(encoding="utf-8")
        self.assertIn('HOST="${MARATHON_UI_HOST:-127.0.0.1}"', script)

    def test_start_web_ui_script_uses_module_entrypoint(self) -> None:
        script = Path("scripts/start_web_ui.sh").read_text(encoding="utf-8")
        self.assertIn("python3 -m host.web_ui", script)

    def test_start_web_ui_script_exports_project_root_on_pythonpath(self) -> None:
        script = Path("scripts/start_web_ui.sh").read_text(encoding="utf-8")
        self.assertIn('export PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"', script)

    def test_start_web_ui_background_command_passes_pythonpath_into_tmux_env(self) -> None:
        script = Path("scripts/start_web_ui.sh").read_text(encoding="utf-8")
        self.assertIn('PYTHONPATH=${PYTHONPATH@Q}', script)

    def test_start_web_ui_script_detects_port_conflicts_before_claiming_success(self) -> None:
        script = Path("scripts/start_web_ui.sh").read_text(encoding="utf-8")
        self.assertIn('Port ${PORT} is already in use', script)
        self.assertIn('wait_for_port', script)

    def test_stop_web_ui_script_can_stop_host_web_ui_listener_without_tmux(self) -> None:
        script = Path("scripts/stop_web_ui.sh").read_text(encoding="utf-8")
        self.assertIn('Stopped Marathon Web UI listener pid', script)


class StaticRouteResolutionTests(unittest.TestCase):
    def test_resolve_static_asset_supports_dashboard_detail_and_create_pages(self) -> None:
        with TemporaryDirectory() as tmpdir:
            static_dir = Path(tmpdir)
            for filename in ("index.html", "sandboxes.html", "container.html", "new.html", "agents.html", "agent.html", "app.css", "app.js", "favicon.svg"):
                (static_dir / filename).write_text(filename, encoding="utf-8")
            with mock.patch.object(web_ui, "STATIC_DIR", static_dir):
                self.assertEqual(web_ui.resolve_static_asset_path("/"), static_dir / "index.html")
                self.assertEqual(web_ui.resolve_static_asset_path("/favicon.ico"), static_dir / "favicon.svg")
                self.assertEqual(web_ui.resolve_static_asset_path("/sandboxes"), static_dir / "sandboxes.html")
                self.assertEqual(web_ui.resolve_static_asset_path("/container"), static_dir / "container.html")
                self.assertEqual(web_ui.resolve_static_asset_path("/new"), static_dir / "new.html")
                self.assertEqual(web_ui.resolve_static_asset_path("/agents"), static_dir / "agents.html")
                self.assertEqual(web_ui.resolve_static_asset_path("/agent"), static_dir / "agent.html")
                self.assertEqual(web_ui.resolve_static_asset_path("/app.css"), static_dir / "app.css")
                self.assertEqual(web_ui.resolve_static_asset_path("/app.js"), static_dir / "app.js")

    def test_resolve_static_asset_rejects_api_and_parent_escape_paths(self) -> None:
        with TemporaryDirectory() as tmpdir:
            static_dir = Path(tmpdir)
            (static_dir / "index.html").write_text("index", encoding="utf-8")
            with mock.patch.object(web_ui, "STATIC_DIR", static_dir):
                self.assertIsNone(web_ui.resolve_static_asset_path("/api/overview"))
                self.assertIsNone(web_ui.resolve_static_asset_path("/../README.md"))


class StaticHtmlContentTests(unittest.TestCase):
    def test_homepage_contains_browser_layout_and_new_page_navigation(self) -> None:
        content = Path("host/static/index.html").read_text(encoding="utf-8")

        self.assertIn("Marathon 总览", content)
        self.assertIn("当前重点", content)
        self.assertIn("最近活跃", content)
        self.assertIn("全部", content)
        self.assertIn("正在运行", content)
        self.assertIn("最近活跃", content)
        self.assertIn("/new", content)
        self.assertIn("/sandboxes", content)
        self.assertIn("filterTabs", content)
        self.assertIn("featuredRow", content)
        self.assertIn("containerGrid", content)
        self.assertNotIn("启动任务模式", content)
        self.assertNotIn("taskPrompt", content)
        self.assertNotIn("primaryRunPanel", content)
        self.assertNotIn("summaryGrid", content)

    def test_sandboxes_page_exists_with_expected_copy(self) -> None:
        sandboxes_path = Path("host/static/sandboxes.html")

        self.assertTrue(sandboxes_path.exists(), f"missing expected file: {sandboxes_path}")
        content = sandboxes_path.read_text(encoding="utf-8")

        self.assertIn("容器列表", content)
        self.assertIn("<table>", content)
        self.assertIn("/sandboxes.js", content)
        self.assertNotIn("summary-grid", content)

    def test_container_and_new_pages_exist_with_expected_sections(self) -> None:
        container_path = Path("host/static/container.html")
        new_path = Path("host/static/new.html")
        agents_path = Path("host/static/agents.html")
        agent_path = Path("host/static/agent.html")
        architecture_path = Path("host/static/architecture.html")

        self.assertTrue(container_path.exists(), f"missing expected file: {container_path}")
        self.assertTrue(new_path.exists(), f"missing expected file: {new_path}")
        self.assertTrue(agents_path.exists(), f"missing expected file: {agents_path}")
        self.assertTrue(agent_path.exists(), f"missing expected file: {agent_path}")
        self.assertTrue(architecture_path.exists(), f"missing expected file: {architecture_path}")

        container_content = container_path.read_text(encoding="utf-8")
        new_content = new_path.read_text(encoding="utf-8")
        agents_content = agents_path.read_text(encoding="utf-8")
        agent_content = agent_path.read_text(encoding="utf-8")
        architecture_content = architecture_path.read_text(encoding="utf-8")

        self.assertIn("容器详情", container_content)
        self.assertIn("返回总览", container_content)
        self.assertIn("retryAgentBtn", container_content)
        self.assertIn("startContainerBtn", container_content)
        self.assertIn("stopContainerBtn", container_content)
        self.assertIn("restartContainerBtn", container_content)
        self.assertIn("运行默认设置", container_content)
        self.assertIn("containerSettingsForm", container_content)
        self.assertIn("settingsMaxRuntimeMinutes", container_content)
        self.assertIn("settingsMaxTotalTokens", container_content)
        self.assertIn("Round Timeline", container_content)
        self.assertIn("折叠的原始轨迹", container_content)
        self.assertIn("折叠的原始日志", container_content)
        self.assertIn("AI 账号", container_content)
        self.assertIn("identityGrid", container_content)
        self.assertIn("<details", container_content)
        self.assertIn("runStripState", container_content)
        self.assertIn("blogList", container_content)
        self.assertIn("traceList", container_content)
        self.assertNotIn("thinkingSummary", container_content)
        self.assertNotIn("最新输出", container_content)

        self.assertIn("新建任务", new_content)
        self.assertIn("来源模板", new_content)
        self.assertIn("运行方式", new_content)
        self.assertIn("创建并开始", new_content)
        self.assertIn("maxRoundsInput", new_content)
        self.assertIn("sleepSecondsInput", new_content)
        self.assertIn("maxRuntimeMinutesInput", new_content)
        self.assertIn("maxTotalTokensInput", new_content)
        self.assertIn("agentHandle", new_content)
        self.assertIn("模型配置", new_content)
        self.assertIn("profileId", new_content)
        self.assertIn("modelInput", new_content)
        self.assertIn("baseUrlInput", new_content)
        self.assertIn("apiKeyInput", new_content)
        self.assertIn("高级参数", new_content)
        self.assertIn("reasoningEffort", new_content)
        self.assertIn("temperatureInput", new_content)
        self.assertIn("topPInput", new_content)
        self.assertIn("requestTimeoutSecondsInput", new_content)
        self.assertIn("requestMaxAttemptsInput", new_content)
        self.assertIn("requestRetryDelaySecondsInput", new_content)
        self.assertIn("extraBodyInput", new_content)
        self.assertIn("testConfigBtn", new_content)
        self.assertIn("saveConfigBtn", new_content)
        self.assertIn("testConfigBtn", new_content)

        self.assertIn("AI 账号", agents_content)
        self.assertIn("accountsGrid", agents_content)
        self.assertIn("credentialPanel", agents_content)
        self.assertIn("/agents.js", agents_content)

        self.assertIn("账号主页", agent_content)
        self.assertIn("accountPosts", agent_content)
        self.assertIn("AI 接入 API", agent_content)
        self.assertIn("apiEndpoint", agent_content)
        self.assertIn("curlExample", agent_content)
        self.assertIn("/agent.js", agent_content)
        self.assertNotIn("postForm", agent_content)
        self.assertNotIn("postAuthToken", agent_content)
        self.assertNotIn("postInstanceId", agent_content)
        self.assertIn("bindAgentForm", container_content)
        self.assertIn("bindAgentHandle", container_content)
        self.assertIn("unbindAgentBtn", container_content)

        self.assertIn("Marathon 架构总览", architecture_content)
        self.assertIn("Marathon Core", architecture_content)
        self.assertIn("GitHub Pages", architecture_content)
        self.assertIn("/api/overview", architecture_content)
        self.assertIn("本地控制台", architecture_content)

    def test_app_shell_assets_include_theme_toggle_support(self) -> None:
        app_js = Path("host/static/app.js").read_text(encoding="utf-8")
        app_css = Path("host/static/app.css").read_text(encoding="utf-8")

        self.assertIn("THEME_PREFERENCE_KEY", app_js)
        self.assertIn("themeToggleBtn", app_js)
        self.assertIn("data-theme", app_css)
        self.assertIn(".theme-toggle", app_css)

    def test_app_shell_assets_include_theme_toggle_support(self) -> None:
        app_js = Path("host/static/app.js").read_text(encoding="utf-8")
        app_css = Path("host/static/app.css").read_text(encoding="utf-8")

        self.assertIn("THEME_PREFERENCE_KEY", app_js)
        self.assertIn("themeToggleBtn", app_js)
        self.assertIn("data-theme", app_css)
        self.assertIn(".theme-toggle", app_css)


if __name__ == "__main__":
    unittest.main()
