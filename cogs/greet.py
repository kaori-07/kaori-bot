import discord
from discord import app_commands
from discord.ext import commands
from cogs.utils.emoji_manager import EMOJI
from cogs.utils.json_store import get_store

STORE_FILE = "greet.json"


class Greet(commands.Cog):
    """Welcome message for new members. Previously this was hardcoded to one
    specific server's name, channel ID, and an expired signed CDN image URL,
    and the on/off toggle lived only in memory (reset every restart). All of
    that is now per-guild, persisted, and generic by default."""

    def __init__(self, bot):
        self.bot = bot
        self.store = get_store(STORE_FILE, dict)

    def _guild_cfg(self, guild_id: int) -> dict:
        return self.store.read().get(str(guild_id), {"enabled": False, "channel_id": None})

    @commands.hybrid_command(name="greet", description="Toggle the welcome greeter on/off.")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def greet(self, ctx: commands.Context, mode: str = None):
        cfg = self._guild_cfg(ctx.guild.id)

        if mode is None:
            status = f"{EMOJI['success']} ON" if cfg["enabled"] else f"{EMOJI['error']} OFF"
            channel = ctx.guild.get_channel(cfg["channel_id"]) if cfg["channel_id"] else None
            embed = discord.Embed(title=f"{EMOJI['wave']} Welcome Greeter", color=discord.Color.blurple())
            embed.add_field(name="Status", value=status, inline=True)
            embed.add_field(name="Channel", value=channel.mention if channel else "*not set*", inline=True)
            embed.set_footer(text="Use ,greet on/off to toggle, or /greet_setchannel to set the channel")
            return await ctx.send(embed=embed)

        mode = mode.lower()
        if mode not in ("on", "off"):
            return await ctx.send(f"{EMOJI['error']} Usage: `,greet on` or `,greet off`")

        def _mut(data):
            entry = data.setdefault(str(ctx.guild.id), {"enabled": False, "channel_id": None})
            entry["enabled"] = (mode == "on")
            return data
        self.store.mutate(_mut)

        if mode == "on" and not cfg["channel_id"]:
            return await ctx.send(f"{EMOJI['success']} Greet is now **ON**, but no channel is set yet — run `/greet_setchannel` too.")
        await ctx.send(f"{EMOJI['success'] if mode == 'on' else EMOJI['no_entry']} Greet is now **{mode.upper()}**.")

    @commands.command(name="greet_setchannel", description="Set the channel welcome messages are posted to.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def greet_setchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        def _mut(data):
            entry = data.setdefault(str(ctx.guild.id), {"enabled": False, "channel_id": None})
            entry["channel_id"] = channel.id
            return data
        self.store.mutate(_mut)
        await ctx.send(f"{EMOJI['success']} Welcome messages will now be posted to {channel.mention}.")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = self._guild_cfg(member.guild.id)
        if not cfg["enabled"] or not cfg["channel_id"]:
            return

        channel = member.guild.get_channel(cfg["channel_id"])
        if not channel:
            return

        embed = discord.Embed(
            title=f"Welcome to {member.guild.name}!",
            description=(
                f"{EMOJI['party']} Welcome {member.mention} — glad to have you here!\n\n"
                f"You're member **#{member.guild.member_count}**. Enjoy your stay! {EMOJI['gem']}"
            ),
            color=discord.Color.purple(),
        )
        if member.guild.icon:
            embed.set_thumbnail(url=member.guild.icon.url)
        embed.set_footer(text=f"{member.guild.name} • {discord.utils.format_dt(member.joined_at or discord.utils.utcnow(), 'f')}")

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass


async def setup(bot):
    await bot.add_cog(Greet(bot))
