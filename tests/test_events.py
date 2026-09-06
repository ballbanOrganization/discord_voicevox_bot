import asyncio
from types import SimpleNamespace

from app.events import (
    cleanup_idle_voice_clients,
    handle_message,
    handle_voice_state_update,
)
from app.message_status import (
    PLAYING_REACTION,
    PLAYING_REACTION_MIN_LENGTH,
)
from app.playback import PlaybackItem
from app.runtime import GuildRuntimeManager


class RecordingRuntime:
    def __init__(self):
        self.items = []

    def get(self, guild_id):
        return SimpleNamespace(
            voice_client=SimpleNamespace(is_connected=lambda: True), text_channel_id=10
        )

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
            (7, PlaybackItem("hello わらわら。", 1)),
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
                    sound=3 if user_id == 0 else 107,
                    speed_scale=1.2 if user_id == 0 else 0.8,
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
        assert [item.speaker_id for _, item in runtime.items] == [3, 3]
        assert [item.speed_scale for _, item in runtime.items] == [1.2, 1.2]

    asyncio.run(scenario())


def test_voice_state_move_into_and_out_of_bot_channel_is_announced():
    async def scenario():
        items = []
        bot_channel = SimpleNamespace(id=20)
        guild = SimpleNamespace(id=7)

        class Runtime:
            def get(self, _guild_id):
                return SimpleNamespace(
                    voice_client=SimpleNamespace(
                        channel=bot_channel,
                        is_connected=lambda: True,
                    )
                )

            async def enqueue(self, guild_id, item):
                items.append((guild_id, item.text))

        bot = SimpleNamespace(
            user=SimpleNamespace(id=999),
            runtimes=Runtime(),
            user_data=SimpleNamespace(
                get_user=lambda _user_id: SimpleNamespace(
                    entry_audio="custom entry",
                    exit_audio="custom exit",
                    sound=3,
                    speed_scale=1.2,
                )
            ),
        )
        member = SimpleNamespace(id=1, guild=guild, display_name="Member")

        await handle_voice_state_update(
            bot,
            member,
            SimpleNamespace(channel=SimpleNamespace(id=10)),
            SimpleNamespace(channel=bot_channel),
        )
        await handle_voice_state_update(
            bot,
            member,
            SimpleNamespace(channel=bot_channel),
            SimpleNamespace(channel=SimpleNamespace(id=30)),
        )

        assert [text for _, text in items] == ["custom entry", "custom exit"]

    asyncio.run(scenario())


def test_idle_cleanup_waits_and_ignores_other_bots():
    async def scenario():
        disconnected = []

        class Guild:
            id = 7

            @staticmethod
            def get_member(user_id):
                return SimpleNamespace(bot=user_id == 1000)

        guild = Guild()
        channel = SimpleNamespace(
            guild=guild,
            voice_states={999: object(), 1000: object()},
        )
        voice_client = SimpleNamespace(channel=channel, guild=guild)

        class Runtime:
            async def disconnect(self, guild_id, client):
                disconnected.append((guild_id, client))

        bot = SimpleNamespace(
            user=SimpleNamespace(id=999),
            settings=SimpleNamespace(queue_idle_timeout=300.0),
            voice_clients=[voice_client],
            runtimes=Runtime(),
        )

        await cleanup_idle_voice_clients(bot, now=100.0)
        await cleanup_idle_voice_clients(bot, now=399.0)
        assert disconnected == []

        await cleanup_idle_voice_clients(bot, now=400.0)
        assert disconnected == [(7, voice_client)]

    asyncio.run(scenario())
