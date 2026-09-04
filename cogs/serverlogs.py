import discord
from discord.ext import commands
from discord import app_commands
import datetime
from cogs.utils.emoji_manager import EMOJI
from cogs.utils.json_store import get_store

STORE_FILE = "serverlogs.json"
DEFAULT_EVENTS = {
    "message_delete": True, "message_edit": True, "member_join": True,
    "member_leave": True, "role_change": True, "nickname_change": True,
    "voice_activity": True,
}


class ServerLogs(commands.Cog):
    """Posts an audit trail of common server events to a configured channel."""

    def __init__(self, bot):
        self.bot = bot
        self.store = get_store(STORE_FILE, dict)

    @property
    def data(self) -> dict:
        return self.store.read()

    def _guild_cfg(self, guild_id: int) -> dict:
        return self.data.get(str(guild_id), {"channel_id": None, "events": dict(DEFAULT_EVENTS)})

    async def _log(self, guild: discord.Guild, event: str, embed: discord.Embed):
        cfg = self._guild_cfg(guild.id)
        if not cfg.get("channel_id") or not cfg.get("events", {}).get(event, True):
            return
        channel = guild.get_channel(cfg["channel_id"])
        if not channel:
            return
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    @commands.hybrid_command(name="logs_setchannel", description="Set the channel server logs are posted to.")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def logs_setchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        def _mut(data):
            entry = data.setdefault(str(ctx.guild.id), {"channel_id": None, "events": dict(DEFAULT_EVENTS)})
            entry["channel_id"] = channel.id
            return data
        self.store.mutate(_mut)
        await ctx.send(f"{EMOJI['success']} Server logs will now be posted to {channel.mention}.")

    @commands.command(name="logs_toggle", description="Enable/disable a specific log event type.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def logs_toggle(self, ctx: commands.Context, event: str):
        event = event.lower()
        if event not in DEFAULT_EVENTS:
            return await ctx.send(f"{EMOJI['error']} Unknown event. Choose from: {', '.join(DEFAULT_EVENTS)}")

        def _mut(data):
            entry = data.setdefault(str(ctx.guild.id), {"channel_id": None, "events": dict(DEFAULT_EVENTS)})
            entry.setdefault("events", dict(DEFAULT_EVENTS))
            entry["events"][event] = not entry["events"].get(event, True)
            return data
        self.store.mutate(_mut)
        new_state = self._guild_cfg(ctx.guild.id)["events"][event]
        await ctx.send(f"{EMOJI['success']} `{event}` logging is now **{'on' if new_state else 'off'}**.")

    # ---------- listeners ----------
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild or not message.content:
            return
        embed = discord.Embed(title=f"{EMOJI['trash']} Message Deleted", color=discord.Color.red(), timestamp=datetime.datetime.utcnow())
        embed.add_field(name="Author", value=message.author.mention, inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        embed.add_field(name="Content", value=message.content[:1000] or "*empty*", inline=False)
        await self._log(message.guild, "message_delete", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content:
            return
        embed = discord.Embed(title=f"{EMOJI['scroll']} Message Edited", color=discord.Color.gold(), timestamp=datetime.datetime.utcnow())
        embed.add_field(name="Author", value=before.author.mention, inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Before", value=(before.content or "*empty*")[:512], inline=False)
        embed.add_field(name="After", value=(after.content or "*empty*")[:512], inline=False)
        await self._log(before.guild, "message_edit", embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(title=f"{EMOJI['wave']} Member Joined", color=discord.Color.green(), timestamp=datetime.datetime.utcnow())
        embed.add_field(name="User", value=f"{member.mention} ({member})", inline=False)
        embed.add_field(name="Account created", value=discord.utils.format_dt(member.created_at, "R"), inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._log(member.guild, "member_join", embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(title=f"{EMOJI['boot_kick']} Member Left", color=discord.Color.red(), timestamp=datetime.datetime.utcnow())
        embed.add_field(name="User", value=f"{member.mention} ({member})", inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)
        await self._log(member.guild, "member_leave", embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles != after.roles:
            added = [r for r in after.roles if r not in before.roles]
            removed = [r for r in before.roles if r not in after.roles]
            if added or removed:
                embed = discord.Embed(title=f"{EMOJI['tag']} Roles Updated", color=discord.Color.blurple(), timestamp=datetime.datetime.utcnow())
                embed.add_field(name="Member", value=after.mention, inline=False)
                if added:
                    embed.add_field(name="Added", value=", ".join(r.mention for r in added), inline=False)
                if removed:
                    embed.add_field(name="Removed", value=", ".join(r.mention for r in removed), inline=False)
                await self._log(after.guild, "role_change", embed)

        if before.nick != after.nick:
            embed = discord.Embed(title=f"{EMOJI['id_card']} Nickname Changed", color=discord.Color.blurple(), timestamp=datetime.datetime.utcnow())
            embed.add_field(name="Member", value=after.mention, inline=False)
            embed.add_field(name="Before", value=before.nick or "*none*", inline=True)
            embed.add_field(name="After", value=after.nick or "*none*", inline=True)
            await self._log(after.guild, "nickname_change", embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel == after.channel:
            return
        embed = discord.Embed(title=f"{EMOJI['speaker']} Voice Activity", color=discord.Color.teal(), timestamp=datetime.datetime.utcnow())
        if before.channel is None:
            embed.description = f"{member.mention} joined {after.channel.mention}"
        elif after.channel is None:
            embed.description = f"{member.mention} left {before.channel.mention}"
        else:
            embed.description = f"{member.mention} moved {before.channel.mention} → {after.channel.mention}"
        await self._log(member.guild, "voice_activity", embed)


async def setup(bot):
    await bot.add_cog(ServerLogs(bot))
