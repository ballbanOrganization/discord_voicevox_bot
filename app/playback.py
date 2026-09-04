import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import discord

logger = logging.getLogger(__name__)

DEFAULT_QUEUE_MAX_SIZE = 20


class PlaybackStatus(Protocol):
    async def mark_started(self) -> None:
        ...

    async def mark_completed(self) -> None:
        ...

    async def mark_failed(self) -> None:
        ...


@dataclass(frozen=True)
class PlaybackItem:
    text: str
    user_id: int
    audio_path: Path | None = None
    status: PlaybackStatus | None = field(
        default=None,
        compare=False,
        repr=False,
    )


class PlaybackQueue:
    """A FIFO queue with sequential preparation and playback for one guild."""

    def __init__(
        self,
        player: Callable[[PlaybackItem], Awaitable[None]],
        idle_timeout: float | None = 300.0,
        prepare: Callable[[PlaybackItem], Awaitable[PlaybackItem]] | None = None,
        max_queue_size: int = DEFAULT_QUEUE_MAX_SIZE,
    ):
        if max_queue_size < 1:
            raise ValueError("max_queue_size must be positive.")
        self.queue: asyncio.Queue[PlaybackItem] = asyncio.Queue(
            maxsize=max_queue_size,
        )
        self._audio_queue: asyncio.Queue[PlaybackItem] = asyncio.Queue(
            maxsize=max_queue_size,
        )
        self._player = player
        self._prepare = prepare or self._identity
        self._idle_timeout = idle_timeout
        self._synthesis_worker: asyncio.Task[None] | None = None
        self._playback_worker: asyncio.Task[None] | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._status_tasks: set[asyncio.Task[None]] = set()
        self._stopping = False

    @property
    def is_running(self) -> bool:
        return any(
            worker is not None and not worker.done()
            for worker in (self._synthesis_worker, self._playback_worker)
        )

    @property
    def pending_count(self) -> int:
        return self.queue.qsize() + self._audio_queue.qsize()

    async def enqueue(self, item: PlaybackItem) -> bool:
        async with self._lifecycle_lock:
            if self._stopping:
                raise RuntimeError("Playback queue is stopping.")
            self._ensure_worker()
            try:
                self.queue.put_nowait(item)
            except asyncio.QueueFull:
                logger.warning(
                    "Playback queue is full; dropping item: %s",
                    item.text,
                )
                self._schedule_status(item.status, "mark_failed")
                return False
            return True

    async def wait_until_empty(self) -> None:
        await self.queue.join()
        await self._audio_queue.join()

    def _ensure_worker(self) -> None:
        if self._synthesis_worker is None or self._synthesis_worker.done():
            self._synthesis_worker = asyncio.create_task(self._run_synthesis())
        if self._playback_worker is None or self._playback_worker.done():
            self._playback_worker = asyncio.create_task(self._run_playback())

    @staticmethod
    async def _identity(item: PlaybackItem) -> PlaybackItem:
        return item

    def _schedule_status(
        self,
        status: PlaybackStatus | None,
        method_name: str,
    ) -> None:
        if status is None:
            return
        task = asyncio.create_task(
            self._notify_status(
                status,
                method_name,
            ),
        )
        self._status_tasks.add(task)
        task.add_done_callback(self._status_tasks.discard)

    @staticmethod
    async def _notify_status(
        status: PlaybackStatus,
        method_name: str,
    ) -> None:
        try:
            await getattr(status, method_name)()
        except discord.HTTPException:
            logger.warning(
                "Updating playback status failed.",
                exc_info=True,
            )

    async def _next_input(self) -> PlaybackItem | None:
        if self._idle_timeout is None:
            return await self.queue.get()

        try:
            return await asyncio.wait_for(
                self.queue.get(),
                timeout=self._idle_timeout,
            )
        except asyncio.TimeoutError:
            async with self._lifecycle_lock:
                if not self.queue.empty():
                    return self.queue.get_nowait()
                if self._synthesis_worker is asyncio.current_task():
                    self._synthesis_worker = None
                return None

    async def _next_audio(self) -> PlaybackItem | None:
        if self._idle_timeout is None:
            return await self._audio_queue.get()

        while True:
            try:
                return await asyncio.wait_for(
                    self._audio_queue.get(),
                    timeout=self._idle_timeout,
                )
            except asyncio.TimeoutError:
                async with self._lifecycle_lock:
                    if not self._audio_queue.empty():
                        return self._audio_queue.get_nowait()
                    synthesis_worker = self._synthesis_worker
                    if (
                        synthesis_worker is not None
                        and not synthesis_worker.done()
                    ) or not self.queue.empty():
                        continue
                    if self._playback_worker is asyncio.current_task():
                        self._playback_worker = None
                    return None

    async def _run_synthesis(self) -> None:
        try:
            while True:
                item = await self._next_input()
                if item is None:
                    return

                try:
                    prepared_item = await self._prepare(item)
                    await self._audio_queue.put(prepared_item)
                except asyncio.CancelledError:
                    self._schedule_status(item.status, "mark_failed")
                    raise
                except Exception:
                    logger.exception("Preparing playback item failed: %s", item.text)
                    self._schedule_status(item.status, "mark_failed")
                finally:
                    self.queue.task_done()
        finally:
            if self._synthesis_worker is asyncio.current_task():
                self._synthesis_worker = None

    async def _run_playback(self) -> None:
        try:
            while True:
                item = await self._next_audio()
                if item is None:
                    return

                try:
                    self._schedule_status(item.status, "mark_started")
                    await self._player(item)
                except asyncio.CancelledError:
                    self._schedule_status(item.status, "mark_failed")
                    raise
                except Exception:
                    logger.exception("Playback item failed: %s", item.text)
                    self._schedule_status(item.status, "mark_failed")
                else:
                    self._schedule_status(item.status, "mark_completed")
                finally:
                    self._audio_queue.task_done()
        finally:
            if self._playback_worker is asyncio.current_task():
                self._playback_worker = None

    async def _cancel_workers(
        self,
        workers: list[asyncio.Task[None]],
    ) -> None:
        current = asyncio.current_task()
        active_workers = [worker for worker in workers if worker is not current]
        for worker in active_workers:
            worker.cancel()
        for worker in active_workers:
            try:
                await worker
            except asyncio.CancelledError:
                pass

    async def _drain(self, queue: asyncio.Queue[PlaybackItem]) -> None:
        while True:
            try:
                item = queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            else:
                self._schedule_status(item.status, "mark_failed")
                queue.task_done()

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            self._stopping = True
            workers = [
                worker
                for worker in (self._synthesis_worker, self._playback_worker)
                if worker is not None
            ]
        await self._cancel_workers(workers)
        async with self._lifecycle_lock:
            self._synthesis_worker = None
            self._playback_worker = None
            await self._drain(self.queue)
            await self._drain(self._audio_queue)
            self._stopping = False


async def play_voice_file(voice_client: discord.VoiceClient, path: Path) -> None:
    """Play a WAV file and await Discord's completion callback."""
    if not voice_client.is_connected():
        raise RuntimeError("Voice client is not connected.")

    loop = asyncio.get_running_loop()
    finished: asyncio.Future[None] = loop.create_future()

    def on_finished(error: Exception | None) -> None:
        def complete() -> None:
            if finished.done():
                return
            if error is None:
                finished.set_result(None)
            else:
                finished.set_exception(error)

        loop.call_soon_threadsafe(complete)

    source = discord.FFmpegPCMAudio(source=str(path))
    try:
        voice_client.play(source, after=on_finished)
    except Exception:
        source.cleanup()
        raise
    await finished
