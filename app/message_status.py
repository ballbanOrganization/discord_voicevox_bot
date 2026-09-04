import asyncio
import logging

import discord

logger = logging.getLogger(__name__)

PLAYING_REACTION = "🔊"
FAILED_REACTION = "⚠️"
PLAYING_REACTION_MIN_LENGTH = 50


class MessagePlaybackStatus:
    def __init__(
        self,
        message: discord.Message,
        bot_user: discord.ClientUser,
        *,
        show_playing_reaction: bool = True,
    ):
        self._message = message
        self._bot_user = bot_user
        self._show_playing_reaction = show_playing_reaction
        self._current_reaction: str | None = None
        self._lock = asyncio.Lock()
        self._enabled = all(
            callable(getattr(message, method, None))
            for method in ("add_reaction", "remove_reaction")
        )

    async def mark_started(self) -> None:
        if not self._show_playing_reaction:
            return
        async with self._lock:
            await self._set_reaction(PLAYING_REACTION)

    async def mark_completed(self) -> None:
        if not self._show_playing_reaction:
            return
        async with self._lock:
            await self._clear_reaction()

    async def mark_failed(self) -> None:
        async with self._lock:
            await self._set_reaction(FAILED_REACTION)

    async def _set_reaction(self, reaction: str) -> None:
        if not self._enabled or self._current_reaction == reaction:
            return

        previous_reaction = self._current_reaction
        try:
            await self._message.add_reaction(reaction)
        except discord.Forbidden as error:
            logger.warning(
                "Could not add playback status reaction to message %s: "
                "missing reaction permissions (%s).",
                self._message.id,
                error,
            )
            return
        except discord.NotFound as error:
            logger.warning(
                "Could not add playback status reaction to message %s: "
                "message was not found (%s).",
                self._message.id,
                error,
            )
            return
        except discord.HTTPException as error:
            logger.warning(
                "Could not add playback status reaction to message %s: %s.",
                self._message.id,
                error,
            )
            return

        if previous_reaction is not None:
            await self._remove_reaction(previous_reaction)

        self._current_reaction = reaction

    async def _clear_reaction(self) -> None:
        if not self._enabled or self._current_reaction is None:
            return
        if await self._remove_reaction(self._current_reaction):
            self._current_reaction = None

    async def _remove_reaction(self, reaction: str) -> bool:
        try:
            await self._message.remove_reaction(
                reaction,
                self._bot_user,
            )
        except discord.NotFound:
            return True
        except discord.Forbidden as error:
            logger.warning(
                "Could not remove playback status reaction from message %s: "
                "missing reaction permissions (%s).",
                self._message.id,
                error,
            )
            return False
        except discord.HTTPException as error:
            logger.warning(
                "Could not remove playback status reaction from message %s: %s.",
                self._message.id,
                error,
            )
            return False
        return True
