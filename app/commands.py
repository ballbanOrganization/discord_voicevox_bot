from typing import Any

import discord
from discord import app_commands

from .playback import PlaybackItem


async def yomiage_channel_autocomplete(
    interaction: discord.Interaction,
    text_channel_name: str,
) -> list[app_commands.Choice[str]]:
    guild = interaction.guild
    if guild is None:
        return []
    result = [
        app_commands.Choice(name=channel.name, value=str(channel.id))
        for channel in guild.text_channels
        if not text_channel_name
        or text_channel_name.lower() in channel.name.lower()
    ]
    return result[:25]


async def speaker_autocomplete(
    interaction: discord.Interaction,
    speaker_name: str,
) -> list[app_commands.Choice[str]]:
    voicevox = interaction.client.voicevox
    result = [
        app_commands.Choice(name=name, value=name)
        for name in voicevox.speaker_dict
        if not speaker_name or speaker_name.lower() in name.lower()
    ]
    return result[:25]


async def style_autocomplete(
    interaction: discord.Interaction,
    style_id: int,
) -> list[app_commands.Choice[int]]:
    voicevox = interaction.client.voicevox
    namespace = getattr(interaction, "namespace", None)
    selected_speaker = getattr(namespace, "speaker_name", "")
    styles = voicevox.speaker_dict.get(selected_speaker, {})
    return [
        app_commands.Choice(name=style_name, value=style)
        for style_name, style in list(styles.items())[:25]
    ]


def _voice_client(bot: Any, guild: discord.Guild) -> Any:
    return guild.voice_client or discord.utils.get(bot.voice_clients, guild=guild)


def _is_connected(voice_client: Any) -> bool:
    check = getattr(voice_client, "is_connected", None)
    return not callable(check) or bool(check())


def _register_join(bot: Any) -> None:
    @bot.tree.command(
        name="join",
        description="指定した文字チャンネルを読み上げる。",
    )
    @app_commands.autocomplete(yomiage_channel=yomiage_channel_autocomplete)
    async def join(inter: discord.Interaction, yomiage_channel: str = "") -> None:
        guild = inter.guild
        if guild is None:
            await inter.response.send_message("サーバーで実行してください。")
            return

        voice_state = getattr(inter.user, "voice", None)
        voice_channel = getattr(voice_state, "channel", None)
        if voice_channel is None:
            await inter.response.send_message(
                "どのチャンネルに入ればいいのかわからないのだ！\n"
                "ボイスチャンネルに入ってから僕を呼ぶのだ！"
            )
            return

        text_channel_id = int(yomiage_channel) if yomiage_channel else inter.channel.id
        voice_client = _voice_client(bot, guild)
        if voice_client is not None and not _is_connected(voice_client):
            await bot.runtimes.disconnect(guild.id, voice_client)
            voice_client = None

        if voice_client is not None:
            if voice_client.channel.id != voice_channel.id:
                await voice_client.move_to(voice_channel)
                announcement = "チャンネル移動なのだ！"
            else:
                state = bot.runtimes.get(guild.id)
                if state is not None and state.text_channel_id == text_channel_id:
                    announcement = "もうこのチャンネルに入っているのだ！"
                else:
                    announcement = "読み上げチャンネルを変更したのだ！"
        else:
            voice_client = await voice_channel.connect()
            announcement = "ウィィィッス！どうもー、しゃむだもんでーす"

        state = await bot.runtimes.configure(
            guild.id,
            voice_client,
            text_channel_id,
        )
        bot_user_id = bot.user.id if bot.user is not None else 0
        await state.playback.enqueue(PlaybackItem(announcement, bot_user_id))

        response_text = (
            f"{announcement}\n> 現在文字読みチャンネル: <#{text_channel_id}>"
        )
        await inter.response.send_message(response_text)


def _register_disconnect(bot: Any) -> None:
    @bot.tree.command(name="disconnect", description="接続を切断します。")
    async def disconnect(inter: discord.Interaction) -> None:
        guild = inter.guild
        if guild is None:
            await inter.response.send_message("サーバーで実行してください。")
            return

        voice_client = _voice_client(bot, guild)
        if voice_client is None:
            await inter.response.send_message("接続していないのだ！")
            return
        await bot.runtimes.disconnect(guild.id, voice_client)
        await inter.response.send_message("疲れたのだ　( ˘ω˘ )ｽﾔｧ…")


def _register_set_voice(bot: Any) -> None:
    @bot.tree.command(
        name="set_voice",
        description="読み上げ音声のキャラクターを変更する。",
    )
    @app_commands.autocomplete(
        speaker_name=speaker_autocomplete,
        style_id=style_autocomplete,
    )
    async def set_voice(
        inter: discord.Interaction,
        speaker_name: str,
        style_id: int = 0,
    ) -> None:
        styles = bot.voicevox.speaker_dict[speaker_name]
        if style_id == 0:
            style_name, style_id = next(iter(styles.items()))
            name = f"{style_name} {speaker_name}"
        else:
            name = bot.voicevox.get_speaker_name(style_id)
        user = bot.user_data.get_user(inter.user.id)
        user.sound = style_id
        bot.user_data.save_user(user)
        await inter.response.send_message(f"音声を**`{name}`**に設定しました。")


def _register_set_entry_audio(bot: Any) -> None:
    @bot.tree.command(
        name="set_entry_audio",
        description="入場時の読み上げ音声を指定、空でリセット。",
    )
    @app_commands.describe(text="文字数は50文字以内。")
    async def set_entry_audio(
        inter: discord.Interaction,
        text: str = "",
    ) -> None:
        if len(text) > 50:
            await inter.response.send_message("50文字以内に設定してください。")
            return
        user = bot.user_data.get_user(inter.user.id)
        user.entry_audio = text
        bot.user_data.save_user(user)
        if text:
            await inter.response.send_message(
                f"入場音声を**`{text}`**に設定しました。"
            )
        else:
            await inter.response.send_message("入場音声をリセットしました。")


def _register_set_exit_audio(bot: Any) -> None:
    @bot.tree.command(
        name="set_exit_audio",
        description="退場時の読み上げ音声を指定、空でリセット。",
    )
    @app_commands.describe(text="文字数は50文字以内。")
    async def set_exit_audio(
        inter: discord.Interaction,
        text: str = "",
    ) -> None:
        if len(text) > 50:
            await inter.response.send_message("50文字以内に設定してください。")
            return
        user = bot.user_data.get_user(inter.user.id)
        user.exit_audio = text
        bot.user_data.save_user(user)
        if text:
            await inter.response.send_message(
                f"退場音声を**`{text}`**に設定しました。"
            )
        else:
            await inter.response.send_message("退場音声をリセットしました。")


def register_commands(bot: Any) -> None:
    _register_join(bot)
    _register_disconnect(bot)
    _register_set_voice(bot)
    _register_set_entry_audio(bot)
    _register_set_exit_audio(bot)
