import logging
import os

import asyncio
import random
import struct
import discord
from discord import FFmpegPCMAudio
from discord import PCMVolumeTransformer
from discord.ext import commands
from voicevox import Client
import yt_dlp

from .music import Music

MAX_SPEAK_LENGTH = 256

PROGRESS_BAR = ["▁", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]
PROGRESS_BAR_LENGTH = 15

QUEUE_SHOW_COUNT = 10

MUSIC_MULTIPLIER_ON_SPEAK = 0.6

VOICEVOX_URL = os.getenv("VOICEVOX_URL")

YDL_OPTS = {
    'format': 'bestaudio/best',
    'quiet': True,
    'noplaylist': True,
}

class YoutubeSource(discord.AudioSource):
    def __init__(self, bot: commands.Bot, url: str, title: str, duration: int):
        self.bot = bot
        self.duration = duration
        self.elapsed_time = 0
        self.is_message_sent = False
        self.is_downloading = False
        self.message = None
        self.source = None
        self.title = title
        self.url = url

    def download(self):
        if self.is_downloading:
            return
        
        self.is_downloading = True

        async def execute_download():
            logging.info("Extracting video info")
            with yt_dlp.YoutubeDL(YDL_OPTS) as ydl:
                info = ydl.extract_info(self.url, download=False)
                url2 = info['url']

                self.source = PCMVolumeTransformer(
                    FFmpegPCMAudio(
                        url2,
                        before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                    ),
                    volume=0.03
                )
        
        asyncio.run_coroutine_threadsafe(
            execute_download(),
            self.bot.loop
        )

    def read(self):
        if not self.is_downloading:
            self.download()
        
        if self.source is None:
            # 20ms of silence for 48kHz 16-bit stereo audio
            return b'\x00' * 3840

        if not self.is_message_sent:
            self.is_message_sent = True

            async def send_message():
                self.message = await self.bot.get_cog("VoiceClient").channel.send(f"再生中なのだ👉 {self.title}")

            asyncio.run_coroutine_threadsafe(
                send_message(),
                self.bot.loop
            )

        self.elapsed_time += 20
        if self.message is not None and self.elapsed_time % 1000 == 0:
            minutes, seconds = divmod(self.elapsed_time // 1000, 60)

            progress = self.elapsed_time / self.duration / 1000

            progress_bar_prefix = PROGRESS_BAR[8] * (int(progress * PROGRESS_BAR_LENGTH))
            progress_bar_suffix = PROGRESS_BAR[0] * (PROGRESS_BAR_LENGTH - int(progress * PROGRESS_BAR_LENGTH) - 1)

            progress_bar_middle = PROGRESS_BAR[int((progress * PROGRESS_BAR_LENGTH) % 1 * 8)]

            progress_bar = f"{progress_bar_prefix}{progress_bar_middle}{progress_bar_suffix} [ {minutes:02}:{seconds:02} / {self.duration // 60:02}:{self.duration % 60:02} ]"

            async def edit_message():
                await self.message.edit(content=f"再生中なのだ👉 {self.title} \n{progress_bar}")

            asyncio.run_coroutine_threadsafe(
                edit_message(),
                self.bot.loop
            )

        return self.source.read()

class CombinedAudioSource(discord.AudioSource):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.speak_queue = []
        self.music_queue = []
        self.current_speak_source = None
        self.current_music_source = None

    def add_speak_source(self, source):
        self.speak_queue.append(source)
        logging.info("Added speak source to audio queue, %d audios are in queue", len(self.speak_queue))
    
    def add_music_source(self, source, position = None):
        if position is not None:
            self.music_queue.insert(position, source)
        else:
            self.music_queue.append(source)
        logging.info("Added music source to audio queue to position %d, %d audios are in queue", position, len(self.music_queue))
    
    def add_youtube_source(self, url, title, duration, position = None):
        source = YoutubeSource(self.bot, url, title, duration)
        self.add_music_source(source, position)
        logging.info("Added youtube source to audio queue")

    def combine_pcm(self, speak_data, music_data):
        # Ensure both data are the same length
        min_length = min(len(speak_data), len(music_data))
        speak_data = speak_data[:min_length]
        music_data = music_data[:min_length]

        # Unpack the PCM data into 16-bit signed integers
        speak_samples = struct.unpack(f"{min_length // 2}h", speak_data)
        music_samples = struct.unpack(f"{min_length // 2}h", music_data)

        # Combine the samples
        combined_samples = [
            int(speak_sample + music_sample * MUSIC_MULTIPLIER_ON_SPEAK)
            for speak_sample, music_sample in zip(speak_samples, music_samples)
        ]

        # Pack the combined samples back into PCM data
        combined_data = struct.pack(f"{len(combined_samples)}h", *combined_samples)
        return combined_data

    def cleanup(self):
        if self.current_speak_source:
            self.speak_source.cleanup()
        if self.current_music_source:
            self.music_source.cleanup()

    def read(self):
        if self.current_speak_source is None and self.speak_queue:
            self.current_speak_source = self.speak_queue.pop(0)
            logging.info("Switched to next speak source")
        if self.current_music_source is None and self.music_queue:
            self.current_music_source = self.music_queue.pop(0)
            logging.info("Switched to next music source")
            if self.music_queue is not None and isinstance(self.music_queue[0], YoutubeSource):
                self.music_queue[0].download()

        speak_data = self.current_speak_source.read() if self.current_speak_source else None
        music_data = self.current_music_source.read() if self.current_music_source else None

        if not speak_data:
            self.current_speak_source = None
        if not music_data:
            self.current_music_source = None

        if not speak_data and not music_data:
            # 20ms of silence for 48kHz 16-bit stereo audio to prevent stopping
            return b'\x00' * 3840

        if not speak_data:
            return music_data
        if not music_data:
            return speak_data

        # Combine the PCM data from both sources
        combined_data = self.combine_pcm(speak_data, music_data)
        return combined_data

    def shuffle(self):
        if self.current_music_source is None:
            return
        random.shuffle(self.music_queue)

    def skip(self, start_position: str = None, skip_count = 1):
        success_skip_count = 0

        if start_position is not None:
            if start_position < 0:
                return success_skip_count

            for i in range(skip_count):
                if start_position >= len(self.music_queue):
                    return success_skip_count
                self.music_queue.pop(start_position)
                success_skip_count += 1
        else:
            self.current_music_source = None

        return success_skip_count

class VoiceClient(commands.Cog):
    character = 3
    channel = None
    conversation_history = []

    def __init__(self, bot: commands.Bot):
        self.audio = CombinedAudioSource(bot)
        self.bot = bot
        self.bot.loop.create_task(self.loop_play())

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

        self.bot.voice_clients[0].play(self.audio)

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
            await self.speak(
                'キャラクターを' + str(self.character) + 'に設定したのだ。',
                ctx.message.guild
            )

        except ValueError:
            await ctx.message.channel.send('数字で入力してください。\n例(ずんだもん)：sora speaker 3')

    async def show_queue(self, ctx):
        if not self.audio.music_queue:
            await ctx.message.reply("順番待ちの曲がないのだ。")
            return

        page = 1
        arg = ctx.message.content[6 + len(self.bot.command_prefix):]
        if arg.isdigit():
            page = int(arg)
            if page < 1:
                page = 1
        
        queue_count = len(self.audio.music_queue)
        
        if queue_count <= (page - 1) * QUEUE_SHOW_COUNT:
            await ctx.message.reply(f"そのページには曲がないのだ。({queue_count}曲しかないのだ。)")
            return

        max_page = (queue_count + QUEUE_SHOW_COUNT - 1) // QUEUE_SHOW_COUNT
        queue_message = f"👇順番待ちの曲なのだ ( {page} / {max_page} ページ )👇"
        for i, item in enumerate(
            self.audio.music_queue,
            start = 1
        ):
            if i <= (page - 1) * QUEUE_SHOW_COUNT:
                continue

            if page * QUEUE_SHOW_COUNT < i:
                queue_message += f"\n合計で{len(self.audio.music_queue)}曲あるのだ。 ( {page} / {max_page} ページ )"
                if page == 1:
                    queue_message += "\n次のページは 「sora queue 2」 で見るのだ。"
                break

            title = item.title
            duration = item.duration

            queue_message += f"\n{i}. [ {int(duration // 60):02}:{int(duration % 60):02} ] {title}"

        await ctx.message.reply(queue_message)

    async def speak(self, message: str, guild: discord.Guild):
        if (len(message) > MAX_SPEAK_LENGTH):
            return

        if (message == '') | (message.startswith('http')):
            return
        if guild.voice_client is None:
            return

        logging.info("check cache file")
        file_path = "./voice/message_" + str(self.character) + "_" + message[:32] + ".wav"

        if os.path.exists(file_path):
            logging.info("cache file exists")
            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(file_path),
                volume=0.15
            )
            self.audio.add_speak_source(source)
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
            volume=0.25
        )

        self.audio.add_speak_source(source)

    async def loop_play(self):
        logging.info("loop_play is called, waiting for bot to be ready...")

        # Wait for the bot to be ready
        await asyncio.sleep(3)

        logging.info("loop_play started")
        while True:
            await asyncio.sleep(1)

            if not self.bot.voice_clients:
                continue

            voice_client = self.bot.voice_clients[0]
            if not voice_client.is_connected():
                continue

            if voice_client.is_playing():
                continue

            logging.info("loop_play: start playing audio")
            try:
                voice_client.play(self.audio)
            except Exception as e:
                logging.error("Error while playing audio: %s", e)
                continue
