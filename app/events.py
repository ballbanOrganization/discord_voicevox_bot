from __future__ import annotations

import time
from typing import TYPE_CHECKING

import discord

from .message_status import (
    PLAYING_REACTION_MIN_LENGTH,
    MessagePlaybackStatus,
)
from .playback import PlaybackItem
from .text import attachment_announcements, normalize_text
from .user_repository import DEFAULT_USER_ID

if TYPE_CHECKING:
    from .bot import VoiceVoxBot


def _is_connected(voice_client: discord.VoiceClient) -> bool:
    return voice_client.is_connected()


async def handle_message(bot: VoiceVoxBot, message: discord.Message) -> None:
    if bot.user is not None and (
        message.author == bot.user or message.author.id == bot.user.id
    ):
        return
    if message.guild is None:
        return

    state = bot.runtimes.get(message.guild.id)
    if state is None or not _is_connected(state.voice_client):
        return
    if message.channel.id != state.text_channel_id:
        return

    texts: list[str] = []
    if message.content:
        normalized = normalize_text(message.content)
        if normalized is None:
            return
        texts.append(normalized)

    texts.extend(attachment_announcements(message.attachments))
    if not texts:
        return

    for text in texts:
        status = (
            MessagePlaybackStatus(
                message,
                bot.user,
                show_playing_reaction=(
                    len(text) > PLAYING_REACTION_MIN_LENGTH
                ),
            )
            if bot.user is not None
            else None
        )
        await bot.runtimes.enqueue(
            message.guild.id,
            PlaybackItem(text, message.author.id, status=status),
        )


async def handle_voice_state_update(
    bot: VoiceVoxBot,
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    if bot.user is not None and member.id == bot.user.id:
        if after.channel is None:
            state = bot.runtimes.get(member.guild.id)
            if state is not None:
                await bot.runtimes.disconnect(member.guild.id, state.voice_client)
        return

    state = bot.runtimes.get(member.guild.id)
    if state is None or not _is_connected(state.voice_client):
        return

    voice_channel_id = getattr(state.voice_client.channel, "id", None)
    if voice_channel_id is None:
        return
    before_channel_id = getattr(before.channel, "id", None)
    after_channel_id = getattr(after.channel, "id", None)
    if voice_channel_id not in (before_channel_id, after_channel_id):
        return

    user = bot.user_data.get_user(member.id)
    default_user = bot.user_data.get_user(DEFAULT_USER_ID)
    entered = (
        before_channel_id != voice_channel_id
        and after_channel_id == voice_channel_id
    )
    left = (
        before_channel_id == voice_channel_id
        and after_channel_id != voice_channel_id
    )
    if left:
        text = user.exit_audio or f"**`{member.display_name}`**さんが退室しました。"
    elif entered:
        text = user.entry_audio or f"**`{member.display_name}`**さんが入室しました。"
    else:
        return

    await bot.runtimes.enqueue(
        member.guild.id,
        PlaybackItem(
            text,
            member.id,
            speaker_id=default_user.sound,
            speed_scale=default_user.speed_scale,
        ),
    )


def _is_bot_user(bot: VoiceVoxBot, channel: object, user_id: int) -> bool:
    if bot.user is not None and user_id == bot.user.id:
        return True

    guild = getattr(channel, "guild", None)
    get_member = getattr(guild, "get_member", None)
    member = get_member(user_id) if callable(get_member) else None
    if member is None:
        get_user = getattr(bot, "get_user", None)
        member = get_user(user_id) if callable(get_user) else None
    return bool(member is not None and getattr(member, "bot", False))


def _has_human_voice_state(
    bot: VoiceVoxBot,
    channel: object,
    voice_states: object,
) -> bool:
    try:
        user_ids = iter(voice_states)
    except TypeError:
        return True
    return any(
        not _is_bot_user(bot, channel, user_id)
        for user_id in user_ids
    )


async def cleanup_idle_voice_clients(
    bot: VoiceVoxBot,
    now: float | None = None,
) -> None:
    idle_since = getattr(bot, "_idle_voice_since", None)
    if idle_since is None:
        idle_since = {}
        setattr(bot, "_idle_voice_since", idle_since)

    settings = getattr(bot, "settings", None)
    idle_timeout = getattr(settings, "queue_idle_timeout", 300.0)
    if idle_timeout is None:
        idle_timeout = 300.0
    current_time = time.monotonic() if now is None else now
    seen_guild_ids: set[int] = set()

    for voice_client in list(bot.voice_clients):
        guild = getattr(voice_client, "guild", None)
        guild_id = getattr(guild, "id", None)
        if guild_id is None:
            continue
        seen_guild_ids.add(guild_id)

        channel = getattr(voice_client, "channel", None)
        voice_states = getattr(channel, "voice_states", None)
        if channel is None or voice_states is None:
            idle_since.pop(guild_id, None)
            continue
        if _has_human_voice_state(bot, channel, voice_states):
            idle_since.pop(guild_id, None)
            continue

        first_idle_at = idle_since.setdefault(guild_id, current_time)
        if current_time - first_idle_at < idle_timeout:
            continue

        idle_since.pop(guild_id, None)
        await bot.runtimes.disconnect(guild_id, voice_client)

    for guild_id in list(idle_since):
        if guild_id not in seen_guild_ids:
            idle_since.pop(guild_id, None)
