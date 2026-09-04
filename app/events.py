from typing import Any

import discord

from .message_status import (
    PLAYING_REACTION_MIN_LENGTH,
    MessagePlaybackStatus,
)
from .playback import PlaybackItem
from .text import attachment_announcements, normalize_text


def _is_connected(voice_client: discord.VoiceClient) -> bool:
    return voice_client.is_connected()


async def handle_message(bot: Any, message: Any) -> None:
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
    bot: Any,
    member: Any,
    before: Any,
    after: Any,
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
    before_channel_id = getattr(before.channel, "id", None)
    after_channel_id = getattr(after.channel, "id", None)
    if voice_channel_id not in (before_channel_id, after_channel_id):
        return

    user = bot.user_data.get_user(member.id)
    if before.channel is not None and after.channel is None:
        text = user.exit_audio or f"**`{member.display_name}`**さんが退室しました。"
    elif before.channel is None and after.channel is not None:
        text = user.entry_audio or f"**`{member.display_name}`**さんが入室しました。"
    else:
        return

    await bot.runtimes.enqueue(
        member.guild.id,
        PlaybackItem(text, member.id),
    )


async def cleanup_idle_voice_clients(bot: Any) -> None:
    for voice_client in list(bot.voice_clients):
        channel = getattr(voice_client, "channel", None)
        voice_states = getattr(channel, "voice_states", None)
        if channel is None or voice_states is None or len(voice_states) >= 2:
            continue
        guild_id = voice_client.guild.id
        await bot.runtimes.disconnect(guild_id, voice_client)
