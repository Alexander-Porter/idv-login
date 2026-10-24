import errno
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import secure_write


class PartialWriteFailure:
    """Write some real temporary-file data before simulating a full disk."""

    def __init__(self, file):
        self.file = file

    def __getattr__(self, name):
        return getattr(self.file, name)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return self.file.__exit__(*args)

    def write(self, data):
        self.file.write(data[:1])
        raise OSError(errno.ENOSPC, "Simulated full disk")


class SecureWriteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "record.json"
        self.original = b'{"saved": "old"}'
        self.path.write_bytes(self.original)
        if sys.platform == "win32":
            # ACL policy is independent of atomicity and requires elevation.
            acl_patch = mock.patch.object(secure_write, "_win_restrict_acl")
            acl_patch.start()
            self.addCleanup(acl_patch.stop)

    def writers(self):
        writers = (
            ("bytes", lambda: secure_write.write_file_restricted(
                str(self.path), b"new bytes")),
            ("json", lambda: secure_write.write_json_restricted(
                str(self.path), {"saved": "新内容"})),
            ("non_strict_json", lambda: secure_write.write_json_restricted(
                str(self.path), {"saved": "新内容"}, atomic_required=False)),
            ("strict_json", lambda: secure_write.write_json_restricted(
                str(self.path), {"saved": "新内容"}, atomic_required=True)),
        )
        for name, write in writers:
            directory = Path(self.directory.name) / name
            directory.mkdir()
            self.path = directory / "record.json"
            self.path.write_bytes(self.original)
            yield name, write

    def assert_original_preserved(self):
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(list(self.path.parent.glob(".tmp_*")), [])

    def test_lock_timeout_preserves_original(self):
        for name, write in self.writers():
            with self.subTest(writer=name):
                lock = threading.Lock()
                lock.acquire()
                timed_lock = mock.Mock(wraps=lock)
                # Exercise a real held lock without waiting five seconds.
                timed_lock.acquire.side_effect = lambda timeout: lock.acquire(False)
                try:
                    with mock.patch.object(secure_write, "_get_lock", return_value=timed_lock):
                        with self.assertRaises(TimeoutError):
                            write()
                    self.assert_original_preserved()
                finally:
                    if lock.locked():
                        lock.release()

    def test_lock_timeout_does_not_release_another_writers_lock(self):
        for name, write in self.writers():
            with self.subTest(writer=name):
                lock = threading.Lock()
                lock.acquire()
                timed_lock = mock.Mock(wraps=lock)
                timed_lock.acquire.side_effect = lambda timeout: lock.acquire(False)
                try:
                    with mock.patch.object(secure_write, "_get_lock", return_value=timed_lock):
                        try:
                            write()
                        except TimeoutError:
                            pass
                    self.assertTrue(lock.locked())
                finally:
                    if lock.locked():
                        lock.release()

    def test_temporary_file_creation_failure_preserves_original(self):
        for name, write in self.writers():
            with self.subTest(writer=name):
                error = OSError(errno.ENOSPC, "Simulated full disk")
                with mock.patch.object(secure_write.tempfile, "mkstemp", side_effect=error), \
                        mock.patch.object(secure_write.tempfile, "NamedTemporaryFile", side_effect=error):
                    with self.assertRaises(OSError) as raised:
                        write()
                self.assertIs(raised.exception, error)
                self.assert_original_preserved()

    def test_partial_temporary_write_failure_preserves_original(self):
        real_fdopen = os.fdopen
        real_named_temp = tempfile.NamedTemporaryFile
        for name, write in self.writers():
            with self.subTest(writer=name):
                if sys.platform == "win32":
                    target = mock.patch.object(
                        secure_write.tempfile, "NamedTemporaryFile",
                        side_effect=lambda *args, **kwargs: PartialWriteFailure(
                            real_named_temp(*args, **kwargs)),
                    )
                else:
                    target = mock.patch.object(
                        secure_write.os, "fdopen",
                        side_effect=lambda *args, **kwargs: PartialWriteFailure(
                            real_fdopen(*args, **kwargs)),
                    )
                with target:
                    with self.assertRaises(OSError) as raised:
                        write()
                self.assertEqual(raised.exception.errno, errno.ENOSPC)
                self.assert_original_preserved()

    def test_fsync_failure_preserves_original(self):
        for name, write in self.writers():
            with self.subTest(writer=name):
                error = OSError(errno.EIO, "Simulated flush failure")
                with mock.patch.object(secure_write.os, "fsync", side_effect=error):
                    with self.assertRaises(OSError) as raised:
                        write()
                self.assertIs(raised.exception, error)
                self.assert_original_preserved()

    def test_replace_failure_preserves_original_and_releases_lock(self):
        for name, write in self.writers():
            with self.subTest(writer=name):
                error = PermissionError("Simulated replace failure")
                with mock.patch.object(secure_write.os, "replace", side_effect=error):
                    with self.assertRaises(PermissionError) as raised:
                        write()
                self.assertIs(raised.exception, error)
                self.assert_original_preserved()
                lock = secure_write._get_lock(str(self.path))
                acquired = lock.acquire(False)
                self.assertTrue(acquired)
                if acquired:
                    lock.release()
                write()
                self.assertNotEqual(self.path.read_bytes(), self.original)
                self.path.write_bytes(self.original)

    def test_failed_creation_does_not_publish_a_destination(self):
        for name, write in self.writers():
            with self.subTest(writer=name):
                self.path.unlink()
                with mock.patch.object(secure_write.os, "replace", side_effect=OSError("replace failed")):
                    with self.assertRaises(OSError):
                        write()
                self.assertFalse(self.path.exists())
                self.assertEqual(list(self.path.parent.iterdir()), [])

    def test_successful_write_replaces_original(self):
        for name, write in self.writers():
            with self.subTest(writer=name):
                write()
                if name == "bytes":
                    self.assertEqual(self.path.read_bytes(), b"new bytes")
                else:
                    self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")),
                                     {"saved": "新内容"})
                    self.assertIn("新内容".encode("utf-8"), self.path.read_bytes())
                self.assertEqual(list(self.path.parent.glob(".tmp_*")), [])
                if sys.platform != "win32":
                    self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

    def test_json_serialization_failure_preserves_original(self):
        with self.assertRaises(TypeError):
            secure_write.write_json_restricted(str(self.path), {"bad": object()})
        self.assert_original_preserved()


if __name__ == "__main__":
    unittest.main()
