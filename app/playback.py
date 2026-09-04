import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import discord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlaybackItem:
    text: str
    user_id: int


class PlaybackQueue:
    """A FIFO queue with one worker that serializes playback for one guild."""

    def __init__(
        self,
        player: Callable[[PlaybackItem], Awaitable[None]],
        idle_timeout: float | None = 300.0,
    ):
        self.queue: asyncio.Queue[PlaybackItem] = asyncio.Queue()
        self._player = player
        self._idle_timeout = idle_timeout
        self._worker: asyncio.Task[None] | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._stopping = False

    @property
    def is_running(self) -> bool:
        return self._worker is not None and not self._worker.done()

    @property
    def pending_count(self) -> int:
        return self.queue.qsize()

    async def enqueue(self, item: PlaybackItem) -> None:
        async with self._lifecycle_lock:
            if self._stopping:
                raise RuntimeError("Playback queue is stopping.")
            self._ensure_worker()
            self.queue.put_nowait(item)

    async def wait_until_empty(self) -> None:
        await self.queue.join()

    def _ensure_worker(self) -> None:
        if self._worker is None or self._worker.done():
            self._worker = asyncio.create_task(self._run())

    async def _next_item(self) -> PlaybackItem | None:
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
                if self._worker is asyncio.current_task():
                    self._worker = None
                return None

    async def _run(self) -> None:
        try:
            while True:
                item = await self._next_item()
                if item is None:
                    return

                try:
                    await self._player(item)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Playback item failed: %s", item.text)
                finally:
                    self.queue.task_done()
        finally:
            async with self._lifecycle_lock:
                if self._worker is asyncio.current_task():
                    self._worker = None

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            self._stopping = True
            worker = self._worker
        if worker is not None and worker is not asyncio.current_task():
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
        async with self._lifecycle_lock:
            self._worker = None
            while True:
                try:
                    self.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                else:
                    self.queue.task_done()
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
