from pathlib import Path
import unittest


class SetupLxcPasswordlessSudoScriptTests(unittest.TestCase):
    def test_script_exists_and_validates_generated_sudoers_file(self) -> None:
        script_path = Path("scripts/setup_lxc_passwordless_sudo.sh")
        self.assertTrue(script_path.exists(), "expected helper script to exist")
        script = script_path.read_text(encoding="utf-8")
        self.assertIn('USER_NAME="${1:-$(id -un)}"', script)
        self.assertIn('PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"', script)
        self.assertIn('/etc/sudoers.d/marathon-lxc', script)
        self.assertIn('sudo visudo -cf "${SUDOERS_FILE}"', script)

    def test_script_requests_sudo_up_front_with_clear_message(self) -> None:
        script = Path("scripts/setup_lxc_passwordless_sudo.sh").read_text(encoding="utf-8")
        self.assertIn('echo "requesting sudo to install ${SUDOERS_FILE}" >&2', script)
        self.assertIn('sudo -v', script)


if __name__ == "__main__":
    unittest.main()
