from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .playback import PlaybackItem, PlaybackQueue


@dataclass
class GuildState:
    guild_id: int
    voice_client: Any
    text_channel_id: int
    playback: PlaybackQueue


class GuildRuntimeManager:
    def __init__(
        self,
        player: Callable[[GuildState, PlaybackItem], Awaitable[None]],
        idle_timeout: float | None = 300.0,
    ):
        self._player = player
        self._idle_timeout = idle_timeout
        self._states: dict[int, GuildState] = {}

    def get(self, guild_id: int) -> GuildState | None:
        return self._states.get(int(guild_id))

    async def configure(
        self,
        guild_id: int,
        voice_client: Any,
        text_channel_id: int,
    ) -> GuildState:
        normalized_id = int(guild_id)
        state = self._states.get(normalized_id)
        if state is None:
            state = GuildState(
                guild_id=normalized_id,
                voice_client=voice_client,
                text_channel_id=int(text_channel_id),
                playback=None,  # type: ignore[arg-type]
            )
            state.playback = PlaybackQueue(
                lambda item: self._player(state, item),
                idle_timeout=self._idle_timeout,
            )
            self._states[normalized_id] = state
        else:
            state.voice_client = voice_client
            state.text_channel_id = int(text_channel_id)
        return state

    async def enqueue(self, guild_id: int, item: PlaybackItem) -> None:
        state = self._states.get(int(guild_id))
        if state is None:
            raise KeyError(f"Guild {guild_id} is not configured.")
        await state.playback.enqueue(item)

    async def disconnect(self, guild_id: int, voice_client: Any = None) -> None:
        state = self._states.pop(int(guild_id), None)
        target = voice_client if voice_client is not None else (
            state.voice_client if state is not None else None
        )
        if target is None:
            return

        is_playing = getattr(target, "is_playing", None)
        if callable(is_playing) and is_playing():
            target.stop()
        if state is not None:
            await state.playback.stop()

        disconnect = getattr(target, "disconnect", None)
        if callable(disconnect):
            await disconnect(force=True)
            return

        cleanup = getattr(target, "cleanup", None)
        if callable(cleanup):
            cleanup()

    async def stop_all(self) -> None:
        for guild_id in list(self._states):
            await self.disconnect(guild_id)
