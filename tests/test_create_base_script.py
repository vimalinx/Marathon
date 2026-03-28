from pathlib import Path
import unittest


class CreateBaseScriptNetworkTests(unittest.TestCase):
    def test_create_base_script_uses_helper_for_unique_ip_and_guest_netplan(self) -> None:
        script = Path("scripts/create_base_container.sh").read_text(encoding="utf-8")
        self.assertIn('suggest-static-ip', script)
        self.assertIn('render-netplan', script)
        self.assertIn('/etc/netplan/10-lxc.yaml', script)


if __name__ == "__main__":
    unittest.main()
