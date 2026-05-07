import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from datetime import timedelta
import json
import os

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.file_path = "mode.json"
        self.warnings = self.load_warnings()

    def load_warnings(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "r") as f:
                return json.load(f)
        return {}

    def save_warnings(self):
        with open(self.file_path, "w") as f:
            json.dump(self.warnings, f, indent=4)

    # -------------------------
    # Moderation commands
    # -------------------------
    @commands.hybrid_command(name="kick", description="Kick a member from the server.")
    @commands.has_permissions(kick_members=True)
    @app_commands.guild_only()
    async def kick(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        await member.kick(reason=reason)
        embed = discord.Embed(
            title="<a:Kick:1489189035736825866> Member Kicked",
            description=f"**{member}** was kicked by **{ctx.author}**.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="ban", description="Ban a member from the server.")
    @commands.has_permissions(ban_members=True)
    @app_commands.guild_only()
    async def ban(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        await member.ban(reason=reason)
        embed = discord.Embed(
            title="🔨 Member Banned",
            description=f"**{member}** was banned by **{ctx.author}**.",
            color=discord.Color.red()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="unban", description="Unban a user by their user ID.")
    @commands.has_permissions(ban_members=True)
    @app_commands.guild_only()
    async def unban(self, ctx, user_id: int):
        bans = await ctx.guild.bans()
        for entry in bans:
            if entry.user.id == user_id:
                await ctx.guild.unban(entry.user)
                embed = discord.Embed(
                    title="<a:tick:1489157731393994854> User Unbanned",
                    description=f"{entry.user.mention} was unbanned by {ctx.author.mention}.",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
                return
        await ctx.send(f"<a:Cross_:1489174755537064046> No banned user found with ID `{user_id}`.")

    @commands.hybrid_command(name="mute", description="Mute (timeout) a member for a set duration.")
    @commands.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def mute(self, ctx, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
        try:
            units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
            unit = duration[-1].lower()
            if unit not in units:
                return await ctx.send("<a:Cross_:1489174755537064046> Invalid duration format. Use `s`, `m`, `h`, or `d` (e.g., 10m, 1h).")
            time = int(duration[:-1]) * units[unit]
            until = discord.utils.utcnow() + timedelta(seconds=time)
            await member.edit(timed_out_until=until, reason=reason)
            embed = discord.Embed(
                title="🔇 Member Timed Out",
                description=f"**{member}** was muted by **{ctx.author}**.",
                color=discord.Color.blurple()
            )
            embed.add_field(name="Duration", value=duration, inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            await ctx.send(embed=embed)
        except ValueError:
            await ctx.send("<a:Cross_:1489174755537064046> Failed to parse duration. Use a number followed by s/m/h/d (e.g., `10m`).")
        except discord.Forbidden:
            await ctx.send("<a:Cross_:1489174755537064046> I do not have permission to mute that user.")

    @commands.hybrid_command(name="unmute", description="Unmute a member (remove timeout).")
    @commands.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def unmute(self, ctx, member: discord.Member):
        try:
            await member.edit(timed_out_until=None)
            embed = discord.Embed(
                title="🔈 Member Unmuted",
                description=f"{member.mention} was unmuted by {ctx.author.mention}.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("<a:Cross_:1489174755537064046> I do not have permission to unmute this user.")

    @commands.hybrid_command(name="warn", description="Warn a member. On 5 warnings, 24h timeout is applied.")
    @commands.has_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def warn(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        guild_id = str(ctx.guild.id)
        user_id = str(member.id)
        self.warnings.setdefault(guild_id, {})
        self.warnings[guild_id][user_id] = self.warnings[guild_id].get(user_id, 0) + 1
        warn_count = self.warnings[guild_id][user_id]
        self.save_warnings()

        embed = discord.Embed(
            title="<a:Alert1:1489188698191822908> Member Warned",
            description=f"**{member}** was warned by **{ctx.author}**.",
            color=discord.Color.yellow()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Total Warnings", value=str(warn_count), inline=False)
        await ctx.send(embed=embed)

        if warn_count >= 5:
            await member.edit(timed_out_until=discord.utils.utcnow() + timedelta(hours=24), reason="Reached 5 warnings")
            self.warnings[guild_id][user_id] = 0
            self.save_warnings()
            timeout_embed = discord.Embed(
                title="⏳ Member Timed Out",
                description=f"**{member}** has been timed out for 24 hours after 5 warnings.",
                color=discord.Color.red()
            )
            await ctx.send(embed=timeout_embed)

    @commands.hybrid_command(name="clear", description="Delete a number of messages in the current channel.")
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int = 10):
        await ctx.channel.purge(limit=amount)
        msg = await ctx.send(f"🧹 Cleared **{amount}** messages.")
        try:
            await asyncio.sleep(5)
            await msg.delete()
        except Exception:
            pass

    @commands.hybrid_command(name="lock", description="Lock the current channel.")
    @commands.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def lock(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, send_messages=False)
        embed = discord.Embed(
            title="🔒 Channel Locked",
            description=f"**{channel.mention}** was locked by **{ctx.author}**.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="unlock", description="Unlock the current channel.")
    @commands.has_permissions(administrator=True)
    @app_commands.guild_only()
    async def unlock(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, send_messages=True)
        embed = discord.Embed(
            title="🔓 Channel Unlocked",
            description=f"**{channel.mention}** was unlocked by **{ctx.author}**.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    # -------------------------
    # Error handlers
    # -------------------------
    async def cog_command_error(self, ctx, error):
        """Handle errors for prefix/hybrid commands."""
        original = getattr(error, "original", error)

        # User lacks permission to run command
        if isinstance(original, commands.MissingPermissions) or isinstance(error, commands.MissingPermissions):
            await ctx.send("not enough perm....")
            return

        # Generic check failure (covers cases like checks failing)
        if isinstance(error, commands.CheckFailure):
            await ctx.send("not enough perm....")
            return

        # Bot does not have required permissions
        if isinstance(original, commands.BotMissingPermissions) or isinstance(error, commands.BotMissingPermissions):
            await ctx.send("<a:Cross_:1489174755537064046> I do not have the required permissions to perform that action.")
            return

        # Fallback: optionally log the error to console
        # print(f"[Moderation Cog] Unhandled command error: {error}")
        return

    async def cog_app_command_error(self, interaction: discord.Interaction, error):
        """Handle errors for application (slash) commands."""
        original = getattr(error, "original", error)

        # User lacks permission to run command
        if isinstance(original, app_commands.MissingPermissions) or isinstance(error, app_commands.MissingPermissions):
            if not interaction.response.is_done():
                await interaction.response.send_message("not enough perm....", ephemeral=True)
            else:
                await interaction.followup.send("not enough perm....", ephemeral=True)
            return

        # Generic check failure for app commands
        if isinstance(error, app_commands.CheckFailure) or isinstance(original, app_commands.CheckFailure):
            if not interaction.response.is_done():
                await interaction.response.send_message("not enough perm....", ephemeral=True)
            else:
                await interaction.followup.send("not enough perm....", ephemeral=True)
            return

        # Bot missing permissions for app command
        if isinstance(original, app_commands.BotMissingPermissions) or isinstance(error, app_commands.BotMissingPermissions):
            if not interaction.response.is_done():
                await interaction.response.send_message("<a:Cross_:1489174755537064046> I do not have the required permissions to perform that action.", ephemeral=True)
            else:
                await interaction.followup.send("<a:Cross_:1489174755537064046> I do not have the required permissions to perform that action.", ephemeral=True)
            return

        # Fallback: optionally log or ignore
        # print(f"[Moderation Cog] Unhandled app command error: {error}")
        return

# Setup
async def setup(bot):
    await bot.add_cog(Moderation(bot))
