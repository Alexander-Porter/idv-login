import asyncio
from threading import Lock

from .utils import (
    Size,
    check_main_thread_exception,
    get_filepath,
    get_range,
    get_url,
    run_callback,
    extract_metadata,
    get_file_size,
)


class Producer:
    def __init__(self, session, logger, tasks):
        self._size = None
        self._failed = []
        self._lock = Lock()
        self._logger = logger
        self._session = session
        self._tasks = tasks
        self._size_avail = True

    @property
    def size(self):
        if self._size_avail:
            return self._size

    @property
    def failed(self):
        with self._lock:
            return self._failed.copy()

    def add_failed(self, url, callback):
        if callback:
            self._logger.debug("Executing callback for failed URL: %s", url)
            run_callback(callback, False, None, self._logger)

        with self._lock:
            self._failed.append(url)

    async def enqueue_tasks(self, in_queue, out_queue):
        self._logger.debug("Producer started")
        while True:
            batch = await in_queue.get()

            if batch is None:
                break

            total_size = 0

            for _id in batch:
                task = self._tasks[_id]
                if task.tries > 0:
                    task.tries -= 1
                    try:
                        (
                            url,
                            file_path,
                            multisegment,
                            etag,
                            size,
                            kwargs,
                        ) = await self._fetch_task_info(
                            task.url, task.file_path, task.multisegment, **task.kwargs
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        check_main_thread_exception(e)
                        self._logger.debug(
                            f"Failed to get header for {task}, skipping task"
                        )
                        self._logger.exception(e)
                        await asyncio.sleep(3)
                        new_url = (
                            task.mirrors.pop(0) if task.mirrors else task.default_url
                        )
                        task.url = new_url
                        await in_queue.put([_id])
                        continue

                    if size.value == 0:
                        self._logger.debug("Size is Unavailable, setting size to None")
                        self._size_avail = False

                    total_size -= task.size.value
                    total_size += size.value
                    task.size = size
                    await out_queue.put(
                        (
                            _id,
                            (
                                url,
                                file_path,
                                multisegment,
                                etag,
                                size,
                                task.segments,
                                task.overwrite,
                                task.speed_limit,
                                task.etag_validation,
                                task.hash_algorithms,
                                task.callback,
                                kwargs,
                            ),
                        )
                    )
                else:
                    self.add_failed(task.url, task.callback)

            if self._size is None:
                self._size = total_size
            else:
                self._size += total_size
        self._logger.debug("Producer exited")

    async def _fetch_task_info(self, url, file_path, multisegment, **kwargs):
        url = await get_url(url)

        user_headers = kwargs.get("headers", {})
        range_header = None

        if user_headers:
            _user_headers = user_headers.copy()
            for key, value in user_headers.items():
                if key.lower() == "range":
                    range_header = value
                    self._logger.debug("Range header found %s", range_header)
                    del _user_headers[key]
            kwargs["headers"] = _user_headers

        metadata = await self._fetch_metadata(url, **kwargs)
        file_path = await get_filepath(url, metadata, file_path)
        file_size = get_file_size(metadata)
        self._logger.debug("file size: %s", file_size)

        if multisegment and range_header:
            size = get_range(range_header, file_size)
        else:
            size = Size(0, file_size - 1)

        etag = metadata.get("etag", "")
        if etag != "":
            self._logger.debug("ETag acquired from header")

        if size.value == 0 or not metadata.get("accept-ranges"):
            self._logger.debug("Single segment mode, accept-ranges or size not found")
            multisegment = False

        if not multisegment:
            kwargs["headers"] = user_headers

        return url, file_path, multisegment, etag, size, kwargs

    async def _fetch_metadata(self, url, **kwargs):
        self._logger.debug("Fetching headers with HEAD to get metadata")
        kwargs["raise_for_status"] = False
        metadata = await extract_metadata(url, self._session, "head", **kwargs)

        if not (
            metadata["accept-ranges"]
            and metadata["etag"]
            and metadata["content-disposition"]
            and (metadata["content-length"] or metadata["content-range"])
        ):
            self._logger.debug("Fetching headers with GET to fill missing metadata")
            kwargs.setdefault("headers", {}).update({"Range": "bytes=0-0"})
            kwargs["raise_for_status"] = True
            metadata.update(await extract_metadata(url, self._session, "get", **kwargs))

        return metadata
