import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import secure_write


@unittest.skipUnless(sys.platform == "win32", "Windows ACL integration tests")
class WindowsRestrictedWriteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "record.json"
        # Even a failed ACL test must leave its own temporary files removable.
        self.addCleanup(self.restore_test_access)

    def restore_test_access(self):
        identity = subprocess.run(
            ["whoami", "/user", "/fo", "csv", "/nh"],
            capture_output=True, text=True, check=True,
        )
        sid = next(csv.reader(identity.stdout.splitlines()))[1]
        subprocess.run(
            ["icacls", self.directory.name, "/grant:r", f"*{sid}:(F)", "/t"],
            capture_output=True, check=True,
        )

    def assert_restricted_acl(self, path):
        # Inspect the actual Windows security descriptor independently of
        # the production whoami/icacls commands and their display language.
        script = """
$ErrorActionPreference = 'Stop'
$acl = [System.IO.File]::GetAccessControl($env:IDV_TEST_ACL_PATH)
[Console]::WriteLine([System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value)
[Console]::WriteLine($acl.AreAccessRulesProtected)
foreach ($rule in $acl.Access) {
    $sid = $rule.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value
    [Console]::WriteLine(('{0}|{1}|{2}|{3}' -f $sid, $rule.IsInherited,
        [int]$rule.AccessControlType, [int]$rule.FileSystemRights))
}
"""
        environment = dict(os.environ, IDV_TEST_ACL_PATH=str(path))
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True,
            env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        user, protected, *rows = result.stdout.splitlines()
        rules = [row.split("|") for row in rows]
        self.assertEqual(protected, "True")
        self.assertEqual({rule[0] for rule in rules},
                         {user, "S-1-5-32-544", "S-1-5-18"})
        for sid, inherited, access_type, rights in rules:
            self.assertEqual(inherited, "False")
            self.assertEqual(access_type, "0")  # Allow
            self.assertEqual(int(rights) & 0x1F01FF, 0x1F01FF)  # FullControl

    def test_native_create_and_repeated_replace_preserve_user_access(self):
        for content in (b"first", b"second"):
            secure_write.write_file_restricted(str(self.path), content)
            self.assertEqual(self.path.read_bytes(), content)
            self.assert_restricted_acl(self.path)
        secure_write.write_json_restricted(str(self.path), {"saved": "新内容"})
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")),
                         {"saved": "新内容"})
        self.assert_restricted_acl(self.path)

    def test_acl_is_applied_before_payload_is_written(self):
        # A broadly readable parent must not expose the written payload.
        subprocess.run(
            ["icacls", self.directory.name, "/grant:r", "*S-1-1-0:(OI)(CI)(R)"],
            capture_output=True, check=True,
        )
        real_restrict_acl = secure_write._win_restrict_acl

        def inspect_empty_file(path):
            self.assertEqual(Path(path).read_bytes(), b"")
            real_restrict_acl(path)
            self.assert_restricted_acl(path)

        with mock.patch.object(secure_write, "_win_restrict_acl", side_effect=inspect_empty_file):
            secure_write.write_file_restricted(str(self.path), b"private test payload")
        self.assertEqual(self.path.read_bytes(), b"private test payload")

    def test_atomic_failure_cleans_up_restricted_temporary_file(self):
        self.path.write_bytes(b"original")
        for operation in ("fsync", "replace"):
            with self.subTest(operation=operation):
                with mock.patch.object(secure_write.os, operation, side_effect=OSError("write failed")):
                    with self.assertRaises(OSError):
                        secure_write.write_file_restricted(str(self.path), b"replacement")
                self.assertEqual(self.path.read_bytes(), b"original")
                self.assertEqual(list(self.path.parent.glob(".tmp_*")), [])


class WindowsAclFailureTests(unittest.TestCase):
    def test_acl_command_failure_preserves_original_without_publishing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            path.write_bytes(b"original")
            for failing_command in ("whoami", "reset", "grant"):
                with self.subTest(command=failing_command):
                    def run(command, **kwargs):
                        stage = "whoami" if os.path.basename(command[0]).lower() == "whoami.exe" else (
                            "reset" if "/reset" in command else "grant")
                        if stage == failing_command:
                            if kwargs.get("check"):
                                raise subprocess.CalledProcessError(1, command)
                            return subprocess.CompletedProcess(command, 1)
                        return subprocess.CompletedProcess(
                            command, 0, stdout='"test-user","S-1-5-21-1-2-3-1001"\n')

                    with mock.patch.object(secure_write.sys, "platform", "win32"), \
                            mock.patch.object(subprocess, "run", side_effect=run):
                        with self.assertRaises(OSError):
                            secure_write.write_file_restricted(str(path), b"replacement")
                    self.assertEqual(path.read_bytes(), b"original")
                    self.assertEqual(list(path.parent.glob(".tmp_*")), [])

    def test_invalid_identity_preserves_original(self):
        for output in ('', '"test-user"\n', '"test-user","invalid SID"\n',
                       '"test-user","S-1-5-21-1-2-3-1001"\nextra,row\n'):
            with self.subTest(output=output), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "record.json"
                path.write_bytes(b"original")
                with mock.patch.object(secure_write.sys, "platform", "win32"), \
                        mock.patch.object(subprocess, "run", return_value=
                                          subprocess.CompletedProcess([], 0, stdout=output)):
                    with self.assertRaises(OSError):
                        secure_write.write_file_restricted(str(path), b"replacement")
                self.assertEqual(path.read_bytes(), b"original")
                self.assertEqual(list(path.parent.glob(".tmp_*")), [])

    def test_command_timeout_or_missing_tool_preserves_original(self):
        for error in (subprocess.TimeoutExpired("whoami", 10), FileNotFoundError("missing tool")):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "record.json"
                path.write_bytes(b"original")
                with mock.patch.object(secure_write.sys, "platform", "win32"), \
                        mock.patch.object(subprocess, "run", side_effect=error):
                    with self.assertRaises(OSError) as raised:
                        secure_write.write_file_restricted(str(path), b"replacement")
                self.assertNotIn("whoami", str(raised.exception))
                self.assertEqual(path.read_bytes(), b"original")
                self.assertEqual(list(path.parent.glob(".tmp_*")), [])


if __name__ == "__main__":
    unittest.main()
