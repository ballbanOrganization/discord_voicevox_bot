import asyncio
import logging
from dataclasses import replace

import discord
from discord import app_commands

from .audio_cache import AudioCache
from .commands import register_commands
from .config import Settings
from .events import (
    cleanup_idle_voice_clients,
    handle_message,
    handle_voice_state_update,
)
from .playback import PlaybackItem, play_voice_file
from .runtime import GuildRuntimeManager, GuildState
from .speech import SpeechService
from .user_repository import UserRepository
from .voicevox import VoiceVox

logger = logging.getLogger(__name__)


async def _disconnect_remaining_voice_clients(
    voice_clients: list[discord.VoiceClient],
) -> None:
    for voice_client in list(voice_clients):
        try:
            if voice_client.is_connected():
                await voice_client.disconnect(force=True)
        except Exception:
            logger.exception("Failed to disconnect voice client during shutdown.")


class VoiceVoxBot(discord.Client):
    def __init__(
        self,
        settings: Settings,
        *,
        user_data: UserRepository | None = None,
        voicevox: VoiceVox | None = None,
        speech: SpeechService | None = None,
    ):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)

        self.settings = settings
        self.tree = app_commands.CommandTree(self)
        self.user_data = user_data or UserRepository(settings.data_path)
        self.voicevox = voicevox or VoiceVox(
            url=settings.voicevox_url,
            timeout=settings.voicevox_timeout,
        )
        self.audio_cache = AudioCache(settings.audio_path)
        self.speech = speech or SpeechService(
            self.voicevox,
            self.user_data,
            self.audio_cache,
        )
        self.runtimes = GuildRuntimeManager(
            self._play_item,
            idle_timeout=settings.queue_idle_timeout,
            preparer=self._prepare_item,
        )
        self._cleanup_task: asyncio.Task[None] | None = None
        register_commands(self)

    async def setup_hook(self) -> None:
        await self.voicevox.load_speakers()
        await self.tree.sync()

    async def on_ready(self) -> None:
        logger.info("We have logged in as %s", self.user)
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        while not self.is_closed():
            await asyncio.sleep(self.settings.cleanup_interval)
            await cleanup_idle_voice_clients(self)

    async def on_message(self, message: discord.Message) -> None:
        await handle_message(self, message)

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        await handle_voice_state_update(self, member, before, after)

    async def _prepare_item(
        self,
        _state: GuildState,
        item: PlaybackItem,
    ) -> PlaybackItem:
        path = await self.speech.audio_path(item.text, item.user_id)
        return replace(item, audio_path=path)

    async def _play_item(self, state: GuildState, item: PlaybackItem) -> None:
        if item.audio_path is None:
            raise RuntimeError("Playback item has not been prepared.")
        await play_voice_file(state.voice_client, item.audio_path)
        user = self.user_data.get_user(item.user_id)
        speaker_name = self.voicevox.get_speaker_name(user.sound)
        logger.info("Speaker: %s, Text: %s", speaker_name, item.text)

    async def close(self) -> None:
        if self._cleanup_task is not None and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        try:
            await self.runtimes.stop_all()
        finally:
            try:
                await _disconnect_remaining_voice_clients(self.voice_clients)
            finally:
                try:
                    await self.voicevox.close()
                finally:
                    await super().close()


def create_bot(settings: Settings | None = None) -> VoiceVoxBot:
    return VoiceVoxBot(settings or Settings.from_env(require_token=False))
