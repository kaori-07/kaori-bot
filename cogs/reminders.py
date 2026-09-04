import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import re
import uuid
from cogs.utils.emoji_manager import EMOJI
from cogs.utils.json_store import get_store

STORE_FILE = "reminders.json"
DURATION_RE = re.compile(r"(\d+)\s*(s|sec|secs|m|min|mins|h|hr|hrs|d|day|days|w|week|weeks)", re.IGNORECASE)
UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def parse_duration(text: str) -> datetime.timedelta | None:
    total = 0
    for amount, unit in DURATION_RE.findall(text):
        total += int(amount) * UNIT_SECONDS[unit[0].lower()]
    return datetime.timedelta(seconds=total) if total > 0 else None


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.store = get_store(STORE_FILE, dict)
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    @commands.hybrid_command(name="remindme", description="Set a reminder — e.g. /remindme 2h Check the oven")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def remindme(self, ctx: commands.Context, duration: str, *, reminder: str):
        delta = parse_duration(duration)
        if not delta:
            return await ctx.send(f"{EMOJI['error']} Couldn't parse that duration. Try things like `10m`, `2h`, `1d`.")
        if delta.total_seconds() > 60 * 60 * 24 * 30:
            return await ctx.send(f"{EMOJI['error']} Reminders can't be more than 30 days out.")

        due = datetime.datetime.utcnow() + delta
        rid = str(uuid.uuid4())

        def _mut(data):
            data[rid] = {
                "user_id": ctx.author.id,
                "channel_id": ctx.channel.id if ctx.guild else None,
                "text": reminder,
                "due": due.isoformat(),
                "sent": False,
            }
            return data
        self.store.mutate(_mut)

        await ctx.send(f"{EMOJI['bell']} Got it — I'll remind you in **{duration}**.")

    @commands.command(name="reminders", description="List your pending reminders.")
    async def reminders_list(self, ctx: commands.Context):
        mine = [(rid, r) for rid, r in self.store.read().items() if r["user_id"] == ctx.author.id and not r["sent"]]
        if not mine:
            return await ctx.send(f"{EMOJI['info']} You have no pending reminders.")
        embed = discord.Embed(title=f"{EMOJI['bell']} Your Reminders", color=discord.Color.blurple())
        for rid, r in mine[:15]:
            due = datetime.datetime.fromisoformat(r["due"])
            embed.add_field(name=discord.utils.format_dt(due, "R"), value=r["text"][:200], inline=False)
        await ctx.send(embed=embed)

    @tasks.loop(seconds=30)
    async def check_reminders(self):
        now = datetime.datetime.utcnow()
        data = self.store.read()
        due_ids = [rid for rid, r in data.items() if not r["sent"] and datetime.datetime.fromisoformat(r["due"]) <= now]
        for rid in due_ids:
            r = data[rid]
            user = self.bot.get_user(r["user_id"])
            if user:
                try:
                    await user.send(f"{EMOJI['bell']} Reminder: {r['text']}")
                except discord.HTTPException:
                    pass
            r["sent"] = True
        if due_ids:
            self.store.save(data)

    @check_reminders.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(Reminders(bot))
