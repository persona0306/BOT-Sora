import asyncio
import logging
import random

from discord.ext import commands
import yt_dlp

class Music(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
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

        insert_query = args_parts[1]
        logging.info("Insert command called with index: %d and query: %s", insert_index, insert_query)

        yt_item = self.get_youtube_info(insert_query)
        self.bot.get_cog("VoiceClient").audio.add_youtube_source(
            url = yt_item['url'],
            title = yt_item['title'],
            duration = yt_item['duration'],
            position = insert_index
        )

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
        logging.info("play command called with arg: %s", query)

        if query == '':
            await ctx.message.reply("曲名を入れるのだ。")
            return

        voice_client = ctx.message.guild.voice_client
        if not voice_client:
            await ctx.message.reply("ボクはまだVCに入ってないのだ。まずは「sora join」コマンドを使うのだ。")
            logging.info("Not connected to a voice channel")
            return
        
        async def queue():
            logging.info("getting youtube url")
            yt_item = await self.get_youtube_info(query)

            logging.info("Calling voiceclient to add youtube source")
            self.bot.get_cog("VoiceClient").audio.add_youtube_source(
                url = yt_item['url'],
                title = yt_item['title'],
                duration = yt_item['duration']
            )
            await ctx.message.reply(f"曲を再生するのだ: {yt_item.get('title')}")
            logging.info("Queued music: %s (%s)", yt_item.get('title'), yt_item.get('url'))

        asyncio.run_coroutine_threadsafe(
            queue(),
            self.bot.loop
        )

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

        asyncio.run_coroutine_threadsafe(
            self.queue_playlist(ctx, query, shuffle),
            self.bot.loop
        )

    @commands.command(
        name="queue",
        brief="順番待ちの曲を見るのだ。",
        usage="sora queue (<page>)",
        help="""順番待ちの曲を見るのだ。
ページを指定すると、そのページの曲を見るのだ。"""
    )
    async def queue(self, ctx):
        asyncio.run_coroutine_threadsafe(
            self.bot.get_cog("VoiceClient").show_queue(ctx),
            self.bot.loop
        )

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
            self.bot.get_cog("VoiceClient").audio.shuffle()
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
            self.bot.get_cog("VoiceClient").audio.skip()
            logging.info("Skipping current music")

            if self.bot.get_cog("VoiceClient").audio.queue_music:
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

            success_skip_count = self.bot.get_cog("VoiceClient").audio.skip(start_index, skip_count)

            logging.info("Skipped %d songs", success_skip_count)

            await ctx.message.reply(f"キューの曲を {success_skip_count}曲 消したのだ。")

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
        self.bot.get_cog("VoiceClient").audio.skip(0, 99999)
        self.bot.get_cog("VoiceClient").audio.skip()

        await ctx.message.reply("音楽を止めたのだ")
        logging.info("Music stopped")

    async def get_youtube_info(self, query):
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
    
        return video

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

            url = entry['url']
            title = entry['title']
            duration = entry['duration']

            self.bot.get_cog("VoiceClient").audio.add_youtube_source(url, title, duration)
            logging.info(f"Added music source to VoiceClient: [%s] %s (%s)", duration, title, url)

        await ctx.message.reply(f"{enrty_count} 曲を順番待ちに入れたのだ。")
        logging.info(f"Queued {len(playlist_entries)} songs from playlist: {playlist_entries}")
