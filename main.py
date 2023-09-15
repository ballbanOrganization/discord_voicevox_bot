import asyncio
import os
import discord
import voicevox
from discord import app_commands
import hashlib
import re

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    await tree.sync()


@client.event
async def on_message(message: discord.Message):
    # ignore own message
    if message.author == client.user:
        return

    # return if bot is not in voice channel
    # or message is not from the voice chat bot located in
    if not client.voice_clients or message.guild.voice_client.channel != message.channel:
        return

    # Check is link
    if re.search(r"(http)?s?(:\/\/)?[\w\d-]*\.[\w\d]{2,3}", message.content):
        message.content = 'リンク省略'

    # Replace 'wwww'
    message.content = re.sub(r'[wW]{4,}', 'わらわら', message.content)

    # Limit maximum length
    if len(message.content) > 300:
        message.content = message.content[:300] + '以下省略'

    await read_text(message.content, message.guild.voice_client)


async def read_text(text: str, voice_client: discord.VoiceProtocol):
    # Get MD5
    md5 = hashlib.md5(text.encode()).hexdigest()

    # Check audio exist
    vox = voicevox.VoiceVox()
    speaker_name = vox.get_speaker_name(speaker_id=3)
    file_path = f'audio/{speaker_name}/{md5}.wav'
    # Check folder path
    audio_folder_path = os.path.dirname(file_path)
    if not os.path.exists(audio_folder_path):
        # Create a new directory
        os.makedirs(audio_folder_path)
    # Create file if file is not exists
    if not os.path.isfile(file_path):
        content = vox.text_to_sound(text)
        # Save file to local
        with open(file_path, mode='wb') as f:
            f.write(content)
    # Check is bot playing audio
    while voice_client.is_playing():
        await asyncio.sleep(0.1)
    # Play audio
    audio_source = discord.FFmpegPCMAudio(source=file_path)
    voice_client.play(audio_source)


@client.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    # ignore own state change
    if member.id == client.user.id:
        return

    # get current voice client
    voice_client = discord.utils.get(client.voice_clients, guild=member.guild)

    # when user left channel
    if before.channel and not after.channel:
        await read_text(f'{member.display_name}さんが退室しました。', voice_client)
    # when user join channel
    elif not before.channel and after.channel:
        await read_text(f'{member.display_name}さんが入室しました。', voice_client)


@tree.command(name='join', description='ユーザーが入っているボイスチャンネルにbotが参加します。')
async def join(inter: discord.Interaction):
    if inter.user.voice:
        voice_channel = inter.user.voice.channel
    else:
        await inter.channel.send('どのチャンネルに入ればいいのかわからないのだ！'
                                 'ボイスチャンネルに入ってから僕を呼ぶのだ！')
        return

    # get current voice_client
    voice_client = discord.utils.get(client.voice_clients, guild=inter.user.guild)
    if voice_client and voice_client.channel != voice_channel:
        voice_client = await voice_channel.move()
    else:
        voice_client = await voice_channel.connect()

    # set current channel
    await inter.response.send_message('ウィィィッス！どうもー、しゃむだもんでーす')

    # get current voice client
    await read_text('ウィィィッス！どうもー、しゃむだもんでーす', voice_client)


@tree.command(name='disconnect', description='接続を切断します。')
async def disconnect(inter: discord.Interaction):
    voice_client = discord.utils.get(client.voice_clients, guild=inter.user.guild)
    await voice_client.disconnect()
    await inter.response.send_message('疲れたのだ　( ˘ω˘ )ｽﾔｧ…')


client.run(os.environ['discord_token'])
