import discord
from discord.ext import commands
from discord import app_commands
import psutil
import datetime
import platform
import humanize

class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = datetime.datetime.utcnow()

    def get_uptime(self):
        """Calculate bot uptime."""
        now = datetime.datetime.utcnow()
        delta = now - self.start_time
        return humanize.naturaldelta(delta)

    # Ping command
    @commands.hybrid_command(name="ping", description="Check the bot's latency.")
    async def ping(self, ctx: commands.Context):
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(title="<a:minecraft_block:1489165065566421104> Pong!", description=f"Latency: **{latency}ms**", color=discord.Color.green())
        await ctx.send(embed=embed)

    # Uptime command
    @commands.hybrid_command(name="uptime", description="Check how long the bot has been online.")
    async def uptime(self, ctx: commands.Context):
        embed = discord.Embed(title="⏱️ Bot Uptime", description=f"Bot has been online for **{self.get_uptime()}**.", color=discord.Color.blue())
        await ctx.send(embed=embed)

    # Server info command
    @commands.hybrid_command(name="serverinfo", description="Get details about the current server.")
    @app_commands.guild_only()
    async def serverinfo(self, ctx: commands.Context):
        guild = ctx.guild
        embed = discord.Embed(title="📊 Server Info", color=discord.Color.blue())
        embed.add_field(name="Server Name", value=guild.name, inline=True)
        embed.add_field(name="Server ID", value=guild.id, inline=True)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Created On", value=guild.created_at.strftime("%b %d, %Y"), inline=True)
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        await ctx.send(embed=embed)

    # User info command
    @commands.hybrid_command(name="userinfo", description="Get information about a user.")
    async def userinfo(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(title=f"👤 {member.name}'s Info", color=discord.Color.blue())
        embed.add_field(name="Username", value=member.name, inline=True)
        embed.add_field(name="User ID", value=member.id, inline=True)
        embed.add_field(name="Joined Server", value=member.joined_at.strftime("%b %d, %Y") if member.joined_at else "N/A", inline=True)
        embed.add_field(name="Account Created", value=member.created_at.strftime("%b %d, %Y"), inline=True)
        embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
        await ctx.send(embed=embed)

    # Bot info command
    @commands.hybrid_command(name="botinfo", description="Get information about the bot.")
    async def botinfo(self, ctx: commands.Context):
        embed = discord.Embed(title="🤖 Bot Info", description="Here is some information about the bot.", color=discord.Color.green())
        embed.add_field(name="Bot Name", value=self.bot.user.name, inline=True)
        embed.add_field(name="Bot ID", value=self.bot.user.id, inline=True)
        embed.add_field(name="Python Version", value=platform.python_version(), inline=True)
        embed.add_field(name="Discord.py Version", value=discord.__version__, inline=True)
        embed.add_field(name="Uptime", value=self.get_uptime(), inline=True)
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)
        await ctx.send(embed=embed)

    # Calculator command
    @commands.hybrid_command(name="calc", description="Evaluate a mathematical expression.")
    async def calc(self, ctx: commands.Context, *, expression: str):
        """Evaluates a math expression."""
        try:
            result = eval(expression, {"__builtins__": {}}, {})  # Safe eval
            embed = discord.Embed(title="🧮 Calculator", color=discord.Color.green())
            embed.add_field(name="📥 Expression", value=f"`{expression}`", inline=False)
            embed.add_field(name="📤 Result", value=f"`{result}`", inline=False)
            embed.set_footer(text="Powered by Python eval()", icon_url="https://cdn-icons-png.flaticon.com/512/2721/2721262.png")
            await ctx.send(embed=embed)
        except Exception:
            await ctx.send("<a:Cross_:1489174755537064046> Invalid mathematical expression.")

    # System stats command
    @commands.hybrid_command(name="sysinfo", description="Get system resource usage.")
    async def sysinfo(self, ctx: commands.Context):
        cpu_usage = psutil.cpu_percent(interval=1)
        ram_usage = psutil.virtual_memory().percent
        embed = discord.Embed(title="💻 System Info", color=discord.Color.purple())
        embed.add_field(name="CPU Usage", value=f"{cpu_usage}%", inline=True)
        embed.add_field(name="RAM Usage", value=f"{ram_usage}%", inline=True)
        await ctx.send(embed=embed)

    # Avatar command
    @commands.hybrid_command(name="avatar", description="Get a user's avatar.")
    async def avatar(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(title=f"🖼️ {member.name}'s Avatar", color=discord.Color.blue())
        embed.set_image(url=member.avatar.url if member.avatar else None)
        await ctx.send(embed=embed)

    # Invite command
    @commands.hybrid_command(name="invite", description="Get the bot's invite link.")
    async def invite(self, ctx: commands.Context):
        embed = discord.Embed(title="🔗 Bot Invite", description="Click the link below to invite the bot.", color=discord.Color.green())
        embed.add_field(name="Invite Link", value=f"[Click Here](https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&permissions=8&scope=bot+applications.commands)", inline=False)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Utility(bot))
