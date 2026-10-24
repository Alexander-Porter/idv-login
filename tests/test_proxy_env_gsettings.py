"""Native GNOME tests use only a private keyfile backend in a temporary directory."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
ROOT = "org.gnome.system.proxy"


def has_proxy_schema():
    if sys.platform != "linux" or not shutil.which("gsettings"):
        return False
    result = subprocess.run(["gsettings", "list-schemas"], capture_output=True, text=True, timeout=5)
    return result.returncode == 0 and ROOT in result.stdout.splitlines()


@unittest.skipUnless(has_proxy_schema(), "requires Linux gsettings and GNOME proxy schemas")
class NativeGSettingsTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        patcher = mock.patch.dict(os.environ, {
            "GSETTINGS_BACKEND": "keyfile", "XDG_CONFIG_HOME": str(self.directory), "SUDO_USER": "",
        })
        patcher.start()
        self.addCleanup(patcher.stop)
        self.module = self.load_module()

    def load_module(self):
        spec = importlib.util.spec_from_file_location("envmgr_native_test", SRC / "envmgr.py")
        environment = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(environment)
        environment._cachePath = str(self.directory / "config.json")
        environment.genv.set("FP_WORKDIR", str(self.directory))
        spec = importlib.util.spec_from_file_location("proxy_env_native_test", SRC / "proxy_env.py")
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {"envmgr": environment}):
            spec.loader.exec_module(module)
        module._logger = mock.Mock()
        return module

    def settings(self, *args):
        # This backend never reads or writes the desktop dconf database.
        self.assertEqual(os.environ["GSETTINGS_BACKEND"], "keyfile")
        result = subprocess.run(["gsettings", *args], capture_output=True, text=True, check=True, timeout=5)
        return result.stdout.strip()

    def prepare(self, mode):
        for protocol, host, port in (("http", "'old http'", "8080"), ("https", "'old-https'", "8443")):
            self.settings("set", ROOT + "." + protocol, "host", host)
            self.settings("set", ROOT + "." + protocol, "port", port)
        self.settings("set", ROOT, "mode", mode)
        self.settings("set", ROOT, "autoconfig-url", "'https://pac.example/'")
        self.settings("set", ROOT, "ignore-hosts", "['localhost', '*.example']")
        return self.snapshot()

    def snapshot(self):
        keys = [(ROOT, "mode"), (ROOT, "autoconfig-url"), (ROOT, "ignore-hosts")]
        keys += [(ROOT + "." + protocol, key) for protocol in ("http", "https") for key in ("host", "port")]
        return {(schema, key): self.settings("get", schema, key) for schema, key in keys}

    def test_native_round_trip_for_all_modes(self):
        for mode in ("'auto'", "'manual'", "'none'"):
            with self.subTest(mode=mode):
                original = self.prepare(mode)
                self.module._set_linux(10717)
                self.assertEqual(self.settings("get", ROOT, "mode"), "'manual'")
                self.module._unset_linux()
                self.assertEqual(self.snapshot(), original)
                self.assertEqual((self.directory / "config.json").stat().st_mode & 0o777, 0o600)

    def test_real_config_survives_module_restart(self):
        original = self.prepare("'auto'")
        self.module._set_linux(10717)
        config = json.loads((self.directory / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["_SAVED_LINUX_PROXY"]["mode"]["before"], "'auto'")
        self.module = self.load_module()
        self.module._set_linux(10718)
        self.module._unset_linux()
        self.assertEqual(self.snapshot(), original)

    def test_real_backend_rolls_back_partial_command_failure(self):
        original = self.prepare("'auto'")
        real_run = subprocess.run
        failed = False

        def run(command, **kwargs):
            nonlocal failed
            if not failed and command[1:4] == ["set", ROOT + ".https", "port"]:
                failed = True
                raise subprocess.CalledProcessError(1, command)
            return real_run(command, **kwargs)

        with mock.patch.object(self.module.subprocess, "run", side_effect=run):
            with self.assertRaises(OSError):
                self.module._set_linux(10717)
        self.assertTrue(failed)
        self.assertEqual(self.snapshot(), original)

    def competing_setup(self):
        script = """
import logging
import os
import proxy_env
from envmgr import genv
genv.set('FP_WORKDIR', os.getcwd())
proxy_env._logger = logging.getLogger('proxy-lock-test')
try:
    proxy_env._set_linux(10718)
except OSError:
    raise SystemExit(0)
raise SystemExit(1)
"""
        return subprocess.run(
            [sys.executable, "-B", "-c", script], cwd=self.directory,
            env=dict(os.environ, PYTHONPATH=str(SRC)), capture_output=True, text=True, timeout=10,
        )

    def test_another_process_cannot_change_settings_while_locked(self):
        original = self.prepare("'auto'")
        with self.module._proxy_state_lock():
            result = self.competing_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.snapshot(), original)
        self.assertFalse((self.directory / "config.json").exists())

    def test_reset_keeps_lock_through_configuration_deletion(self):
        original = self.prepare("'auto'")
        self.module._set_linux(10717)
        real_reset = self.module.genv.reset_cache

        def reset():
            # Compete precisely between completed restoration and deletion.
            result = self.competing_setup()
            self.assertEqual(result.returncode, 0, result.stderr)
            return real_reset()

        with mock.patch.object(self.module.genv, "reset_cache", side_effect=reset):
            self.module.reset_proxy_state()
        self.assertEqual(self.snapshot(), original)
        self.assertFalse((self.directory / "config.json").exists())

    def test_process_exit_during_setup_releases_lock_and_recovers(self):
        original = self.prepare("'auto'")
        script = """
import logging
import os
import proxy_env
from envmgr import genv
genv.set('FP_WORKDIR', os.getcwd())
proxy_env._logger = logging.getLogger('proxy-crash-test')
real_command = proxy_env._gsettings_cmd
def command(args, user=''):
    result = real_command(args, user)
    if args[0] == 'set':
        os._exit(0)
    return result
proxy_env._gsettings_cmd = command
proxy_env._set_linux(10717)
raise SystemExit(1)
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", script], cwd=self.directory,
            env=dict(os.environ, PYTHONPATH=str(SRC)), capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.snapshot(), original)
        self.module._unset_linux()
        self.assertEqual(self.snapshot(), original)

    def test_corrupt_config_does_not_change_system_settings(self):
        original = self.prepare("'auto'")
        (self.directory / "config.json").write_text("{invalid", encoding="utf-8")
        with self.assertRaises(OSError):
            self.module._set_linux(10717)
        self.assertEqual(self.snapshot(), original)


if __name__ == "__main__":
    unittest.main()
