import os
import logging
import zipfile
import subprocess
import sys
from discord.ext import commands
import discord

from . import core

class System(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(
        name="log",
        brief="ログファイルを送信するのだ。",
        category="システム",
        usage="sora log [start_datetime] [end_datetime]",
        help="""ログファイルを送信するのだ。
        オプションで開始日時と終了日時を指定できるのだ。
        日時の形式は 'MMDDHH' なのだ。"""
    )
    async def log(self, ctx):
        logging.info("log command called")

        log_files = []
        for root, dirs, files in os.walk(core.log_file_dir):
            for file in files:
                file_path = os.path.join(root, file)
                log_files.append(file_path)
        
        logging.info("log_files: %s", log_files)

        logging.info("Creating zip file...")

        zip_file_path = os.path.join(core.log_file_dir, "sora_logs.zip")
        with zipfile.ZipFile(zip_file_path, 'w') as zipf:
            for log_file in log_files:
                zipf.write(log_file, os.path.basename(log_file) + ".txt")

        logging.info("Sending zip file...")

        await ctx.message.channel.send(file=discord.File(zip_file_path))

        logging.info("Removing zip file...")

        os.remove(zip_file_path)

        logging.info("log command completed")

    @commands.command(
        name="reboot",
        brief="ボクを再起動するのだ。",
        category="システム",
        usage="sora reboot",
        help="""ボクを再起動するのだ。
        そもそも起動していないと再起動できないから、
        ボクがオフラインになってたら、ぺるに聞くのだ。"""
    )
    async def reboot(self, ctx):
        await ctx.message.reply("再起動するのだ")
        if ctx.message.guild.voice_client is not None:
            await ctx.message.guild.voice_client.disconnect()
        self.bot.voice_clients.clear()
        self.bot.clear()
        
        command = f"{sys.executable} {' '.join(sys.argv)}"
        subprocess.Popen(command, shell=True)

        os._exit(0)

    @commands.command(
        name="update",
        brief="ボクを更新するのだ。",
        category="システム",
        usage="sora update",
        help="""ボクを更新するのだ。
        Gitリポジトリから最新の変更を取得するのだ。
        branchを指定しなければ、mainを使うのだ。
        取得したら、自動で再起動するのだ。"""
    )
    async def update(self, ctx):
        args = ctx.message.content.split()
        branch = args[2] if len(args) > 2 else "main"
        await ctx.message.reply(f"更新を開始するのだ... (ブランチ: {branch})")
        
        try:
            result = subprocess.run(["git", "pull", "origin", branch], capture_output=True, text=True)
            if result.returncode == 0:
                await ctx.message.reply("更新できたのだ！")
                await self.reboot(ctx)
            else:
                await ctx.message.reply(f"更新に失敗したのだ・・・。\n{result.stderr}")
        except Exception as e:
            await ctx.message.reply(f"更新中にエラーが発生したのだ・・・。\n{e}")

def setup(bot):
    bot.add_cog(System(bot))