import asyncio

from app.playback import PlaybackItem, PlaybackQueue
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

    asyncio.run(scenario())
