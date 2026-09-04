import discord
from discord.ext import commands
from discord import app_commands
import re
import time
from collections import defaultdict, deque
from cogs.utils.emoji_manager import EMOJI
from cogs.utils.json_store import get_store

STORE_FILE = "automod.json"
DEFAULT_CFG = {
    "enabled": False,
    "banned_words": [],
    "block_invites": False,
    "max_mentions": 5,
    "spam_msgs": 5,
    "spam_seconds": 5,
    "nickname_words": [],
    "min_account_age_days": 0,
    "raid_join_threshold": 10,
    "raid_join_seconds": 30,
    "raid_lockdown_active": False,
}
INVITE_RE = re.compile(r"(discord\.gg|discord(?:app)?\.com/invite)/\S+", re.IGNORECASE)


class AutoMod(commands.Cog):
    """Lightweight chat-level auto-moderation: bad words, invite links, mention spam, message flooding."""

    def __init__(self, bot):
        self.bot = bot
        self.store = get_store(STORE_FILE, dict)
        self._recent: dict[int, deque] = defaultdict(deque)
        self._recent_joins: dict[int, deque] = defaultdict(deque)

    @property
    def data(self) -> dict:
        return self.store.read()

    def _guild_cfg(self, guild_id: int) -> dict:
        return {**DEFAULT_CFG, **self.data.get(str(guild_id), {})}

    def _mut_cfg(self, guild_id: int, fn):
        def _mut(data):
            entry = {**DEFAULT_CFG, **data.get(str(guild_id), {})}
            fn(entry)
            data[str(guild_id)] = entry
            return data
        self.store.mutate(_mut)

    @commands.hybrid_command(name="automod_toggle", description="Turn auto-moderation on/off for this server.")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def automod_toggle(self, ctx: commands.Context):
        cfg = self._guild_cfg(ctx.guild.id)
        new_state = not cfg["enabled"]
        self._mut_cfg(ctx.guild.id, lambda e: e.update(enabled=new_state))
        await ctx.send(f"{EMOJI['success']} Auto-moderation is now **{'ON' if new_state else 'OFF'}**.")

    @commands.command(name="automod_addword", description="Add a word to the banned-word filter.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def automod_addword(self, ctx: commands.Context, *, word: str):
        word = word.lower().strip()
        self._mut_cfg(ctx.guild.id, lambda e: e["banned_words"].append(word) if word not in e["banned_words"] else None)
        await ctx.send(f"{EMOJI['success']} Added `{word}` to the filter.")

    @commands.command(name="automod_removeword", description="Remove a word from the banned-word filter.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def automod_removeword(self, ctx: commands.Context, *, word: str):
        word = word.lower().strip()
        self._mut_cfg(ctx.guild.id, lambda e: e["banned_words"].remove(word) if word in e["banned_words"] else None)
        await ctx.send(f"{EMOJI['success']} Removed `{word}` from the filter.")

    @commands.command(name="automod_invites", description="Toggle blocking Discord invite links.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def automod_invites(self, ctx: commands.Context):
        cfg = self._guild_cfg(ctx.guild.id)
        new_state = not cfg["block_invites"]
        self._mut_cfg(ctx.guild.id, lambda e: e.update(block_invites=new_state))
        await ctx.send(f"{EMOJI['success']} Blocking invite links is now **{'ON' if new_state else 'OFF'}**.")

    @commands.command(name="automod_settings", description="View this server's auto-moderation settings.")
    @commands.guild_only()
    async def automod_settings(self, ctx: commands.Context):
        cfg = self._guild_cfg(ctx.guild.id)
        embed = discord.Embed(title=f"{EMOJI['shield']} Auto-Moderation Settings", color=discord.Color.blurple())
        embed.add_field(name="Enabled", value=str(cfg["enabled"]), inline=True)
        embed.add_field(name="Block invites", value=str(cfg["block_invites"]), inline=True)
        embed.add_field(name="Max mentions/msg", value=str(cfg["max_mentions"]), inline=True)
        embed.add_field(name="Spam threshold", value=f"{cfg['spam_msgs']} msgs / {cfg['spam_seconds']}s", inline=True)
        embed.add_field(name="Banned words", value=str(len(cfg["banned_words"])), inline=True)
        embed.add_field(name="Nickname filter words", value=str(len(cfg["nickname_words"])), inline=True)
        embed.add_field(name="Min account age", value=f"{cfg['min_account_age_days']} day(s)" if cfg["min_account_age_days"] else "disabled", inline=True)
        embed.add_field(name="Raid threshold", value=f"{cfg['raid_join_threshold']} joins / {cfg['raid_join_seconds']}s", inline=True)
        embed.add_field(name="Raid lockdown", value=f"{EMOJI['warning']} ACTIVE" if cfg["raid_lockdown_active"] else "inactive", inline=True)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="automod_nickfilter", description="Add/remove a word blocked from nicknames (auto-resets on match).")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def automod_nickfilter(self, ctx: commands.Context, *, word: str):
        word = word.lower().strip()

        def _toggle(e):
            if word in e["nickname_words"]:
                e["nickname_words"].remove(word)
            else:
                e["nickname_words"].append(word)
        self._mut_cfg(ctx.guild.id, _toggle)
        now_in = word in self._guild_cfg(ctx.guild.id)["nickname_words"]
        await ctx.send(f"{EMOJI['success']} `{word}` is now {'blocked' if now_in else 'allowed'} in nicknames.")

    @commands.hybrid_command(name="automod_minage", description="Set minimum Discord account age (in days) required to talk. 0 disables it.")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def automod_minage(self, ctx: commands.Context, days: int):
        days = max(0, days)
        self._mut_cfg(ctx.guild.id, lambda e: e.update(min_account_age_days=days))
        await ctx.send(f"{EMOJI['success']} Minimum account age set to **{days}** day(s)." if days else f"{EMOJI['success']} Minimum account age check disabled.")

    @commands.hybrid_command(name="automod_raidconfig", description="Configure raid-join detection (auto-lockdown on mass joins).")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def automod_raidconfig(self, ctx: commands.Context, join_threshold: int, within_seconds: int):
        self._mut_cfg(ctx.guild.id, lambda e: e.update(raid_join_threshold=max(2, join_threshold), raid_join_seconds=max(5, within_seconds)))
        await ctx.send(f"{EMOJI['success']} Raid detection: lockdown triggers at **{join_threshold}** joins within **{within_seconds}s**.")

    @commands.command(name="automod_unlock", description="Manually lift an active raid lockdown.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def automod_unlock(self, ctx: commands.Context):
        self._mut_cfg(ctx.guild.id, lambda e: e.update(raid_lockdown_active=False))
        try:
            await ctx.guild.default_role.edit(permissions=ctx.guild.default_role.permissions)
        except discord.HTTPException:
            pass
        try:
            await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=None)
        except discord.HTTPException:
            pass
        await ctx.send(f"{EMOJI['unlocked']} Raid lockdown lifted for this channel. Check other channels if the lockdown covered more.")

    async def _punish(self, message: discord.Message, reason: str):
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        try:
            await message.channel.send(f"{EMOJI['warning']} {message.author.mention}, your message was removed: {reason}", delete_after=6)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.author.guild_permissions.manage_messages:
            return

        cfg = self._guild_cfg(message.guild.id)
        if not cfg["enabled"]:
            return

        if cfg["min_account_age_days"] > 0:
            age_days = (discord.utils.utcnow() - message.author.created_at).days
            if age_days < cfg["min_account_age_days"]:
                return await self._punish(message, f"your account must be at least {cfg['min_account_age_days']} day(s) old to chat here")

        content_lower = message.content.lower()

        if cfg["banned_words"] and any(w in content_lower for w in cfg["banned_words"]):
            return await self._punish(message, "banned word detected")

        if cfg["block_invites"] and INVITE_RE.search(message.content):
            return await self._punish(message, "invite links aren't allowed here")

        if len(message.mentions) > cfg["max_mentions"]:
            return await self._punish(message, "too many mentions")

        now = time.time()
        window = self._recent[message.author.id]
        window.append(now)
        while window and now - window[0] > cfg["spam_seconds"]:
            window.popleft()
        if len(window) > cfg["spam_msgs"]:
            return await self._punish(message, "sending messages too quickly")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.nick == after.nick and before.display_name == after.display_name:
            return
        cfg = self._guild_cfg(after.guild.id)
        if not cfg["enabled"] or not cfg["nickname_words"]:
            return
        name_lower = after.display_name.lower()
        if any(w in name_lower for w in cfg["nickname_words"]):
            try:
                await after.edit(nick=None, reason="AutoMod: nickname filter match")
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = self._guild_cfg(member.guild.id)
        if not cfg["enabled"] or cfg["raid_lockdown_active"]:
            return

        now = time.time()
        joins = self._recent_joins[member.guild.id]
        joins.append(now)
        while joins and now - joins[0] > cfg["raid_join_seconds"]:
            joins.popleft()

        if len(joins) < cfg["raid_join_threshold"]:
            return

        # raid threshold hit - lock the default role from sending messages server-wide
        self._mut_cfg(member.guild.id, lambda e: e.update(raid_lockdown_active=True))
        try:
            perms = member.guild.default_role.permissions
            perms.send_messages = False
            await member.guild.default_role.edit(permissions=perms, reason="AutoMod: raid detected")
        except discord.HTTPException:
            pass

        alert = (
            f"{EMOJI['warning']} **Raid detected** — {len(joins)} joins within {cfg['raid_join_seconds']}s. "
            f"Server-wide send permission for @everyone has been disabled. "
            f"Run `/automod_unlock` once things calm down."
        )
        for channel in member.guild.text_channels:
            perms = channel.permissions_for(member.guild.me)
            if perms.send_messages:
                try:
                    await channel.send(alert)
                except discord.HTTPException:
                    pass
                break


async def setup(bot):
    await bot.add_cog(AutoMod(bot))
