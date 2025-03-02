import logging
from logging.handlers import TimedRotatingFileHandler
import os

import src.core as core
import src.system as system

# Configure logging
log_file_dir = "./log"
if not os.path.exists(log_file_dir):
    os.makedirs(log_file_dir)
log_file_path = log_file_dir + "/sora_log"
handler = TimedRotatingFileHandler(log_file_path, when="H", interval=1, backupCount=24 * 31)

system.log_file_dir = log_file_dir

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

logging.basicConfig(level=logging.INFO, handlers=[handler])

# Prepare bot token
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if DISCORD_BOT_TOKEN is None:
    raise ValueError("DISCORD_BOT_TOKEN environment variable is not set")

# Run the bot
core.bot.run(
    DISCORD_BOT_TOKEN,
    log_handler = handler,
    log_level = logging.DEBUG
)
