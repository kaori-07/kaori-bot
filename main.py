import os
import asyncio
import logging
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Optional color support for console
try:
    from colorama import init as colorama_init, Fore, Style
    colorama_init(autoreset=True)
    COLORAMA_AVAILABLE = True
except Exception:
    COLORAMA_AVAILABLE = False

# -----------------------
# Configuration
# -----------------------
load_dotenv()
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN not found in .env")

PREFIX = ","
intents = discord.Intents.all()

# -----------------------
# Colored logger (console only)
# -----------------------
class ColoredFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: Fore.CYAN if COLORAMA_AVAILABLE else "",
        logging.INFO: Fore.GREEN if COLORAMA_AVAILABLE else "",
        logging.WARNING: Fore.YELLOW if COLORAMA_AVAILABLE else "",
        logging.ERROR: Fore.RED if COLORAMA_AVAILABLE else "",
        logging.CRITICAL: Fore.MAGENTA if COLORAMA_AVAILABLE else "",
    }

    def format(self, record):
        msg = super().format(record)
        if COLORAMA_AVAILABLE:
            color = self.LEVEL_COLORS.get(record.levelno, "")
            return f"{color}{msg}{Style.RESET_ALL}"
        return msg

def setup_logger(name="bot", level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.hasHandlers():
        logger.handlers.clear()

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    fmt = "[%(asctime)s] [%(levelname)s] %(message)s"
    ch.setFormatter(ColoredFormatter(fmt))
    logger.addHandler(ch)

    return logger

logger = setup_logger("KaoriBot", logging.DEBUG)

# -----------------------
# Bot Initialization
# -----------------------
bot = commands.AutoShardedBot(command_prefix=PREFIX, intents=intents, help_command=None)
bot._my_prefix = PREFIX

# -----------------------
# Cog loader
# -----------------------
async def load_cogs():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cogs_dir = os.path.join(base_dir, "cogs")
    
    if not os.path.isdir(cogs_dir):
        logger.warning(f"No cogs folder found at {cogs_dir}. Creating one.")
        os.makedirs(cogs_dir, exist_ok=True)
        return

    # os.walk goes through the main cogs folder AND all subfolders (like antinuke)
    for root, dirs, files in os.walk(cogs_dir):
        if "__pycache__" in root:
            continue
            
        for filename in sorted(files):
            if filename.endswith(".py"):
                file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(file_path, base_dir)
                
                # Convert path to dot notation (e.g., cogs.antinuke.antiban)
                cog_name = rel_path.replace(os.sep, ".")[:-3]
                
                try:
                    await bot.load_extension(cog_name)
                    logger.info(f"✅ Loaded {cog_name}")
                except commands.NoEntryPointError:
                    # If the file is missing the setup() function, it skips it safely instead of crashing
                    logger.warning(f"⚠️ Skipped {cog_name}: It is missing the 'async def setup(bot):' function at the bottom.")
                except Exception as e:
                    logger.exception(f"❌ Failed to load {cog_name}: {e}")

# -----------------------
# Events
# -----------------------
@bot.event
async def on_ready():
    logger.info(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        await bot.tree.sync()
        logger.info("✅ Synced global application (slash) commands")
    except Exception as e:
        logger.exception(f"Failed to sync slash commands: {e}")

@bot.event
async def on_message(message: discord.Message):
    if message.guild is None and not message.author.bot:
        try:
            await message.channel.send("Hello! I can respond to commands here.")
        except Exception:
            pass
    
    await bot.process_commands(message)

# -----------------------
# Startup / main
# -----------------------
async def main():
    async with bot:
        await load_cogs()
        logger.info("Starting bot...")
        try:
            await bot.start(TOKEN)
        except KeyboardInterrupt:
            logger.info("Received exit signal, shutting down...")
        except Exception:
            logger.exception("Bot crashed unexpectedly")
        finally:
            await bot.close()

if __name__ == "__main__":
    asyncio.run(main())