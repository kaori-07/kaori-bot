import discord
from discord.ext import commands
from discord import app_commands
import random
from datetime import datetime, timedelta
import humanize
from cogs.utils.emoji_manager import EMOJI
from cogs.utils.json_store import get_store

LEVELING_FILE = "leveling.json"


class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.store = get_store(LEVELING_FILE, dict)

    @property
    def data(self) -> dict:
        return self.store.read()

    def save_data(self):
        self.store.save(self.data)

    def get_user_level(self, user_id):
        user = self.data.get(str(user_id), {"level": 1, "xp": 0})
        return user["level"], user["xp"]

    def update_user_xp(self, user_id, xp_to_add):
        user_id = str(user_id)
        data = self.data
        if user_id not in data:
            data[user_id] = {"level": 1, "xp": 0}

        user_data = data[user_id]
        user_data["xp"] += xp_to_add
        level, xp = user_data["level"], user_data["xp"]

        xp_required = self.get_next_level_xp(level)
        leveled_up = False
        if xp >= xp_required:
            user_data["level"] += 1
            user_data["xp"] = 0
            leveled_up = True

        self.save_data()
        return leveled_up

    def get_next_level_xp(self, level):
        return level * 100

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        xp_earned = random.randint(5, 15)
        leveled_up = self.update_user_xp(message.author.id, xp_earned)
        if leveled_up:
            level = self.data[str(message.author.id)]["level"]
            embed = discord.Embed(
                title=f"{EMOJI['party']} Level Up!",
                description=f"Congrats {message.author.mention}, you reached level **{level}**!",
                color=discord.Color.purple()
            )
            try:
                await message.channel.send(embed=embed)
            except discord.HTTPException:
                pass

    @commands.hybrid_command(name="level", description="Check your level or another user's level.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def level(self, ctx, user: discord.User = None):
        user = user or ctx.author
        level, xp = self.get_user_level(user.id)
        next_level_xp = self.get_next_level_xp(level)
        embed = discord.Embed(
            title=f"{EMOJI['trophy']} {user.name}'s Level",
            description=f"{user.name} is level **{level}** with **{xp} XP**.\n"
                        f"XP to next level: **{next_level_xp - xp}**.",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(name="xp", description="Check the XP of you or another user.")
    async def xp(self, ctx, user: discord.User = None):
        user = user or ctx.author
        _, xp = self.get_user_level(user.id)
        embed = discord.Embed(
            title=f"{EMOJI['gem']} {user.name}'s XP",
            description=f"{user.name} has **{xp} XP**.",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=user.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="leaderboard", description="View the top 10 users by level.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def leaderboard(self, ctx):
        sorted_users = sorted(self.data.items(), key=lambda x: (x[1]["level"], x[1]["xp"]), reverse=True)[:10]
        if not sorted_users:
            return await ctx.send(f"{EMOJI['info']} No one has earned XP yet.")

        embed = discord.Embed(
            title=f"{EMOJI['trophy']} Level Leaderboard",
            description="Here are the top users by level:",
            color=discord.Color.gold()
        )
        for i, (user_id, udata) in enumerate(sorted_users, 1):
            try:
                user = self.bot.get_user(int(user_id)) or await self.bot.fetch_user(int(user_id))
                name = str(user)
            except (discord.NotFound, discord.HTTPException):
                name = f"Unknown User ({user_id})"
            embed.add_field(name=f"{i}. {name}", value=f"Level {udata['level']} - {udata['xp']} XP", inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="addxp", description="Admin-only: Add XP to a user.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def addxp(self, ctx, member: discord.Member, xp: int):
        self.update_user_xp(member.id, xp)
        embed = discord.Embed(
            title=f"{EMOJI['success']} XP Added",
            description=f"{xp} XP added to {member.name}.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command(name="work", description="Work every 1 hour to earn XP.")
    async def work(self, ctx):
        now = datetime.utcnow()
        last_work = self.data.get(str(ctx.author.id), {}).get("last_work", None)
        if last_work and now - datetime.strptime(last_work, "%Y-%m-%d %H:%M:%S") < timedelta(hours=1):
            remaining = datetime.strptime(last_work, "%Y-%m-%d %H:%M:%S") + timedelta(hours=1) - now
            embed = discord.Embed(
                title=f"{EMOJI['loading']} Cooldown",
                description=f"You can work again in **{humanize.naturaldelta(remaining)}**.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        xp_earned = random.randint(10, 50)
        leveled_up = self.update_user_xp(ctx.author.id, xp_earned)
        data = self.data
        data[str(ctx.author.id)]["last_work"] = now.strftime("%Y-%m-%d %H:%M:%S")
        self.save_data()

        embed = discord.Embed(
            title=f"{EMOJI['briefcase']} Work Complete",
            description=f"You earned **{xp_earned} XP** for working!",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

        if leveled_up:
            level = self.data[str(ctx.author.id)]["level"]
            level_up_embed = discord.Embed(
                title=f"{EMOJI['party']} Level Up!",
                description=f"Great job {ctx.author.mention}, you're now level **{level}**!",
                color=discord.Color.purple()
            )
            await ctx.send(embed=level_up_embed)

    @commands.command(name="daily", description="Claim a daily XP reward.")
    async def daily(self, ctx):
        now = datetime.utcnow()
        last_claim = self.data.get(str(ctx.author.id), {}).get("last_daily", None)

        if last_claim and now - datetime.strptime(last_claim, "%Y-%m-%d %H:%M:%S") < timedelta(days=1):
            next_time = datetime.strptime(last_claim, "%Y-%m-%d %H:%M:%S") + timedelta(days=1)
            remaining = next_time - now
            embed = discord.Embed(
                title=f"{EMOJI['error']} Already Claimed",
                description=f"Come back in **{humanize.naturaldelta(remaining)}** to claim again.",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed)

        reward_xp = random.randint(50, 200)
        leveled_up = self.update_user_xp(ctx.author.id, reward_xp)
        data = self.data
        data[str(ctx.author.id)]["last_daily"] = now.strftime("%Y-%m-%d %H:%M:%S")
        self.save_data()

        embed = discord.Embed(
            title=f"{EMOJI['gift']} Daily Reward",
            description=f"You earned **{reward_xp} XP** today!",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

        if leveled_up:
            level = self.data[str(ctx.author.id)]["level"]
            level_up_embed = discord.Embed(
                title=f"{EMOJI['party']} Level Up!",
                description=f"You reached level **{level}**!",
                color=discord.Color.purple()
            )
            await ctx.send(embed=level_up_embed)


async def setup(bot):
    await bot.add_cog(Leveling(bot))
