import asyncio
from types import SimpleNamespace

from app.events import handle_message, handle_voice_state_update
from app.message_status import (
    PLAYING_REACTION_MIN_LENGTH,
    PLAYING_REACTION,
)
from app.playback import PlaybackItem
from app.runtime import GuildRuntimeManager


class RecordingRuntime:
    def __init__(self):
        self.items = []

    def get(self, guild_id):
        return SimpleNamespace(voice_client=SimpleNamespace(is_connected=lambda: True),
                               text_channel_id=10)

    async def enqueue(self, guild_id, item):
        self.items.append((guild_id, item))


def test_message_normalization_does_not_mutate_discord_message():
    async def scenario():
        bot = SimpleNamespace(
            user=SimpleNamespace(id=999),
            runtimes=RecordingRuntime(),
        )
        message = SimpleNamespace(
            author=SimpleNamespace(id=1),
            guild=SimpleNamespace(id=7),
            channel=SimpleNamespace(id=10),
            content="hello wwwww",
            attachments=[],
        )

        await handle_message(bot, message)

        assert message.content == "hello wwwww"
        assert bot.runtimes.items == [
            (7, PlaybackItem("hello わらわら", 1)),
        ]

    asyncio.run(scenario())


def test_only_long_messages_get_playback_reaction():
    async def scenario():
        class Message:
            id = 123

            def __init__(self):
                self.reactions = []

            async def add_reaction(self, reaction):
                self.reactions.append(("add", reaction))

            async def remove_reaction(self, reaction, user):
                self.reactions.append(("remove", reaction, user))

        class VoiceClient:
            def is_connected(self):
                return True

        first_started = asyncio.Event()
        release_first = asyncio.Event()
        played_count = 0

        async def player(_state, _item):
            nonlocal played_count
            played_count += 1
            if played_count == 1:
                first_started.set()
                await release_first.wait()

        runtime = GuildRuntimeManager(player, idle_timeout=0.05)
        state = await runtime.configure(7, VoiceClient(), 10)
        bot_user = SimpleNamespace(id=999)
        bot = SimpleNamespace(user=bot_user, runtimes=runtime)
        message = Message()
        message.author = SimpleNamespace(id=1)
        message.guild = SimpleNamespace(id=7)
        message.channel = SimpleNamespace(id=10)
        message.content = "a" * (PLAYING_REACTION_MIN_LENGTH + 1)
        message.attachments = []

        await handle_message(bot, message)
        await asyncio.wait_for(first_started.wait(), timeout=1)
        await asyncio.sleep(0.01)
        assert message.reactions == [
            ("add", PLAYING_REACTION),
        ]

        release_first.set()
        await state.playback.wait_until_empty()
        await state.playback.stop()
        await asyncio.sleep(0.01)

        assert message.reactions == [
            ("add", PLAYING_REACTION),
            ("remove", PLAYING_REACTION, bot_user),
        ]

        short_message = Message()
        short_message.author = SimpleNamespace(id=2)
        short_message.guild = SimpleNamespace(id=7)
        short_message.channel = SimpleNamespace(id=10)
        short_message.content = "short"
        short_message.attachments = []

        await handle_message(bot, short_message)
        await state.playback.wait_until_empty()
        await asyncio.sleep(0.01)
        assert short_message.reactions == []

    asyncio.run(scenario())


def test_command_message_with_attachment_is_ignored():
    async def scenario():
        runtime = RecordingRuntime()
        bot = SimpleNamespace(
            user=SimpleNamespace(id=999),
            runtimes=runtime,
        )
        message = SimpleNamespace(
            author=SimpleNamespace(id=1),
            guild=SimpleNamespace(id=7),
            channel=SimpleNamespace(id=10),
            content="/help",
            attachments=[SimpleNamespace(content_type="image/png")],
        )

        await handle_message(bot, message)

        assert runtime.items == []

    asyncio.run(scenario())


def test_bot_leaving_voice_channel_cleans_guild_runtime():
    async def scenario():
        disconnected = []
        voice_client = SimpleNamespace()
        state = SimpleNamespace(voice_client=voice_client)

        class Runtime:
            def get(self, guild_id):
                return state

            async def disconnect(self, guild_id, target):
                disconnected.append((guild_id, target))

        bot = SimpleNamespace(
            user=SimpleNamespace(id=999),
            runtimes=Runtime(),
        )
        member = SimpleNamespace(
            id=999,
            guild=SimpleNamespace(id=7),
        )

        await handle_voice_state_update(
            bot,
            member,
            SimpleNamespace(channel=SimpleNamespace(id=20)),
            SimpleNamespace(channel=None),
        )

        assert disconnected == [(7, voice_client)]

    asyncio.run(scenario())


def test_voice_state_uses_entry_audio_for_join_and_exit_audio_for_leave():
    async def scenario():
        runtime = RecordingRuntime()
        bot = SimpleNamespace(
            user=SimpleNamespace(id=999),
            runtimes=runtime,
            user_data=SimpleNamespace(
                get_user=lambda user_id: SimpleNamespace(
                    entry_audio="custom entry",
                    exit_audio="custom exit",
                )
            ),
        )
        guild = SimpleNamespace(id=7)
        member = SimpleNamespace(id=1, guild=guild, display_name="Member")
        channel = SimpleNamespace(id=20)
        runtime.get = lambda guild_id: SimpleNamespace(
            voice_client=SimpleNamespace(
                channel=channel,
                is_connected=lambda: True,
            ),
            text_channel_id=10,
        )

        await handle_voice_state_update(
            bot,
            member,
            SimpleNamespace(channel=None),
            SimpleNamespace(channel=channel),
        )
        await handle_voice_state_update(
            bot,
            member,
            SimpleNamespace(channel=channel),
            SimpleNamespace(channel=None),
        )

        assert [item.text for _, item in runtime.items] == [
            "custom entry",
            "custom exit",
        ]

    asyncio.run(scenario())
