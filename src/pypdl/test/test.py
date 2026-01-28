import hashlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
import warnings
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

from server import LocalServer
from pypdl import Pypdl


class TestPypdl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = LocalServer()
        cls.server.start()
        cls.url_tiny = f"{cls.server.base_url}/file_tiny"
        cls.url_small = f"{cls.server.base_url}/file_small"
        cls.url_large = f"{cls.server.base_url}/file_large"
        cls.url_nohead = f"{cls.server.base_url}/nohead_small"
        cls.url_stream = f"{cls.server.base_url}/stream_chunked"

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def __init__(self, *args, **kwargs):
        super(TestPypdl, self).__init__(*args, **kwargs)
        self.temp_dir = os.path.join(tempfile.gettempdir(), "pypdl_test")
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        os.mkdir(self.temp_dir)

    def setUp(self):
        warnings.filterwarnings(
            "ignore", message="unclosed <socket.socket", category=ResourceWarning
        )
        warnings.filterwarnings(
            "ignore",
            message="unclosed transport",
            category=ResourceWarning,
        )

    def _assert_download(self, expected, success, filepath):
        self.assertEqual(success, expected, f"{expected - success} downloads failed")
        for path in filepath:
            self.assertTrue(os.path.exists(path))

    def test_single_segment_download(self):
        dl = Pypdl()
        url = self.url_small
        file_path = os.path.join(self.temp_dir)
        result = dl.start(url, file_path, display=False, multisegment=False)
        success = len(result)
        self.assertEqual(success, 1, "Download failed")

    def test_multi_segment_download(self):
        dl = Pypdl()
        url = self.url_small
        file_path = os.path.join(self.temp_dir, "test.dat")
        future = dl.start(url, file_path, display=False, block=False, speed_limit=0.5)
        time.sleep(2)
        self.assertTrue(os.path.exists(file_path + ".json"))
        success = len(future.result())
        self._assert_download(1, success, [file_path])

    def test_multiple_downloads(self):
        dl = Pypdl(max_concurrent=2)
        filepath = [os.path.join(self.temp_dir, f"file{i}.dat") for i in range(4)]
        tasks = [
            {
                "url": self.url_small,
                "file_path": filepath[0],
            },
            {
                "url": self.url_small,
                "file_path": filepath[1],
            },
            {
                "url": self.url_small,
                "file_path": filepath[2],
            },
            {
                "url": self.url_small,
                "file_path": filepath[3],
            },
        ]
        result = dl.start(tasks=tasks, block=True, display=False)
        success = len(result)
        self._assert_download(4, success, filepath)

    def test_allow_reuse(self):
        result = []
        dl = Pypdl(allow_reuse=True)
        url = self.url_small
        filepath = [os.path.join(self.temp_dir, f"file{i}.dat") for i in range(2)]

        res1 = dl.start(url, filepath[0], display=False)
        result.append(res1)
        res2 = dl.start(url, filepath[1], display=False)
        result.append(res2)
        success = len(result)
        dl.shutdown()
        self._assert_download(2, success, filepath)

    def test_speed_limit(self):
        cases = [
            (self.url_tiny, 262144, 0.5, 0, 3),  # ~256KB @ 0.5MB/s ~0.5s
            (self.url_small, 1572864, 0.2, 5, 20),  # ~1.5MB @ 0.2MB/s ~7.5s
        ]
        for url, size, limit, tmin, tmax in cases:
            dl = Pypdl()
            file_path = os.path.join(
                self.temp_dir, f"speed_{os.path.basename(url)}.dat"
            )
            dl.start(url, file_path, display=False, speed_limit=limit)
            self.assertTrue(os.path.exists(file_path))
            self.assertEqual(os.path.getsize(file_path), size)
            self.assertTrue(
                tmin <= dl.time_spent <= tmax,
                f"{url} took {dl.time_spent:.2f}s; expected [{tmin}, {tmax}]s",
            )

    def test_unblocked_download(self):
        dl = Pypdl(max_concurrent=2)
        filepath = [os.path.join(self.temp_dir, f"file{i}.dat") for i in range(2)]
        tasks = [
            {
                "url": self.url_small,
                "file_path": filepath[0],
            },
            {
                "url": self.url_small,
                "file_path": filepath[1],
            },
        ]
        future = dl.start(tasks=tasks, block=False, display=False)
        while not dl.completed:
            time.sleep(1)
        success = len(future.result())
        self._assert_download(2, success, filepath)

    def test_stop_restart_with_segements(self):
        dl = Pypdl(max_concurrent=2)
        url = self.url_small
        file_path = os.path.join(self.temp_dir, "test.dat")
        dl.start(
            url, file_path, block=False, display=False, speed_limit=0.15, segments=3
        )
        time.sleep(5)
        progress = dl.progress
        dl.stop()
        self.assertTrue(os.path.exists(file_path + ".0"))
        self.assertTrue(os.path.exists(file_path + ".1"))
        self.assertTrue(dl.is_idle)
        dl.start(url, file_path, display=False, speed_limit=0.01, block=False)
        time.sleep(3)
        self.assertTrue(dl.progress >= progress)
        dl.stop()
        self.assertTrue(dl.is_idle)
        res = dl.start(url, file_path, display=False)
        success = len(res)
        self._assert_download(1, success, [file_path])

    def test_logger(self):
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)
        log_file = os.path.join(self.temp_dir, "test.log")
        handler = logging.FileHandler(log_file, mode="a", delay=True)
        logger.addHandler(handler)

        dl = Pypdl(logger=logger)
        url = self.url_small
        file_path = os.path.join(self.temp_dir, "test.dat")
        dl.start(url, file_path, display=False, block=False)
        time.sleep(3)
        dl.shutdown()
        logger.removeHandler(handler)
        handler.close()
        self.assertTrue(os.path.exists(log_file))

    def test_header(self):
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)
        log_file = os.path.join(self.temp_dir, "header.log")
        handler = logging.FileHandler(log_file, mode="a", delay=True)
        logger.addHandler(handler)

        dl = Pypdl(allow_reuse=True, logger=logger)
        url = self.url_small
        file_path = os.path.join(self.temp_dir, "test.dat")
        dl.start(url, file_path, display=False, block=False, speed_limit=0.1)
        time.sleep(3)
        dl.stop()
        self.assertTrue(os.path.exists(log_file))
        with open(log_file, "r") as f:
            log_content = f.read()
        header_pattern = re.compile("Fetching headers with HEAD to get metadata")
        self.assertTrue(
            header_pattern.search(log_content),
            "Unable to acquire header from HEAD request",
        )

        url = self.url_nohead
        file_path = os.path.join(self.temp_dir, "temp.csv")
        dl.start(url, file_path, display=False, block=False, speed_limit=0.1)
        time.sleep(2)

        dl.shutdown()
        logger.removeHandler(handler)
        handler.close()

        with open(log_file, "r") as f:
            log_content = f.read()
        header_pattern = re.compile(
            "Fetching headers with GET to fill missing metadata"
        )
        self.assertTrue(
            header_pattern.search(log_content),
            "Unable to acquire header from GET request",
        )

    def test_retries(self):
        mirrors = [self.url_small, "http://fake_website/file2"]
        file_path = os.path.join(self.temp_dir, "test.dat")
        dl = Pypdl()
        res = dl.start(
            "http://fake_website/file",
            file_path,
            display=False,
            retries=2,
            mirrors=mirrors,
        )
        success = len(res)
        self._assert_download(1, success, [file_path])

    def test_overwrite(self):
        logger = logging.getLogger()
        logger.setLevel(logging.DEBUG)
        log_file = os.path.join(self.temp_dir, "overwrite.log")
        handler = logging.FileHandler(log_file, mode="a", delay=True)
        logger.addHandler(handler)

        dl = Pypdl(logger=logger, allow_reuse=True)
        url = self.url_small
        file_path = os.path.join(self.temp_dir, "test.dat")
        res = dl.start(url, file_path, display=False)
        success = len(res)
        self._assert_download(1, success, [file_path])
        res = dl.start(url, file_path, display=False, overwrite=False)
        success = len(res)
        self._assert_download(1, success, [file_path])

        with open(log_file, "r") as f:
            log_content = f.read()
        header_pattern = re.compile("File already exists, download completed")
        self.assertTrue(header_pattern.search(log_content), "overwrite not working")
        dl.shutdown()
        logger.removeHandler(handler)
        handler.close()

    def test_etag_validation(self):
        dl = Pypdl()
        url = self.url_large
        file_path = os.path.join(self.temp_dir, "test.dat")
        dl.start(
            url, file_path, display=False, block=False, speed_limit=0.1, segments=4
        )
        time.sleep(3)
        progress = dl.progress
        dl.stop()

        with open(file_path + ".json", "r") as f:
            json_file = json.load(f)

        json_file["etag"] = "fake_etag"

        with open(file_path + ".json", "w") as f:
            json.dump(json_file, f)

        dl.start(
            url,
            file_path,
            display=False,
            etag_validation=False,
            speed_limit=0.01,
            block=False,
        )
        time.sleep(3)
        self.assertTrue(dl.progress >= progress)
        dl.shutdown()

    def test_failed(self):
        dl = Pypdl()
        url = "http://fake_website/file"
        file_path = os.path.join(self.temp_dir, "test.dat")
        dl.start(url, file_path, display=False)
        self.assertEqual(len(dl.failed), 1, "Failed downloads not found")

    def test_range_header(self):
        dl = Pypdl()
        url = self.url_small
        file_path = os.path.join(self.temp_dir, "range_test.dat")
        headers = {"Range": "bytes=0-99999"}  # 100,000 bytes
        res = dl.start(url, file_path, display=False, segments=4, headers=headers)
        self.assertEqual(len(res), 1)
        self.assertTrue(os.path.exists(file_path))
        self.assertEqual(os.path.getsize(file_path), 100000)

    def test_callback_and_hash(self):
        dl = Pypdl()
        url = self.url_small
        file_path = os.path.join(self.temp_dir, "hash_test.dat")
        results = []

        def cb(status, fv):
            try:
                md5 = fv.get_hash("md5") if fv else None
            except Exception:
                md5 = None
            results.append((status, md5))

        res = dl.start(
            url,
            file_path,
            display=False,
            hash_algorithms=["md5"],
            callback=cb,
        )
        self.assertEqual(len(res), 1)
        timeout = time.time() + 5
        while not results and time.time() < timeout:
            time.sleep(0.05)
        self.assertTrue(results and results[0][0] is True)
        with open(file_path, "rb") as f:
            expected_md5 = hashlib.md5(f.read()).hexdigest()
        self.assertEqual(results[0][1], expected_md5)

    def test_streaming_without_content_length(self):
        # This simulates a server that streams data (chunked) without Content-Length.
        # We expect pypdl to download in single-segment mode and not raise ValueError.
        dl = Pypdl()
        url = self.url_stream
        file_path = os.path.join(self.temp_dir, "stream_chunked.dat")

        # Run download; should not raise exceptions like ValueError due to size handling
        res = dl.start(url, file_path, display=False)
        self.assertEqual(len(res), 1)
        self.assertTrue(os.path.exists(file_path))
        # Size should be the streamed size from server
        expected_size = len(self.server.data_stream)
        self.assertEqual(os.path.getsize(file_path), expected_size)


if __name__ == "__main__":
    unittest.main(verbosity=2)
