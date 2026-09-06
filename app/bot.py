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
from .voicevox import VoiceVox, VoiceVoxError

logger = logging.getLogger(__name__)

SPEAKER_LOAD_ATTEMPTS = 3
SPEAKER_LOAD_RETRY_DELAY = 5.0


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
        self._idle_voice_since: dict[int, float] = {}
        self.tree.on_error = self._on_app_command_error
        register_commands(self)

    async def _load_speakers_with_retry(self) -> bool:
        for attempt in range(1, SPEAKER_LOAD_ATTEMPTS + 1):
            try:
                await self.voicevox.load_speakers()
            except VoiceVoxError as error:
                if attempt == SPEAKER_LOAD_ATTEMPTS:
                    logger.warning(
                        "VOICEVOX speakers could not be loaded after %d attempts: %s",
                        attempt,
                        error,
                    )
                    return False
                logger.warning(
                    "VOICEVOX speaker loading failed (attempt %d/%d): %s",
                    attempt,
                    SPEAKER_LOAD_ATTEMPTS,
                    error,
                )
                await asyncio.sleep(SPEAKER_LOAD_RETRY_DELAY)
            else:
                return True
        return False

    async def setup_hook(self) -> None:
        await self._load_speakers_with_retry()
        await self.tree.sync()

    async def _on_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        original = getattr(error, "original", error)
        if isinstance(original, discord.Forbidden):
            response_text = (
                "VOICEVOXボットに必要な権限がないのだ。"
                "ボイスチャンネルの「接続」と「発言」権限を確認するのだ。"
            )
        elif isinstance(original, discord.ClientException):
            response_text = (
                "ボイスチャンネルに接続できない状態なのだ。"
                "既存の接続を確認して、もう一度試すのだ。"
            )
        else:
            logger.error(
                "Unhandled application command error.",
                exc_info=(
                    type(original),
                    original,
                    getattr(original, "__traceback__", None),
                ),
            )
            response_text = "コマンドの実行中にエラーが発生したのだ。ログを確認するのだ。"

        try:
            if interaction.response.is_done():
                await interaction.followup.send(response_text, ephemeral=True)
            else:
                await interaction.response.send_message(response_text, ephemeral=True)
        except discord.HTTPException:
            logger.exception("Could not send application command error response.")

    async def on_ready(self) -> None:
        logger.info("We have logged in as %s", self.user)
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def _cleanup_loop(self) -> None:
        while not self.is_closed():
            await asyncio.sleep(self.settings.cleanup_interval)
            removed = await asyncio.to_thread(self.audio_cache.cleanup_expired)
            if removed:
                logger.info("Removed %d expired audio cache files.", removed)
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
        result = await self.speech.synthesize(item.text, item.user_id)
        return replace(
            item,
            audio_path=result.path,
            speaker_name=result.speaker_name,
        )

    async def _play_item(self, state: GuildState, item: PlaybackItem) -> None:
        if item.audio_path is None:
            raise RuntimeError("Playback item has not been prepared.")
        await play_voice_file(state.voice_client, item.audio_path)
        speaker_name = item.speaker_name
        if speaker_name is None:
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
