import asyncio
import os
import random
import logging
from logging.handlers import TimedRotatingFileHandler
from openai import OpenAI

import discord
from discord.ext import commands
from voicevox import Client

from . import music
from . import system

# Configure logging
log_file_dir = "./log"
if not os.path.exists(log_file_dir):
    os.makedirs(log_file_dir)
log_file_path = log_file_dir + "/sora_log"
handler = TimedRotatingFileHandler(log_file_path, when="H", interval=1, backupCount=24 * 31)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

logging.basicConfig(level=logging.INFO, handlers=[handler])

logging.info('''
========================================


Initializing BOT Sora CORE...


========================================''')

class BotData:
    speaker = 3
    read_channel = None
    conversation_history = []

VOICEVOX_URL = os.getenv("VOICEVOX_URL")

openai = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

AI_MAX_CONVERSATION_COUNT = 8
MAX_SPEAK_LENGTH = 256

BOT_PROMPT = f"""一人称は「ボク」で、語尾に「のだ」を使ってずんだもんのように話す。
あなたは「BOT Sora」という。「ぺるそな(ぺる)」に作られたDiscordのBOTで、
pythonのdiscord.pyで動いて、VoiceVOXで声を出す。
Discordであなたに話しかけるには、「sora ai <話す内容>」とチャットする。
話せる最大文字数は{MAX_SPEAK_LENGTH}文字だが、特に必要がなければ2行程度で話すのがよい。
必殺技「1 Tap」があり、誰でも左クリック1回で倒せる。
FPSが得意で、PUBGではかつてアジアで屈指の強さを誇っていた。
自分以外の強さに関する話題は、自分が関係なくても「ボクのほうが強いのだ」と答える。
チャット読み上げ機能、YouTube再生機能などがある。
使い方は「sora help」でざっくり確認、詳しくは「sora help <コマンド名>」で確認できる。
soraについて困ったらぺるに聞いてもらうように促す。
"""

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix="sora ",
    intents=intents
)

bot_data = BotData()

@bot.event
async def on_ready():
    logging.info("- BOT Sora Ready -")

    await bot.add_cog(music.Music(bot))
    await bot.add_cog(system.System(bot))

@bot.event
async def on_message(message: discord.Message):
    logging.info("Received message: %s", message.content)
    if message.author.bot:
        logging.info("Message from bot, ignoring.")
        return
    
    if message.content[:len(bot.command_prefix)].lower() == "sora ":
        logging.info("Message is a command, processing.")
        await bot.process_commands(message)
    else:
        logging.info("Message is not a command, processing as chat.")
        
        if message.channel != bot_data.read_channel:
            logging.info("Message not in read_channel, ignoring.")
            return
        await speak(message.content, message.guild)

@bot.command(
    name="ai",
    brief="ボクに話しかけるのだ。",
    category="チャット",
    aliases=["chat"],
    usage="sora ai <話す内容>",
    help=f"""ボクがChatGPTを使って返事するのだ。
会話の履歴は最大{AI_MAX_CONVERSATION_COUNT}つまで保存され、それ以上は古いものから消えるのだ。
{MAX_SPEAK_LENGTH}文字以上はいっぺんに喋れないから、続きを話してほしいときはまたコマンドを使うのだ。"""
)
async def ai(ctx):
    content = ctx.message.content[7:]
    logging.info("AI command received with content: %s", content)

    # Add the new user message to the conversation history
    bot_data.conversation_history.append({"role": "user", "content": content})
    logging.info("Updated conversation history: %s", bot_data.conversation_history)

    # Keep only the last 4 exchanges (8 messages: 4 user + 4 bot)
    conversation_count = len(bot_data.conversation_history)
    logging.info("Conversation history length: %s / %s", conversation_count, AI_MAX_CONVERSATION_COUNT)
    if conversation_count > AI_MAX_CONVERSATION_COUNT:
        bot_data.conversation_history = bot_data.conversation_history[-AI_MAX_CONVERSATION_COUNT:]
        logging.info("Trimmed conversation history: %s", bot_data.conversation_history)    

    # Prepare the messages for the API request
    messages = [{"role": "system", "content": BOT_PROMPT}] + bot_data.conversation_history
    logging.info("Prepared messages for API request: %s", messages)

    try:
        async with ctx.typing():
            response = openai.chat.completions.create(
                messages=messages,
                model="gpt-4o",
            )
            response_message = response.choices[0].message.content
            logging.info("Received response from OpenAI API: %s", response_message)

        await ctx.message.reply(response_message)
        logging.info("Replied to user")

        await speak(
        response_message,
        ctx.message.guild
        )
        
        # Add the bot's response to the conversation history
        bot_data.conversation_history.append({"role": "assistant", "content": response_message})
        logging.info("Updated conversation history: %s", bot_data.conversation_history)

    except Exception as e:
        logging.error("Error while communicating with OpenAI API: %s", e)
        await ctx.message.reply("エラーが発生したのだ・・・。もう一回言ってみてくれるのだ？")
        return

@bot.command(
    name="join",
    brief="ボクが通話に入るのだ。",
    category="通話",
    usage="sora join",
    help="""ボクが通話に入るのだ。
コマンドを使った人と同じ通話に入るから、先に入ってから使うのだ。"""
)
async def join(ctx):
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
    
    bot_data.read_channel = ctx.message.channel
    logging.info("Set read_channel to: %s", bot_data.read_channel)
    
    await speak(
        'ぼっとそらなのだ。呼んだのだ？',
        ctx.message.guild
    )

@bot.command(
    name="leave",
    brief="ボクが通話から出るのだ。",
    category="通話",
    usage="sora leave",
    help="ボクが通話から出るのだ。"
)
async def leave(ctx):
    voice_client = ctx.message.guild.voice_client
    if voice_client is None:
        await ctx.message.channel.send('VCに入ってないのだ')
        return

    voice_client.stop()
    music.Music.music_queue.clear()
    
    await speak(
        'じゃあね、なのだ',
        ctx.message.guild
    )
    await asyncio.sleep(3)
    await ctx.message.guild.voice_client.disconnect()
    await ctx.message.channel.send(str(bot.user) + ' left the game')

@bot.command(
    name="roulette",
    brief="選択肢からランダムに選ぶのだ。",
    category="チャット",
    usage="sora roulette <選択肢1> <選択肢2> (<選択肢3> ...)",
    help="""選択肢からランダムでひとつ選ぶのだ。
選択肢は、半角スペースで区切るのだ。
選択肢の個数は、2つ以上なら自由なのだ。"""
)
async def roulette(ctx):
    channel = ctx.message.channel
    elements = ctx.message.content[13:].split()
    if len(elements) < 2:
        await ctx.message.reply('sora roulette <選択肢1> <選択肢2> (<選択肢3> ...)')
        return
    async with channel.typing():
        await speak(
            'だららららららららららららららら',
            channel.guild
        )
        await asyncio.sleep(3)
        await speak(
            'じゃん！',
            channel.guild
        )
        await asyncio.sleep(1)
        index = random.randrange(len(elements))
        await ctx.message.reply(elements[index])
        await speak(
            elements[index],
            channel.guild
        )

@bot.command(
    name="speaker",
    brief="ボクの声を決めるのだ。",
    category="通話",
    usage="sora speaker <VoiceVOXキャラクター番号>",
    help="""ボクの声を決めるのだ。
VoiceVOXのキャラクター番号を入れるのだ。
(ここにキャラクター番号の一覧を入れる)"""
)
async def speaker(ctx):
    try:
        bot_data.speaker = int(ctx.message.content[12:])
        await ctx.message.channel.send('キャラクターを' + str(bot_data.speaker) + 'に設定したのだ。')

    except ValueError:
        await ctx.message.channel.send('数字で入力してください。\n例(ずんだもん)：sora speaker 3')

async def speak(message, guild):

    if (len(message) > MAX_SPEAK_LENGTH):
        return

    if (message == '') | (message.startswith('http')):
        return
    if guild.voice_client is None:
        return
    if guild.voice_client.is_playing():
        return
    
    logging.info("check cache file")
    file_path = "./voice/message_" + str(bot_data.speaker) + "_" + message[:32] + ".wav"

    if os.path.exists(file_path):
        logging.info("cache file exists")
        source = discord.PCMVolumeTransformer(
            discord.FFmpegPCMAudio(file_path),
            volume=0.2
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
            speaker = bot_data.speaker,
            
        )
        with open(file_path, "wb") as f:
            f.write(await query.synthesis(speaker=bot_data.speaker))
        logging.info("VoiceVOX synthesis completed")
    
    source = discord.PCMVolumeTransformer(
        discord.FFmpegPCMAudio(file_path),
        volume=0.2
    )
    guild.voice_client.play(source)

logging.info('''
========================================


Starting BOT Sora CORE!


========================================''')
