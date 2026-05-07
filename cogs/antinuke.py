import discord
from discord.ext import commands
import aiosqlite
import asyncio
import datetime
from datetime import timedelta
import pytz
import random
import os

class antinuke(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.event_limits = {}
        self.cooldowns = {}
        self.spam_cache = {} # Used for anti-spam tracking

    async def cog_load(self):
        """Ensures the folders and databases exist on startup."""
        os.makedirs('db', exist_ok=True)
        async with aiosqlite.connect('db/anti.db') as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS antinuke (guild_id TEXT PRIMARY KEY, status INTEGER)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS extraowners (guild_id TEXT, owner_id TEXT)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS whitelisted_users (
                                guild_id TEXT, user_id TEXT, chcr INTEGER, chdl INTEGER, chup INTEGER,
                                mngstemo INTEGER, meneve INTEGER, memup INTEGER, ban INTEGER, kick INTEGER, 
                                prune INTEGER, botadd INTEGER, rlcr INTEGER, rldl INTEGER, rlup INTEGER, 
                                serverup INTEGER, mngweb INTEGER)''')
            await db.commit()

        async with aiosqlite.connect('db/block.db') as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS guild_blacklist (guild_id TEXT PRIMARY KEY)''')
            await db.commit()

    # ==========================================
    # CUSTOM PERMISSION CHECKS
    # ==========================================
    def is_server_owner():
        """Custom check to ensure ONLY the server owner can run specific commands."""
        async def predicate(ctx):
            if ctx.author.id != ctx.guild.owner_id and not await ctx.bot.is_owner(ctx.author):
                embed = discord.Embed(title="<a:Cross_:1489174755537064046> Access Denied", description="Only the Server Owner can use this command.", color=discord.Color.red())
                await ctx.send(embed=embed, ephemeral=True)
                return False
            return True
        return commands.check(predicate)

    # ==========================================
    # CORE HELPER METHODS & LOGGING
    # ==========================================

    async def send_log(self, guild, action_title, description, user, color=discord.Color.red()):
        """Automatically creates a log channel and sends rich embeds."""
        log_channel = discord.utils.get(guild.channels, name="🛡️・anti-nuke-logs")
        
        # Auto-create log channel if it doesn't exist
        if not log_channel:
            try:
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
                    guild.owner: discord.PermissionOverwrite(read_messages=True)
                }
                log_channel = await guild.create_text_channel("🛡️・anti-nuke-logs", overwrites=overwrites, reason="Auto-created for Antinuke Logging")
            except Exception:
                return # Give up if bot lacks permissions to create channel

        embed = discord.Embed(title=f"<a:Alert1:1489188698191822908> {action_title}", description=description, color=color, timestamp=discord.utils.utcnow())
        embed.add_field(name="Offender", value=f"{user.mention} (`{user.id}`)", inline=True)
        embed.set_thumbnail(url=user.display_avatar.url if user.display_avatar else None)
        embed.set_footer(text="Automated Security System", icon_url=self.bot.user.display_avatar.url)
        
        try:
            await log_channel.send(embed=embed)
        except Exception:
            pass

    async def is_blacklisted_guild(self, guild_id):
        async with aiosqlite.connect('db/block.db') as block_db:
            cursor = await block_db.execute("SELECT 1 FROM guild_blacklist WHERE guild_id = ?", (str(guild_id),))
            return await cursor.fetchone() is not None

    def can_fetch_audit(self, guild_id, event_name, max_requests=5, interval=10, cooldown_duration=300):
        now = datetime.datetime.now()
        self.event_limits.setdefault(guild_id, {}).setdefault(event_name, []).append(now)
        timestamps = self.event_limits[guild_id][event_name]
        timestamps = [t for t in timestamps if (now - t).total_seconds() <= interval]
        self.event_limits[guild_id][event_name] = timestamps

        if guild_id in self.cooldowns and event_name in self.cooldowns[guild_id]:
            if (now - self.cooldowns[guild_id][event_name]).total_seconds() < cooldown_duration: return False
            del self.cooldowns[guild_id][event_name]

        if len(timestamps) > max_requests:
            self.cooldowns.setdefault(guild_id, {})[event_name] = now
            return False
        return True

    async def fetch_audit_logs(self, guild, action, target_id=None, delay=0.0):
        try:
            if delay > 0: await asyncio.sleep(delay)
            async for entry in guild.audit_logs(action=action, limit=1):
                if target_id is not None and entry.target.id != target_id: continue
                now = datetime.datetime.now(pytz.utc)
                if (now - entry.created_at).total_seconds() * 1000 >= 3600000: return None
                return entry
        except discord.HTTPException as e:
            if e.status == 429:
                await asyncio.sleep(float(e.response.headers.get('Retry-After', 1.0)))
                return await self.fetch_audit_logs(guild, action, target_id, delay)
        except Exception: pass
        return None

    async def check_permissions(self, guild, executor_id, module_col):
        if executor_id in {guild.owner_id, self.bot.user.id}: return True
        async with aiosqlite.connect('db/anti.db') as db:
            async with db.execute("SELECT status FROM antinuke WHERE guild_id = ?", (str(guild.id),)) as cursor:
                status = await cursor.fetchone()
                if not status or not status[0]: return True # System is off

            async with db.execute("SELECT owner_id FROM extraowners WHERE guild_id = ? AND owner_id = ?", (str(guild.id), str(executor_id))) as cursor:
                if await cursor.fetchone(): return True 

            query = f"SELECT {module_col} FROM whitelisted_users WHERE guild_id = ? AND user_id = ?"
            try:
                async with db.execute(query, (str(guild.id), str(executor_id))) as cursor:
                    whitelist = await cursor.fetchone()
                    if whitelist and whitelist[0]: return True 
            except aiosqlite.OperationalError: pass
        return False 

    async def execute_punishment(self, guild, user, reason, action="ban"):
        retries = 3
        success = False
        while retries > 0 and not success:
            try:
                if action == "ban":
                    await guild.ban(user, reason=reason)
                elif action == "kick":
                    await guild.kick(user, reason=reason)
                elif action == "timeout":
                    await user.edit(timed_out_until=discord.utils.utcnow() + timedelta(minutes=2), reason=reason)
                success = True
            except discord.HTTPException as e:
                if e.status == 429:
                    await asyncio.sleep(float(e.response.headers.get('Retry-After', 1.0)))
                    retries -= 1
                else: break
            except Exception: break
        
        if success:
            action_emoji = "🔨" if action == "ban" else "<a:Kick:1489189035736825866>" if action == "kick" else "⏳"
            await self.send_log(guild, f"{action_emoji} User Punished: {action.capitalize()}", f"**Reason:** {reason}\n**Status:** Successfully protected the server.", user)
        return success

    # ==========================================
    # COMMANDS (Toggle, Status, & Whitelist)
    # ==========================================

    @commands.hybrid_command(name="antinuke_toggle", description="Turn the Antinuke system ON or OFF")
    @commands.has_permissions(administrator=True)
    async def antinuke_toggle(self, ctx):
        async with aiosqlite.connect('db/anti.db') as db:
            async with db.execute("SELECT status FROM antinuke WHERE guild_id = ?", (str(ctx.guild.id),)) as cursor:
                row = await cursor.fetchone()
            
            if row:
                new_status = 0 if row[0] else 1
                await db.execute("UPDATE antinuke SET status = ? WHERE guild_id = ?", (new_status, str(ctx.guild.id)))
            else:
                new_status = 1
                await db.execute("INSERT INTO antinuke (guild_id, status) VALUES (?, ?)", (str(ctx.guild.id), new_status))
            await db.commit()

        state = "Enabled <a:tick:1489157731393994854>" if new_status else "Disabled <a:Cross_:1489174755537064046>"
        color = discord.Color.green() if new_status else discord.Color.red()
        embed = discord.Embed(title="🛡️ Shield Status Updated", description=f"The Antinuke System is now **{state}**.", color=color)
        await ctx.send(embed=embed)
        if new_status:
            await self.send_log(ctx.guild, "🛡️ System Enabled", "The anti-nuke shield was turned on.", ctx.author, discord.Color.green())

    @commands.hybrid_command(name="antinuke_status", description="Check the status of the Antinuke system")
    @commands.has_permissions(administrator=True)
    async def antinuke_status(self, ctx):
        async with aiosqlite.connect('db/anti.db') as db:
            async with db.execute("SELECT status FROM antinuke WHERE guild_id = ?", (str(ctx.guild.id),)) as cursor:
                status = await cursor.fetchone()
                
        state = "Enabled <a:tick:1489157731393994854>" if status and status[0] else "Disabled <a:Cross_:1489174755537064046>"
        color = discord.Color.green() if status and status[0] else discord.Color.red()
        embed = discord.Embed(title="🛡️ Antinuke Status", description=f"The system is currently **{state}**.\n\n*Use `/antinuke_toggle` to change this.\nUse `/whitelist` to allow specific users.*", color=color)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="whitelist", description="Whitelist a user so the bot ignores their actions.")
    @is_server_owner()
    async def whitelist_user(self, ctx, user: discord.Member):
        async with aiosqlite.connect('db/anti.db') as db:
            await db.execute("DELETE FROM whitelisted_users WHERE guild_id = ? AND user_id = ?", (str(ctx.guild.id), str(user.id)))
            await db.execute("""INSERT INTO whitelisted_users 
                (guild_id, user_id, chcr, chdl, chup, mngstemo, meneve, memup, ban, kick, prune, botadd, rlcr, rldl, rlup, serverup, mngweb) 
                VALUES (?, ?, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1)""", (str(ctx.guild.id), str(user.id)))
            await db.commit()
            
        embed = discord.Embed(title="<a:tick:1489157731393994854> User Whitelisted", description=f"{user.mention} is now fully whitelisted and can bypass the antinuke.", color=discord.Color.green())
        await ctx.send(embed=embed)
        await self.send_log(ctx.guild, "<a:tick:1489157731393994854> Whitelist Added", f"{user.mention} was whitelisted by {ctx.author.mention}.", user, discord.Color.green())

    @commands.hybrid_command(name="unwhitelist", description="Remove a user from the whitelist.")
    @is_server_owner()
    async def unwhitelist_user(self, ctx, user: discord.Member):
        async with aiosqlite.connect('db/anti.db') as db:
            await db.execute("DELETE FROM whitelisted_users WHERE guild_id = ? AND user_id = ?", (str(ctx.guild.id), str(user.id)))
            await db.commit()
            
        embed = discord.Embed(title="<a:Cross_:1489174755537064046> Whitelist Removed", description=f"{user.mention} has been removed from the whitelist.", color=discord.Color.red())
        await ctx.send(embed=embed)
        await self.send_log(ctx.guild, "<a:Cross_:1489174755537064046> Whitelist Removed", f"{user.mention}'s whitelist was removed by {ctx.author.mention}.", user, discord.Color.orange())

    @commands.hybrid_command(name="trust_admin", description="Add an extra owner to the bot's highest trust tier.")
    @is_server_owner()
    async def add_extra_owner(self, ctx, user: discord.Member):
        async with aiosqlite.connect('db/anti.db') as db:
            await db.execute("INSERT INTO extraowners (guild_id, owner_id) VALUES (?, ?)", (str(ctx.guild.id), str(user.id)))
            await db.commit()
        embed = discord.Embed(title="👑 Admin Trusted", description=f"{user.mention} is now considered an Extra Owner.", color=discord.Color.gold())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="untrust_admin", description="Remove an extra owner.")
    @is_server_owner()
    async def remove_extra_owner(self, ctx, user: discord.Member):
        async with aiosqlite.connect('db/anti.db') as db:
            await db.execute("DELETE FROM extraowners WHERE guild_id = ? AND owner_id = ?", (str(ctx.guild.id), str(user.id)))
            await db.commit()
        embed = discord.Embed(title="🛑 Trust Removed", description=f"{user.mention} is no longer an Extra Owner.", color=discord.Color.red())
        await ctx.send(embed=embed)

    # ==========================================
    # ANTI-SPAM & EVERYONE LISTENERS
    # ==========================================

    @commands.Cog.listener()
    async def on_message(self, message):
        guild = message.guild
        if not guild or message.author.bot: return

        # 1. Anti-Everyone Ping
        if message.mention_everyone:
            if not self.can_fetch_audit(guild.id, 'mention_everyone') or await self.check_permissions(guild, message.author.id, "meneve"): return
            try:
                await message.author.edit(timed_out_until=discord.utils.utcnow() + timedelta(hours=1), reason="Mentioned Everyone/Here | Unwhitelisted User")
                await self.send_log(guild, "⏳ User Muted (1 Hour)", f"**Reason:** Attempted mass ping (@everyone/@here)", message.author)
                async for msg in message.channel.history(limit=100):
                    if msg.mention_everyone: await msg.delete()
            except Exception: pass
            return

        # 2. Anti-Spam (Timeout 2 Mins)
        if await self.check_permissions(guild, message.author.id, "meneve"): return # Ignore whitelisted users for spam

        now = datetime.datetime.now()
        user_cache = self.spam_cache.setdefault(guild.id, {}).setdefault(message.author.id, [])
        user_cache.append(now)
        
        # Clean cache to last 4 seconds
        self.spam_cache[guild.id][message.author.id] = [t for t in user_cache if (now - t).total_seconds() <= 4]
        
        # If 5 messages in 4 seconds -> Spam detected
        if len(self.spam_cache[guild.id][message.author.id]) >= 5:
            self.spam_cache[guild.id][message.author.id] = [] # Reset cache
            await self.execute_punishment(guild, message.author, "Anti-Spam: Sending messages too quickly", action="timeout")
            try:
                # Delete the spam messages
                async for msg in message.channel.history(limit=10):
                    if msg.author.id == message.author.id: await msg.delete()
            except Exception: pass

    # ==========================================
    # CHANNEL LISTENERS
    # ==========================================

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        guild = channel.guild
        if await self.is_blacklisted_guild(guild.id) or not self.can_fetch_audit(guild.id, "channel_create", max_requests=6): return
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.channel_create, channel.id, delay=2)
        if not logs or await self.check_permissions(guild, logs.user.id, "chcr"): return
        
        try: await channel.delete(reason="Channel created by unwhitelisted user")
        except: pass
        await self.execute_punishment(guild, logs.user, "Channel Create | Unwhitelisted User", action="ban")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        guild = channel.guild
        if await self.is_blacklisted_guild(guild.id) or not self.can_fetch_audit(guild.id, "channel_delete"): return
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.channel_delete, channel.id)
        if not logs or await self.check_permissions(guild, logs.user.id, "chdl"): return

        try:
            new_channel = await channel.clone(reason="Channel Delete | Unwhitelisted User")
            await new_channel.edit(position=channel.position)
        except: pass
        await self.execute_punishment(guild, logs.user, "Channel Delete | Unwhitelisted User", action="ban")

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        guild = before.guild
        if await self.is_blacklisted_guild(guild.id) or not self.can_fetch_audit(guild.id, "channel_update"): return
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.channel_update, after.id)
        if not logs or await self.check_permissions(guild, logs.user.id, "chup"): return

        try: await after.edit(name=before.name, topic=before.topic, position=before.position, nsfw=before.nsfw, bitrate=getattr(before, 'bitrate', None), user_limit=getattr(before, 'user_limit', None), reason="Channel Update | Unwhitelisted User")
        except: pass
        await self.execute_punishment(guild, logs.user, "Channel Update | Unwhitelisted User", action="ban")

    # ==========================================
    # EMOJI & STICKER LISTENERS
    # ==========================================

    @commands.Cog.listener("on_guild_emojis_update")
    async def anti_emoji_all(self, guild, before, after):
        action = discord.AuditLogAction.emoji_update
        if len(after) > len(before): action = discord.AuditLogAction.emoji_create
        elif len(after) < len(before): action = discord.AuditLogAction.emoji_delete

        logs = await self.fetch_audit_logs(guild, action, delay=random.uniform(0.5, 1.5))
        if not logs or await self.check_permissions(guild, logs.user.id, "mngstemo"): return
        await self.execute_punishment(guild, logs.user, "Emoji Action | Unwhitelisted User", action="kick")

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild, before, after):
        action = discord.AuditLogAction.sticker_update
        if len(after) > len(before): action = discord.AuditLogAction.sticker_create
        elif len(after) < len(before): action = discord.AuditLogAction.sticker_delete

        logs = await self.fetch_audit_logs(guild, action, delay=1.0)
        if not logs or await self.check_permissions(guild, logs.user.id, "mngstemo"): return
        await self.execute_punishment(guild, logs.user, "Sticker Action | Unwhitelisted User", action="kick")

    # ==========================================
    # MEMBER LISTENERS
    # ==========================================

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        guild = before.guild
        if await self.is_blacklisted_guild(guild.id) or not self.can_fetch_audit(guild.id, 'member_update'): return
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.member_role_update, after.id)
        if not logs or await self.check_permissions(guild, logs.user.id, "memup"): return

        try: new_role = next(role for role in after.roles if role not in before.roles)
        except StopIteration: return

        if any([new_role.permissions.ban_members, new_role.permissions.administrator, new_role.permissions.manage_guild, new_role.permissions.manage_channels, new_role.permissions.manage_roles, new_role.permissions.mention_everyone, new_role.permissions.manage_webhooks]):
            try: await after.remove_roles(new_role, reason="Member Role Update with Dangerous Permissions | Unwhitelisted User")
            except: pass
            await self.execute_punishment(guild, logs.user, "Member Role Update with Dangerous Permissions", action="ban")

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        if not self.can_fetch_audit(guild.id, "member_ban"): return
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.ban, user.id)
        if not logs or await self.check_permissions(guild, logs.user.id, "ban"): return
        
        if await self.execute_punishment(guild, logs.user, "Member Ban | Unwhitelisted User", action="ban"):
            try: await guild.unban(user, reason="Reverting ban by unwhitelisted user")
            except: pass

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.unban, user.id)
        if not logs or await self.check_permissions(guild, logs.user.id, "ban"): return

        if await self.execute_punishment(guild, logs.user, "Member Unban | Unwhitelisted User", action="ban"):
            try: await guild.ban(user, reason="Reverting unban by unwhitelisted user")
            except: pass

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if not member.bot: return
        guild = member.guild
        if not self.can_fetch_audit(guild.id, "bot_add"): return
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.bot_add, member.id)
        if not logs or await self.check_permissions(guild, logs.user.id, "botadd"): return

        await self.execute_punishment(guild, member, "Unwhitelisted user added a bot", action="kick")
        await self.execute_punishment(guild, logs.user, "Unwhitelisted user added a bot", action="ban")

    @commands.Cog.listener("on_member_remove")
    async def anti_kick_prune_listener(self, member):
        guild = member.guild
        if await self.is_blacklisted_guild(guild.id) or not self.can_fetch_audit(guild.id, 'kick_prune', max_requests=6): return
        
        # Check Kick
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.kick, member.id)
        if logs and not await self.check_permissions(guild, logs.user.id, "kick"):
            await self.execute_punishment(guild, logs.user, "Member Kick | Unwhitelisted User", action="ban")
            return
            
        # Check Prune
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.member_prune)
        if logs and not await self.check_permissions(guild, logs.user.id, "prune"):
            await self.execute_punishment(guild, logs.user, "Member Prune | Unwhitelisted User", action="ban")

    # ==========================================
    # ROLE LISTENERS
    # ==========================================

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        guild = role.guild
        if await self.is_blacklisted_guild(guild.id) or not self.can_fetch_audit(guild.id, 'role_create'): return
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.role_create)
        if not logs or await self.check_permissions(guild, logs.user.id, "rlcr"): return

        try: await role.delete(reason="Role created by unwhitelisted user")
        except: pass
        await self.execute_punishment(guild, logs.user, "Role Create | Unwhitelisted User", action="ban")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        guild = role.guild
        if await self.is_blacklisted_guild(guild.id) or not self.can_fetch_audit(guild.id, 'role_delete'): return
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.role_delete)
        if not logs or await self.check_permissions(guild, logs.user.id, "rldl"): return

        try: await guild.create_role(name=role.name, permissions=role.permissions, color=role.color, hoist=role.hoist, mentionable=role.mentionable, reason="Role deleted by unwhitelisted user")
        except: pass
        await self.execute_punishment(guild, logs.user, "Role Delete | Unwhitelisted User", action="ban")

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        guild = before.guild
        if await self.is_blacklisted_guild(guild.id) or not self.can_fetch_audit(guild.id, 'role_update'): return
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.role_update, before.id)
        if not logs or await self.check_permissions(guild, logs.user.id, "rlup"): return

        try: await after.edit(name=before.name, permissions=before.permissions, color=before.color, hoist=before.hoist, mentionable=before.mentionable, reason="Role updated by unwhitelisted user")
        except: pass
        await self.execute_punishment(guild, logs.user, "Role Update | Unwhitelisted User", action="ban")

    # ==========================================
    # GUILD & WEBHOOK LISTENERS
    # ==========================================

    @commands.Cog.listener()
    async def on_guild_update(self, before, after):
        guild = before
        if await self.is_blacklisted_guild(guild.id) or not self.can_fetch_audit(guild.id, 'guild_update'): return
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.guild_update)
        if not logs or await self.check_permissions(guild, logs.user.id, "serverup"): return

        try:
            if before.name != after.name: await after.edit(name=before.name)
            if before.icon != after.icon: await after.edit(icon=before.icon)
            if before.splash != after.splash: await after.edit(splash=before.splash)
            if before.banner != after.banner: await after.edit(banner=before.banner)
        except: pass
        await self.execute_punishment(guild, logs.user, "Guild Update | Unwhitelisted User", action="ban")

    @commands.Cog.listener()
    async def on_guild_integrations_update(self, guild):
        if await self.is_blacklisted_guild(guild.id) or not self.can_fetch_audit(guild.id, 'integration_create', max_requests=6): return
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.integration_create)
        if not logs or await self.check_permissions(guild, logs.user.id, "mngweb"): return

        try: await guild.edit(integrations=[])
        except: pass
        await self.execute_punishment(guild, logs.user, "Integration Create | Unwhitelisted User", action="ban")

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel):
        guild = channel.guild
        if await self.is_blacklisted_guild(guild.id) or not self.can_fetch_audit(guild.id, 'webhook_update', max_requests=6): return
        logs = await self.fetch_audit_logs(guild, discord.AuditLogAction.webhook_update, channel.id)
        if not logs or await self.check_permissions(guild, logs.user.id, "mngweb"): return

        try:
            if logs.target: await logs.target.delete(reason="Webhook updated by unwhitelisted user")
        except: pass
        await self.execute_punishment(guild, logs.user, "Webhook Update | Unwhitelisted User", action="ban")


async def setup(bot):
    await bot.add_cog(antinuke(bot))