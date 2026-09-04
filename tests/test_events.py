import asyncio
from types import SimpleNamespace

from app.events import handle_message, handle_voice_state_update
from app.playback import PlaybackItem


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
