import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import discord

from .playback import PlaybackItem, PlaybackQueue

logger = logging.getLogger(__name__)


@dataclass
class GuildState:
    guild_id: int
    voice_client: discord.VoiceClient
    text_channel_id: int
    playback: PlaybackQueue


class GuildRuntimeManager:
    def __init__(
        self,
        player: Callable[[GuildState, PlaybackItem], Awaitable[None]],
        idle_timeout: float | None = 300.0,
        preparer: Callable[
            [GuildState, PlaybackItem],
            Awaitable[PlaybackItem],
        ]
        | None = None,
    ):
        self._player = player
        self._idle_timeout = idle_timeout
        self._preparer = preparer
        self._states: dict[int, GuildState] = {}

    def get(self, guild_id: int) -> GuildState | None:
        return self._states.get(int(guild_id))

    async def configure(
        self,
        guild_id: int,
        voice_client: discord.VoiceClient,
        text_channel_id: int,
    ) -> GuildState:
        normalized_id = int(guild_id)
        state = self._states.get(normalized_id)
        if state is not None and state.voice_client is not voice_client:
            await self.disconnect(normalized_id, state.voice_client)
            state = None
        if state is None:
            state = GuildState(
                guild_id=normalized_id,
                voice_client=voice_client,
                text_channel_id=int(text_channel_id),
                playback=None,  # type: ignore[arg-type]
            )
            if self._preparer is None:
                state.playback = PlaybackQueue(
                    lambda item: self._player(state, item),
                    idle_timeout=self._idle_timeout,
                )
            else:
                preparer = self._preparer

                async def prepare(item: PlaybackItem) -> PlaybackItem:
                    return await preparer(state, item)

                state.playback = PlaybackQueue(
                    lambda item: self._player(state, item),
                    idle_timeout=self._idle_timeout,
                    prepare=prepare,
                )
            self._states[normalized_id] = state
        else:
            state.text_channel_id = int(text_channel_id)
        return state

    async def enqueue(self, guild_id: int, item: PlaybackItem) -> None:
        state = self._states.get(int(guild_id))
        if state is None:
            raise KeyError(f"Guild {guild_id} is not configured.")
        await state.playback.enqueue(item)

    async def disconnect(
        self,
        guild_id: int,
        voice_client: discord.VoiceClient | None = None,
    ) -> None:
        normalized_id = int(guild_id)
        state = self._states.get(normalized_id)
        target = (
            voice_client
            if voice_client is not None
            else (state.voice_client if state is not None else None)
        )
        if target is None:
            return

        if target.is_playing():
            target.stop()
        if state is not None and target is state.voice_client:
            self._states.pop(normalized_id, None)
            await state.playback.stop()

        await target.disconnect(force=True)

    async def stop_all(self) -> None:
        for guild_id in list(self._states):
            try:
                await self.disconnect(guild_id)
            except Exception:
                logger.exception(
                    "Failed to disconnect guild runtime during shutdown: %s",
                    guild_id,
                )
