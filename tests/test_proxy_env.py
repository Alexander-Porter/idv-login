import copy
import contextlib
import importlib.util
import json
import os
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock


SRC = Path(__file__).resolve().parents[1] / "src"


class SavedState:
    def __init__(self, disk=None):
        self.disk = copy.deepcopy(disk or {})
        self.values = copy.deepcopy(self.disk)
        self.fail_save = False

    def get(self, key, default=None):
        return copy.deepcopy(self.values.get(key, default))

    def get_from_file(self, key, default=None, *, require_read=False):
        return copy.deepcopy(self.disk.get(key, default))

    def set(self, key, value, cached=False, *, require_saved=False):
        if cached:
            if self.fail_save:
                raise OSError("simulated persistence failure")
            self.disk[key] = json.loads(json.dumps(value))
        self.values[key] = copy.deepcopy(value)


def load_proxy(state):
    spec = importlib.util.spec_from_file_location("proxy_env_test", SRC / "proxy_env.py")
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {"envmgr": types.SimpleNamespace(genv=state)}):
        spec.loader.exec_module(module)
    module._logger = mock.Mock()
    # File locking is exercised by native Linux integration tests.
    module._proxy_state_lock = contextlib.nullcontext
    return module


def load_reset_handler(state):
    spec = importlib.util.spec_from_file_location("local_handler_proxy_test", SRC / "local_handler.py")
    module = importlib.util.module_from_spec(spec)
    stubs = {name: types.ModuleType(name) for name in ("app_state", "const")}
    stubs.update({
        "envmgr": types.SimpleNamespace(genv=state),
        "login_stack_mgr": types.SimpleNamespace(LoginStackManager=object),
        "cloudSync": types.SimpleNamespace(CloudSyncManager=object),
        "cloudRes": types.SimpleNamespace(CloudRes=object),
        "channelHandler.channelUtils": types.SimpleNamespace(cmp_game_id=lambda *args: False,
                                                            getShortGameId=lambda value: value),
    })
    with mock.patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    handler = module.LocalRequestHandler.__new__(module.LocalRequestHandler)
    handler.logger = mock.Mock()
    handler._json_response = lambda status, payload: (status, payload)
    return module, handler


def proxy(enabled=False, server="", port=0, authenticated=False):
    return dict(enabled=enabled, server=server, port=port, authenticated=authenticated)


class MacCommands:
    def __init__(self, state):
        self.services = {
            "Wi-Fi": {"http": proxy(True, "old-http.example", 8080),
                      "https": proxy(False, "old-https.example", 8443)},
            "USB Ethernet": {"http": proxy(), "https": proxy()},
        }
        self.state = state
        self.writes = []
        self.fail = None
        self.after_failure = False
        self.bad_read = False
        self.interrupt = None

    def run(self, command, **kwargs):
        if command[0] != "networksetup":
            raise AssertionError("unexpected external command")
        verb = command[1]
        if verb == "-listnetworkserviceorder":
            text = "\n".join(f"({i}) {name}\n(Hardware Port: Ethernet, Device: en{i})"
                             for i, name in enumerate(self.services, 1))
            return subprocess.CompletedProcess(command, 0, stdout=text)
        service = command[2]
        protocol = "https" if "secureweb" in verb else "http"
        current = self.services[service][protocol]
        if verb.startswith("-get"):
            if self.bad_read:
                return subprocess.CompletedProcess(command, 0, stdout="unrecognized output")
            text = (f"Enabled: {'Yes' if current['enabled'] else 'No'}\n"
                    f"Server: {current['server']}\nPort: {current['port']}\n"
                    f"Authenticated Proxy Enabled: {int(current['authenticated'])}\n")
            return subprocess.CompletedProcess(command, 0, stdout=text)
        self.writes.append(command)
        fail = self.fail == (verb, service)
        if fail:
            self.fail = None
        if not fail or self.after_failure:
            if verb.endswith("state"):
                current["enabled"] = command[3] == "on"
            else:
                current.update(server=command[3], port=int(command[4]), enabled=True,
                               authenticated=len(command) > 5 and command[5] == "on")
        if fail:
            if self.after_failure:
                raise subprocess.TimeoutExpired(command, 5)
            if kwargs.get("check"):
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 1, stdout="")
        if self.interrupt == (verb, service):
            self.interrupt = None
            raise KeyboardInterrupt()
        return subprocess.CompletedProcess(command, 0, stdout="")


class MacProxyTests(unittest.TestCase):
    def setUp(self):
        self.state = SavedState()
        self.module = load_proxy(self.state)
        self.commands = MacCommands(self.state)
        self.original = copy.deepcopy(self.commands.services)
        self.patch = mock.patch.object(self.module.subprocess, "run", side_effect=self.commands.run)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_round_trip_restores_each_service_and_disabled_values(self):
        self.module._set_darwin(10717)
        self.assertTrue(self.state.disk)
        self.module._unset_darwin()
        self.assertEqual(self.commands.services, self.original)
        self.module._unset_darwin()
        self.assertEqual(self.commands.services, self.original)

    def test_restart_recovers_persisted_snapshot(self):
        self.module._set_darwin(10717)
        self.module = load_proxy(SavedState(self.state.disk))
        self.module._unset_darwin()
        self.assertEqual(self.commands.services, self.original)

    def test_repeated_setup_preserves_original_snapshot(self):
        self.module._set_darwin(10717)
        self.module._set_darwin(10718)
        self.module._unset_darwin()
        self.assertEqual(self.commands.services, self.original)

    def test_failed_or_unreadable_snapshot_does_not_change_settings(self):
        for failure in ("save", "read"):
            with self.subTest(failure=failure):
                self.state.fail_save = failure == "save"
                self.commands.bad_read = failure == "read"
                with self.assertRaises(OSError):
                    self.module._set_darwin(10717)
                self.assertEqual(self.commands.writes, [])
                self.assertEqual(self.commands.services, self.original)

    def test_authenticated_service_is_left_untouched(self):
        self.commands.services["Wi-Fi"]["http"]["authenticated"] = True
        original = copy.deepcopy(self.commands.services["Wi-Fi"])
        self.module._set_darwin(10717)
        self.module._unset_darwin()
        self.assertEqual(self.commands.services["Wi-Fi"], original)
        self.assertFalse(any(command[2] == "Wi-Fi" for command in self.commands.writes))

    def test_partial_setup_failure_rolls_back_even_after_timeout(self):
        for after in (False, True):
            with self.subTest(timeout_after_change=after):
                self.commands.fail = ("-setsecurewebproxy", "Wi-Fi")
                self.commands.after_failure = after
                with self.assertRaises(OSError):
                    self.module._set_darwin(10717)
                self.assertEqual(self.commands.services, self.original)

    def test_failed_restore_keeps_backup_for_retry(self):
        self.module._set_darwin(10717)
        self.commands.fail = ("-setwebproxy", "Wi-Fi")
        with self.assertRaises(OSError):
            self.module._unset_darwin()
        self.assertTrue(any(self.state.disk.values()))
        self.module = load_proxy(SavedState(self.state.disk))
        self.module._unset_darwin()
        self.assertEqual(self.commands.services, self.original)

    def test_external_proxy_change_is_preserved(self):
        self.module._set_darwin(10717)
        external = proxy(True, "new-user-proxy.example", 9000)
        self.commands.services["Wi-Fi"]["http"] = copy.deepcopy(external)
        self.module._unset_darwin()
        self.assertEqual(self.commands.services["Wi-Fi"]["http"], external)
        self.assertEqual(self.commands.services["Wi-Fi"]["https"], self.original["Wi-Fi"]["https"])

    def test_restart_during_restore_resumes_disabled_original_state(self):
        self.module._set_darwin(10717)
        # Fail between restoring an endpoint and its original disabled flag.
        self.commands.fail = ("-setsecurewebproxystate", "Wi-Fi")
        with self.assertRaises(OSError):
            self.module._unset_darwin()
        self.assertTrue(self.commands.services["Wi-Fi"]["https"]["enabled"])
        self.module = load_proxy(SavedState(self.state.disk))
        self.module._unset_darwin()
        self.assertEqual(self.commands.services, self.original)

    def test_clear_backup_failure_is_safe_to_retry(self):
        self.module._set_darwin(10717)
        original_set = self.state.set

        def fail_clear(key, value, *args, **kwargs):
            if not value:
                raise OSError("clear failed")
            return original_set(key, value, *args, **kwargs)

        with mock.patch.object(self.state, "set", side_effect=fail_clear):
            with self.assertRaises(OSError):
                self.module._unset_darwin()
        self.assertEqual(self.commands.services, self.original)
        self.module._unset_darwin()
        self.assertEqual(self.commands.services, self.original)

    def test_unreadable_restore_retains_backup(self):
        self.module._set_darwin(10717)
        disk = copy.deepcopy(self.state.disk)
        self.commands.bad_read = True
        with self.assertRaises(OSError):
            self.module._unset_darwin()
        self.assertEqual(self.state.disk, disk)
        self.commands.bad_read = False
        self.module._unset_darwin()
        self.assertEqual(self.commands.services, self.original)

    def test_reset_endpoint_restores_before_deleting_configuration(self):
        self.module._set_darwin(10717)
        module, handler = load_reset_handler(self.state)
        locked = []

        @contextlib.contextmanager
        def lock():
            locked.append(True)
            try:
                yield
            finally:
                locked.pop()

        def reset():
            self.assertTrue(locked, "reset must not delete another process's new snapshot")
            self.assertEqual(self.commands.services, self.original)
            self.state.disk.clear()
            self.state.values.clear()
            self.state.fail_save = True
            return "config.json"

        self.state.reset_cache = mock.Mock(side_effect=reset)
        with mock.patch.dict(sys.modules, {"proxy_env": self.module}), \
                mock.patch.object(sys, "platform", "darwin"), \
                mock.patch.object(self.module, "_proxy_state_lock", lock), \
                mock.patch.object(module.threading, "Thread"):
            status, _ = handler._diagnostics_reset_state({}, {}, "POST")
        self.assertEqual(status, 202)
        self.assertEqual(self.state.disk, {})
        self.module._unset_darwin()

    def test_reset_endpoint_keeps_config_when_restore_fails(self):
        self.module._set_darwin(10717)
        module, handler = load_reset_handler(self.state)
        self.state.reset_cache = mock.Mock(return_value="config.json")
        self.commands.bad_read = True
        with mock.patch.dict(sys.modules, {"proxy_env": self.module}), \
                mock.patch.object(sys, "platform", "darwin"), \
                mock.patch.object(module.threading, "Thread"):
            status, _ = handler._diagnostics_reset_state({}, {}, "POST")
        self.assertEqual(status, 500)
        self.state.reset_cache.assert_not_called()
        self.assertFalse(module.LocalRequestHandler._reset_started)
        self.assertTrue(any(self.state.disk.values()))

    def test_live_owner_prevents_another_instance_restoring(self):
        self.module._set_darwin(10717)
        saved = self.state.disk["_SAVED_DARWIN_PROXY_SVCS"]
        saved["owner_pid"] = os.getpid() + 1
        count = len(self.commands.writes)
        with mock.patch.object(self.module.os, "kill", return_value=None):
            with self.assertRaises(OSError):
                self.module._unset_darwin()
        self.assertEqual(len(self.commands.writes), count)

    def test_dead_owner_is_recovered_after_restart(self):
        self.module._set_darwin(10717)
        self.state.disk["_SAVED_DARWIN_PROXY_SVCS"]["owner_pid"] = os.getpid() + 1
        self.module = load_proxy(SavedState(self.state.disk))
        with mock.patch.object(self.module.os, "kill", side_effect=ProcessLookupError()):
            self.module._unset_darwin()
        self.assertEqual(self.commands.services, self.original)


ROOT = "org.gnome.system.proxy"


class LinuxCommands:
    def __init__(self):
        self.values = {(ROOT, "mode"): "'auto'", (ROOT + ".http", "host"): "'old http'",
                       (ROOT + ".http", "port"): "8080", (ROOT + ".https", "host"): "'old-https'",
                       (ROOT + ".https", "port"): "8443", (ROOT, "autoconfig-url"): "'https://pac.example/'",
                       (ROOT, "ignore-hosts"): "['localhost']"}
        self.writes = []
        self.users = []
        self.fail = None
        self.bad_read = False
        self.missing = False
        self.ignore_write = None
        self.interrupt = None

    def run(self, command, **kwargs):
        if command[0] == "sudo":
            self.users.append(command[2])
            command = command[3:]
        if command[0] != "gsettings":
            raise AssertionError("unexpected external command")
        if self.missing:
            raise FileNotFoundError("gsettings unavailable")
        if command[1] == "--version":
            return subprocess.CompletedProcess(command, 0, stdout="2.80")
        verb, schema, key = command[1:4]
        if verb == "get":
            if self.bad_read:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0, stdout=self.values[(schema, key)] + "\n")
        self.writes.append(command)
        if self.fail == (schema, key):
            self.fail = None
            if kwargs.get("check"):
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 1)
        value = command[4]
        if key in ("host", "mode") and not value.startswith(("'", '"')):
            value = repr(value)
        if self.ignore_write != (schema, key):
            self.values[(schema, key)] = value
        if self.interrupt == (schema, key):
            self.interrupt = None
            raise KeyboardInterrupt()
        return subprocess.CompletedProcess(command, 0, stdout="")


class LinuxProxyTests(unittest.TestCase):
    def setUp(self):
        self.state = SavedState()
        self.module = load_proxy(self.state)
        self.commands = LinuxCommands()
        self.original = copy.deepcopy(self.commands.values)
        patcher = mock.patch.object(self.module.subprocess, "run", side_effect=self.commands.run)
        patcher.start()
        self.addCleanup(patcher.stop)
        user = mock.patch.object(self.module, "_get_real_user", return_value="desktop-user")
        user.start()
        self.addCleanup(user.stop)

    def test_round_trip_restores_mode_hosts_ports_and_leaves_pac_bypass(self):
        for mode in ("'auto'", "'manual'", "'none'"):
            with self.subTest(mode=mode):
                self.commands.values[(ROOT, "mode")] = mode
                original = copy.deepcopy(self.commands.values)
                self.module._set_linux(10717)
                self.assertTrue(self.state.disk)
                self.module._unset_linux()
                self.assertEqual(self.commands.values, original)
                self.assertTrue(self.commands.users)
                self.assertEqual(set(self.commands.users), {"desktop-user"})

    def test_restart_and_repeated_setup_recover_original(self):
        self.module._set_linux(10717)
        self.module = load_proxy(SavedState(self.state.disk))
        self.module._set_linux(10718)
        self.module._unset_linux()
        self.assertEqual(self.commands.values, self.original)

    def test_missing_gsettings_does_not_change_settings(self):
        self.commands.missing = True
        self.module._set_linux(10717)
        self.assertEqual(self.commands.writes, [])

    def test_snapshot_failure_does_not_change_settings(self):
        for failure in ("read", "save"):
            with self.subTest(failure=failure):
                self.commands.bad_read = failure == "read"
                self.state.fail_save = failure == "save"
                with self.assertRaises(OSError):
                    self.module._set_linux(10717)
                self.assertEqual(self.commands.writes, [])

    def test_partial_setup_failure_rolls_back(self):
        self.commands.fail = (ROOT + ".https", "port")
        with self.assertRaises(OSError):
            self.module._set_linux(10717)
        self.assertEqual(self.commands.values, self.original)

    def test_failed_restore_keeps_original_snapshot_for_retry(self):
        self.module._set_linux(10717)
        self.commands.fail = (ROOT + ".http", "host")
        with self.assertRaises(OSError):
            self.module._unset_linux()
        self.assertTrue(any(self.state.disk.values()))
        self.module._unset_linux()
        self.assertEqual(self.commands.values, self.original)

    def test_external_changes_are_not_overwritten(self):
        self.module._set_linux(10717)
        self.commands.values[(ROOT + ".http", "host")] = "'new-user-proxy'"
        self.commands.values[(ROOT + ".http", "port")] = "9000"
        self.commands.values[(ROOT, "mode")] = "'none'"
        self.module._unset_linux()
        self.assertEqual(self.commands.values[(ROOT + ".http", "host")], "'new-user-proxy'")
        self.assertEqual(self.commands.values[(ROOT + ".http", "port")], "9000")
        self.assertEqual(self.commands.values[(ROOT, "mode")], "'none'")
        self.assertEqual(self.commands.values[(ROOT + ".https", "host")], self.original[(ROOT + ".https", "host")])

    def test_success_exit_without_effect_is_detected_and_rolled_back(self):
        self.commands.ignore_write = (ROOT + ".https", "port")
        with self.assertRaises(OSError):
            self.module._set_linux(10717)
        self.assertEqual(self.commands.values, self.original)

    def test_restart_during_partial_setup_restores_all_modified_keys(self):
        self.commands.interrupt = (ROOT + ".https", "host")
        with self.assertRaises(KeyboardInterrupt):
            self.module._set_linux(10717)
        self.module = load_proxy(SavedState(self.state.disk))
        self.module._unset_linux()
        self.assertEqual(self.commands.values, self.original)

    def test_failed_mode_restore_is_retained_for_retry(self):
        self.module._set_linux(10717)
        self.commands.fail = (ROOT, "mode")
        with self.assertRaises(OSError):
            self.module._unset_linux()
        self.assertTrue(any(self.state.disk.values()))
        self.module._unset_linux()
        self.assertEqual(self.commands.values, self.original)

    def test_empty_snapshot_is_rejected_before_setting(self):
        self.commands.values[(ROOT + ".http", "host")] = ""
        with self.assertRaises(OSError):
            self.module._set_linux(10717)
        self.assertEqual(self.commands.writes, [])

    def test_live_owner_prevents_another_instance_restoring(self):
        self.module._set_linux(10717)
        self.state.disk["_SAVED_LINUX_PROXY"]["owner_pid"] = os.getpid() + 1
        count = len(self.commands.writes)
        with mock.patch.object(self.module.os, "kill", return_value=None):
            with self.assertRaises(OSError):
                self.module._unset_linux()
        self.assertEqual(len(self.commands.writes), count)

    def test_dead_owner_is_recovered_after_restart(self):
        self.module._set_linux(10717)
        self.state.disk["_SAVED_LINUX_PROXY"]["owner_pid"] = os.getpid() + 1
        self.module = load_proxy(SavedState(self.state.disk))
        with mock.patch.object(self.module.os, "kill", side_effect=ProcessLookupError()):
            self.module._unset_linux()
        self.assertEqual(self.commands.values, self.original)


if __name__ == "__main__":
    unittest.main()
