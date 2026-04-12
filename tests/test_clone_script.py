from pathlib import Path
import unittest


class CloneScriptPrivilegeTests(unittest.TestCase):
    def test_rewrite_network_config_runs_with_sudo(self) -> None:
        script = Path("scripts/clone_container.sh").read_text(encoding="utf-8")
        self.assertIn('sudo -n python3 "${ROOT_DIR}/host/lxc_network.py" rewrite-config', script)

    def test_clone_script_uses_helper_for_unique_ip_and_guest_netplan(self) -> None:
        script = Path("scripts/clone_container.sh").read_text(encoding="utf-8")
        self.assertIn('suggest-static-ip', script)
        self.assertIn('render-netplan', script)
        self.assertIn('/etc/netplan/10-lxc.yaml', script)

    def test_clone_script_preserves_agent_settings_metadata(self) -> None:
        script = Path("scripts/clone_container.sh").read_text(encoding="utf-8")
        self.assertIn("agent_settings", script)
        self.assertIn("agent_settings_updated_at", script)


class StartRunCleanupTests(unittest.TestCase):
    def test_start_run_cleanup_removes_container_state_meta(self) -> None:
        script = Path("scripts/start_run.sh").read_text(encoding="utf-8")
        self.assertIn('rm -f "${ROOT_DIR}/state/containers/${RUN_NAME}.json"', script)

    def test_start_run_script_loads_local_model_env_defaults(self) -> None:
        script = Path("scripts/start_run.sh").read_text(encoding="utf-8")
        self.assertIn('source "${ROOT_DIR}/scripts/load_model_env.sh"', script)

    def test_start_run_script_exports_project_root_on_pythonpath(self) -> None:
        script = Path("scripts/start_run.sh").read_text(encoding="utf-8")
        self.assertIn('export PYTHONPATH="${ROOT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"', script)

    def test_start_run_script_requires_explicit_model_provider_settings(self) -> None:
        script = Path("scripts/start_run.sh").read_text(encoding="utf-8")
        self.assertIn('missing MARATHON_BASE_URL', script)
        self.assertIn('missing MARATHON_API_KEY', script)


if __name__ == "__main__":
    unittest.main()
