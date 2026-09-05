import asyncio
from types import SimpleNamespace

from app.commands import register_commands


class _CommandTree:
    def __init__(self):
        self.commands = {}

    def command(self, **kwargs):
        def decorate(callback):
            self.commands[kwargs["name"]] = callback
            return callback

        return decorate


class _Response:
    def __init__(self):
        self.messages = []

    async def send_message(self, content, **kwargs):
        self.messages.append((content, kwargs))


class _UserData:
    def get_user(self, _user_id):
        raise AssertionError("invalid command input must not access user data")

    def save_user(self, _user):
        raise AssertionError("invalid command input must not save user data")


class _VoiceVox:
    speaker_dict = {"ずんだもん": {"ノーマル": 3}}


class _Bot:
    def __init__(self):
        self.tree = _CommandTree()
        self.voicevox = _VoiceVox()
        self.user_data = _UserData()
        self.voice_clients = []


def _commands():
    bot = _Bot()
    register_commands(bot)
    return bot.tree.commands


def test_set_voice_rejects_unknown_speaker_and_style():
    async def scenario():
        command = _commands()["set_voice"]
        interaction = SimpleNamespace(
            response=_Response(),
            user=SimpleNamespace(id=1),
        )

        await command(interaction, "存在しない話者")
        assert interaction.response.messages == [
            ("指定した音声またはスタイルが見つからないのだ。", {})
        ]

        interaction.response.messages.clear()
        await command(interaction, "ずんだもん", 999)
        assert interaction.response.messages == [
            ("指定した音声またはスタイルが見つからないのだ。", {})
        ]

    asyncio.run(scenario())


def test_join_rejects_nonexistent_text_channel_values():
    async def scenario():
        interaction = SimpleNamespace(
            guild=SimpleNamespace(
                text_channels=[SimpleNamespace(id=10)],
                voice_client=None,
            ),
            user=SimpleNamespace(
                voice=SimpleNamespace(channel=SimpleNamespace(id=20)),
            ),
            channel=SimpleNamespace(id=10),
            response=_Response(),
        )
        bot = _Bot()
        register_commands(bot)
        command = bot.tree.commands["join"]

        for value in ("not-a-channel-id", "999"):
            interaction.response.messages.clear()
            await command(interaction, value)
            assert interaction.response.messages == [
                ("指定した文字チャンネルが見つからないのだ。", {})
            ]

    asyncio.run(scenario())
