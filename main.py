import asyncio
import os
from typing import List
import discord
from discord import app_commands
from discord.ext import tasks
import voicevox as v
import user as u
import hashlib
import re
from collections import defaultdict

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
user_data = u.UserData()
voice_vox = v.VoiceVox()


@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    background_task.start()
    await tree.sync()


@client.event
async def on_message(message: discord.Message):
    # ignore own message
    if message.author == client.user:
        return

    # return if bot is not in voice channel
    # or message is not from the voice chat bot located in
    if not client.voice_clients \
            or not message.guild.voice_client \
            or message.guild.voice_client.channel != message.channel:
        return

    if message.content:
        # Check is link
        pattern = r"(http(s):\/\/.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-z]{2,6}\b([-a-zA-Z0-9@:%_\+.~#?&//=]*)"
        if re.search(pattern, message.content):
            message.content = 'リンク省略'

        # Replace 'w' if 'w' is repeated more than 4 times in row
        message.content = re.sub(r'[wWｗＷ]{4,}', 'わらわら', message.content)

        # Limit maximum length
        if len(message.content) > 300:
            message.content = message.content[:300] + '以下省略'

        await read_text(message.content, message.guild.voice_client, message.author.id)

    # Check attachments
    attachment_dict = defaultdict(int)
    for attachment in message.attachments:
        if 'application' in attachment.content_type:
            attachment_dict['アプリケーション'] += 1
        elif 'audio' in attachment.content_type:
            attachment_dict['音声'] += 1
        elif 'image' in attachment.content_type:
            attachment_dict['画像'] += 1
        elif 'message' in attachment.content_type:
            attachment_dict['メッセージ'] += 1
        elif 'multipart' in attachment.content_type:
            attachment_dict['マルチ'] += 1
        elif 'text' in attachment.content_type:
            attachment_dict['テキスト'] += 1
        elif 'video' in attachment.content_type:
            attachment_dict['動画'] += 1
        else:
            attachment_dict['うんこなう'] += 1
            print(f'unknown content_type: {attachment.content_type}')
    for key, value in attachment_dict.items():
        if value > 1:
            await read_text(f'添付{key}{value}', message.guild.voice_client, message.author.id)
        else:
            await read_text(f'添付{key}', message.guild.voice_client, message.author.id)


async def read_text(text: str, voice_client: discord.VoiceProtocol, user_id: int):
    # Get user
    user = user_data.get_user(user_id)

    # Get MD5
    md5 = hashlib.md5(text.encode()).hexdigest()

    # Check audio exist
    speaker_name = voice_vox.get_speaker_name(speaker_id=user.sound)
    file_path = f'audio/{speaker_name}/{md5}.wav'
    # Check folder path
    audio_folder_path = os.path.dirname(file_path)
    if not os.path.exists(audio_folder_path):
        # Create a new directory
        os.makedirs(audio_folder_path)
    # Create file if file is not exists
    if not os.path.isfile(file_path):
        content = voice_vox.text_to_sound(text, user.sound)
        # Save file to local
        with open(file_path, mode='wb') as f:
            f.write(content)
    # Check is bot playing audio
    while voice_client.is_playing():
        await asyncio.sleep(0.5)
    # Play audio
    audio_source = discord.FFmpegPCMAudio(source=file_path)
    voice_client.play(audio_source)
    print(f'Speaker: {speaker_name}, Text: {text}')


@client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    # ignore own state change
    if member.id == client.user.id:
        return

    # get current voice client
    voice_client = discord.utils.get(client.voice_clients, guild=member.guild)

    # detect state change in same channel
    if voice_client \
            and (voice_client.channel == before.channel or voice_client.channel == after.channel):
        # when user left channel
        if before.channel and not after.channel:
            await read_text(f'{member.display_name}さんが退室しました。', voice_client, member.id)
        # when user join channel
        elif not before.channel and after.channel:
            await read_text(f'{member.display_name}さんが入室しました。', voice_client, member.id)


@tree.command(name='join', description='ユーザーが入っているボイスチャンネルにbotが参加します。')
async def join(inter: discord.Interaction):
    if inter.user.voice:
        voice_channel = inter.user.voice.channel
    else:
        await inter.response.send_message('どのチャンネルに入ればいいのかわからないのだ！'
                                          'ボイスチャンネルに入ってから僕を呼ぶのだ！')

    # get current voice_client
    voice_client = discord.utils.get(client.voice_clients, guild=inter.user.guild)
    # if bot is in voice channel already
    if voice_client:
        if voice_client.channel.id != voice_channel.id:
            await voice_client.move_to(voice_channel)
            while voice_client.is_connected():
                await asyncio.sleep(0.1)
            text = 'チャンネル移動なのだ！'
            await inter.response.send_message(text)
            await read_text(text, voice_client, client.user.id)
        else:
            await inter.response.send_message('もうチャンネルに入っているのだ！')
    else:
        # join the voice channel that user in
        voice_client = await voice_channel.connect()
        text = 'ウィィィッス！どうもー、しゃむだもんでーす'
        await inter.response.send_message(text)
        await read_text(text, voice_client, client.user.id)


@tree.command(name='disconnect', description='接続を切断します。')
async def disconnect(inter: discord.Interaction):
    voice_client = discord.utils.get(client.voice_clients, guild=inter.user.guild)
    await voice_client.disconnect(force=True)
    await inter.response.send_message('疲れたのだ　( ˘ω˘ )ｽﾔｧ…')


async def speaker_autocomplete(interaction: discord.Interaction, speaker_name: str) -> List[app_commands.Choice[str]]:
    if speaker_name:
        result = [
            app_commands.Choice(name=key, value=key)
            for key in voice_vox.speaker_dict.keys() if speaker_name.lower() in key.lower()
        ]
    else:
        result = [
            app_commands.Choice(name=key, value=key)
            for key in voice_vox.speaker_dict.keys()
        ]
    return result[:25]


async def style_autocomplete(interaction: discord.Interaction, style: int) -> List[app_commands.Choice[str]]:
    result = []
    for speaker_name, styles in voice_vox.speaker_dict.items():
        if speaker_name == interaction.namespace.speaker_name:
            for style_name, speaker_id in styles.items():
                result.append(app_commands.Choice(name=style_name, value=speaker_id))
            break
    return result[:25]


@tree.command(name='set_voice', description='読み上げ音声のキャラクターを変更します。'
                                            'discordの制限で25項目しかだせない。')
@app_commands.autocomplete(speaker_name=speaker_autocomplete, style_id=style_autocomplete)
async def set_voice(inter: discord.Interaction, speaker_name: str, style_id: int = 0):
    if style_id == 0:
        style_name, speaker_id = list(voice_vox.speaker_dict[speaker_name].items())[0]
        name = style_name + speaker_name
    else:
        name = voice_vox.get_speaker_name(style_id)
    user = user_data.get_user(inter.user.id)
    user.sound = style_id
    user_data.save_user(user)
    await inter.response.send_message(f'音声を{name}に設定しました。')


@tasks.loop(seconds=60)
async def background_task():
    """
    Background task run in every 1 minutes
    """
    await client.wait_until_ready()
    # Leave voice channel if no member in voice channel
    for voice_client in client.voice_clients:
        if len(voice_client.channel.voice_states.keys()) < 2:
            await voice_client.disconnect(force=True)


client.run(os.environ['discord_token'])
