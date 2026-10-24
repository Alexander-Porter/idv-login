"""Opt-in native tests for disposable GitHub macOS runners only.

Run with IDV_TEST_MACOS_PROXY=1. Each test creates and immediately disables a
dedicated network service, limits the production helper to that service, and
deletes it on cleanup. Existing services and the user's config are untouched.
"""
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@unittest.skipUnless(
    sys.platform == "darwin" and os.environ.get("GITHUB_ACTIONS") == "true"
    and os.environ.get("IDV_TEST_MACOS_PROXY") == "1",
    "requires explicit opt-in on a disposable GitHub macOS runner",
)
class NativeMacProxyTests(unittest.TestCase):
    def setUp(self):
        self._real_run = subprocess.run
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.module = self.load_module()
        patcher = mock.patch.object(self.module.subprocess, "run", side_effect=self.run_networksetup)
        patcher.start()
        self.addCleanup(patcher.stop)
        hardware = self.module._networksetup(["-listallhardwareports"])
        device = re.search(r"^Device: (\S+)$", hardware, re.M)
        self.assertIsNotNone(device, "runner needs a network interface for the test service")
        self.service = "idv-proxy-test-" + uuid.uuid4().hex
        self.module._networksetup(["-createnetworkservice", self.service, device.group(1)])
        self.addCleanup(self.module._networksetup, ["-removenetworkservice", self.service])
        self.module._networksetup(["-setnetworkserviceenabled", self.service, "off"])
        self.module._get_network_services = lambda: [self.service]

    def run_networksetup(self, command, **kwargs):
        # Exercise the production command construction, timeout, locale and return-code checks.
        self.assertEqual(command[0], "networksetup")
        if command[1] != "-listallhardwareports":
            self.assertEqual(command[2], self.service)
        return self._real_run(["sudo", "-n", "/usr/sbin/networksetup", *command[1:]], **kwargs)

    def load_module(self):
        spec = importlib.util.spec_from_file_location("envmgr_native_mac_test", SRC / "envmgr.py")
        environment = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(environment)
        environment._cachePath = str(self.directory / "config.json")
        environment.genv.set("FP_WORKDIR", str(self.directory))
        spec = importlib.util.spec_from_file_location("proxy_env_native_mac_test", SRC / "proxy_env.py")
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {"envmgr": environment}):
            spec.loader.exec_module(module)
        module._logger = mock.Mock()
        return module

    def snapshot(self):
        return {protocol: self.module._read_darwin_proxy(self.service, protocol)
                for protocol in ("web", "secureweb")}

    def assert_round_trip(self):
        before = self.snapshot()
        self.module._set_darwin(10717)
        self.module._unset_darwin()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.module.genv.get_from_file("_SAVED_DARWIN_PROXY_SVCS", None), {})

    def test_default_empty_server_and_zero_port_round_trip(self):
        for state in self.snapshot().values():
            self.assertEqual(state, dict(enabled=False, server="", port=0, authenticated=False))
        self.assert_round_trip()

    def test_endpoint_edge_cases_preserve_enabled_and_disabled_states(self):
        for enabled in (False, True):
            for server, port in (("", 0), ("", 8080), ("127.0.0.2", 0), ("127.0.0.2", 8080)):
                with self.subTest(enabled=enabled, server=server, port=port):
                    for protocol in ("web", "secureweb"):
                        self.module._networksetup([f"-set{protocol}proxy", self.service, server, str(port), "off"])
                        self.module._networksetup([f"-set{protocol}proxystate", self.service,
                                                   "on" if enabled else "off"])
                    for state in self.snapshot().values():
                        self.assertEqual(state, dict(enabled=enabled, server=server, port=port, authenticated=False))
                    self.assert_round_trip()

    def recover_after_command_failure(self, verb):
        before = self.snapshot()
        self.module._set_darwin(10717)
        failed = False

        def fail_once(command, **kwargs):
            nonlocal failed
            if not failed and command[1] == verb:
                failed = True
                raise subprocess.CalledProcessError(1, command)
            return self.run_networksetup(command, **kwargs)

        with mock.patch.object(self.module.subprocess, "run", side_effect=fail_once):
            with self.assertRaises(OSError):
                self.module._unset_darwin()
        self.assertTrue(failed)
        current = self.snapshot()["web"]
        if verb == "-setwebproxy":
            self.assertEqual(current, dict(enabled=False, server="127.0.0.1", port=10717, authenticated=False))
        else:
            self.assertEqual(current, dict(enabled=True, server="", port=0, authenticated=False))
        self.assertTrue(self.module.genv.get_from_file("_SAVED_DARWIN_PROXY_SVCS", None))
        self.module = self.load_module()
        self.module._unset_darwin()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.module.genv.get_from_file("_SAVED_DARWIN_PROXY_SVCS", None), {})

    def test_empty_endpoint_setter_failure_keeps_backup_for_retry(self):
        self.recover_after_command_failure("-setwebproxy")

    def test_empty_endpoint_disable_failure_recovers_after_reload(self):
        self.recover_after_command_failure("-setwebproxystate")
