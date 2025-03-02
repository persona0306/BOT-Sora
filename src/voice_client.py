import logging
import os

import asyncio
import discord
from discord.ext import commands
from voicevox import Client

from .music import Music

MAX_SPEAK_LENGTH = 256

VOICEVOX_URL = os.getenv("VOICEVOX_URL")

class VoiceClient(commands.Cog):
    character = 3
    channel = None
    conversation_history = []

    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name="join",
        brief="ボクが通話に入るのだ。",
        category="通話",
        usage="sora join",
        help="""ボクが通話に入るのだ。
    コマンドを使った人と同じ通話に入るから、先に入ってから使うのだ。"""
    )
    async def join(self, ctx):
        logging.info("join command called")
        voice_state = ctx.author.voice

        if voice_state is None:
            logging.info("Author is not in a voice channel")
            await ctx.message.reply("joinはVCに入ってから使うのだ")
            return

        sender_vc = voice_state.channel
        logging.info("Author's voice channel: %s", sender_vc)

        if sender_vc is None:
            logging.info("sender_vc is None")
            await ctx.message.reply("sender_vc is None")
            return

        voice_client = ctx.message.guild.voice_client
        logging.info("Current voice client: %s", voice_client)

        if voice_client is not None:
            if voice_client.channel == sender_vc:
                logging.info("Already in the same voice channel")
                await ctx.message.reply("もう入ってるのだ")
                return

            await voice_client.disconnect()

        logging.info("Connecting to voice channel")
        await sender_vc.connect()
        logging.info("Connected to voice channel")

        self.channel = ctx.message.channel
        logging.info("Set channel to: %s", self.channel)

        await self.speak(
            'ぼっとそらなのだ。呼んだのだ？',
            ctx.message.guild
        )

    @commands.command(
        name="leave",
        brief="ボクが通話から出るのだ。",
        category="通話",
        usage="sora leave",
        help="ボクが通話から出るのだ。"
    )
    async def leave(self, ctx):
        voice_client = ctx.message.guild.voice_client
        if voice_client is None:
            await ctx.message.channel.send('VCに入ってないのだ')
            return

        voice_client.stop()
        Music.music_queue.clear()

        await self.speak(
            'じゃあね、なのだ',
            ctx.message.guild
        )
        await asyncio.sleep(3)
        await ctx.message.guild.voice_client.disconnect()
        await ctx.message.channel.send(str(self.bot.user) + ' left the game')

    @commands.command(
        name="speaker",
        brief="ボクの声を決めるのだ。",
        category="通話",
        usage="sora speaker <VoiceVOXキャラクター番号>",
        help="""ボクの声を決めるのだ。
    VoiceVOXのキャラクター番号を入れるのだ。
    (ここにキャラクター番号の一覧を入れる)"""
    )
    async def speaker(self, ctx):
        try:
            self.character = int(ctx.message.content[12:])
            await ctx.message.channel.send('キャラクターを' + str(self.character) + 'に設定したのだ。')

        except ValueError:
            await ctx.message.channel.send('数字で入力してください。\n例(ずんだもん)：sora speaker 3')

    async def speak(self, message: str, guild: discord.Guild):
        if (len(message) > MAX_SPEAK_LENGTH):
            return

        if (message == '') | (message.startswith('http')):
            return
        if guild.voice_client is None:
            return
        if guild.voice_client.is_playing():
            return

        logging.info("check cache file")
        file_path = "./voice/message_" + str(self.character) + "_" + message[:32] + ".wav"

        if os.path.exists(file_path):
            logging.info("cache file exists")
            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(file_path),
                volume=0.1
            )
            guild.voice_client.play(source)
            return

        logging.info("cache file not exists. Request to VoiceVOX")
        async with Client(
            base_url = VOICEVOX_URL
            ) as client:
            logging.info("VoiceVOX client connected")
            query = await client.create_audio_query(
                message,
                speaker = self.character
            )
            with open(file_path, "wb") as f:
                f.write(await query.synthesis(speaker=self.character))
            logging.info("VoiceVOX synthesis completed")

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(file_path),
            volume=0.1
        )
        guild.voice_client.play(source)
