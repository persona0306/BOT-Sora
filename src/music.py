import asyncio
import logging
from logging.handlers import TimedRotatingFileHandler
import time

import discord
from discord.ext import commands
import yt_dlp

import src.core as core

MAX_QUEUE_SHOW_COUNT = 9

class Music(commands.Cog):

    music_queue = []

    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(
    name="music",
    brief="音楽を再生するのだ。",
    category="通話",
    usage="sora music",
    help="""音楽を再生するのだ。
曲名を指定して再生するか、stopで再生を止めるのだ。"""
)
    async def music(self, ctx):
        query = ctx.message.content[11:]
        logging.info("music command called with arg: %s", query)

        if query == '':
            await ctx.message.reply()
            return

        if query.startswith('playlist'):
            parts = query.split(maxsplit=1)
            if len(parts) < 2:
                await ctx.message.reply("プレイリストのURLを指定するのだ")
                return

            playlist_url = parts[1]
            await self.queue_playlist(ctx, playlist_url)
            return
        
        if query == 'stop':
            voice_client = ctx.message.guild.voice_client
            if voice_client is None or not voice_client.is_playing():
                await ctx.message.reply("再生中の音楽がないのだ")
                return
            voice_client.stop()
            self.music_queue.clear()
            await ctx.message.reply("音楽を止めたのだ")
            return

        if query.startswith('skip'):
            voice_client = ctx.message.guild.voice_client
            if voice_client is None or not voice_client.is_playing():
                await ctx.message.reply("再生中の音楽がないのだ")
                return

            parts = query.split()
            if len(parts) == 2:
                if not parts[1].isdigit():
                    await ctx.message.reply("スキップしたい音楽を半角数字で指定するのだ。")
                    return

                index = int(parts[1]) - 1

                if not 0 <= index < len(self.music_queue):
                    await ctx.message.reply("指定した番号の曲がないのだ。")
                    return

                item = self.music_queue.pop(index)
                await ctx.message.reply(f"キューの {index + 1} 番目の曲を消したのだ。 ({item.get('title')})")

            else:
                voice_client.stop()
                if self.music_queue:
                    await ctx.message.reply("次の曲にスキップしたのだ。")
                else:
                    await ctx.message.reply("次の曲がないのだ。")
            return

        if query == 'queue':
            await self.show_queue(ctx)
            return

        if query.startswith('insert'):
            parts = query.split(maxsplit=2)
            if len(parts) < 3 or not parts[1].isdigit():
                await ctx.message.reply("挿入したい位置と曲名を正しく指定するのだ\n例: sora music insert <位置> <曲名>")
                return

            index = int(parts[1]) - 1
            if index < 0 or index > len(self.music_queue):
                await ctx.message.reply("その番号はないのだ")
                return

            insert_query = parts[2]
            logging.info("Insert command called with index: %d and query: %s", index, insert_query)

            yt_item = self.get_youtube_url(insert_query)
            self.music_queue.insert(index, yt_item)

            await ctx.message.reply(f"曲をキューの {index + 1} 番目に挿入したのだ: {yt_item.get('title')}")
            logging.info("Inserted to queue at position %d: %s (%s)", index, yt_item.get('title'), yt_item.get('url'))

            return

        yt_item = self.get_youtube_url(query)

        voice_client = ctx.message.guild.voice_client
        if voice_client and voice_client.is_playing():
            self.music_queue.append(yt_item)
            await ctx.message.reply(f"曲をキューに追加したのだ: {yt_item.get('title')}")
            logging.info("Added to queue: [%s] %s (%s)", yt_item.get('duration'), yt_item.get('title'), yt_item.get('url'))
        else:
            await self.bot.get_cog("Music").stream_music(ctx, yt_item)

    def get_youtube_url(self, query):
        ydl_opts = {
            'default_search': 'ytsearch',
            'quiet': True,
            'verbose': True,
        }
    
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            if 'entries' in info:
                video = info['entries'][0]
            else:
                video = info
    
        url = video['webpage_url']
        title = video.get('title', 'Unknown title')
        duration = video.get('duration', 0)
        logging.info("Found video: [%s] %s (%s)", duration, title, url)
        return {'url': url, 'title': title, 'duration': duration}

    async def show_queue(self, ctx):
        if not self.music_queue:
            await ctx.message.reply("順番待ちの曲がないのだ。")
            return

        queue_message = "👇順番待ちの曲なのだ👇"
        for i, item in enumerate(self.music_queue):
            if MAX_QUEUE_SHOW_COUNT <= i:
                queue_message += f"\n・・・あと{len(self.music_queue) - i}曲あるのだ"
                break

            title = item['title']
            duration = item['duration']

            queue_message += f"\n{i + 1}. [ {int(duration // 60):02}:{int(duration % 60):02} ] {title}"

        await ctx.message.reply(queue_message)

    async def stream_music(self, ctx, item):
        url = item['url']

        logging.info("stream_music called with Music Item: %s", item)

        if url == '':
            await ctx.message.reply("sora music <曲名>で曲を指定するのだ。")
            logging.info("No URL provided")
            return

        voice_client = ctx.message.guild.voice_client
        if voice_client is None:
            await ctx.message.reply("ボクはまだVCに入ってないのだ。まずは「sora join」コマンドを使うのだ。")
            logging.info("Not connected to a voice channel")
            return

        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'noplaylist': True,
        }

        logging.info("Extracting video info")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            url2 = info['url']
            title = info.get('title', 'Unknown title')
            duration = info.get('duration', 0)

        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(
                url2,
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
            ),
            volume=0.2
        )

        playback_finished = asyncio.Event()

        def after_playing(error):
            if error:
                logging.error(f"Error while playing: {error}")
            playback_finished.set()
            if self.music_queue:
                next_url = self.music_queue.pop(0)
                asyncio.run_coroutine_threadsafe(self.stream_music(ctx, next_url), core.bot.loop)

        logging.info("Playing music: [%s] %s (%s)", duration, title, url2)
        voice_client.play(source, after=after_playing)

        message = await ctx.message.reply(f"再生中なのだ👉 {title}")

        start_time = time.time()
        while voice_client.is_playing():
            elapsed_time = time.time() - start_time
            if elapsed_time > duration:
                break

            minutes, seconds = divmod(int(elapsed_time), 60)
            await message.edit(content=f"再生中なのだ👉 [ {minutes:02}:{seconds:02} / {duration // 60:02}:{duration % 60:02} ] {title}")
            await asyncio.sleep(0.8)

        await playback_finished.wait()
        logging.info(f"Finished playing: {title}")

    async def queue_playlist(self, ctx, playlist_url):
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'skip_download': True,
            'force_generic_extractor': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(playlist_url, download=False)

        if 'entries' not in info:
            await ctx.message.reply("プレイリストが見つからなかったのだ")
            return

        playlist_entries = info['entries']
        for entry in playlist_entries:
            yt_item = {
                'url': entry['url'],
                'title': entry.get('title', 'Unknown title'),
                'duration': entry.get('duration', 0)
            }
            self.music_queue.append(yt_item)

        await ctx.message.reply(f"{len(playlist_entries)} 曲が順番待ちに入ったのだ")
        logging.info(f"Queued songs from playlist: {playlist_entries}")

        voice_client = ctx.message.guild.voice_client
        if voice_client is None or not voice_client.is_playing():
            url = self.music_queue.pop(0)
            await self.stream_music(ctx, url)
