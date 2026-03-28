import unittest
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from unittest import mock

import host.web_ui as web_ui

ROOT_DIR = Path(__file__).resolve().parent.parent
DESIGN_LAB_DIR = ROOT_DIR / "host" / "static" / "design-lab"


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


class DeriveSelfModificationSummaryTests(unittest.TestCase):
    def test_detects_prompt_source_change(self) -> None:
        summary = web_ui.derive_self_modification_summary(
            {"prompt_source": "before", "tool_source": "same", "loop_source": "same"},
            {"prompt_source": "after", "tool_source": "same", "loop_source": "same"},
        )

        self.assertEqual(
            summary,
            {
                "observed": True,
                "categories": ["prompt_source"],
                "latest_category": "prompt_source",
            },
        )

    def test_detects_tool_source_change(self) -> None:
        summary = web_ui.derive_self_modification_summary(
            {"prompt_source": "same", "tool_source": "before", "loop_source": "same"},
            {"prompt_source": "same", "tool_source": "after", "loop_source": "same"},
        )

        self.assertEqual(summary["categories"], ["tool_source"])
        self.assertEqual(summary["latest_category"], "tool_source")
        self.assertTrue(summary["observed"])

    def test_detects_loop_source_change(self) -> None:
        summary = web_ui.derive_self_modification_summary(
            {"prompt_source": "same", "tool_source": "same", "loop_source": "before"},
            {"prompt_source": "same", "tool_source": "same", "loop_source": "after"},
        )

        self.assertEqual(summary["categories"], ["loop_source"])
        self.assertEqual(summary["latest_category"], "loop_source")
        self.assertTrue(summary["observed"])

    def test_reports_not_observed_when_sources_unchanged_or_missing(self) -> None:
        same = web_ui.derive_self_modification_summary(
            {"prompt_source": "same", "tool_source": "same", "loop_source": "same"},
            {"prompt_source": "same", "tool_source": "same", "loop_source": "same"},
        )
        missing = web_ui.derive_self_modification_summary({}, {})

        self.assertEqual(
            same,
            {"observed": False, "categories": [], "latest_category": None},
        )
        self.assertEqual(
            missing,
            {"observed": False, "categories": [], "latest_category": None},
        )


class SummarizeRunSelfModificationTests(unittest.TestCase):
    def test_uses_round_artifacts_for_count_and_latest_round_metadata(self) -> None:
        with TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            round_one = run_dir / "rounds" / "0001"
            round_two = run_dir / "rounds" / "0002"
            round_one.mkdir(parents=True)
            round_two.mkdir(parents=True)
            web_ui.write_json(round_one / "state_before.json", {"prompt_source": "p1", "tool_source": "t", "loop_source": "l"})
            web_ui.write_json(round_one / "state_after.json", {"prompt_source": "p2", "tool_source": "t", "loop_source": "l"})
            web_ui.write_json(round_two / "state_before.json", {"prompt_source": "p2", "tool_source": "t1", "loop_source": "l"})
            web_ui.write_json(round_two / "state_after.json", {"prompt_source": "p2", "tool_source": "t2", "loop_source": "l"})

            summary = web_ui.summarize_run_self_modification(run_dir, None, None)

        self.assertEqual(summary["observed"], True)
        self.assertEqual(summary["categories"], ["prompt_source", "tool_source"])
        self.assertEqual(summary["latest_category"], "tool_source")
        self.assertEqual(summary["count"], 2)
        self.assertEqual(summary["latest_round"], 2)

    def test_falls_back_to_latest_state_pair_when_round_artifacts_are_absent(self) -> None:
        with TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            summary = web_ui.summarize_run_self_modification(
                run_dir,
                {"prompt_source": "before", "tool_source": "same", "loop_source": "same"},
                {"prompt_source": "after", "tool_source": "same", "loop_source": "same"},
            )

        self.assertEqual(summary["observed"], True)
        self.assertEqual(summary["categories"], ["prompt_source"])
        self.assertEqual(summary["latest_category"], "prompt_source")
        self.assertEqual(summary["count"], 1)
        self.assertIsNone(summary["latest_round"])

    def test_falls_back_when_rounds_dir_exists_without_usable_state_artifacts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            (run_dir / "rounds" / "0001").mkdir(parents=True)
            summary = web_ui.summarize_run_self_modification(
                run_dir,
                {"prompt_source": "before", "tool_source": "same", "loop_source": "same"},
                {"prompt_source": "after", "tool_source": "same", "loop_source": "same"},
            )

        self.assertEqual(summary["observed"], True)
        self.assertEqual(summary["categories"], ["prompt_source"])
        self.assertEqual(summary["latest_category"], "prompt_source")
        self.assertEqual(summary["count"], 1)
        self.assertIsNone(summary["latest_round"])

    def test_uses_latest_state_fallback_when_newest_round_artifacts_are_unusable(self) -> None:
        with TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            round_one = run_dir / "rounds" / "0001"
            round_two = run_dir / "rounds" / "0002"
            round_one.mkdir(parents=True)
            round_two.mkdir(parents=True)
            web_ui.write_json(
                round_one / "state_before.json",
                {"prompt_source": "p1", "tool_source": "t1", "loop_source": "l1"},
            )
            web_ui.write_json(
                round_one / "state_after.json",
                {"prompt_source": "p2", "tool_source": "t1", "loop_source": "l1"},
            )

            summary = web_ui.summarize_run_self_modification(
                run_dir,
                {"prompt_source": "p2", "tool_source": "t1", "loop_source": "l1"},
                {"prompt_source": "p2", "tool_source": "t1", "loop_source": "l2"},
            )

        self.assertEqual(summary["observed"], True)
        self.assertEqual(summary["categories"], ["prompt_source", "loop_source"])
        self.assertEqual(summary["latest_category"], "loop_source")
        self.assertEqual(summary["count"], 2)
        self.assertIsNone(summary["latest_round"])


class DeriveRunObservationTests(unittest.TestCase):
    def test_attaches_self_modification_payload_to_run_detail_observation(self) -> None:
        with TemporaryDirectory() as tmpdir:
            runs_dir = Path(tmpdir)
            run_dir = runs_dir / "run-test"
            run_dir.mkdir()
            (run_dir / "rounds" / "0002").mkdir(parents=True)
            web_ui.write_json(run_dir / "host_run.json", {"container": "sandbox-1"})
            web_ui.write_json(run_dir / "status.json", {"state": "completed", "completed_rounds": 2})
            web_ui.write_json(run_dir / "latest_state_before.json", {"prompt_source": "p1", "tool_source": "t1", "loop_source": "l1"})
            web_ui.write_json(run_dir / "latest_state_after.json", {"prompt_source": "p1", "tool_source": "t2", "loop_source": "l1"})
            web_ui.write_json(run_dir / "latest_round.json", {"round": 2, "summary": "updated tools"})
            web_ui.write_json(run_dir / "rounds" / "0002" / "state_before.json", {"prompt_source": "p1", "tool_source": "t1", "loop_source": "l1"})
            web_ui.write_json(run_dir / "rounds" / "0002" / "state_after.json", {"prompt_source": "p1", "tool_source": "t2", "loop_source": "l1"})

            with mock.patch.object(web_ui, "RUNS_DIR", runs_dir), mock.patch.object(
                web_ui, "read_container_runtime", return_value=None
            ):
                detail = web_ui.run_detail("run-test")

        self.assertIn("observation", detail)
        self.assertEqual(
            detail["observation"]["self_modification"],
            {
                "observed": True,
                "categories": ["tool_source"],
                "latest_category": "tool_source",
                "latest_round": 2,
                "count": 1,
            },
        )


class DesignLabStaticRouteTests(unittest.TestCase):
    def test_serves_sandboxes_html_from_root_static_dir(self) -> None:
        with TemporaryDirectory() as tmpdir:
            static_dir = Path(tmpdir)
            (static_dir / "sandboxes.html").write_text("<!doctype html><title>sandboxes</title>", encoding="utf-8")

            with mock.patch.object(web_ui, "STATIC_DIR", static_dir), serve_app() as (_, base_url):
                with urllib.request.urlopen(f"{base_url}/sandboxes") as response:
                    body = response.read().decode("utf-8")
                    content_type = response.headers.get_content_type()

        self.assertEqual(body, "<!doctype html><title>sandboxes</title>")
        self.assertEqual(content_type, "text/html")

    def test_serves_design_lab_index_html(self) -> None:
        with TemporaryDirectory() as tmpdir:
            static_dir = Path(tmpdir)
            design_lab_dir = static_dir / "design-lab"
            design_lab_dir.mkdir(parents=True)
            (design_lab_dir / "index.html").write_text("<!doctype html><title>design lab</title>", encoding="utf-8")

            with mock.patch.object(web_ui, "STATIC_DIR", static_dir), serve_app() as (_, base_url):
                with urllib.request.urlopen(f"{base_url}/design-lab/index.html") as response:
                    body = response.read().decode("utf-8")
                    content_type = response.headers.get_content_type()

        self.assertEqual(body, "<!doctype html><title>design lab</title>")
        self.assertEqual(content_type, "text/html")

    def test_serves_design_lab_shared_js(self) -> None:
        with TemporaryDirectory() as tmpdir:
            static_dir = Path(tmpdir)
            design_lab_dir = static_dir / "design-lab"
            design_lab_dir.mkdir(parents=True)
            (design_lab_dir / "shared.js").write_text("console.log('design lab');", encoding="utf-8")

            with mock.patch.object(web_ui, "STATIC_DIR", static_dir), serve_app() as (_, base_url):
                with urllib.request.urlopen(f"{base_url}/design-lab/shared.js") as response:
                    body = response.read().decode("utf-8")
                    content_type = response.headers.get_content_type()

        self.assertEqual(body, "console.log('design lab');")
        self.assertEqual(content_type, "text/javascript")

    def test_rejects_design_lab_path_traversal(self) -> None:
        with TemporaryDirectory() as tmpdir:
            static_dir = Path(tmpdir)
            design_lab_dir = static_dir / "design-lab"
            design_lab_dir.mkdir(parents=True)
            (static_dir / "README.md").write_text("sensitive", encoding="utf-8")

            with mock.patch.object(web_ui, "STATIC_DIR", static_dir), serve_app() as (_, base_url):
                with self.assertRaises(urllib.error.HTTPError) as exc_info:
                    urllib.request.urlopen(f"{base_url}/design-lab/../../README.md")

        self.assertEqual(exc_info.exception.code, 404)

    def test_rejects_design_lab_encoded_path_traversal(self) -> None:
        with TemporaryDirectory() as tmpdir:
            static_dir = Path(tmpdir)
            design_lab_dir = static_dir / "design-lab"
            design_lab_dir.mkdir(parents=True)
            (static_dir / "README.md").write_text("sensitive", encoding="utf-8")

            with mock.patch.object(web_ui, "STATIC_DIR", static_dir), serve_app() as (_, base_url):
                with self.assertRaises(urllib.error.HTTPError) as exc_info:
                    urllib.request.urlopen(f"{base_url}/design-lab/%2e%2e/%2e%2e/README.md")

        self.assertEqual(exc_info.exception.code, 404)


class DesignLabShellSmokeTests(unittest.TestCase):
    def test_index_html_exists_with_expected_title_copy(self) -> None:
        index_path = DESIGN_LAB_DIR / "index.html"

        self.assertTrue(index_path.exists(), f"missing expected file: {index_path}")
        content = index_path.read_text(encoding="utf-8")

        self.assertIn("Marathon 设计实验室", content)

    def test_index_uses_block_target_for_overview_summary(self) -> None:
        index_path = DESIGN_LAB_DIR / "index.html"

        self.assertTrue(index_path.exists(), f"missing expected file: {index_path}")
        self.assertIn('data-overview-summary', index_path.read_text(encoding="utf-8"))

    def test_shared_css_stays_neutral_without_page_wide_gradient_branding(self) -> None:
        shared_css_path = DESIGN_LAB_DIR / "shared.css"

        self.assertTrue(shared_css_path.exists(), f"missing expected file: {shared_css_path}")
        content = shared_css_path.read_text(encoding="utf-8")

        self.assertNotIn("radial-gradient(", content)
        self.assertNotIn("body {", content)
        self.assertNotIn(".page-shell", content)
        self.assertNotIn(".page-header", content)
        self.assertNotIn("box-shadow", content)

    def test_shared_js_uses_dom_nodes_for_state_rendering(self) -> None:
        shared_js_path = DESIGN_LAB_DIR / "shared.js"

        self.assertTrue(shared_js_path.exists(), f"missing expected file: {shared_js_path}")
        content = shared_js_path.read_text(encoding="utf-8")

        self.assertIn("document.createElement", content)
        self.assertNotIn("target.innerHTML", content)

    def test_shared_js_contains_query_parsing_and_variant_link_helpers(self) -> None:
        shared_js_path = DESIGN_LAB_DIR / "shared.js"

        self.assertTrue(shared_js_path.exists(), f"missing expected file: {shared_js_path}")
        content = shared_js_path.read_text(encoding="utf-8")

        self.assertIn("function getSelectedContext()", content)
        self.assertIn("function buildVariantHref(page, context)", content)
        self.assertIn("searchParams.get(\"run_id\")", content)
        self.assertIn("searchParams.get(\"container\")", content)
        self.assertIn("URLSearchParams()", content)
        self.assertIn("params.set(\"run_id\", context.runId)", content)
        self.assertIn("params.set(\"container\", context.container)", content)

    def test_shared_js_declares_required_fetch_and_state_helpers(self) -> None:
        shared_js_path = DESIGN_LAB_DIR / "shared.js"

        self.assertTrue(shared_js_path.exists(), f"missing expected file: {shared_js_path}")
        content = shared_js_path.read_text(encoding="utf-8")

        self.assertIn("async function fetchOverview()", content)
        self.assertIn("async function fetchRunDetail(runId)", content)
        self.assertIn("async function fetchContainerDetail(container)", content)
        self.assertIn("function renderEmptyState(", content)
        self.assertIn("function renderErrorState(", content)


class DesignVariantMarkupTests(unittest.TestCase):
    def test_observation_deck_sections(self) -> None:
        page_path = DESIGN_LAB_DIR / "design-consultation.html"

        self.assertTrue(page_path.exists(), f"missing expected file: {page_path}")
        content = page_path.read_text(encoding="utf-8")

        self.assertIn("观察台", content)
        self.assertIn("时间线", content)
        self.assertIn("输出", content)
        self.assertIn('id="deck-current"', content)
        self.assertIn('id="deck-timeline"', content)
        self.assertIn('id="deck-output"', content)
        self.assertNotIn('id="deck-current-round"', content)
        self.assertNotIn('id="deck-self-modification"', content)
        self.assertNotIn('id="deck-command-output"', content)

    def test_control_cockpit_sections(self) -> None:
        page_path = DESIGN_LAB_DIR / "ui-ux-pro-max.html"

        self.assertTrue(page_path.exists(), f"missing expected file: {page_path}")
        content = page_path.read_text(encoding="utf-8")

        self.assertIn("控制台", content)
        self.assertIn("动态", content)
        self.assertIn("状态", content)
        self.assertIn('id="cockpit-status"', content)
        self.assertIn('id="cockpit-feed"', content)
        self.assertIn('id="cockpit-output"', content)
        self.assertNotIn('id="cockpit-status-band"', content)
        self.assertNotIn('id="cockpit-kpis"', content)
        self.assertNotIn('id="cockpit-live-feed"', content)
        self.assertNotIn('id="cockpit-self-modification"', content)

    def test_flow_desk_sections(self) -> None:
        page_path = DESIGN_LAB_DIR / "penpot-uiux-design.html"

        self.assertTrue(page_path.exists(), f"missing expected file: {page_path}")
        content = page_path.read_text(encoding="utf-8")

        self.assertIn("流程台", content)
        self.assertIn("上下文", content)
        self.assertIn("细节", content)
        self.assertIn('id="flow-context"', content)
        self.assertIn('id="flow-timeline"', content)
        self.assertIn('id="flow-detail"', content)
        self.assertNotIn('id="flow-lifecycle"', content)
        self.assertNotIn('id="flow-detail-inspector"', content)
        self.assertNotIn('id="flow-self-modification"', content)


class DesignLabStateCopyTests(unittest.TestCase):
    def test_shared_js_declares_required_empty_and_error_messages(self) -> None:
        shared_js_path = DESIGN_LAB_DIR / "shared.js"

        self.assertTrue(shared_js_path.exists(), f"missing expected file: {shared_js_path}")
        content = shared_js_path.read_text(encoding="utf-8")

        self.assertIn("还没有选中实验", content)
        self.assertIn("未观察到自我修改", content)
        self.assertIn("读取模型信息失败", content)
        self.assertIn("操作失败", content)


class DesignLabEntryPointTests(unittest.TestCase):
    def test_main_ui_contains_design_lab_entry_link(self) -> None:
        main_ui_path = ROOT_DIR / "host" / "static" / "index.html"

        self.assertTrue(main_ui_path.exists(), f"missing expected file: {main_ui_path}")
        content = main_ui_path.read_text(encoding="utf-8")

        self.assertIn("/design-lab/index.html", content)


if __name__ == "__main__":
    unittest.main()
