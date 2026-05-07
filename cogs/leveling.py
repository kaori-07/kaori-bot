import discord
from discord.ext import commands
import json
import random
from datetime import datetime, timedelta
import humanize

leveling_data = {}

class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.load_data()
        self.cooldowns = {}

    def load_data(self):
        try:
            with open("leveling.json", "r") as f:
                global leveling_data
                leveling_data = json.load(f)
        except FileNotFoundError:
            leveling_data = {}

    def save_data(self):
        with open("leveling.json", "w") as f:
            json.dump(leveling_data, f, indent=4)

    def get_user_level(self, user_id):
        user = leveling_data.get(str(user_id), {"level": 1, "xp": 0})
        return user["level"], user["xp"]

    def update_user_xp(self, user_id, xp_to_add):
        user_id = str(user_id)
        if user_id not in leveling_data:
            leveling_data[user_id] = {"level": 1, "xp": 0}

        user_data = leveling_data[user_id]
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
    async def on_message(self, message):
        if message.author.bot:
            return

        xp_earned = random.randint(5, 15)
        leveled_up = self.update_user_xp(message.author.id, xp_earned)
        if leveled_up:
            level = leveling_data[str(message.author.id)]["level"]
            embed = discord.Embed(
                title="<a:prizes:1489156992512557216> Level Up!",
                description=f"Congrats {message.author.mention}, you reached level **{level}**!",
                color=discord.Color.purple()
            )
            await message.channel.send(embed=embed)

    @commands.command(description="Check your level or another user's level.")
    async def level(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        level, xp = self.get_user_level(member.id)
        next_level_xp = self.get_next_level_xp(level)
        embed = discord.Embed(
            title=f"🏆 {member.name}'s Level",
            description=f"{member.name} is level **{level}** with **{xp} XP**.\n"
                        f"XP to next level: **{next_level_xp - xp}**.",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=member.avatar.url)
        await ctx.send(embed=embed)

    @commands.command(description="Check the XP of you or another user.")
    async def xp(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        _, xp = self.get_user_level(member.id)
        embed = discord.Embed(
            title=f"💎 {member.name}'s XP",
            description=f"{member.name} has **{xp} XP**.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command(description="View the top 5 users by level.")
    async def leaderboard(self, ctx):
        sorted_users = sorted(leveling_data.items(), key=lambda x: (x[1]["level"], x[1]["xp"]), reverse=True)[:5]
        embed = discord.Embed(
            title="🏆 Level Leaderboard",
            description="Here are the top 5 users by level:",
            color=discord.Color.gold()
        )
        for i, (user_id, data) in enumerate(sorted_users, 1):
            user = self.bot.get_user(int(user_id)) or await self.bot.fetch_user(int(user_id))
            embed.add_field(name=f"{i}. {user}", value=f"Level {data['level']} - {data['xp']} XP", inline=False)

        await ctx.send(embed=embed)

    @commands.command(description="Admin-only: Add XP to a user.")
    @commands.has_permissions(administrator=True)
    async def addxp(self, ctx, member: discord.Member, xp: int):
        self.update_user_xp(member.id, xp)
        embed = discord.Embed(
            title="<a:tick:1489157731393994854> XP Added",
            description=f"{xp} XP added to {member.name}.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command(description="Work every 1 hour to earn XP.")
    async def work(self, ctx):
        now = datetime.utcnow()
        last_work = leveling_data.get(str(ctx.author.id), {}).get("last_work", None)
        if last_work and now - datetime.strptime(last_work, "%Y-%m-%d %H:%M:%S") < timedelta(hours=1):
            remaining = datetime.strptime(last_work, "%Y-%m-%d %H:%M:%S") + timedelta(hours=1) - now
            embed = discord.Embed(
                title="⏳ Cooldown",
                description=f"You can work again in **{humanize.naturaldelta(remaining)}**.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        xp_earned = random.randint(10, 50)
        leveled_up = self.update_user_xp(ctx.author.id, xp_earned)
        leveling_data[str(ctx.author.id)]["last_work"] = now.strftime("%Y-%m-%d %H:%M:%S")
        self.save_data()

        embed = discord.Embed(
            title="💼 Work Complete",
            description=f"You earned **{xp_earned} XP** for working!",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

        if leveled_up:
            level = leveling_data[str(ctx.author.id)]["level"]
            level_up_embed = discord.Embed(
                title="<a:prizes:1489156992512557216> Level Up!",
                description=f"Great job {ctx.author.mention}, you're now level **{level}**!",
                color=discord.Color.purple()
            )
            await ctx.send(embed=level_up_embed)

    @commands.command(description="Claim a daily XP reward.")
    async def daily(self, ctx):
        now = datetime.utcnow()
        last_claim = leveling_data.get(str(ctx.author.id), {}).get("last_daily", None)

        if last_claim and now - datetime.strptime(last_claim, "%Y-%m-%d %H:%M:%S") < timedelta(days=1):
            next_time = datetime.strptime(last_claim, "%Y-%m-%d %H:%M:%S") + timedelta(days=1)
            remaining = next_time - now
            embed = discord.Embed(
                title="<a:Cross_:1489174755537064046> Already Claimed",
                description=f"Come back in **{humanize.naturaldelta(remaining)}** to claim again.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        reward_xp = random.randint(50, 200)
        leveled_up = self.update_user_xp(ctx.author.id, reward_xp)
        leveling_data[str(ctx.author.id)]["last_daily"] = now.strftime("%Y-%m-%d %H:%M:%S")
        self.save_data()

        embed = discord.Embed(
            title="<a:gift_:1489165623165583371> Daily Reward",
            description=f"You earned **{reward_xp} XP** today!",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

        if leveled_up:
            level = leveling_data[str(ctx.author.id)]["level"]
            level_up_embed = discord.Embed(
                title="<a:minecraft_block:1489165065566421104> Level Up!",
                description=f"You reached level **{level}**!",
                color=discord.Color.purple()
            )
            await ctx.send(embed=level_up_embed)

# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(Leveling(bot))
