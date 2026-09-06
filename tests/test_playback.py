import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.playback import (
    DEFAULT_QUEUE_MAX_SIZE,
    PlaybackItem,
    PlaybackQueue,
    play_voice_file,
)

from app.runtime import GuildRuntimeManager


def test_playback_queue_preserves_fifo_order_and_stops():
    async def scenario():
        played = []

        async def player(item):
            await asyncio.sleep(0.001)
            played.append(item.text)

        queue = PlaybackQueue(player, idle_timeout=0.05)
        for text in ("first", "second", "third"):
            await queue.enqueue(PlaybackItem(text, 1))
        await queue.wait_until_empty()

        assert played == ["first", "second", "third"]
        await queue.stop()
        assert not queue.is_running

    asyncio.run(scenario())


def test_playback_queue_rejects_items_after_reaching_capacity():
    async def scenario():
        preparation_started = asyncio.Event()
        release_preparation = asyncio.Event()

        async def prepare(item):
            if item.text == "first":
                preparation_started.set()
                await release_preparation.wait()
            return item

        async def player(_item):
            await asyncio.sleep(0)

        queue = PlaybackQueue(
            player,
            idle_timeout=None,
            prepare=prepare,
        )
        assert await queue.enqueue(PlaybackItem("first", 1))
        await asyncio.wait_for(preparation_started.wait(), timeout=1)

        for index in range(DEFAULT_QUEUE_MAX_SIZE - 1):
            assert await queue.enqueue(PlaybackItem(f"queued-{index}", 1))
        assert queue.pending_count == DEFAULT_QUEUE_MAX_SIZE
        assert not await queue.enqueue(PlaybackItem("rejected", 1))
        assert queue.queue.maxsize == DEFAULT_QUEUE_MAX_SIZE
        assert queue._audio_queue.maxsize == DEFAULT_QUEUE_MAX_SIZE

        release_preparation.set()
        await asyncio.wait_for(queue.wait_until_empty(), timeout=1)
        assert queue.pending_count == 0
        await queue.stop()

    asyncio.run(scenario())


def test_enqueue_after_idle_worker_exits_starts_a_new_worker():
    async def scenario():
        played = []

        async def player(item):
            played.append(item.text)

        queue = PlaybackQueue(player, idle_timeout=0.01)
        await queue.enqueue(PlaybackItem("first", 1))
        await queue.wait_until_empty()
        await asyncio.sleep(0.03)

        await queue.enqueue(PlaybackItem("second", 1))
        await queue.wait_until_empty()
        await queue.stop()

        assert played == ["first", "second"]

    asyncio.run(scenario())


def test_playback_queue_prepares_next_item_while_previous_item_plays():
    async def scenario():
        preparing = []
        played = []
        first_started = asyncio.Event()
        second_prepared = asyncio.Event()
        release_first = asyncio.Event()

        async def prepare(item):
            preparing.append(item.text)
            if item.text == "second":
                second_prepared.set()
            return item

        async def player(item):
            if item.text == "first":
                first_started.set()
                await release_first.wait()
            played.append(item.text)

        queue = PlaybackQueue(
            player,
            idle_timeout=0.05,
            prepare=prepare,
        )
        await queue.enqueue(PlaybackItem("first", 1))
        await asyncio.wait_for(first_started.wait(), timeout=1)
        await queue.enqueue(PlaybackItem("second", 1))
        await asyncio.wait_for(second_prepared.wait(), timeout=1)

        assert preparing == ["first", "second"]
        assert played == []

        release_first.set()
        await queue.wait_until_empty()
        await queue.stop()

        assert played == ["first", "second"]

    asyncio.run(scenario())


def test_playback_queue_waits_for_synthesis_before_idle_shutdown():
    async def scenario():
        preparing = asyncio.Event()
        release_preparation = asyncio.Event()
        played = []

        async def prepare(item):
            preparing.set()
            await release_preparation.wait()
            return item

        async def player(item):
            played.append(item.text)

        queue = PlaybackQueue(
            player,
            idle_timeout=0.01,
            prepare=prepare,
        )
        await queue.enqueue(PlaybackItem("slow", 1))
        await asyncio.wait_for(preparing.wait(), timeout=1)
        await asyncio.sleep(0.03)

        release_preparation.set()
        await asyncio.wait_for(queue.wait_until_empty(), timeout=1)
        await queue.stop()

        assert played == ["slow"]

    asyncio.run(scenario())


def test_guild_runtime_disconnect_cleans_state_and_worker():
    async def scenario():
        disconnected = []

        class VoiceClient:
            channel = object()

            def is_connected(self):
                return True

            def is_playing(self):
                return False

            async def disconnect(self, force=False):
                disconnected.append(force)

        async def player(state, item):
            await asyncio.sleep(0)

        manager = GuildRuntimeManager(player, idle_timeout=1)
        state = await manager.configure(123, VoiceClient(), 456)
        await manager.enqueue(123, PlaybackItem("hello", 1))
        await state.playback.wait_until_empty()

        await manager.disconnect(123)

        assert manager.get(123) is None
        assert disconnected == [True]
        assert not state.playback.is_running

    asyncio.run(scenario())


def test_guild_runtime_disconnects_stale_voice_client():
    async def scenario():
        disconnected = []

        class VoiceClient:
            channel = object()

            def is_connected(self):
                return False

            def is_playing(self):
                return False

            async def disconnect(self, force=False):
                disconnected.append(force)

        manager = GuildRuntimeManager(lambda state, item: asyncio.sleep(0))
        await manager.configure(123, VoiceClient(), 456)

        await manager.disconnect(123)

        assert disconnected == [True]


def test_guild_runtime_replaces_previous_voice_client():
    async def scenario():
        class VoiceClient:
            channel = object()

            def __init__(self):
                self.disconnected = []

            def is_connected(self):
                return True

            def is_playing(self):
                return False

            async def disconnect(self, force=False):
                self.disconnected.append(force)

        manager = GuildRuntimeManager(lambda state, item: asyncio.sleep(0))
        old_client = VoiceClient()
        new_client = VoiceClient()

        await manager.configure(123, old_client, 456)
        state = await manager.configure(123, new_client, 789)

        assert old_client.disconnected == [True]
        assert state.voice_client is new_client
        assert state.text_channel_id == 789

        await manager.disconnect(123)

    asyncio.run(scenario())


def test_guild_runtime_disconnect_keeps_active_state_for_different_client():
    async def scenario():
        class VoiceClient:
            channel = object()

            def __init__(self):
                self.disconnected = []

            def is_playing(self):
                return False

            def stop(self):
                raise AssertionError("inactive client should not be stopped")

            async def disconnect(self, force=False):
                self.disconnected.append(force)

        manager = GuildRuntimeManager(lambda state, item: asyncio.sleep(0))
        active_client = VoiceClient()
        stale_client = VoiceClient()
        state = await manager.configure(123, active_client, 456)

        await manager.disconnect(123, stale_client)

        assert manager.get(123) is state
        assert active_client.disconnected == []
        assert stale_client.disconnected == [True]

        await manager.disconnect(123)
        assert manager.get(123) is None

    asyncio.run(scenario())


def test_guild_runtime_stop_all_continues_after_disconnect_failure():
    async def scenario():
        class VoiceClient:
            channel = object()

            def __init__(self, should_fail):
                self.should_fail = should_fail
                self.disconnected = []

            def is_playing(self):
                return False

            async def disconnect(self, force=False):
                if self.should_fail:
                    raise RuntimeError("disconnect failed")
                self.disconnected.append(force)

        manager = GuildRuntimeManager(lambda state, item: asyncio.sleep(0))
        failed_client = VoiceClient(True)
        healthy_client = VoiceClient(False)
        await manager.configure(123, failed_client, 456)
        await manager.configure(456, healthy_client, 789)

        await manager.stop_all()

        assert healthy_client.disconnected == [True]
        assert manager.get(123) is None
        assert manager.get(456) is None

    asyncio.run(scenario())


def test_play_voice_file_stops_and_cleans_source_when_cancelled(monkeypatch):
    async def scenario():
        source = Mock()
        stop = Mock()
        monkeypatch.setattr(
            "app.playback.discord.FFmpegPCMAudio",
            lambda **_kwargs: source,
        )
        voice_client = SimpleNamespace(
            is_connected=lambda: True,
            play=lambda _source, after: None,
            is_playing=lambda: True,
            stop=stop,
        )
        task = asyncio.create_task(play_voice_file(voice_client, Path("sample.wav")))
        await asyncio.sleep(0)
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        stop.assert_called_once_with()
        source.cleanup.assert_called_once_with()

    asyncio.run(scenario())
