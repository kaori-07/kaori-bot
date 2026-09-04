import asyncio
import datetime
import re
import discord
from discord.ext import commands
from discord import app_commands
from datetime import timedelta
import json
import os
from cogs.utils.emoji_manager import EMOJI

# Escalation ladder: at each warning-count threshold, take the paired action.
# Falls back to nothing if a member's count doesn't hit any threshold yet.
WARN_LADDER = [
    (3, "timeout", timedelta(hours=1)),
    (5, "timeout", timedelta(hours=24)),
    (7, "kick", None),
    (10, "ban", None),
]


class DeleteCategoryConfirmView(discord.ui.View):
    """Safety gate for a fully destructive, irreversible action - deletes an
    entire category and every channel inside it."""

    def __init__(self, author: discord.abc.User):
        super().__init__(timeout=30)
        self.author = author
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message(f"{EMOJI['error']} Only the command author can confirm this.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

    @discord.ui.button(label="Delete Everything", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content=f"{EMOJI['loading']} Deleting category and channels...", embed=None, view=self)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="✖️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content=f"{EMOJI['error']} Cancelled — nothing was deleted.", embed=None, view=self)
        self.stop()

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        os.makedirs(data_dir, exist_ok=True)
        self.file_path = os.path.join(data_dir, "mode.json")
        self.warnings = self.load_warnings()

    def load_warnings(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "r") as f:
                return json.load(f)
        return {}

    def save_warnings(self):
        with open(self.file_path, "w") as f:
            json.dump(self.warnings, f, indent=4)

    def _cases(self, guild_id: str) -> list:
        """Case log lives alongside the legacy warning counters in the same
        file: {"<guild_id>": {"<user_id>": <count>, "_cases": [...]}}."""
        guild_data = self.warnings.setdefault(guild_id, {})
        return guild_data.setdefault("_cases", [])

    def _next_case_id(self, guild_id: str) -> int:
        cases = self._cases(guild_id)
        return (max((c["id"] for c in cases), default=0)) + 1

    # -------------------------
    # Moderation commands
    # -------------------------
    @commands.hybrid_command(name="kick", description="Kick a member from the server.")
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        await member.kick(reason=reason)
        embed = discord.Embed(
            title=f"{EMOJI['boot_kick']} Member Kicked",
            description=f"**{member}** was kicked by **{ctx.author}**.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="ban", description="Ban a member from the server.")
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        await member.ban(reason=reason)
        embed = discord.Embed(
            title=f"{EMOJI['hammer']} Member Banned",
            description=f"**{member}** was banned by **{ctx.author}**.",
            color=discord.Color.red()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="unban", description="Unban a user by their user ID.")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int):
        bans = await ctx.guild.bans()
        for entry in bans:
            if entry.user.id == user_id:
                await ctx.guild.unban(entry.user)
                embed = discord.Embed(
                    title=f"{EMOJI['success']} User Unbanned",
                    description=f"{entry.user.mention} was unbanned by {ctx.author.mention}.",
                    color=discord.Color.green()
                )
                await ctx.send(embed=embed)
                return
        await ctx.send(f"{EMOJI['error']} No banned user found with ID `{user_id}`.")

    @commands.hybrid_command(name="mute", description="Mute (timeout) a member for a set duration.")
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.has_permissions(moderate_members=True)
    async def mute(self, ctx, member: discord.Member, duration: str, *, reason: str = "No reason provided"):
        try:
            units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
            unit = duration[-1].lower()
            if unit not in units:
                return await ctx.send(f"{EMOJI['error']} Invalid duration format. Use `s`, `m`, `h`, or `d` (e.g., 10m, 1h).")
            time = int(duration[:-1]) * units[unit]
            until = discord.utils.utcnow() + timedelta(seconds=time)
            await member.edit(timed_out_until=until, reason=reason)
            embed = discord.Embed(
                title=f"{EMOJI['muted']} Member Timed Out",
                description=f"**{member}** was muted by **{ctx.author}**.",
                color=discord.Color.blurple()
            )
            embed.add_field(name="Duration", value=duration, inline=False)
            embed.add_field(name="Reason", value=reason, inline=False)
            await ctx.send(embed=embed)
        except ValueError:
            await ctx.send(f"{EMOJI['error']} Failed to parse duration. Use a number followed by s/m/h/d (e.g., `10m`).")
        except discord.Forbidden:
            await ctx.send(f"{EMOJI['error']} I do not have permission to mute that user.")

    @commands.hybrid_command(name="unmute", description="Unmute a member (remove timeout).")
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx, member: discord.Member):
        try:
            await member.edit(timed_out_until=None)
            embed = discord.Embed(
                title=f"{EMOJI['speaker_low']} Member Unmuted",
                description=f"{member.mention} was unmuted by {ctx.author.mention}.",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send(f"{EMOJI['error']} I do not have permission to unmute this user.")

    @commands.hybrid_command(name="warn", description="Warn a member. On 5 warnings, 24h timeout is applied.")
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.has_permissions(manage_roles=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str = "No reason provided"):
        guild_id = str(ctx.guild.id)
        user_id = str(member.id)
        self.warnings.setdefault(guild_id, {})
        self.warnings[guild_id][user_id] = self.warnings[guild_id].get(user_id, 0) + 1
        warn_count = self.warnings[guild_id][user_id]

        case_id = self._next_case_id(guild_id)
        self._cases(guild_id).append({
            "id": case_id, "type": "warn", "user_id": user_id, "moderator_id": str(ctx.author.id),
            "reason": reason, "timestamp": datetime.datetime.utcnow().isoformat(),
        })
        self.save_warnings()

        embed = discord.Embed(
            title=f"{EMOJI['warning']} Member Warned — Case #{case_id}",
            description=f"**{member}** was warned by **{ctx.author}**.",
            color=discord.Color.yellow()
        )
        embed.add_field(name="Reason", value=reason, inline=False)
        embed.add_field(name="Total Warnings", value=str(warn_count), inline=False)
        await ctx.send(embed=embed)

        # escalation ladder: take the highest-tier action this count now qualifies for
        matched = next((entry for entry in reversed(WARN_LADDER) if warn_count >= entry[0]), None)
        if matched and warn_count == matched[0]:
            _, action_type, duration = matched
            try:
                if action_type == "timeout":
                    await member.edit(timed_out_until=discord.utils.utcnow() + duration, reason=f"Reached {warn_count} warnings")
                    result_text = f"**{member}** has been timed out ({duration}) after reaching **{warn_count}** warnings."
                elif action_type == "kick":
                    await member.kick(reason=f"Reached {warn_count} warnings")
                    result_text = f"**{member}** has been kicked after reaching **{warn_count}** warnings."
                elif action_type == "ban":
                    await member.ban(reason=f"Reached {warn_count} warnings")
                    result_text = f"**{member}** has been banned after reaching **{warn_count}** warnings."
                else:
                    result_text = None

                if result_text:
                    self._cases(guild_id).append({
                        "id": self._next_case_id(guild_id), "type": f"auto_{action_type}", "user_id": user_id,
                        "moderator_id": "auto-escalation", "reason": f"Escalation at {warn_count} warnings",
                        "timestamp": datetime.datetime.utcnow().isoformat(),
                    })
                    self.save_warnings()
                    await ctx.send(embed=discord.Embed(title=f"{EMOJI['boot_kick']} Escalation Triggered", description=result_text, color=discord.Color.red()))
            except discord.Forbidden:
                await ctx.send(f"{EMOJI['error']} Warning logged, but I lack permission to apply the escalation action ({action_type}).")

    @commands.command(name="cases", description="View a member's moderation case history.")
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    async def cases(self, ctx, member: discord.Member):
        guild_id = str(ctx.guild.id)
        cases = [c for c in self._cases(guild_id) if c["user_id"] == str(member.id)]
        if not cases:
            return await ctx.send(f"{EMOJI['info']} No moderation cases on record for **{member}**.")

        embed = discord.Embed(title=f"{EMOJI['scroll']} Case History — {member}", color=discord.Color.blurple())
        for c in cases[-15:]:
            mod = "Auto-escalation" if c["moderator_id"] == "auto-escalation" else f"<@{c['moderator_id']}>"
            embed.add_field(
                name=f"Case #{c['id']} — {c['type']}",
                value=f"By {mod}\n{c['reason'][:200]}",
                inline=False,
            )
        embed.set_footer(text=f"{len(cases)} total case(s)")
        await ctx.send(embed=embed)

    @commands.command(name="deletecategory", aliases=['delcategory', 'clearcategory'])
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def deletecategory(self, ctx: commands.Context, category_id: int):
        """Delete a category and every channel inside it, by category ID. Irreversible — requires confirmation."""
        category = ctx.guild.get_channel(category_id)
        if not category or not isinstance(category, discord.CategoryChannel):
            return await ctx.send(f"{EMOJI['error']} No category found with ID `{category_id}` in this server.")

        channels = category.channels
        preview = "\n".join(f"• {'🔊' if isinstance(c, discord.VoiceChannel) else '#'}{c.name}" for c in channels[:20])
        if len(channels) > 20:
            preview += f"\n...and {len(channels) - 20} more"
        if not preview:
            preview = "*(empty category — no channels inside)*"

        embed = discord.Embed(
            title=f"{EMOJI['warning']} Confirm Category Deletion",
            description=(
                f"This will permanently delete the category **{category.name}** "
                f"and **{len(channels)}** channel(s) inside it:\n\n{preview}"
            ),
            color=discord.Color.red(),
        )
        embed.set_footer(text="This cannot be undone. Confirm within 30 seconds.")

        view = DeleteCategoryConfirmView(ctx.author)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()

        if not view.confirmed:
            return

        category_name = category.name
        deleted, failed = 0, 0
        for channel in list(category.channels):
            try:
                await channel.delete(reason=f"Category cleanup requested by {ctx.author}")
                deleted += 1
            except discord.HTTPException:
                failed += 1

        category_deleted = False
        try:
            await category.delete(reason=f"Category cleanup requested by {ctx.author}")
            category_deleted = True
        except discord.HTTPException:
            pass

        result = discord.Embed(
            title=f"{EMOJI['success']} Category Deleted" if category_deleted else f"{EMOJI['warning']} Partially Completed",
            description=f"**{category_name}**",
            color=discord.Color.green() if category_deleted else discord.Color.orange(),
        )
        result.add_field(name="Channels deleted", value=str(deleted), inline=True)
        if failed:
            result.add_field(name="Channels failed", value=str(failed), inline=True)
        if not category_deleted:
            result.add_field(name="Note", value="Failed to delete the category itself — check my permissions.", inline=False)

        # the channel the confirmation was posted in may have been deleted as
        # part of the cleanup, so the edit can legitimately fail here
        try:
            await msg.edit(content=None, embed=result, view=None)
        except discord.HTTPException:
            pass

    @commands.command(name="softban")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    async def softban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        """Ban then immediately unban a member — wipes their recent messages without a permanent ban."""
        try:
            await member.ban(reason=f"Softban: {reason}", delete_message_seconds=86400)
            await ctx.guild.unban(member, reason="Softban cleanup")
        except discord.Forbidden:
            return await ctx.send(f"{EMOJI['error']} I don't have permission to do that.")
        await ctx.send(f"{EMOJI['success']} Softbanned **{member}** — their recent messages were wiped, they can rejoin.")

    @commands.command(name="massban")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def massban(self, ctx: commands.Context, *, user_ids: str):
        """Ban a list of user IDs at once (space or comma separated)."""
        ids = [i.strip() for i in re.split(r"[,\s]+", user_ids) if i.strip().isdigit()]
        if not ids:
            return await ctx.send(f"{EMOJI['error']} No valid user IDs found.")

        banned, failed = 0, 0
        for uid in ids:
            try:
                await ctx.guild.ban(discord.Object(id=int(uid)), reason=f"Mass ban by {ctx.author}")
                banned += 1
            except discord.HTTPException:
                failed += 1

        embed = discord.Embed(title=f"{EMOJI['boot_kick']} Mass Ban Complete", color=discord.Color.red())
        embed.add_field(name="Banned", value=str(banned), inline=True)
        if failed:
            embed.add_field(name="Failed", value=str(failed), inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="lockdown")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    async def lockdown(self, ctx: commands.Context, mode: str = "toggle"):
        """Lock or unlock the current channel for @everyone. Usage: ,lockdown on/off/toggle"""
        overwrite = ctx.channel.overwrites_for(ctx.guild.default_role)
        mode = mode.lower()
        if mode == "toggle":
            new_state = not (overwrite.send_messages is False)
        else:
            new_state = mode not in ("on", "lock", "true")

        overwrite.send_messages = False if not new_state else None
        try:
            await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"Lockdown toggled by {ctx.author}")
        except discord.Forbidden:
            return await ctx.send(f"{EMOJI['error']} I don't have permission to edit channel permissions.")

        if new_state:
            await ctx.send(f"{EMOJI['unlocked']} This channel is now unlocked.")
        else:
            await ctx.send(f"{EMOJI['locked']} This channel is now locked — @everyone can't send messages.")

    @commands.hybrid_command(name="clear", description="Delete a number of messages in the current channel.")
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int = 10, user: discord.Member = None, contains: str = None):
        """Delete recent messages. Optionally filter by author and/or text they contain."""
        amount = max(1, min(amount, 200))

        def _check(m):
            if user and m.author.id != user.id:
                return False
            if contains and contains.lower() not in (m.content or "").lower():
                return False
            return True

        deleted = await ctx.channel.purge(limit=amount, check=_check if (user or contains) else None)
        desc = f"{EMOJI['broom']} Cleared **{len(deleted)}** message(s)."
        if user:
            desc += f" (from {user.mention})"
        if contains:
            desc += f" (containing `{contains}`)"
        msg = await ctx.send(desc)
        try:
            await asyncio.sleep(5)
            await msg.delete()
        except Exception:
            pass

    @commands.command(name="lock", description="Lock the current channel.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def lock(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, send_messages=False)
        embed = discord.Embed(
            title=f"{EMOJI['locked']} Channel Locked",
            description=f"**{channel.mention}** was locked by **{ctx.author}**.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    @commands.command(name="unlock", description="Unlock the current channel.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def unlock(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await channel.set_permissions(ctx.guild.default_role, send_messages=True)
        embed = discord.Embed(
            title=f"{EMOJI['unlocked']} Channel Unlocked",
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
            missing = ", ".join(original.missing_permissions) if hasattr(original, "missing_permissions") else "the required permission"
            await ctx.send(f"{EMOJI['locked']} You need **{missing}** to use this command.")
            return

        # Generic check failure (covers cases like checks failing)
        if isinstance(error, commands.CheckFailure):
            await ctx.send(f"{EMOJI['locked']} You don't have permission to use this command.")
            return

        # Bot does not have required permissions
        if isinstance(original, commands.BotMissingPermissions) or isinstance(error, commands.BotMissingPermissions):
            await ctx.send(f"{EMOJI['error']} I do not have the required permissions to perform that action.")
            return

        # Fallback: optionally log the error to console
        # print(f"[Moderation Cog] Unhandled command error: {error}")
        return

    async def cog_app_command_error(self, interaction: discord.Interaction, error):
        """Handle errors for application (slash) commands."""
        original = getattr(error, "original", error)

        # User lacks permission to run command
        if isinstance(original, app_commands.MissingPermissions) or isinstance(error, app_commands.MissingPermissions):
            missing = ", ".join(original.missing_permissions) if hasattr(original, "missing_permissions") else "the required permission"
            msg = f"{EMOJI['locked']} You need **{missing}** to use this command."
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return

        # Generic check failure for app commands
        if isinstance(error, app_commands.CheckFailure) or isinstance(original, app_commands.CheckFailure):
            msg = f"{EMOJI['locked']} You don't have permission to use this command."
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
            else:
                await interaction.followup.send(msg, ephemeral=True)
            return

        # Bot missing permissions for app command
        if isinstance(original, app_commands.BotMissingPermissions) or isinstance(error, app_commands.BotMissingPermissions):
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{EMOJI['error']} I do not have the required permissions to perform that action.", ephemeral=True)
            else:
                await interaction.followup.send(f"{EMOJI['error']} I do not have the required permissions to perform that action.", ephemeral=True)
            return

        # Fallback: optionally log or ignore
        # print(f"[Moderation Cog] Unhandled app command error: {error}")
        return

# Setup
async def setup(bot):
    await bot.add_cog(Moderation(bot))
