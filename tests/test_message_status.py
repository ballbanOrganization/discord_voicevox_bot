import asyncio
from types import SimpleNamespace

from app.message_status import (
    FAILED_REACTION,
    PLAYING_REACTION,
    MessagePlaybackStatus,
)
from app.playback import PlaybackItem, PlaybackQueue


class RecordingMessage:
    id = 123

    def __init__(self):
        self.reactions = []

    async def add_reaction(self, reaction):
        self.reactions.append(("add", reaction))

    async def remove_reaction(self, reaction, user):
        self.reactions.append(("remove", reaction, user))


def test_message_status_adds_playing_reaction_until_completion():
    async def scenario():
        message = RecordingMessage()
        bot_user = SimpleNamespace(id=999)
        status = MessagePlaybackStatus(message, bot_user)

        await status.mark_started()
        await status.mark_completed()

        assert message.reactions == [
            ("add", PLAYING_REACTION),
            ("remove", PLAYING_REACTION, bot_user),
        ]

    asyncio.run(scenario())


def test_message_status_marks_failed_playback():
    async def scenario():
        message = RecordingMessage()
        bot_user = SimpleNamespace(id=999)
        status = MessagePlaybackStatus(message, bot_user)

        await status.mark_started()
        await status.mark_failed()

        assert message.reactions[-2:] == [
            ("add", FAILED_REACTION),
            ("remove", PLAYING_REACTION, bot_user),
        ]

    asyncio.run(scenario())


def test_short_message_only_adds_reaction_when_playback_fails():
    async def scenario():
        message = RecordingMessage()
        status = MessagePlaybackStatus(
            message,
            SimpleNamespace(id=999),
            show_playing_reaction=False,
        )

        await status.mark_started()
        await status.mark_failed()

        assert message.reactions == [
            ("add", FAILED_REACTION),
        ]

    asyncio.run(scenario())


def test_playback_queue_updates_status_at_lifecycle_boundaries():
    async def scenario():
        status_events = []

        class Status:
            async def mark_started(self):
                status_events.append("started")

            async def mark_completed(self):
                status_events.append("completed")

            async def mark_failed(self):
                status_events.append("failed")

        async def player(item):
            await asyncio.sleep(0)
            status_events.append("playing")

        queue = PlaybackQueue(player, idle_timeout=0.05)
        await queue.enqueue(
            PlaybackItem("hello", 1, status=Status()),
        )
        await queue.wait_until_empty()
        await queue.stop()

        assert status_events == ["started", "playing", "completed"]

    asyncio.run(scenario())


def test_playback_queue_marks_preparation_failure():
    async def scenario():
        status_events = []

        class Status:
            async def mark_failed(self):
                status_events.append("failed")

        async def prepare(_item):
            raise RuntimeError("preparation failed")

        async def player(_item):
            status_events.append("playing")

        queue = PlaybackQueue(
            player,
            idle_timeout=0.05,
            prepare=prepare,
        )
        await queue.enqueue(
            PlaybackItem("hello", 1, status=Status()),
        )
        await queue.wait_until_empty()
        await queue.stop()

        assert status_events == ["failed"]
        assert "playing" not in status_events

    asyncio.run(scenario())


def test_playback_continues_while_reaction_update_is_waiting():
    async def scenario():
        reaction_started = asyncio.Event()
        release_reaction = asyncio.Event()
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        second_started = asyncio.Event()
        played_count = 0

        class Message:
            id = 123

            async def add_reaction(self, reaction):
                if reaction == PLAYING_REACTION:
                    reaction_started.set()
                    await release_reaction.wait()

            async def remove_reaction(self, _reaction, _user):
                pass

        async def player(_item):
            nonlocal played_count
            played_count += 1
            if played_count == 1:
                first_started.set()
                await release_first.wait()
            else:
                second_started.set()

        status = MessagePlaybackStatus(
            Message(),
            SimpleNamespace(id=999),
        )
        queue = PlaybackQueue(player, idle_timeout=0.05)
        await queue.enqueue(PlaybackItem("first", 1, status=status))
        await asyncio.wait_for(first_started.wait(), timeout=1)
        await queue.enqueue(PlaybackItem("second", 1))
        await asyncio.wait_for(reaction_started.wait(), timeout=1)

        release_first.set()
        await asyncio.wait_for(second_started.wait(), timeout=1)

        release_reaction.set()
        await queue.wait_until_empty()
        await queue.stop()

    asyncio.run(scenario())
