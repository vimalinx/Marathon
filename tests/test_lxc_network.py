import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import host.lxc_network as lxc_network


class ChoosePreferredBridgeTests(unittest.TestCase):
    def test_prefers_stable_virtual_bridge_over_docker_style_bridges(self) -> None:
        self.assertEqual(
            lxc_network.choose_preferred_bridge(["lo", "docker0", "br-deadbeef", "virbr0"]),
            "virbr0",
        )


class ResolveContainerNetworkTests(unittest.TestCase):
    def test_falls_back_to_empty_when_static_bridge_is_missing(self) -> None:
        resolved = lxc_network.resolve_container_network(
            {
                "network_mode": "bridge-static",
                "bridge_name": "br-ef44f54afd12",
                "bridge_cidr": "172.21.0.1/16",
                "ipv4_address": "172.21.0.228/16",
                "ipv4_gateway": "172.21.0.1",
            },
            available_links=["lo", "wlan0"],
            allow_empty_fallback=True,
            veth_support={"available": True, "reason": ""},
        )
        self.assertEqual(resolved["network_mode"], "empty")
        self.assertEqual(resolved["bridge_name"], "")
        self.assertIn("missing bridge", resolved["warning"])

    def test_reports_kernel_module_mismatch_before_using_veth(self) -> None:
        with TemporaryDirectory() as tmpdir:
            modules_root = Path(tmpdir) / "lib_modules"
            modules_root.mkdir()
            (modules_root / "6.19.8-arch1-1").mkdir()
            diagnostics = lxc_network.detect_veth_support(
                kernel_release="6.19.6-arch1-1",
                modules_root=modules_root,
                sys_module_root=Path(tmpdir) / "sys_module",
            )
        self.assertFalse(diagnostics["available"])
        self.assertIn("kernel/modules mismatch", diagnostics["reason"])

    def test_falls_back_to_empty_when_host_lacks_veth_support(self) -> None:
        resolved = lxc_network.resolve_container_network(
            {
                "network_mode": "bridge-static",
                "bridge_name": "virbr0",
                "bridge_cidr": "192.168.122.1/24",
                "ipv4_address": "192.168.122.20/24",
                "ipv4_gateway": "192.168.122.1",
            },
            available_links=["lo", "virbr0"],
            allow_empty_fallback=True,
            veth_support={"available": False, "reason": "kernel/modules mismatch: running 6.19.6-arch1-1 but only /lib/modules/6.19.8-arch1-1 exists"},
        )
        self.assertEqual(resolved["network_mode"], "empty")
        self.assertIn("kernel/modules mismatch", resolved["warning"])


class StaticIpv4SelectionTests(unittest.TestCase):
    def test_suggest_static_ipv4_skips_used_addresses_from_state(self) -> None:
        with TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir)
            container_root = Path(tmpdir) / "lxc"
            container_root.mkdir()
            for name, ipv4 in (
                ("marathon-base", "192.168.122.234/24"),
                ("other-used", "192.168.122.235/24"),
            ):
                (state_dir / f"{name}.json").write_text(
                    json.dumps(
                        {
                            "container_name": name,
                            "network_mode": "bridge-static",
                            "bridge_name": "virbr0",
                            "bridge_cidr": "192.168.122.1/24",
                            "ipv4_address": ipv4,
                            "ipv4_gateway": "192.168.122.1",
                        }
                    ),
                    encoding="utf-8",
                )
                (container_root / name).mkdir()

            resolved = lxc_network.suggest_static_ipv4(
                "marathon-config-probe",
                "192.168.122.1/24",
                state_dir=state_dir,
                container_root=container_root,
            )

        self.assertEqual(resolved["ipv4_address"], "192.168.122.236/24")
        self.assertEqual(resolved["ipv4_gateway"], "192.168.122.1")

    def test_suggest_static_ipv4_ignores_stale_state_for_missing_container(self) -> None:
        with TemporaryDirectory() as tmpdir:
            state_dir = Path(tmpdir) / "state"
            state_dir.mkdir()
            container_root = Path(tmpdir) / "lxc"
            container_root.mkdir()
            (state_dir / "ghost.json").write_text(
                json.dumps(
                    {
                        "container_name": "ghost",
                        "network_mode": "bridge-static",
                        "bridge_name": "virbr0",
                        "bridge_cidr": "192.168.122.1/24",
                        "ipv4_address": "192.168.122.236/24",
                        "ipv4_gateway": "192.168.122.1",
                    }
                ),
                encoding="utf-8",
            )

            resolved = lxc_network.suggest_static_ipv4(
                "probe-7",
                "192.168.122.1/24",
                state_dir=state_dir,
                container_root=container_root,
            )

        self.assertEqual(resolved["ipv4_address"], "192.168.122.236/24")


class GuestNetplanRenderingTests(unittest.TestCase):
    def test_render_guest_netplan_disables_dhcp_for_bridge_static(self) -> None:
        rendered = lxc_network.render_guest_netplan("bridge-static")
        self.assertIn("eth0:", rendered)
        self.assertIn("dhcp4: false", rendered)
        self.assertNotIn("dhcp4: true", rendered)

    def test_render_guest_netplan_keeps_dhcp_for_bridge_dhcp(self) -> None:
        rendered = lxc_network.render_guest_netplan("bridge-dhcp")
        self.assertIn("dhcp4: true", rendered)
        self.assertIn("dhcp-identifier: mac", rendered)


if __name__ == "__main__":
    unittest.main()
