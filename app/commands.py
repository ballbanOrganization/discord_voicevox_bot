from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

from .playback import PlaybackItem
from .speed import DEFAULT_SPEED_SCALE, normalize_speed_scale
from .voicevox import ALL_RANDOM_SPEAKER_ID, VoiceVoxError

if TYPE_CHECKING:
    from .bot import VoiceVoxBot


ALL_RANDOM_SPEAKER_NAME: str = "All Random"
RANDOM_SPEAKER_NAME: str = "Random / ランダム"


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
        if not text_channel_name or text_channel_name.lower() in channel.name.lower()
    ]
    return result[:25]


def _voice_client(
    bot: VoiceVoxBot,
    guild: discord.Guild,
) -> discord.VoiceClient | None:
    voice_client = guild.voice_client
    if isinstance(voice_client, discord.VoiceClient):
        return voice_client
    for candidate in bot.voice_clients:
        if isinstance(candidate, discord.VoiceClient) and candidate.guild is guild:
            return candidate
    return None


def _is_connected(voice_client: discord.VoiceClient) -> bool:
    return voice_client.is_connected()


def _parse_text_channel_id(guild: discord.Guild, value: str) -> int | None:
    try:
        channel_id = int(value)
    except (TypeError, ValueError):
        return None
    if any(channel.id == channel_id for channel in guild.text_channels):
        return channel_id
    return None


def _resolve_text_channel_id(
    interaction: discord.Interaction,
    guild: discord.Guild,
    value: str,
) -> tuple[int | None, str | None]:
    if value:
        channel_id = _parse_text_channel_id(guild, value)
        if channel_id is None:
            return None, "指定した文字チャンネルが見つからないのだ。"
        return channel_id, None
    if interaction.channel is None:
        return None, "文字チャンネルで実行してください。"
    return interaction.channel.id, None


def _try_normalize_speed_scale(value: object) -> float | None:
    try:
        return normalize_speed_scale(value)
    except (TypeError, ValueError):
        return None


def _resolve_voice_selection(
    bot: VoiceVoxBot,
    speaker_name: str,
    style_id: int,
) -> tuple[int, str] | None:
    if speaker_name == RANDOM_SPEAKER_NAME:
        selected_style_id = bot.voicevox.get_random_speaker_id()
        return (
            selected_style_id,
            bot.voicevox.get_speaker_name(selected_style_id),
        )
    if speaker_name == ALL_RANDOM_SPEAKER_NAME:
        return ALL_RANDOM_SPEAKER_ID, ALL_RANDOM_SPEAKER_NAME

    styles = bot.voicevox.speaker_dict.get(speaker_name)
    if not styles:
        return None
    if style_id == 0:
        style_name, selected_style_id = next(iter(styles.items()))
        return selected_style_id, f"{style_name} {speaker_name}"

    style_name = next(
        (
            name
            for name, selected_style_id in styles.items()
            if selected_style_id == style_id
        ),
        None,
    )
    if style_name is None:
        return None
    return style_id, f"{style_name} {speaker_name}"


def _register_reload_speakers(bot: VoiceVoxBot) -> None:
    @bot.tree.command(
        name="reload_speakers",
        description="VOICEVOXの音声一覧を再読み込みします。",
    )
    async def reload_speakers(inter: discord.Interaction) -> None:
        try:
            speakers = await bot.voicevox.load_speakers()
        except VoiceVoxError:
            await inter.response.send_message(
                "VOICEVOXに接続できず、音声一覧を再読み込みできないのだ。"
            )
            return
        await inter.response.send_message(
            f"VOICEVOXの音声一覧を再読み込みしたのだ（{len(speakers)}件）。"
        )


def _register_join(bot: VoiceVoxBot) -> None:
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

        text_channel_id, error_message = _resolve_text_channel_id(
            inter,
            guild,
            yomiage_channel,
        )
        if error_message is not None:
            await inter.response.send_message(error_message)
            return
        voice_client = _voice_client(bot, guild)
        if voice_client is not None and not _is_connected(voice_client):
            await bot.runtimes.disconnect(guild.id, voice_client)
            voice_client = None

        if voice_client is not None:
            if getattr(voice_client.channel, "id", None) != voice_channel.id:
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


def _register_disconnect(bot: VoiceVoxBot) -> None:
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


def _register_set_voice(bot: VoiceVoxBot) -> None:
    async def speaker_autocomplete(
        _interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        result: list[app_commands.Choice[str]] = []
        if not current or current.lower() in RANDOM_SPEAKER_NAME.lower():
            result.append(
                app_commands.Choice(
                    name=RANDOM_SPEAKER_NAME,
                    value=RANDOM_SPEAKER_NAME,
                )
            )
        if current and current.lower() in ALL_RANDOM_SPEAKER_NAME.lower():
            result.append(
                app_commands.Choice(
                    name=ALL_RANDOM_SPEAKER_NAME,
                    value=ALL_RANDOM_SPEAKER_NAME,
                )
            )
        result.extend(
            app_commands.Choice(name=name, value=name)
            for name in bot.voicevox.speaker_dict
            if not current or current.lower() in name.lower()
        )
        return result[:25]

    async def style_autocomplete(
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[int]]:
        selected_speaker = getattr(interaction.namespace, "speaker_name", "")
        if not isinstance(selected_speaker, str):
            return []
        styles = bot.voicevox.speaker_dict.get(selected_speaker, {})
        style_items = list(styles.items())
        if current:
            query = current.casefold()
            style_items = [
                (style_name, style)
                for style_name, style in style_items
                if query in style_name.casefold() or current in str(style)
            ]
        return [
            app_commands.Choice(name=style_name, value=style)
            for style_name, style in style_items[:25]
        ]

    @bot.tree.command(
        name="set_voice",
        description="読み上げ音声のキャラクターを変更する。",
    )
    @app_commands.describe(
        style_id="音声のスタイル、ノーマルが標準。",
        speed_scale="話速。1.0が標準。",
    )
    @app_commands.autocomplete(style_id=style_autocomplete)
    @app_commands.autocomplete(speaker_name=speaker_autocomplete)
    async def set_voice(
        inter: discord.Interaction,
        speaker_name: str,
        style_id: int = 0,
        speed_scale: float = DEFAULT_SPEED_SCALE,
    ) -> None:
        speed_scale = _try_normalize_speed_scale(speed_scale)
        if speed_scale is None:
            await inter.response.send_message(
                "speedScaleは0より大きい数値で設定してください。"
            )
            return

        selection = _resolve_voice_selection(bot, speaker_name, style_id)
        if selection is None:
            await inter.response.send_message(
                "指定した音声またはスタイルが見つからないのだ。"
            )
            return
        style_id, name = selection
        user = bot.user_data.get_user(inter.user.id)
        user.sound = style_id
        user.speed_scale = speed_scale
        bot.user_data.save_user(user)
        await inter.response.send_message(
            f"音声を**`{name}`**（話速: **`{speed_scale}`**）に設定しました。"
        )


def _register_set_speed(bot: VoiceVoxBot) -> None:
    @bot.tree.command(
        name="set_speed",
        description="読み上げ音声の話速を変更する。",
    )
    @app_commands.describe(
        speed_scale="話速。1.0が標準です。",
    )
    async def set_speed(
        inter: discord.Interaction,
        speed_scale: float,
    ) -> None:
        try:
            speed_scale = normalize_speed_scale(speed_scale)
        except (TypeError, ValueError):
            await inter.response.send_message(
                "speedScaleは0より大きい数値で設定してください。"
            )
            return

        user = bot.user_data.get_user(inter.user.id)
        user.speed_scale = speed_scale
        bot.user_data.save_user(user)
        await inter.response.send_message(f"話速を**`{speed_scale}`**に設定しました。")


def _register_set_entry_audio(bot: VoiceVoxBot) -> None:
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
            await inter.response.send_message(f"入場音声を**`{text}`**に設定しました。")
        else:
            await inter.response.send_message("入場音声をリセットしました。")


def _register_set_exit_audio(bot: VoiceVoxBot) -> None:
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
            await inter.response.send_message(f"退場音声を**`{text}`**に設定しました。")
        else:
            await inter.response.send_message("退場音声をリセットしました。")


def register_commands(bot: VoiceVoxBot) -> None:
    _register_reload_speakers(bot)
    _register_join(bot)
    _register_disconnect(bot)
    _register_set_voice(bot)
    _register_set_speed(bot)
    _register_set_entry_audio(bot)
    _register_set_exit_audio(bot)
