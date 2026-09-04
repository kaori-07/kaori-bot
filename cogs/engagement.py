import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import random
from cogs.utils.emoji_manager import EMOJI
from cogs.utils.json_store import get_store

BIRTHDAY_FILE = "birthdays.json"
MARRIAGE_FILE = "marriages.json"
ACHIEVEMENTS_FILE = "achievements.json"

NHIE_PROMPTS = [
    "never have I ever forgotten someone's name right after they told me",
    "never have I ever sung in the shower",
    "never have I ever pretended to be busy to avoid someone",
    "never have I ever laughed at the wrong moment",
    "never have I ever eaten food off the floor",
    "never have I ever talked to myself out loud",
]


class NHIEView(discord.ui.View):
    def __init__(self, prompt: str):
        super().__init__(timeout=60)
        self.prompt = prompt
        self.votes = {}
        self.message = None

    def build_embed(self) -> discord.Embed:
        have = sum(1 for v in self.votes.values() if v)
        havent = len(self.votes) - have
        embed = discord.Embed(title="🙈 Never Have I Ever", description=f"**{self.prompt.capitalize()}**", color=discord.Color.purple())
        embed.add_field(name="I have 🙋", value=str(have), inline=True)
        embed.add_field(name="I haven't 🙅", value=str(havent), inline=True)
        return embed

    async def _vote(self, interaction, value):
        self.votes[interaction.user.id] = value
        await interaction.response.edit_message(embed=self.build_embed())

    @discord.ui.button(label="I have", style=discord.ButtonStyle.success, emoji="🙋")
    async def have_btn(self, interaction, button):
        await self._vote(interaction, True)

    @discord.ui.button(label="I haven't", style=discord.ButtonStyle.secondary, emoji="🙅")
    async def havent_btn(self, interaction, button):
        await self._vote(interaction, False)


class MarriageProposalView(discord.ui.View):
    def __init__(self, proposer: discord.abc.User, target: discord.abc.User, store):
        super().__init__(timeout=120)
        self.proposer = proposer
        self.target = target
        self.store = store

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.target:
            await interaction.response.send_message(f"{EMOJI['error']} This proposal isn't for you.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success, emoji="💍")
    async def accept(self, interaction, button):
        def _mut(data):
            data[str(self.proposer.id)] = self.target.id
            data[str(self.target.id)] = self.proposer.id
            return data
        self.store.mutate(_mut)
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content=f"{EMOJI['party']} {self.proposer.mention} and {self.target.mention} are now married! 💍", view=self
        )

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger, emoji="💔")
    async def decline(self, interaction, button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content=f"💔 {self.target.mention} declined the proposal.", view=self)


class Engagement(commands.Cog):
    """Birthdays, server anniversaries, boost shoutouts, achievements,
    marriage, and Never Have I Ever."""

    def __init__(self, bot):
        self.bot = bot
        self.birthdays = get_store(BIRTHDAY_FILE, dict)
        self.marriages = get_store(MARRIAGE_FILE, dict)
        self.achievements = get_store(ACHIEVEMENTS_FILE, dict)

    async def cog_load(self):
        self.daily_check.start()

    def cog_unload(self):
        self.daily_check.cancel()

    def award(self, user_id: int, badge: str):
        def _mut(data):
            badges = data.setdefault(str(user_id), [])
            if badge not in badges:
                badges.append(badge)
            return data
        self.achievements.mutate(_mut)

    # ---------------- birthdays ----------------
    @commands.hybrid_command(name="setbirthday", description="Set your birthday (MM-DD) for the server to celebrate.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def setbirthday(self, ctx: commands.Context, month: int, day: int):
        try:
            datetime.date(2000, month, day)
        except ValueError:
            return await ctx.send(f"{EMOJI['error']} That's not a valid date.")

        def _mut(data):
            data[str(ctx.author.id)] = f"{month:02d}-{day:02d}"
            return data
        self.birthdays.mutate(_mut)
        await ctx.send(f"{EMOJI['success']} Birthday saved: **{month:02d}-{day:02d}**.")

    @commands.command(name="birthday_setchannel", description="Set the channel birthday announcements post to.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def birthday_setchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        def _mut(data):
            entry = data.setdefault("_guild_channels", {})
            entry[str(ctx.guild.id)] = channel.id
            return data
        self.birthdays.mutate(_mut)
        await ctx.send(f"{EMOJI['success']} Birthday shoutouts will post in {channel.mention}.")

    @tasks.loop(hours=24)
    async def daily_check(self):
        today = datetime.datetime.utcnow().strftime("%m-%d")
        birthdays = self.birthdays.read()
        guild_channels = birthdays.get("_guild_channels", {})

        birthday_users = [int(uid) for uid, bday in birthdays.items() if uid != "_guild_channels" and bday == today]
        if birthday_users:
            for guild in self.bot.guilds:
                channel_id = guild_channels.get(str(guild.id))
                if not channel_id:
                    continue
                channel = guild.get_channel(channel_id)
                if not channel:
                    continue
                for uid in birthday_users:
                    member = guild.get_member(uid)
                    if member:
                        try:
                            await channel.send(f"{EMOJI['party']} Happy Birthday {member.mention}! 🎂")
                        except discord.HTTPException:
                            pass

        # server anniversaries
        for guild in self.bot.guilds:
            for member in guild.members:
                if member.bot or not member.joined_at:
                    continue
                joined = member.joined_at
                years = datetime.datetime.utcnow().year - joined.year
                if years > 0 and joined.month == datetime.datetime.utcnow().month and joined.day == datetime.datetime.utcnow().day:
                    channel_id = guild_channels.get(str(guild.id))
                    channel = guild.get_channel(channel_id) if channel_id else None
                    if channel:
                        try:
                            await channel.send(f"{EMOJI['sparkle']} {member.mention} has been here **{years} year{'s' if years != 1 else ''}** today! 🎉")
                        except discord.HTTPException:
                            pass

    @daily_check.before_loop
    async def before_daily(self):
        await self.bot.wait_until_ready()

    # ---------------- boost tracker ----------------
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.premium_since is None and after.premium_since is not None:
            channel = after.guild.system_channel
            if channel:
                try:
                    await channel.send(f"{EMOJI['gem']} {after.mention} just boosted **{after.guild.name}**! Thank you! {EMOJI['party']}")
                except discord.HTTPException:
                    pass
            self.award(after.id, "booster")

    # ---------------- achievements ----------------
    @commands.hybrid_command(name="achievements", description="View your (or someone else's) earned badges.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def achievements_cmd(self, ctx: commands.Context, user: discord.User = None):
        user = user or ctx.author
        badges = self.achievements.read().get(str(user.id), [])
        embed = discord.Embed(title=f"{EMOJI['trophy']} {user.name}'s Achievements", color=discord.Color.gold())
        embed.description = "\n".join(f"• {b}" for b in badges) if badges else "*No badges yet.*"
        await ctx.send(embed=embed)

    # ---------------- marriage ----------------
    @commands.hybrid_command(name="marry", description="Propose marriage to another user.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def marry(self, ctx: commands.Context, user: discord.User):
        if user.bot or user.id == ctx.author.id:
            return await ctx.send(f"{EMOJI['error']} You can't marry that.")
        marriages = self.marriages.read()
        if str(ctx.author.id) in marriages:
            return await ctx.send(f"{EMOJI['error']} You're already married! Use `/divorce` first.")
        if str(user.id) in marriages:
            return await ctx.send(f"{EMOJI['error']} They're already married to someone else.")

        view = MarriageProposalView(ctx.author, user, self.marriages)
        await ctx.send(f"{EMOJI['gem']} {user.mention}, {ctx.author.mention} has proposed to you! Do you accept?", view=view)

    @commands.command(name="divorce", description="End your current marriage.")
    async def divorce(self, ctx: commands.Context):
        marriages = self.marriages.read()
        partner_id = marriages.get(str(ctx.author.id))
        if not partner_id:
            return await ctx.send(f"{EMOJI['error']} You're not married.")

        def _mut(data):
            data.pop(str(ctx.author.id), None)
            data.pop(str(partner_id), None)
            return data
        self.marriages.mutate(_mut)
        await ctx.send(f"{EMOJI['error']} You are now divorced. 💔")

    @commands.command(name="spouse", description="See who a user is married to.")
    async def spouse(self, ctx: commands.Context, user: discord.User = None):
        user = user or ctx.author
        partner_id = self.marriages.read().get(str(user.id))
        if not partner_id:
            return await ctx.send(f"{EMOJI['info']} {user.mention} isn't married.")
        await ctx.send(f"{EMOJI['gem']} {user.mention} is married to <@{partner_id}>.")

    # ---------------- Never Have I Ever ----------------
    @commands.command(name="nhie", description="Never Have I Ever — vote and see the results live.")
    async def nhie(self, ctx: commands.Context):
        prompt = random.choice(NHIE_PROMPTS)
        view = NHIEView(prompt)
        msg = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg


async def setup(bot):
    await bot.add_cog(Engagement(bot))
