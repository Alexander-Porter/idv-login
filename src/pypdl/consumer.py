import asyncio
from threading import Lock

from aiofiles import os

from .downloader import SegmentDownloader, SingleSegmentDownloader
from .utils import (
    FileValidator,
    auto_cancel_gather,
    check_main_thread_exception,
    combine_files,
    create_segment_table,
    run_callback,
)


class Consumer:
    def __init__(self, session, logger, _id):
        self._workers = []
        self._downloaded_size = 0
        self._size = 0
        self._success = []
        self._show_size = True
        self._lock = Lock()
        self._id = _id
        self._logger = logger
        self._session = session

    @property
    def size(self):
        if self._show_size:
            self._size = (
                sum(worker.curr for worker in self._workers) + self._downloaded_size
            )
        return self._size

    @property
    def success(self):
        with self._lock:
            return self._success.copy()

    async def add_success(self, url, file_path, hash_algorithms, callback):
        file_validator = FileValidator(file_path)
        if hash_algorithms:
            self._logger.debug("Calculating file hash %s", url)
            await file_validator._calculate_hash(hash_algorithms)

        if callback:
            self._logger.debug("Executing callback for %s", url)
            run_callback(callback, True, file_validator, self._logger)

        with self._lock:
            self._success.append((url, file_validator))

    async def process_tasks(self, in_queue, out_queue):
        self._logger.debug("Consumer %s started", self._id)
        while True:
            task = await in_queue.get()
            if task is None:
                break
            self._logger.debug("Consumer %s received task", self._id)
            try:
                await self._download(task)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                check_main_thread_exception(e)
                self._logger.debug("Task %s failed", self._id)
                self._logger.exception(e)
                await out_queue.put([task[0]])

            # Clear workers after task completion
            self._workers.clear()
            self._show_size = True

            self._logger.debug("Consumer %s completed task", self._id)
        self._logger.debug("Consumer %s exited", self._id)

    async def _download(
        self,
        task,
    ):
        _id, task = task
        (
            url,
            file_path,
            multisegment,
            etag,
            size,
            segments,
            overwrite,
            speed_limit,
            etag_validation,
            hash_algorithms,
            callback,
            kwargs,
        ) = task

        self._logger.debug("Download started %s", self._id)
        if not overwrite and await os.path.exists(file_path):
            self._logger.debug("File already exists, download completed")
            self._downloaded_size += await os.path.getsize(file_path)
            await self.add_success(url, file_path, hash_algorithms, callback)
            return

        if multisegment:
            segment_table = await create_segment_table(
                url, file_path, segments, size, etag, etag_validation
            )
            await self._multi_segment(segment_table, file_path, speed_limit, **kwargs)
        else:
            await self._single_segment(url, file_path, speed_limit, **kwargs)

        await self.add_success(url, file_path, hash_algorithms, callback)
        self._logger.debug("Download exited %s", self._id)

    async def _multi_segment(self, segment_table, file_path, speed_limit, **kwargs):
        tasks = set()
        segments = segment_table["segments"]
        speed_limit = speed_limit / segments
        self._logger.debug("Multi-Segment download started %s", self._id)
        for segment in range(segments):
            md = SegmentDownloader(self._session, speed_limit)
            self._workers.append(md)
            tasks.add(asyncio.create_task(md.worker(segment_table, segment, **kwargs)))

        await auto_cancel_gather(*tasks)
        await combine_files(file_path, segments)
        self._logger.debug("Downloaded all segments %s", self._id)
        self._show_size = False
        self._downloaded_size += await os.path.getsize(file_path)

    async def _single_segment(self, url, file_path, speed_limit, **kwargs):
        self._logger.debug("Single-Segment download started %s", self._id)
        sd = SingleSegmentDownloader(self._session, speed_limit)
        self._workers.append(sd)
        await sd.worker(url, file_path, **kwargs)
        self._logger.debug("Downloaded single segment %s", self._id)
        self._show_size = False
        self._downloaded_size += await os.path.getsize(file_path)
