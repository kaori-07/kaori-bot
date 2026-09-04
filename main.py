# main.py
import os
import asyncio
import datetime
import logging
import sys
from typing import List, Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv

from cogs.utils.emoji_manager import EMOJI
from cogs.utils.cog_control import is_enabled
from cogs.utils.log_buffer import LOG_BUFFER
from cogs.utils.help_data import find_category
from cogs.utils.help_view import HelpView, build_home_embed, build_category_embed
from cogs.utils.json_store import get_store

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

PREFIX = os.getenv("PREFIX", ",")
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
    logger.addHandler(LOG_BUFFER)

    return logger

logger = setup_logger("KaoriBot", logging.DEBUG)

# -----------------------
# Bot Initialization
# -----------------------
bot = commands.AutoShardedBot(command_prefix=PREFIX, intents=intents, help_command=None)
bot._my_prefix = PREFIX
bot._started_at = datetime.datetime.utcnow()

# -----------------------
# Cog loader (respects cogs/utils/cog_control.py toggles set by the dashboard)
# -----------------------
async def load_cogs():
    cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")
    if not os.path.isdir(cogs_dir):
        logger.warning(f"No cogs folder found at {cogs_dir}. Creating one.")
        os.makedirs(cogs_dir, exist_ok=True)
        return

    for filename in sorted(os.listdir(cogs_dir)):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        stem = filename[:-3]
        cog_name = f"cogs.{stem}"

        if not is_enabled(stem):
            logger.warning(f"⏭️  Skipped {cog_name} (disabled via dashboard)")
            continue

        try:
            await bot.load_extension(cog_name)
            logger.info(f"✅ Loaded {cog_name}")
        except Exception as e:
            logger.exception(f"❌ Failed to load {cog_name}: {e}")


async def reload_all_cogs():
    """Used by the owner-only /reload command and the dashboard's restart button."""
    for ext in list(bot.extensions.keys()):
        try:
            await bot.unload_extension(ext)
        except Exception:
            logger.exception(f"Failed to unload {ext}")
    await load_cogs()

# -----------------------
# Command usage analytics (lightweight, for the dashboard)
# -----------------------
_usage_store = get_store("command_usage.json", dict)

@bot.before_invoke
async def _track_usage(ctx: commands.Context):
    def _mut(data):
        name = ctx.command.qualified_name if ctx.command else "unknown"
        guild_id = str(ctx.guild.id) if ctx.guild else "dm"
        data["total"] = data.get("total", 0) + 1
        data.setdefault("by_command", {})[name] = data.get("by_command", {}).get(name, 0) + 1
        data.setdefault("by_guild", {})[guild_id] = data.get("by_guild", {}).get(guild_id, 0) + 1
        return data
    _usage_store.mutate(_mut)


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
    # DM logging (no auto-reply, to avoid spamming users who just DM the bot)
    if message.guild is None and not message.author.bot:
        logger.info(f"📩 DM from {message.author} - {message.content!r}")
    await bot.process_commands(message)


# -----------------------
# Global error handler
# -----------------------
# Single source of truth for command errors across every cog. Any cog that
# used to define its own on_command_error listener has had that removed -
# discord.py dispatches on_command_error bot-wide regardless of which cog
# defines the listener, so having more than one caused duplicate replies.
@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    error = getattr(error, "original", error)

    if isinstance(error, commands.CommandNotFound):
        return  # silent - avoids noise for typos / other bots' prefixes

    if isinstance(error, commands.MissingRequiredArgument):
        return await ctx.send(f"{EMOJI['warning']} Missing argument: `{error.param.name}`. Check `/help` for usage.")

    if isinstance(error, commands.TooManyArguments):
        return await ctx.send(f"{EMOJI['warning']} Too many arguments for that command.")

    if isinstance(error, commands.BadArgument):
        return await ctx.send(f"{EMOJI['warning']} Invalid argument: {error}")

    if isinstance(error, commands.CommandOnCooldown):
        return await ctx.send(f"{EMOJI['clock']} That's on cooldown — try again in {error.retry_after:.1f}s.")

    if isinstance(error, commands.MissingPermissions):
        perms = ", ".join(error.missing_permissions)
        return await ctx.send(f"{EMOJI['locked']} You need the **{perms}** permission to do that.")

    if isinstance(error, commands.BotMissingPermissions):
        perms = ", ".join(error.missing_permissions)
        return await ctx.send(f"{EMOJI['locked']} I need the **{perms}** permission to do that.")

    if isinstance(error, commands.NoPrivateMessage):
        return await ctx.send(f"{EMOJI['warning']} That command can't be used in DMs.")

    if isinstance(error, commands.CheckFailure):
        return await ctx.send(f"{EMOJI['error']} {error}")

    if isinstance(error, discord.Forbidden):
        return await ctx.send(f"{EMOJI['locked']} I don't have permission to do that.")

    # Unexpected error — log full traceback to console, give the user a clean message
    logger.exception(f"Unhandled error in command '{getattr(ctx.command, 'qualified_name', '?')}'", exc_info=error)
    try:
        await ctx.send(f"{EMOJI['error']} Something went wrong running that command. The issue has been logged.")
    except Exception:
        pass


# -----------------------
# Help command (hybrid) — interactive dropdown panel
# -----------------------
@bot.hybrid_command(name="help", with_app_command=True, description="Shows the help menu with categories and commands.")
async def help(ctx: commands.Context, category: Optional[str] = None):
    """Displays the interactive help panel. Use `/help <category>` to jump straight to one."""
    prefix = bot._my_prefix if hasattr(bot, "_my_prefix") else ","

    if category:
        meta = find_category(category)
        if not meta:
            return await ctx.send(f"{EMOJI['error']} No category matching `{category}` found. Run `/help` to see the list.")
        embed = build_category_embed(bot, meta, prefix)
    else:
        embed = build_home_embed(bot, prefix)

    view = HelpView(bot, prefix, ctx.author.id)
    msg = await ctx.send(embed=embed, view=view)
    view.message = msg


@bot.command(name="reload", hidden=True)
@commands.is_owner()
async def reload_cmd(ctx: commands.Context):
    """Owner-only: hot-reload every cog (also respects newly toggled cogs)."""
    msg = await ctx.send(f"{EMOJI['loading']} Reloading all cogs...")
    await reload_all_cogs()
    try:
        await bot.tree.sync()
    except Exception:
        logger.exception("Failed to re-sync slash commands after reload")
    await msg.edit(content=f"{EMOJI['success']} Reloaded {len(bot.extensions)} cog(s).")


# -----------------------
# Optional: launch the web dashboard alongside the bot
# -----------------------
def maybe_start_dashboard():
    if os.getenv("DASHBOARD_ENABLED", "false").lower() not in ("1", "true", "yes"):
        return
    try:
        import threading
        from dashboard.app import create_app

        port = int(os.getenv("DASHBOARD_PORT", "5000"))
        host = os.getenv("DASHBOARD_HOST", "127.0.0.1")

        app = create_app(bot)

        def _run():
            app.run(host=host, port=port, debug=False, use_reloader=False)

        t = threading.Thread(target=_run, name="dashboard", daemon=True)
        t.start()
        logger.info(f"🌐 Dashboard running at http://{host}:{port}")
    except Exception:
        logger.exception("Failed to start web dashboard")


# -----------------------
# Startup / main
# -----------------------
async def main():
    async with bot:
        await load_cogs()
        maybe_start_dashboard()
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
