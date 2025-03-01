import asyncio
import logging
from logging.handlers import TimedRotatingFileHandler
import random
import time

from discord import FFmpegPCMAudio
from discord import PCMVolumeTransformer
from discord.ext import commands
import yt_dlp

from . import core

MAX_QUEUE_SHOW_COUNT = 9

PROGRESS_BAR = ["▁", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]

class Music(commands.Cog):

    music_queue = []

    def __init__(self, bot):
        self.bot = bot
    
    @commands.command(
        name="insert",
        brief="音楽を検索して、順番待ちに割り込むのだ。",
        usage="sora insert <順番> <曲名>",
        help="""音楽を検索して、順番待ちに割り込むのだ。"""
    )
    async def insert(self, ctx):
        args = ctx.message.content[7 + len(core.bot.command_prefix):]
        logging.info("Insert command called with query: %s", args)

        args_parts = args.split(maxsplit=1)
        if len(args_parts) < 2 or not args_parts[0].isdigit():
            await ctx.message.reply("挿入したい位置と曲名を正しく指定するのだ\n例: sora music insert <位置> <曲名>")
            logging.info("Invalid arguments: %s", args)
            return

        insert_index = int(args_parts[0]) - 1

        if insert_index < 0:
            insert_index = 0

        if insert_index > len(self.music_queue):
            insert_index = len(self.music_queue)

        insert_query = args_parts[1]
        logging.info("Insert command called with index: %d and query: %s", insert_index, insert_query)

        yt_item = self.get_youtube_url(insert_query)
        self.music_queue.insert(insert_index, yt_item)

        await ctx.message.reply(f"曲をキューの {insert_index + 1} 番目に挿入したのだ: {yt_item.get('title')}")
        logging.info("Inserted to queue at position %d: %s (%s)", insert_index, yt_item.get('title'), yt_item.get('url'))

        return
    
    @commands.command(
        name="play",
        brief="音楽を検索して再生するのだ。",
        usage="sora play <曲名>",
        help="""音楽を検索して再生するのだ。
再生中の曲があるときは、順番待ちに入れるのだ。"""
    )
    async def play(self, ctx):
        query = ctx.message.content[5 + len(core.bot.command_prefix):]
        logging.info("music command called with arg: %s", query)

        if query == '':
            await ctx.message.reply("曲名を入れるのだ。")
            return

        yt_item = self.get_youtube_url(query)

        voice_client = ctx.message.guild.voice_client
        if voice_client and voice_client.is_playing():
            self.music_queue.append(yt_item)
            await ctx.message.reply(f"曲をキューに追加したのだ: {yt_item.get('title')}")
            logging.info("Added to queue: [%s] %s (%s)", yt_item.get('duration'), yt_item.get('title'), yt_item.get('url'))
        else:
            await self.bot.get_cog("Music").stream_music(ctx, yt_item)

    @commands.command(
        name="playlist",
        brief="プレイリストを再生するのだ。",
        usage="sora playlist (shuffle) <プレイリストのURL>",
        help="""プレイリストを再生するのだ。
再生中の曲があるときは、順番待ちに入れるのだ。
URLの前に「shuffle」と書くと、
プレイリストをシャッフルして順番待ちの最後に入れるのだ。
もう順番待ちに入ってるものも混ぜたいときは、
このコマンドの後に「sora shuffle」を使うのだ。"""
    )
    async def playlist(self, ctx):
        query = ctx.message.content[9 + len(core.bot.command_prefix):]
        logging.info("music command called with arg: %s", query)

        shuffle = False

        sprit_query = query.split()
        if len(sprit_query) > 1 and sprit_query[0] == 'shuffle':
            shuffle = True
            query = sprit_query[1]
            logging.info("Shuffle mode enabled")

        await self.queue_playlist(ctx, query, shuffle)

    @commands.command(
        name="queue",
        brief="順番待ちの曲を見るのだ。",
        usage="sora queue",
        help="""順番待ちの曲を見るのだ。"""
    )
    async def queue(self, ctx):
        await self.show_queue(ctx)

    @commands.command(
        name="shuffle",
        brief="順番待ちの曲をシャッフルするのだ。",
        usage="sora shuffle (<プレイリストのURL>)",
        help="""順番待ちの曲をシャッフルするのだ。
プレイリストのURLを入れると、
プレイリストをシャッフルして順番待ちの最後に入れるのだ。
順番待ちとプレイリストを混ぜたいときは、
プレイリストを入れた後にシャッフルするのだ。"""
    )
    async def shuffle(self, ctx):
        query = ctx.message.content[8 + len(core.bot.command_prefix):]

        logging.info("Shuffle command called with arg: %s", query)

        if len(query) > 1:
            logging.info("URL is provided, shuffling playlist")
            await self.queue_playlist(ctx, query, True)
        else:
            random.shuffle(self.music_queue)
            logging.info("No URL is provided, shuffled queue")
            await ctx.message.reply("順番待ちの曲をシャッフルしたのだ。")

    @commands.command(
        name="skip",
        brief="再生中の音楽を飛ばして、次の曲に進むのだ。",
        usage="sora skip <飛ばしたい曲の番号> <範囲>",
        help="""再生中の音楽を飛ばして、次の曲に進むのだ。
数字を入れると、順番待ちの位置を選んで飛ばせるのだ。
数字を2つ入れると、1番目の数字から、2番目の数字までの間を飛ばすのだ。"""
    )
    async def skip(self, ctx):
        args = ctx.message.content[5 + len(core.bot.command_prefix):].split()
        logging.info("skip command called with args: %s", args)

        voice_client = ctx.message.guild.voice_client
        if voice_client is None or not voice_client.is_playing():
            await ctx.message.reply("再生中の音楽がないのだ")
            logging.info("No music is playing")
            return

        if len(args) == 0:
            voice_client.stop()
            logging.info("Skipping current music")

            if self.music_queue:
                await ctx.message.reply("次の曲にスキップしたのだ。")
            else:
                await ctx.message.reply("次の曲がないのだ。")

        else:
            if not args[0].isdigit():
                await ctx.message.reply("スキップしたい音楽の順番を「sora queue」で見て、半角数字で指定するのだ。")
                logging.info("args[0] is not a number")
                return
            
            start_index = int(args[0]) - 1
            skip_count = 1

            if len(args) > 1:
                if not args[1].isdigit():
                    await ctx.message.reply("範囲の2番目の数字が数字じゃないのだ。")
                    logging.info("args[1] is not a number")
                    return

                end_index = int(args[1]) - 1
                skip_count = end_index - start_index + 1

            logging.info("Skipping %d songs starting from %d", skip_count, start_index)

            for i in range(skip_count):
                self.music_queue.pop(start_index)

            await ctx.message.reply(f"キューの曲を {skip_count}曲 消したのだ。")

    @commands.command(
        name="stop",
        brief="音楽を止めるのだ。",
        usage="sora stop",
        help="""音楽を止めるのだ。
順番待ちの曲も消すのだ。"""
    )
    async def stop(self, ctx):
        voice_client = ctx.message.guild.voice_client
        if voice_client is None or not voice_client.is_playing():
            await ctx.message.reply("再生中の音楽がないのだ")
            logging.info("No music is playing")
            return
        
        logging.info("Stopping music")
        voice_client.stop()
        self.music_queue.clear()

        await ctx.message.reply("音楽を止めたのだ")
        logging.info("Music stopped")

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

        source = PCMVolumeTransformer(
            FFmpegPCMAudio(
                url2,
                before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            ),
            volume=0.01
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

        message = await ctx.message.channel.send(f"再生中なのだ👉 {title}")

        start_time = time.time()
        while voice_client.is_playing():
            elapsed_time = time.time() - start_time
            if elapsed_time > duration:
                break

            minutes, seconds = divmod(int(elapsed_time), 60)

            progress = elapsed_time / duration

            progress_bar_prefix = PROGRESS_BAR[8] * (int(progress * 20))
            progress_bar_suffix = PROGRESS_BAR[0] * (19 - int(progress * 20))

            progress_bar_middle = PROGRESS_BAR[int((progress * 20) % 1 * 8)]

            progress_bar = f"{progress_bar_prefix}{progress_bar_middle}{progress_bar_suffix} [ {minutes:02}:{seconds:02} / {duration // 60:02}:{duration % 60:02} ]"

            await message.edit(content=f"再生中なのだ👉 {title} \n{progress_bar}")
            await asyncio.sleep(0.8)

        await playback_finished.wait()
        logging.info(f"Finished playing: {title}")

    async def queue_playlist(self, ctx, url, shuffle=False):
        if url == '':
            await ctx.message.reply("プレイリストのURLを書くのだ。")
            logging.info("No URL provided")
            return

        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'skip_download': True,
            'force_generic_extractor': True,
        }

        logging.info("Extracting playlist info")
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as e:
            await ctx.message.reply("プレイリストが再生できなかったのだ・・・。\n%s" % e)
            return

        if 'entries' not in info:
            await ctx.message.reply("プレイリストが見つからなかったのだ・・・。")
            logging.info("No playlist found")
            return

        playlist_entries = info['entries']
        logging.info("Found playlist with %d entries", len(playlist_entries))

        if shuffle:
            random.shuffle(playlist_entries)
            logging.info("Shuffled playlist")

        for entry in playlist_entries:
            yt_item = {
                'url': entry['url'],
                'title': entry.get('title', 'Unknown title'),
                'duration': entry.get('duration', 0)
            }
            self.music_queue.append(yt_item)
            logging.info("Added to queue: [%s] %s (%s)", yt_item.get('duration'), yt_item.get('title'), yt_item.get('url'))

        await ctx.message.reply(f"{len(playlist_entries)} 曲を順番待ちに入れたのだ。")
        logging.info(f"Queued {len(playlist_entries)} songs from playlist: {playlist_entries}")

        voice_client = ctx.message.guild.voice_client
        if voice_client is None or not voice_client.is_playing():
            logging.info("No music is playing, starting playback")
            url = self.music_queue.pop(0)
            await self.stream_music(ctx, url)
