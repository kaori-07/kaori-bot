import discord
from discord.ext import commands
from discord.ui import View, Select, Button
import aiosqlite
import asyncio
import re
import json
from typing import Optional

# --- Fallback stubs for custom checks ---
def blacklist_check():
    def decorator(func=None):
        return func if func else (lambda f: f)
    return decorator()

def ignore_check():
    def decorator(func=None):
        return func if func else (lambda f: f)
    return decorator()


# ---------------- Variable helper button ----------------
class VariableButton(Button):
    def __init__(self, author):
        super().__init__(label="Variables", style=discord.ButtonStyle.secondary)
        self.author = author

    async def callback(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            await interaction.response.send_message("Only the command author can use this button.", ephemeral=True)
            return

        variables = {
            "{user}": "Mentions the user (e.g., @UserName)",
            "{user_avatar}": "User's avatar URL",
            "{user_name}": "User's username",
            "{user_id}": "User's ID",
            "{user_nick}": "User's nickname in server",
            "{user_joindate}": "User's join date",
            "{user_createdate}": "Account creation date",
            "{server_name}": "Server name",
            "{server_id}": "Server ID",
            "{server_membercount}": "Total members in server",
            "{server_icon}": "Server icon URL",
            "{timestamp}": "Current dynamic timestamp"
        }

        embed = discord.Embed(title="Available Placeholders", description="Use these placeholders in your messages and embeds:", color=0x2f3136)
        for k, v in variables.items():
            embed.add_field(name=k, value=v, inline=True)
        embed.set_footer(text="Placeholders will be replaced automatically when a user joins.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


# ---------------- Main Cog ----------------
class Greet(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.join_queue = {}
        self.processing = set()
        self.bot.loop.create_task(self._create_and_migrate())

    async def _create_and_migrate(self):
        """Creates the database and updates tables if they are missing columns."""
        async with aiosqlite.connect("db/welcome.db") as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS welcome (
                    guild_id INTEGER PRIMARY KEY,
                    welcome_type TEXT,
                    welcome_message TEXT,
                    channel_id INTEGER,
                    embed_data TEXT,
                    auto_delete_duration INTEGER
                )
            """)
            # Add missing columns safely
            for col_sql in [
                "ALTER TABLE welcome ADD COLUMN channel_ids TEXT",
                "ALTER TABLE welcome ADD COLUMN ping_enabled INTEGER DEFAULT 0",
                "ALTER TABLE welcome ADD COLUMN ping_channel_ids TEXT",
                "ALTER TABLE welcome ADD COLUMN ping_message TEXT",
                "ALTER TABLE welcome ADD COLUMN ping_delete_seconds INTEGER"
            ]:
                try:
                    await db.execute(col_sql)
                except Exception:
                    pass
            await db.commit()

            # Migration: if channel_id missing but channel_ids exists, pick first as main channel
            async with db.execute("SELECT guild_id, channel_id, channel_ids FROM welcome") as cur:
                rows = await cur.fetchall()
            for row in rows:
                guild_id, channel_id, channel_ids_json = row
                if (channel_id is None or channel_id == 0) and channel_ids_json:
                    try:
                        arr = json.loads(channel_ids_json)
                        if isinstance(arr, list) and arr:
                            await db.execute("UPDATE welcome SET channel_id = ? WHERE guild_id = ?", (int(arr[0]), guild_id))
                    except Exception:
                        pass
            await db.commit()

    async def safe_format(self, text, placeholders):
        """Safely replaces placeholders in text without raising KeyError."""
        if not text:
            return text
        placeholders_lower = {k.lower(): v for k, v in placeholders.items()}
        def replace_var(match):
            var_name = match.group(1).lower()
            return str(placeholders_lower.get(var_name, f"{{{var_name}}}"))
        return re.sub(r"\{(\w+)\}", replace_var, text)

    def get_placeholders(self, member, guild):
        """Generates dynamic placeholders for a specific member and guild."""
        return {
            "user": member.mention,
            "user_avatar": member.display_avatar.url if member.display_avatar else member.default_avatar.url,
            "user_name": member.name,
            "user_id": member.id,
            "user_nick": member.display_name,
            "user_joindate": member.joined_at.strftime("%a, %b %d, %Y") if member.joined_at else "Unknown",
            "user_createdate": member.created_at.strftime("%a, %b %d, %Y"),
            "server_name": guild.name,
            "server_id": guild.id,
            "server_membercount": guild.member_count,
            "server_icon": guild.icon.url if guild.icon else "https://cdn.discordapp.com/embed/avatars/0.png",
            "timestamp": discord.utils.format_dt(discord.utils.utcnow())
        }

    async def build_embed(self, embed_info, placeholders):
        """Builds a rich discord.Embed dynamically from saved JSON data."""
        color_value = embed_info.get("color", 0x2f3136)
        try:
            embed_color = discord.Color(color_value) if isinstance(color_value, int) else discord.Color(int(str(color_value).lstrip("#"), 16))
        except ValueError:
            embed_color = discord.Color(0x2f3136)

        embed = discord.Embed(
            title=await self.safe_format(embed_info.get("title", ""), placeholders),
            description=await self.safe_format(embed_info.get("description", ""), placeholders),
            color=embed_color
        )
        embed.timestamp = discord.utils.utcnow()
        
        if embed_info.get("footer_text"):
            embed.set_footer(
                text=await self.safe_format(embed_info["footer_text"], placeholders),
                icon_url=await self.safe_format(embed_info.get("footer_icon", ""), placeholders)
            )
        if embed_info.get("author_name"):
            embed.set_author(
                name=await self.safe_format(embed_info["author_name"], placeholders),
                icon_url=await self.safe_format(embed_info.get("author_icon", ""), placeholders)
            )
        if embed_info.get("thumbnail"):
            embed.set_thumbnail(url=await self.safe_format(embed_info["thumbnail"], placeholders))
        if embed_info.get("image"):
            embed.set_image(url=await self.safe_format(embed_info["image"], placeholders))
            
        return embed

    # ---------- Command Group ----------
    @commands.hybrid_group(invoke_without_command=True, name="greet", help="Welcome and ping configuration")
    @blacklist_check()
    @ignore_check()
    async def greet(self, ctx: commands.Context):
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)

    # ---------- Setup ----------
    @greet.command(name="setup", help="Set up welcome message (simple or embed).")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def greet_setup(self, ctx):
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute("SELECT welcome_type FROM welcome WHERE guild_id = ?", (ctx.guild.id,)) as cur:
                existing = await cur.fetchone()
        if existing:
            return await ctx.send(f"A welcome config already exists. Use `{ctx.prefix}greet reset` to remove it first, or `{ctx.prefix}greet edit` to change it.")

        view = View(timeout=600)
        btn_simple = Button(label="Simple Text", style=discord.ButtonStyle.success)
        btn_embed = Button(label="Rich Embed", style=discord.ButtonStyle.primary)
        btn_cancel = Button(label="Cancel", style=discord.ButtonStyle.danger)

        async def simple_cb(interaction: discord.Interaction):
            if interaction.user != ctx.author: return await interaction.response.send_message("Not yours.", ephemeral=True)
            await interaction.response.defer()
            await interaction.message.delete()
            await self._simple_setup_flow(ctx)

        async def embed_cb(interaction: discord.Interaction):
            if interaction.user != ctx.author: return await interaction.response.send_message("Not yours.", ephemeral=True)
            await interaction.response.defer()
            await interaction.message.delete()
            await self._embed_setup_flow(ctx)

        async def cancel_cb(interaction: discord.Interaction):
            if interaction.user != ctx.author: return await interaction.response.send_message("Not yours.", ephemeral=True)
            await interaction.message.delete()

        btn_simple.callback, btn_embed.callback, btn_cancel.callback = simple_cb, embed_cb, cancel_cb
        view.add_item(btn_simple)
        view.add_item(btn_embed)
        view.add_item(btn_cancel)

        embed = discord.Embed(title="Welcome Setup", description="Choose whether you want a simple text message or a rich embed for your welcomes.", color=0x2f3136)
        await ctx.send(embed=embed, view=view)

    async def _simple_setup_flow(self, ctx):
        await ctx.send("Send the welcome message below. You can use placeholders like `{user}` and `{server_name}`.")
        try:
            msg = await self.bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel, timeout=600)
        except asyncio.TimeoutError:
            return await ctx.send("Timed out.")
        await self._save_welcome_data(ctx.guild.id, "simple", msg.content)
        await ctx.send("Saved simple welcome message! Now set the channel using `/greet channel`.")

    async def _embed_setup_flow(self, ctx):
        await ctx.send("Embed setup: I will ask you for values. Send the value or type `skip` to leave it blank. You have 10 minutes per prompt.")
        keys = [
            ("title", "Embed title"), ("description", "Embed description"), ("color", "Hex color (e.g. #3498db)"),
            ("footer_text", "Footer text"), ("footer_icon", "Footer icon URL"), ("author_name", "Author name"),
            ("author_icon", "Author icon URL"), ("thumbnail", "Thumbnail URL"), ("image", "Image URL"),
            ("message", "Optional regular text message outside/above the embed")
        ]
        embed_data = {}
        for key, prompt in keys:
            await ctx.send(f"**{prompt}** (or send `skip`)")
            try:
                resp = await self.bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel, timeout=600)
            except asyncio.TimeoutError:
                return await ctx.send("Setup timed out.")
            if resp.content.lower() == "skip":
                continue
            if key == "color":
                code = resp.content.lstrip("#")
                if all(c in "0123456789abcdefABCDEF" for c in code) and len(code) in {3, 6}:
                    embed_data[key] = int(code, 16)
                else:
                    await ctx.send("Invalid color format, skipping color.")
            else:
                embed_data[key] = resp.content
                
        await self._save_welcome_data(ctx.guild.id, "embed", embed_data.get("message", ""), embed_data)
        await ctx.send("Saved embed welcome message! Now set the channel using `/greet channel`.")

    async def _save_welcome_data(self, guild_id, welcome_type, message, embed_data=None, channel_id: Optional[int]=None):
        embed_json = json.dumps(embed_data) if embed_data else None
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute("SELECT 1 FROM welcome WHERE guild_id = ?", (guild_id,)) as cur:
                exists = await cur.fetchone()
            if exists:
                await db.execute("UPDATE welcome SET welcome_type=?, welcome_message=?, embed_data=?, channel_id=? WHERE guild_id=?", (welcome_type, message, embed_json, channel_id, guild_id))
            else:
                await db.execute("INSERT INTO welcome (guild_id, welcome_type, welcome_message, embed_data, channel_id) VALUES (?, ?, ?, ?, ?)", (guild_id, welcome_type, message, embed_json, channel_id))
            await db.commit()

    # ---------- Set Main Channel ----------
    @greet.command(name="channel", help="Set the MAIN channel for the welcome message.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def greet_channel(self, ctx):
        channels = ctx.guild.text_channels
        if not channels: return await ctx.send("No text channels in this server.")

        chunk_size = 25
        pages = [channels[i:i+chunk_size] for i in range(0, len(channels), chunk_size)]
        page = 0
        selected = None

        def make_embed(sel_id: Optional[int] = None):
            sel_text = f"<#{sel_id}>" if sel_id else "Not set"
            e = discord.Embed(title="Select MAIN Welcome Channel", description=f"Selected: {sel_text}", color=0x2f3136)
            e.set_footer(text="Use the dropdown to choose, then click Save.")
            return e

        def gen_view(p):
            opts = [discord.SelectOption(label=c.name, value=str(c.id)) for c in pages[p]]
            select = Select(placeholder="Pick a channel from this page", options=opts, min_values=1, max_values=1)

            async def select_cb(interaction: discord.Interaction):
                nonlocal selected
                if interaction.user != ctx.author: return await interaction.response.send_message("Not yours.", ephemeral=True)
                selected = int(select.values[0])
                await interaction.response.send_message(f"Selected <#{selected}>. Press Save to lock it in.", ephemeral=True)

            select.callback = select_cb

            prev_btn = Button(label="Previous", style=discord.ButtonStyle.secondary, disabled=(p == 0))
            next_btn = Button(label="Next", style=discord.ButtonStyle.secondary, disabled=(p == len(pages) - 1))
            save_btn = Button(label="Save as MAIN", style=discord.ButtonStyle.success)

            async def prev_cb(interaction: discord.Interaction):
                nonlocal page
                if interaction.user != ctx.author: return
                page -= 1
                await interaction.response.edit_message(embed=make_embed(selected), view=gen_view(page))

            async def next_cb(interaction: discord.Interaction):
                nonlocal page
                if interaction.user != ctx.author: return
                page += 1
                await interaction.response.edit_message(embed=make_embed(selected), view=gen_view(page))

            async def save_cb(interaction: discord.Interaction):
                if interaction.user != ctx.author: return await interaction.response.send_message("Not yours.", ephemeral=True)
                if not selected: return await interaction.response.send_message("Select a channel first.", ephemeral=True)
                async with aiosqlite.connect("db/welcome.db") as db:
                    await db.execute("INSERT OR IGNORE INTO welcome (guild_id) VALUES (?)", (ctx.guild.id,))
                    await db.execute("UPDATE welcome SET channel_id = ? WHERE guild_id = ?", (selected, ctx.guild.id))
                    await db.commit()
                await interaction.response.edit_message(embed=discord.Embed(title="Saved", description=f"Main welcome channel set to <#{selected}>.", color=0x2f3136), view=None)

            prev_btn.callback, next_btn.callback, save_btn.callback = prev_cb, next_cb, save_cb

            v = View()
            v.add_item(select)
            v.add_item(prev_btn)
            v.add_item(next_btn)
            v.add_item(save_btn)
            return v

        await ctx.send(embed=make_embed(), view=gen_view(page))

    # ---------- Set Ping Channels (Multiple) ----------
    @greet.command(name="pingchannel", help="Select multiple channels that should receive the ping message.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def greet_pingchannel(self, ctx):
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute("SELECT ping_channel_ids FROM welcome WHERE guild_id = ?", (ctx.guild.id,)) as cur:
                row = await cur.fetchone()
        
        existing = set()
        if row and row[0]:
            try: existing = set(int(x) for x in json.loads(row[0]))
            except Exception: pass

        channels = ctx.guild.text_channels
        if not channels: return await ctx.send("No text channels found.")

        chunk_size = 25
        pages = [channels[i:i+chunk_size] for i in range(0, len(channels), chunk_size)]
        page = 0
        selected_set = set(existing)

        def make_embed():
            disp = ", ".join(f"<#{x}>" for x in selected_set) if selected_set else "None"
            e = discord.Embed(title="Ping Channels Configuration", description=f"**Currently Selected:**\n{disp}", color=0x2f3136)
            return e

        def gen_view(p):
            opts = [discord.SelectOption(label=c.name, value=str(c.id)) for c in pages[p]]
            select = Select(placeholder="Select channels on this page", options=opts, min_values=0, max_values=len(opts))

            async def select_cb(interaction: discord.Interaction):
                if interaction.user != ctx.author: return await interaction.response.send_message("Not yours.", ephemeral=True)
                select._last_selected = list(select.values)
                await interaction.response.defer()

            select.callback = select_cb

            prev_btn = Button(label="◀", style=discord.ButtonStyle.secondary, disabled=(p == 0))
            next_btn = Button(label="▶", style=discord.ButtonStyle.secondary, disabled=(p == len(pages) - 1))
            add_btn = Button(label="Add Selected", style=discord.ButtonStyle.success)
            remove_btn = Button(label="Remove Selected", style=discord.ButtonStyle.danger)
            finish_btn = Button(label="Save", style=discord.ButtonStyle.primary)

            async def nav_cb(interaction: discord.Interaction, dir: int):
                nonlocal page
                if interaction.user != ctx.author: return
                page += dir
                await interaction.response.edit_message(embed=make_embed(), view=gen_view(page))

            async def mod_cb(interaction: discord.Interaction, is_add: bool):
                if interaction.user != ctx.author: return
                for cid in getattr(select, "_last_selected", []):
                    if is_add: selected_set.add(int(cid))
                    else: selected_set.discard(int(cid))
                await interaction.response.edit_message(embed=make_embed(), view=gen_view(page))

            async def finish_cb(interaction: discord.Interaction):
                if interaction.user != ctx.author: return
                async with aiosqlite.connect("db/welcome.db") as db:
                    await db.execute("INSERT OR IGNORE INTO welcome (guild_id) VALUES (?)", (ctx.guild.id,))
                    await db.execute("UPDATE welcome SET ping_channel_ids = ? WHERE guild_id = ?", (json.dumps(list(selected_set)) if selected_set else None, ctx.guild.id))
                    await db.commit()
                await interaction.response.edit_message(embed=discord.Embed(title="Saved", description=f"Successfully mapped {len(selected_set)} ping channels.", color=0x2f3136), view=None)

            prev_btn.callback = lambda i: nav_cb(i, -1)
            next_btn.callback = lambda i: nav_cb(i, 1)
            add_btn.callback = lambda i: mod_cb(i, True)
            remove_btn.callback = lambda i: mod_cb(i, False)
            finish_btn.callback = finish_cb

            v = View()
            v.add_item(select)
            v.add_item(prev_btn)
            v.add_item(next_btn)
            v.add_item(add_btn)
            v.add_item(remove_btn)
            v.add_item(finish_btn)
            return v

        await ctx.send(embed=make_embed(), view=gen_view(page))

    # ---------- Config Edits ----------
    @greet.command(name="pingmsg", help="Toggle join ping messages 'on' or 'off'.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def greet_pingmsg(self, ctx, mode: str):
        mode = mode.lower()
        if mode not in ("on", "off"): return await ctx.send("Usage: `/greet pingmsg on` or `/greet pingmsg off`")
        val = 1 if mode == "on" else 0
        async with aiosqlite.connect("db/welcome.db") as db:
            await db.execute("INSERT OR IGNORE INTO welcome (guild_id) VALUES (?)", (ctx.guild.id,))
            await db.execute("UPDATE welcome SET ping_enabled = ? WHERE guild_id = ?", (val, ctx.guild.id))
            await db.commit()
        await ctx.send(f"<a:tick:1489157731393994854> Ping messages are now **{'enabled' if val else 'disabled'}**.")

    @greet.command(name="setpingmsg", help="Set the text sent to the ping channels.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def greet_setpingmsg(self, ctx, *, message: str):
        if len(message) > 1800: return await ctx.send("Ping message too long.")
        async with aiosqlite.connect("db/welcome.db") as db:
            await db.execute("INSERT OR IGNORE INTO welcome (guild_id) VALUES (?)", (ctx.guild.id,))
            await db.execute("UPDATE welcome SET ping_message = ? WHERE guild_id = ?", (message, ctx.guild.id))
            await db.commit()
        await ctx.send("<a:tick:1489157731393994854> Ping message updated successfully.")

    @greet.command(name="setpingdel", help="Set auto-delete time for ping messages (e.g. 20s).")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def greet_setpingdel(self, ctx, time: str):
        try: seconds = int(time.replace("s", ""))
        except ValueError: return await ctx.send("Invalid time. Use format like `20s` or `20`.")
        if not (3 <= seconds <= 300): return await ctx.send("Time must be between 3 and 300 seconds.")
        async with aiosqlite.connect("db/welcome.db") as db:
            await db.execute("INSERT OR IGNORE INTO welcome (guild_id) VALUES (?)", (ctx.guild.id,))
            await db.execute("UPDATE welcome SET ping_delete_seconds = ? WHERE guild_id = ?", (seconds, ctx.guild.id))
            await db.commit()
        await ctx.send(f"<a:tick:1489157731393994854> Ping messages will now self-delete after {seconds} seconds.")

    @greet.command(name="autodelete", aliases=["autodel"], help="Set auto-delete time for the MAIN welcome message.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def greet_autodelete(self, ctx, time: str):
        try:
            if time.endswith("m"): seconds = int(time[:-1]) * 60
            else: seconds = int(time.replace("s", ""))
        except ValueError: return await ctx.send("Invalid time value. Use `10s` or `2m`.")
        if not (3 <= seconds <= 300): return await ctx.send("Time must be between 3 and 300 seconds.")
        async with aiosqlite.connect("db/welcome.db") as db:
            await db.execute("UPDATE welcome SET auto_delete_duration = ? WHERE guild_id = ?", (seconds, ctx.guild.id))
            await db.commit()
        await ctx.send(f"<a:tick:1489157731393994854> MAIN Welcome messages will now self-delete after {seconds} seconds.")

    @greet.command(name="edit", help="Edit existing embed/simple welcome settings.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def greet_edit(self, ctx):
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute("SELECT welcome_type, welcome_message, embed_data FROM welcome WHERE guild_id = ?", (ctx.guild.id,)) as cur:
                row = await cur.fetchone()
        if not row: return await ctx.send("No welcome setup found. Run `/greet setup` first.")

        welcome_type, welcome_message, embed_data = row
        if welcome_type == "simple":
            embed = discord.Embed(title="Edit Welcome (Simple)", description=f"**Current:**\n{welcome_message or 'None'}", color=0x2f3136)
            btn_edit = Button(label="Edit Message", style=discord.ButtonStyle.primary)

            async def edit_cb(interaction: discord.Interaction):
                if interaction.user != ctx.author: return await interaction.response.send_message("Not yours.", ephemeral=True)
                await interaction.response.send_message("Type the new message now:", ephemeral=True)
                try: msg = await self.bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel, timeout=300)
                except asyncio.TimeoutError: return await ctx.send("Timed out.")
                async with aiosqlite.connect("db/welcome.db") as db:
                    await db.execute("UPDATE welcome SET welcome_message = ? WHERE guild_id = ?", (msg.content, ctx.guild.id))
                    await db.commit()
                await ctx.send("<a:tick:1489157731393994854> Welcome message updated.")

            btn_edit.callback = edit_cb
            v = View()
            v.add_item(btn_edit)
            v.add_item(VariableButton(ctx.author))
            await ctx.send(embed=embed, view=v)
        else:
            data = json.loads(embed_data) if embed_data else {}
            formatted = "\n".join(f"**{k.replace('_', ' ').title()}**: {v}" for k, v in data.items()) or "None"
            embed = discord.Embed(title="Edit Welcome (Embed)", description=formatted[:4096], color=0x2f3136)
            options = [discord.SelectOption(label=k.replace("_", " ").title(), value=k) for k in data.keys()]
            if not options: return await ctx.send("No embed fields exist to edit.")
            
            sel = Select(placeholder="Select field to edit", options=options)

            async def sel_cb(interaction: discord.Interaction):
                if interaction.user != ctx.author: return await interaction.response.send_message("Not yours.", ephemeral=True)
                key = sel.values[0]
                await interaction.response.send_message(f"Type new value for `{key}` (or send `skip`):", ephemeral=True)
                try: msg = await self.bot.wait_for("message", check=lambda m: m.author == ctx.author and m.channel == ctx.channel, timeout=300)
                except asyncio.TimeoutError: return await ctx.send("Timed out.")
                if msg.content.lower() != "skip":
                    if key == "color":
                        try: data[key] = int(msg.content.lstrip("#"), 16)
                        except: return await ctx.send("Invalid hex color.")
                    else: data[key] = msg.content
                    async with aiosqlite.connect("db/welcome.db") as db:
                        await db.execute("UPDATE welcome SET embed_data = ? WHERE guild_id = ?", (json.dumps(data), ctx.guild.id))
                        await db.commit()
                    await ctx.send(f"<a:tick:1489157731393994854> `{key}` has been updated.")

            sel.callback = sel_cb
            v = View()
            v.add_item(sel)
            v.add_item(VariableButton(ctx.author))
            await ctx.send(embed=embed, view=v)

    # ---------- Test / Preview ----------
    @greet.command(name="test", help="Simulate a member joining to test your configuration.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def greet_test(self, ctx):
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute("SELECT welcome_type, welcome_message, channel_id, embed_data, ping_enabled, ping_channel_ids, ping_message FROM welcome WHERE guild_id = ?", (ctx.guild.id,)) as cur:
                row = await cur.fetchone()
        if not row: return await ctx.send("No configuration found. Run `/greet setup` first.")
        
        welcome_type, welcome_message, channel_id, embed_data, ping_enabled, ping_cids_json, ping_message = row
        main_ch = self.bot.get_channel(int(channel_id)) if channel_id else None
        
        if not main_ch: return await ctx.send("Main welcome channel is not valid or not set. Use `/greet channel`.")

        placeholders = self.get_placeholders(ctx.author, ctx.guild) # Use command author as the "joining" user

        # 1. Test Pings
        if ping_enabled and ping_cids_json:
            try:
                ping_cids = json.loads(ping_cids_json)
                for cid in ping_cids:
                    ch = self.bot.get_channel(int(cid))
                    if ch: await ch.send(f"[TEST PING] {await self.safe_format(ping_message or 'Welcome {user}!', placeholders)}")
            except Exception as e:
                await ctx.send(f"Error testing pings: {e}")

        # 2. Test Main Welcome
        try:
            if welcome_type == "simple":
                await main_ch.send(f"[TEST WELCOME] {await self.safe_format(welcome_message or 'Welcome {user}!', placeholders)}")
            else:
                emb_info = json.loads(embed_data) if embed_data else {}
                content = await self.safe_format(emb_info.get("message", ""), placeholders)
                embed = await self.build_embed(emb_info, placeholders)
                await main_ch.send(content=f"[TEST] {content}" if content else "[TEST]", embed=embed)
            await ctx.send("<a:tick:1489157731393994854> Test sent successfully.")
        except Exception as e:
            await ctx.send(f"Failed to send test: {e}")

    # ---------- View Config ----------
    @greet.command(name="config", help="View the current active greet settings.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def greet_config(self, ctx):
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute("SELECT welcome_type, channel_id, auto_delete_duration, ping_enabled, ping_channel_ids, ping_delete_seconds FROM welcome WHERE guild_id = ?", (ctx.guild.id,)) as cur:
                row = await cur.fetchone()
        if not row: return await ctx.send("No configuration found.")

        welcome_type, channel_id, auto_delete_duration, ping_enabled, ping_channel_ids, ping_delete_seconds = row
        main_ch = f"<#{channel_id}>" if channel_id else "Not set"
        
        ping_display = "None"
        if ping_channel_ids:
            try:
                arr = json.loads(ping_channel_ids)
                ping_display = ", ".join(f"<#{x}>" for x in arr) if arr else "None"
            except: pass

        embed = discord.Embed(title=f"Greeting Config for {ctx.guild.name}", color=0x2f3136)
        embed.add_field(name="Main Channel", value=main_ch, inline=True)
        embed.add_field(name="Welcome Type", value=welcome_type.title(), inline=True)
        embed.add_field(name="Auto-Delete", value=f"{auto_delete_duration}s" if auto_delete_duration else "Disabled", inline=True)
        embed.add_field(name="Ping Enabled", value="Yes <a:tick:1489157731393994854>" if ping_enabled else "No <a:Cross_:1489174755537064046>", inline=True)
        embed.add_field(name="Ping Channels", value=ping_display, inline=True)
        embed.add_field(name="Ping Auto-Delete", value=f"{ping_delete_seconds or 20}s", inline=True)
        await ctx.send(embed=embed)

    # ---------- Reset ----------
    @greet.command(name="reset", help="Delete all welcome & ping configurations.")
    @blacklist_check()
    @ignore_check()
    @commands.has_permissions(administrator=True)
    async def greet_reset(self, ctx):
        async with aiosqlite.connect("db/welcome.db") as db:
            await db.execute("DELETE FROM welcome WHERE guild_id = ?", (ctx.guild.id,))
            await db.commit()
        await ctx.send("<a:tick:1489157731393994854> All welcome and ping configurations have been wiped.")


    # ==========================================
    # JOIN EVENT / RATE LIMIT QUEUE LOGIC
    # ==========================================
    @commands.Cog.listener()
    async def on_member_join(self, member):
        guild = member.guild
        if guild.id not in self.join_queue:
            self.join_queue[guild.id] = []
        self.join_queue[guild.id].append(member)
        
        # Start processor if it's not currently running for this guild
        if guild.id not in self.processing:
            self.processing.add(guild.id)
            await self.process_queue(guild)

    async def process_queue(self, guild):
        while self.join_queue.get(guild.id):
            member = self.join_queue[guild.id].pop(0)
            
            # Fetch config for the member
            async with aiosqlite.connect("db/welcome.db") as db:
                async with db.execute("SELECT welcome_type, welcome_message, channel_id, embed_data, auto_delete_duration, ping_enabled, ping_channel_ids, ping_message, ping_delete_seconds FROM welcome WHERE guild_id = ?", (guild.id,)) as cursor:
                    row = await cursor.fetchone()
            if not row:
                continue

            welcome_type, welcome_message, channel_id, embed_data, auto_delete_duration, ping_enabled, ping_cids_json, ping_message, ping_delete_seconds = row
            placeholders = self.get_placeholders(member, guild)

            # --- 1. Process Pings ---
            if ping_enabled and ping_cids_json:
                try:
                    ping_cids = json.loads(ping_cids_json)
                    for cid in ping_cids:
                        ch = guild.get_channel(int(cid))
                        if ch and ch.permissions_for(guild.me).send_messages:
                            ping_content = await self.safe_format(ping_message or "{user}", placeholders)
                            try:
                                ping_msg = await ch.send(ping_content)
                                await ping_msg.delete(delay=int(ping_delete_seconds) if ping_delete_seconds else 20)
                            except Exception: pass
                except Exception: pass

            # --- 2. Process Main Welcome Message ---
            main_channel = guild.get_channel(int(channel_id)) if channel_id else None
            if main_channel and main_channel.permissions_for(guild.me).send_messages:
                try:
                    if welcome_type == "simple" and welcome_message:
                        content = await self.safe_format(welcome_message, placeholders)
                        sent_msg = await main_channel.send(content=content)
                    elif welcome_type == "embed" and embed_data:
                        emb_info = json.loads(embed_data)
                        content = await self.safe_format(emb_info.get("message", ""), placeholders) or None
                        embed = await self.build_embed(emb_info, placeholders)
                        sent_msg = await main_channel.send(content=content, embed=embed)
                    else:
                        sent_msg = None

                    if sent_msg and auto_delete_duration:
                        await sent_msg.delete(delay=int(auto_delete_duration))

                except discord.HTTPException as e:
                    # If rate limited, put the user back in the queue and wait
                    if e.code == 50035 or e.status == 429:
                        await asyncio.sleep(2)
                        self.join_queue[guild.id].insert(0, member) 
                        continue
                except Exception:
                    pass

            # Pause between sends to prevent triggering Discord's rate limits (critical for massive raids/joins)
            await asyncio.sleep(2)
            
        self.processing.discard(guild.id)


async def setup(bot):
    await bot.add_cog(Greet(bot))