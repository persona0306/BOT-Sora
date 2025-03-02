import asyncio
import logging
import random
import threading
import time

from discord import FFmpegPCMAudio
from discord import PCMVolumeTransformer
from discord.ext import commands
import yt_dlp

QUEUE_SHOW_COUNT = 10

PROGRESS_BAR = ["▁", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]

PROGRESS_BAR_LENGTH = 15

class Music(commands.Cog):

    music_queue = []

    def __init__(self, bot):
        self.bot = bot
        self.play_loop_thread = threading.Thread(target=self.play_loop)
        self.play_loop_thread.start()
    
    @commands.command(
        name="insert",
        brief="音楽を検索して、順番待ちに割り込むのだ。",
        usage="sora insert <順番> <曲名>",
        help="""音楽を検索して、順番待ちに割り込むのだ。"""
    )
    async def insert(self, ctx):
        args = ctx.message.content[7 + len(self.bot.command_prefix):]
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
        query = ctx.message.content[5 + len(self.bot.command_prefix):]
        logging.info("music command called with arg: %s", query)

        if query == '':
            await ctx.message.reply("曲名を入れるのだ。")
            return

        yt_item = self.get_youtube_url(query)

        voice_client = ctx.message.guild.voice_client
        if not voice_client:
            await ctx.message.reply("ボクはまだVCに入ってないのだ。まずは「sora join」コマンドを使うのだ。")
            logging.info("Not connected to a voice channel")
            return
        
        if voice_client.is_playing():
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
        query = ctx.message.content[9 + len(self.bot.command_prefix):]
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
        usage="sora queue (<page>)",
        help="""順番待ちの曲を見るのだ。
ページを指定すると、そのページの曲を見るのだ。"""
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
        query = ctx.message.content[8 + len(self.bot.command_prefix):]

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
数字を2つ入れると、1番目の数字から、2番目の数字までの間を飛ばすのだ。
例: sora skip 3 で、3番目の曲を飛ばす。
例: sora skip 2 5 で、2番目から5番目までの4曲を飛ばす。
例: sora skip 1 9999 で、全曲を飛ばす。"""
    )
    async def skip(self, ctx):
        args = ctx.message.content[5 + len(self.bot.command_prefix):].split()
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
                if start_index >= len(self.music_queue):
                    skip_count = i
                    break
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

        page = 1
        arg = ctx.message.content[6 + len(self.bot.command_prefix):]
        if arg.isdigit():
            page = int(arg)
            if page < 1:
                page = 1
        
        queue_count = len(self.music_queue)
        
        if queue_count <= (page - 1) * QUEUE_SHOW_COUNT:
            await ctx.message.reply(f"そのページには曲がないのだ。({queue_count}曲しかないのだ。)")
            return

        max_page = (queue_count + QUEUE_SHOW_COUNT - 1) // QUEUE_SHOW_COUNT
        queue_message = f"👇順番待ちの曲なのだ ( {page} / {max_page} ページ )👇"
        for i, item in enumerate(
            self.music_queue,
            start = 1
        ):
            if i <= (page - 1) * QUEUE_SHOW_COUNT:
                continue

            if page * QUEUE_SHOW_COUNT <= i:
                queue_message += f"\n合計で{len(self.music_queue)}曲あるのだ。 ( {page} / {max_page} ページ )\n" \
                    f"次のページは 「sora queue {page + 1}」 で見るのだ。"
                break

            title = item['title']
            duration = item['duration']

            queue_message += f"\n{i}. [ {int(duration // 60):02}:{int(duration % 60):02} ] {title}"

        await ctx.message.reply(queue_message)

    async def stream_music(self, voice_client, item):
        url = item['url']

        logging.info("stream_music called with Music Item: %s", item)

        if url == '':
            logging.info("No URL provided")
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
            volume=0.03
        )

        playback_finished = asyncio.Event()

        def after_playing(error):
            if error:
                logging.error(f"Error while playing: {error}")
            playback_finished.set()

        logging.info("Playing music: [%s] %s (%s)", duration, title, url2)
        voice_client.play(source, after=after_playing)

        message = await self.bot.get_cog("VoiceClient").channel.send(f"再生中なのだ👉 {title}")

        start_time = time.time()
        while voice_client.is_playing():
            elapsed_time = time.time() - start_time
            if elapsed_time > duration:
                break

            minutes, seconds = divmod(int(elapsed_time), 60)

            progress = elapsed_time / duration

            progress_bar_prefix = PROGRESS_BAR[8] * (int(progress * PROGRESS_BAR_LENGTH))
            progress_bar_suffix = PROGRESS_BAR[0] * (PROGRESS_BAR_LENGTH - int(progress * PROGRESS_BAR_LENGTH) - 1)

            progress_bar_middle = PROGRESS_BAR[int((progress * PROGRESS_BAR_LENGTH) % 1 * 8)]

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

        enrty_count = len(playlist_entries)

        for entry in playlist_entries:
            if entry.get('duration') is None:
                enrty_count -= 1
                logging.info("Skipping invalid entry: %s", entry)
                continue

            yt_item = {
                'url': entry['url'],
                'title': entry.get('title', 'Unknown title'),
                'duration': entry.get('duration', 0)
            }
            self.music_queue.append(yt_item)
            logging.info("Added to queue: [%s] %s (%s)", yt_item.get('duration'), yt_item.get('title'), yt_item.get('url'))

        await ctx.message.reply(f"{enrty_count} 曲を順番待ちに入れたのだ。")
        logging.info(f"Queued {len(playlist_entries)} songs from playlist: {playlist_entries}")

    def play_loop(self):
        logging.info("Play loop started")
        while True:
            if not self.music_queue:
                time.sleep(1)
                continue

            voice_client = self.bot.voice_clients[0]
            if voice_client is None or voice_client.is_playing():
                time.sleep(1)
                continue

            logging.info("play_loop: Playing next music")
            url = self.music_queue.pop(0)
            asyncio.run_coroutine_threadsafe(self.stream_music(voice_client, url), self.bot.loop)
            while not voice_client.is_playing():
                time.sleep(1)
