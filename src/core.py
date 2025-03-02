import asyncio
from logging.handlers import TimedRotatingFileHandler
import os
import random
import logging
from openai import OpenAI

import discord
from discord import Message
from discord.ext import commands

from .music import Music
from .system import System
from .voice_client import VoiceClient

from . import voice_client

# Configure logging
log_file_dir = "./log"

log_file_path = log_file_dir + "/sora_log"
handler = TimedRotatingFileHandler(log_file_path, when="H", interval=1, backupCount=24 * 31)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

logging.basicConfig(level=logging.INFO, handlers=[handler])

logging.info('''
========================================


Initializing BOT Sora CORE...


========================================''')

openai = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

AI_MAX_CONVERSATION_COUNT = 8

BOT_PROMPT = f"""一人称は「ボク」で、語尾に「のだ」を使ってずんだもんのように話す。
あなたは「BOT Sora」という。「ぺるそな(ぺる)」に作られたDiscordのBOTで、
pythonのdiscord.pyで動いて、VoiceVOXで声を出す。
Discordであなたに話しかけるには、「sora ai <話す内容>」とチャットする。
話せる最大文字数は{voice_client.MAX_SPEAK_LENGTH}文字だが、特に必要がなければ2行程度で話すのがよい。
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

@bot.event
async def on_ready():
    await bot.change_presence(
        activity=discord.Game(name="起動中..."),
        status=discord.Status.do_not_disturb
    )

    await bot.add_cog(Music(bot))
    await bot.add_cog(System(bot))
    await bot.add_cog(VoiceClient(bot))

    await bot.change_presence(
        activity=discord.Game(name="sora help"),
        status=discord.Status.online
    )

    logging.info("- BOT Sora Ready -")

@bot.event
async def on_message(message: Message):
    logging.info("Received message: %s", message.content)
    if message.author.bot:
        logging.info("Message from bot, ignoring.")
        return
    
    if message.content[:len(bot.command_prefix)].lower() == "sora ":
        logging.info("Message is a command, processing.")
        await bot.process_commands(message)
    else:
        logging.info("Message is not a command, processing as chat.")

        client = bot.get_cog("VoiceClient")

        logging.info("message.channel: %s", message.channel)
        logging.info("VoiceClient.channel: %s", client.channel)
        
        if message.channel != client.channel:
            logging.info("Message not in VoiceClient.channel, ignoring.")
            return
        await client.speak(message.content, message.guild)

@bot.command(
    name="ai",
    brief="ボクに話しかけるのだ。",
    category="チャット",
    aliases=["chat"],
    usage="sora ai <話す内容>",
    help=f"""ボクがChatGPTを使って返事するのだ。
会話の履歴は最大{AI_MAX_CONVERSATION_COUNT}つまで保存され、それ以上は古いものから消えるのだ。
{voice_client.MAX_SPEAK_LENGTH}文字以上はいっぺんに喋れないから、続きを話してほしいときはまたコマンドを使うのだ。"""
)
async def ai(ctx):
    content = ctx.message.content[7:]
    logging.info("AI command received with content: %s", content)

    conversation_history = bot.get_cog("VoiceClient").conversation_history

    # Add the new user message to the conversation history
    conversation_history.append({"role": "user", "content": content})
    logging.info("Updated conversation history: %s", conversation_history)

    # Keep only the last 4 exchanges (8 messages: 4 user + 4 bot)
    conversation_count = len(conversation_history)
    logging.info("Conversation history length: %s / %s", conversation_count, AI_MAX_CONVERSATION_COUNT)
    if conversation_count > AI_MAX_CONVERSATION_COUNT:
        conversation_history = conversation_history[-AI_MAX_CONVERSATION_COUNT:]
        logging.info("Trimmed conversation history: %s", conversation_history)    

    # Prepare the messages for the API request
    messages = [{"role": "system", "content": BOT_PROMPT}] + conversation_history
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

        client = bot.get_cog("VoiceClient")

        await client.speak(
            response_message,
            ctx.message.guild
        )
        
        # Add the bot's response to the conversation history
        conversation_history.append({"role": "assistant", "content": response_message})
        logging.info("Updated conversation history: %s", conversation_history)

    except Exception as e:
        logging.error("Error while communicating with OpenAI API: %s", e)
        await ctx.message.reply("エラーが発生したのだ・・・。もう一回言ってみてくれるのだ？")
        return

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
        client = bot.get_cog("VoiceClient")

        await client.speak(
            'だららららららららららららららら',
            channel.guild
        )
        await asyncio.sleep(3)
        await client.speak(
            'じゃん！',
            channel.guild
        )
        await asyncio.sleep(1)
        index = random.randrange(len(elements))
        await ctx.message.reply(elements[index])
        await client.speak(
            elements[index],
            channel.guild
        )

logging.info('''
========================================


Starting BOT Sora CORE!


========================================''')
