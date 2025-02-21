import os

import src.core as core

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if DISCORD_BOT_TOKEN is None:
    raise ValueError("DISCORD_BOT_TOKEN environment variable is not set")

core.bot.run(DISCORD_BOT_TOKEN)
