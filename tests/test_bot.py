import asyncio

import discord

from app.bot import VoiceVoxBot, _disconnect_remaining_voice_clients
from app.config import Settings


def test_disconnect_remaining_voice_clients_only_disconnects_connected_clients():
    async def scenario():
        class VoiceClient:
            def __init__(self, connected):
                self.connected = connected
                self.disconnect_calls = []

            def is_connected(self):
                return self.connected

            async def disconnect(self, force=False):
                self.disconnect_calls.append(force)
                self.connected = False

        connected = VoiceClient(True)
        disconnected = VoiceClient(False)

        await _disconnect_remaining_voice_clients([connected, disconnected])

        assert connected.disconnect_calls == [True]
        assert disconnected.disconnect_calls == []

    asyncio.run(scenario())


def test_disconnect_remaining_voice_clients_continues_after_failure():
    async def scenario():
        class VoiceClient:
            def __init__(self, should_fail):
                self.should_fail = should_fail
                self.disconnect_calls = []

            def is_connected(self):
                return True

            async def disconnect(self, force=False):
                self.disconnect_calls.append(force)
                if self.should_fail:
                    raise RuntimeError("disconnect failed")

        failed = VoiceClient(True)
        healthy = VoiceClient(False)

        await _disconnect_remaining_voice_clients([failed, healthy])

        assert failed.disconnect_calls == [True]
        assert healthy.disconnect_calls == [True]

    asyncio.run(scenario())


def test_bot_close_finishes_resource_cleanup_after_runtime_failure(monkeypatch):
    async def scenario():
        events = []

        class Runtime:
            async def stop_all(self):
                events.append("runtime")
                raise RuntimeError("runtime shutdown failed")

        class VoiceVox:
            async def close(self):
                events.append("voicevox")

        async def close_client(_self):
            events.append("discord")

        monkeypatch.setattr(discord.Client, "close", close_client)
        bot = VoiceVoxBot(
            Settings(),
            user_data=object(),
            voicevox=VoiceVox(),
            speech=object(),
        )
        bot.runtimes = Runtime()

        try:
            await bot.close()
        except RuntimeError:
            pass
        else:
            raise AssertionError("runtime shutdown failure should propagate")

        assert events == ["runtime", "voicevox", "discord"]

    asyncio.run(scenario())
