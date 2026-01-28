import asyncio
import hashlib
import json
import logging
import shutil
import sys
import time
from concurrent.futures import CancelledError, Executor, Future, ThreadPoolExecutor
from os import path
from threading import Event, Thread
from typing import Callable, Dict, List, Optional, Union
from urllib.parse import unquote, urlparse

from aiohttp import ClientSession as Session
from aiofiles import open as fopen
from aiofiles import os as aio_os

MEGABYTE = 1048576
BLOCKSIZE = 4096
BLOCKS = 1024
CHUNKSIZE = BLOCKSIZE * BLOCKS
MAX_FILENAME_LENGTH = 255


class MainThreadException(Exception):
    pass


class Size:
    def __init__(self, start: int, end: int) -> None:
        self.start = start
        self.end = end
        self.value = end - start + 1  # since range is inclusive[0-99 -> 100]

    def __repr__(self) -> str:
        return str(self.value)


class Task:
    def __init__(
        self,
        multisegment: bool,
        segments: int,
        tries: int,
        overwrite: bool,
        speed_limit: Union[float, int],
        etag_validation: bool,
        hash_algorithms: List[str],
        callback: Callable,
        **kwargs,
    ):
        self.url = None
        self.file_path = None
        self.mirrors = None
        self.default_url = None
        self.multisegment = multisegment
        self.segments = segments
        self.tries = tries + 1
        self.overwrite = overwrite
        self.speed_limit = speed_limit
        self.etag_validation = etag_validation
        self.size = Size(0, 0)
        self.hash_algorithms = hash_algorithms
        self.callback = callback
        self.kwargs = kwargs if kwargs else {}

    def set(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if key == "retries":
                key = "tries"
                value = value + 1

            if hasattr(self, key):
                setattr(self, key, value)
            else:
                self.kwargs[key] = value
        self.validate()

        if self.mirrors is not None and not isinstance(self.mirrors, list):
            self.mirrors = [self.mirrors]

        if self.hash_algorithms is not None and isinstance(self.hash_algorithms, str):
            self.hash_algorithms = [self.hash_algorithms]

        self.default_url = self.url

    def validate(self) -> None:
        if not (isinstance(self.url, str) or callable(self.url)):
            raise TypeError(
                f"url should be of type str or callable, got {type(self.url).__name__}"
            )
        if not (isinstance(self.file_path, str) or self.file_path is None):
            raise TypeError(
                f"file_path should be of type str or None, got {type(self.file_path).__name__}"
            )
        if not (
            isinstance(self.mirrors, (list, str))
            or self.mirrors is None
            or callable(self.mirrors)
        ):
            raise TypeError(
                f"mirrors should be of type str, callable, list or None, got {type(self.mirrors).__name__}"
            )
        if not isinstance(self.multisegment, bool):
            raise TypeError(
                f"multisegment should be of type bool, got {type(self.multisegment).__name__}"
            )
        if not isinstance(self.segments, int):
            raise TypeError(
                f"segments should be of type int, got {type(self.segments).__name__}"
            )
        if not isinstance(self.tries, int):
            raise TypeError(
                f"tries should be of type int, got {type(self.tries).__name__}"
            )
        if not isinstance(self.overwrite, bool):
            raise TypeError(
                f"overwrite should be of type bool, got {type(self.overwrite).__name__}"
            )
        if not isinstance(self.speed_limit, (float, int)):
            raise TypeError(
                f"speed_limit should be of type float or int, got {type(self.speed_limit).__name__}"
            )
        if not isinstance(self.etag_validation, bool):
            raise TypeError(
                f"etag_validation should be of type bool, got {type(self.etag_validation).__name__}"
            )
        if not (
            isinstance(self.hash_algorithms, (list, str))
            or self.hash_algorithms is None
        ):
            raise TypeError(
                f"hash_algorithms should be of type list or str, got {type(self.hash_algorithms).__name__}"
            )
        if not (callable(self.callback) or self.callback is None):
            raise TypeError(
                f"callback should be a function, got {type(self.callback).__name__}"
            )

    def __repr__(self) -> str:
        return f"Task(url={self.url}, file_path={self.file_path}, tries={self.tries}, size={self.size})"


class TEventLoop:
    """A Threaded Eventloop"""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        self.loop.run_forever()
        self.loop.close()

    def get(self) -> asyncio.AbstractEventLoop:
        return self.loop

    def call_soon_threadsafe(self, func, *args) -> None:
        return self.loop.call_soon_threadsafe(func, *args)

    def has_running_tasks(self) -> bool:
        tasks = asyncio.all_tasks(self.loop)
        return any(not task.done() for task in tasks)

    def clear_wait(self) -> None:
        while self.has_running_tasks():
            time.sleep(0.1)

    def stop(self, *args) -> None:
        self.clear_wait()
        self.call_soon_threadsafe(self.loop.stop)
        self._thread.join()


class LoggingExecutor:
    """An Executor that logs exceptions."""

    def __init__(self, logger: logging.Logger, *args, **kwargs):
        self.executor = ThreadPoolExecutor(*args, **kwargs)
        self.logger = logger

    def submit(self, func: Callable, *args, **kwargs) -> Future:
        return self.executor.submit(self._wrap(func, *args, **kwargs))

    def shutdown(self) -> None:
        self.executor.shutdown()

    def _wrap(self, func: Callable, *args, **kwargs) -> Callable:
        def wrapper():
            try:
                return func(*args, **kwargs)
            except Exception as e:
                self.logger.exception(e)

        return wrapper


class FileValidator:
    """A class used to validate the integrity of the file."""

    def __init__(self, path: str):
        self.path = path
        self._cache = {}

    async def _calculate_hash(self, algorithms: List[str]) -> None:
        hash_objects = {}

        for algorithm in algorithms:
            if algorithm not in self._cache:
                hash_objects[algorithm] = hashlib.new(algorithm)

        async with fopen(self.path, "rb") as file:
            while chunk := await file.read(4096):
                for hash_object in hash_objects.values():
                    hash_object.update(chunk)

        for algorithm, hash_object in hash_objects.items():
            self._cache[algorithm] = hash_object.hexdigest()

    def get_hash(self, algorithm: str) -> str:
        """Get the hash of the file for the specified algorithm."""
        if algorithm not in self._cache:
            asyncio.run(self._calculate_hash([algorithm]))
        return self._cache[algorithm]

    def validate_hash(self, correct_hash: str, algorithm: str) -> bool:
        file_hash = self.get_hash(algorithm)
        return bytes.fromhex(file_hash) == bytes.fromhex(correct_hash)


class AutoShutdownFuture:
    """A Future object wrapper that shuts down the eventloop and executor when the result is retrieved."""

    def __init__(self, future: Future, loop: TEventLoop, executor: Executor):
        self._future = future
        self._executor = executor
        self._loop = loop

    def result(
        self, timeout: Optional[float] = None
    ) -> Union[List[FileValidator], None]:
        result = self._future.result(timeout)
        self._loop.stop()
        self._executor.shutdown()
        return result


class EFuture:
    """A Future object wrapper that cancels the future and clears the eventloop when stopped."""

    def __init__(self, future: Future, loop: TEventLoop, interrupt: Event):
        self._future = future
        self._loop = loop
        self._interrupt = interrupt

    def result(
        self, timeout: Optional[float] = None
    ) -> Union[List[FileValidator], None]:
        try:
            while not self._future.done():
                time.sleep(1)
        except KeyboardInterrupt:
            self._stop()
            self._loop.stop()
            raise

        if self._future.done():
            return self._future.result(timeout)

    def _stop(self) -> None:
        self._loop.call_soon_threadsafe(self._future.cancel)
        try:
            self.result()
        except CancelledError:
            pass

        self._loop.clear_wait()
        self._interrupt.set()


class ScreenCleaner:
    """Context manager to hide the terminal cursor and add spacing for cleaner output."""

    def __init__(self, display: bool):
        self.display = display

    def __enter__(self):
        if self.display:
            sys.stdout.write(2 * "\n")
            sys.stdout.write("\x1b[?25l")  # Hide cursor
            sys.stdout.flush()

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.display:
            sys.stdout.write("\x1b[?25h")  # Show cursor
            sys.stdout.flush()


def to_mb(size_in_bytes: int) -> float:
    return max(0, size_in_bytes) / MEGABYTE


def cursor_up() -> None:
    sys.stdout.write("\x1b[1A" * 2)  # Move cursor up two lines
    sys.stdout.flush()


def pad_line(text: str) -> str:
    terminal_width = shutil.get_terminal_size().columns
    return text + " " * max(0, terminal_width - len(text))


def check_main_thread_exception(e: Exception) -> None:
    if str(e) == "cannot schedule new futures after shutdown":
        raise MainThreadException from e


def get_int(value: str) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def seconds_to_hms(sec: float) -> str:
    if sec == -1:
        return "99:59:59"
    time_struct = time.gmtime(sec)
    return time.strftime("%H:%M:%S", time_struct)


def make_progress_bar(percentage: int) -> str:
    terminal_width = shutil.get_terminal_size().columns
    bar_width = max(10, min(100, terminal_width - 7))
    filled = int((percentage / 100) * bar_width)
    return f"[{'█' * filled}{'·' * (bar_width - filled)}] {percentage}%"


def get_file_size(metadata: dict) -> int:
    status = metadata.get("status")
    if status == 200:
        return get_int(metadata.get("content-length"))
    elif status == 206:
        return get_int(metadata["content-range"].split("/")[-1])
    else:
        return 0


async def extract_metadata(url: str, session: Session, method: str, **kwargs) -> dict:
    async with getattr(session, method)(url, **kwargs) as resp:
        h = {k.lower(): v.strip('"') for k, v in resp.headers.items()}
        return {
            "accept-ranges": h.get("accept-ranges", "").lower() == "bytes",
            "content-length": h.get("content-length", ""),
            "content-range": h.get("content-range", ""),
            "etag": h.get("etag", ""),
            "content-disposition": h.get("content-disposition", ""),
            "status": resp.status,
        }


async def get_url(url: Union[str, Callable]) -> str:
    if callable(url):
        if asyncio.iscoroutinefunction(url):
            url = await url()
        else:
            url = url()

    if isinstance(url, str):
        return url
    raise TypeError(f"Function returned a non-string URL, got {type(url).__name__}")


async def auto_cancel_gather(*args, **kwargs) -> List:
    tasks = []
    for task in args:
        if isinstance(task, asyncio.Task):
            tasks.append(task)
        else:
            tasks.append(asyncio.create_task(task))
    try:
        return await asyncio.gather(*tasks, **kwargs)
    except Exception:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def get_filepath(url: str, headers: Dict[str, str], file_path: str) -> str:
    # Try to get filename from Content-Disposition header
    filename = None
    content_disposition = headers.get("content-disposition", "")

    # Check for filename* parameter (RFC 6266)
    if "filename*=" in content_disposition:
        try:
            start_pos = content_disposition.find("filename*=") + len("filename*=")
            end_pos = content_disposition.find(";", start_pos)
            encoded_filename = content_disposition[
                start_pos : end_pos if end_pos > 0 else None
            ]

            if "'" in encoded_filename:
                parts = encoded_filename.split("'", 2)
                if len(parts) == 3:
                    _, _, encoded_part = parts
                    filename = unquote(encoded_part.strip())
        except Exception:
            filename = None

    if not filename and "filename=" in content_disposition:
        try:
            start_pos = content_disposition.find("filename=") + len("filename=")
            # Handle quoted filenames
            if content_disposition[start_pos : start_pos + 1] == '"':
                end_pos = content_disposition.find('"', start_pos + 1)
                if end_pos > start_pos:
                    filename = content_disposition[start_pos + 1 : end_pos]
            else:
                # Non-quoted filename - read until semicolon or end
                end_pos = content_disposition.find(";", start_pos)
                filename = content_disposition[
                    start_pos : end_pos if end_pos > 0 else None
                ]

            filename = unquote(filename.strip())
        except Exception:
            filename = None

    # Fallback to URL if filename wasn't found
    if not filename:
        path_part = urlparse(url).path
        filename = unquote(path_part.split("/")[-1])

        if not filename or filename.startswith("?"):
            domain = urlparse(url).netloc.split(":")[0]  # Remove port if present
            filename = domain or "download"

    # Sanitize filename to avoid OS errors (replace invalid chars)
    invalid_chars = ["<", ">", ":", '"', "/", "\\", "|", "?", "*"]
    for char in invalid_chars:
        filename = filename.replace(char, "_")

    # If filename is still empty after all processing, use a default name
    if not filename:
        filename = "download"

    # Trim to reasonable filename length
    if len(filename.encode("utf-8")) > MAX_FILENAME_LENGTH:
        name, ext = path.splitext(filename)
        max_name_len = MAX_FILENAME_LENGTH - len(ext.encode("utf-8"))
        filename = (
            name.encode("utf-8")[:max_name_len].decode("utf-8", errors="ignore") + ext
        )

    if file_path:
        if await aio_os.path.isdir(file_path):
            return path.join(file_path, filename)
        return file_path

    return filename


async def create_segment_table(
    url: str,
    file_path: str,
    segments: int,
    size: Size,
    etag: str,
    etag_validation: bool,
) -> Dict:
    """Create a segment table for multi-segment download."""
    progress_file = file_path + ".json"
    overwrite = True

    if await aio_os.path.exists(progress_file):
        async with fopen(progress_file, "r") as f:
            progress = json.loads(await f.read())
            if not etag_validation or (
                progress["etag"]
                and (progress["url"] == url and progress["etag"] == etag)
            ):
                segments = progress["segments"]
                overwrite = False

    async with fopen(progress_file, "w") as f:
        await f.write(
            json.dumps(
                {"url": url, "etag": etag, "segments": segments},
                indent=4,
            )
        )

    dic = {"url": url, "segments": segments, "overwrite": overwrite}
    partition_size, add_bytes = divmod(size.value, segments)

    for segment in range(segments):
        start = size.start + partition_size * segment
        end = (
            size.start + partition_size * (segment + 1) - 1
        )  # since range is inclusive[0-99]

        if segment == segments - 1:
            end += add_bytes

        dic[segment] = {
            "segment_size": Size(start, end),
            "segment_path": f"{file_path}.{segment}",
        }

    return dic


async def combine_files(file_path: str, segments: int) -> None:
    """Combine the downloaded file segments into a single file."""
    async with fopen(file_path, "wb") as dest:
        for segment in range(segments):
            segment_file = f"{file_path}.{segment}"
            async with fopen(segment_file, "rb") as src:
                while True:
                    chunk = await src.read(CHUNKSIZE)
                    if chunk:
                        await dest.write(chunk)
                    else:
                        break

            await aio_os.remove(segment_file)

    progress_file = f"{file_path}.json"
    await aio_os.remove(progress_file)


def default_logger(name: str) -> logging.Logger:
    """Creates a default debugging logger."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.WARN)
    handler = logging.FileHandler("pypdl.log", mode="a", delay=True)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s - %(levelname)s: %(message)s",
            datefmt="%d-%m-%y %H:%M:%S",
        )
    )
    logger.addHandler(handler)
    return logger


def get_range(range_header: str, file_size: int) -> Size:
    if not range_header.lower().startswith("bytes="):
        raise ValueError('Range header must start with "bytes="')

    range_value = range_header.split("=")[1].strip()
    parts = range_value.split("-", 1)

    try:
        start = int(parts[0]) if parts[0] else None
        end = int(parts[1]) if parts[1] else None
    except (ValueError, IndexError):
        raise ValueError(f"Invalid range format: {range_value}")

    # Case 1: "bytes=start-end"
    if start is not None and end is not None:
        # Already parsed correctly
        pass

    # Case 2: "bytes=start-"
    elif start is not None and end is None:
        end = file_size - 1

    # Case 3: "bytes=-suffix_length"
    elif end is not None and start is None:
        if end == 0:
            raise ValueError("Invalid range: suffix length cannot be zero")
        start = max(0, file_size - end)
        end = file_size - 1

    # Case 4: Invalid format like "bytes=-"
    else:
        raise ValueError(f"Invalid range format: {range_value}")

    if start > end:
        if end == -1:  # file_size == 0
            start = 0
        else:
            raise ValueError(f"Invalid range: start ({start}) > end ({end})")

    return Size(start, end)


def run_callback(
    func: Callable,
    status: bool,
    result: Union[FileValidator, None],
    logger: logging.Logger,
) -> None:
    def _callback():
        try:
            func(status, result)
        except Exception as e:
            logger.exception(f"Callback function {func.__name__} failed: {e}")

    Thread(target=_callback, daemon=True).start()
