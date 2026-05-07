import discord
from discord.ext import commands
import aiosqlite
import os
import io
import datetime

# ==========================================
# ADVANCED HTML TRANSCRIPT GENERATOR (PREMIUM)
# ==========================================
async def generate_transcript(channel: discord.TextChannel) -> discord.File:
    """Generates a high-fidelity Discord-styled HTML transcript."""
    messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]
    
    guild_icon = channel.guild.icon.url if channel.guild.icon else "https://cdn.discordapp.com/embed/avatars/0.png"
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Transcript - {channel.name}</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');
            body {{ background-color: #313338; color: #dcddde; font-family: 'Roboto', sans-serif; margin: 0; padding: 0; }}
            .container {{ max-width: 1000px; margin: 0 auto; padding: 40px 20px; }}
            
            /* Header Styling */
            .header {{ display: flex; align-items: center; padding-bottom: 20px; border-bottom: 1px solid #3f4147; margin-bottom: 30px; }}
            .header-icon {{ width: 80px; height: 80px; border-radius: 25px; margin-right: 20px; }}
            .header-info h1 {{ font-size: 24px; color: #ffffff; margin: 0; }}
            .header-info p {{ color: #b5bac1; margin: 5px 0 0 0; font-size: 14px; }}

            /* Message Styling */
            .message-group {{ display: flex; margin-bottom: 18px; padding: 5px 0; }}
            .avatar {{ width: 45px; height: 45px; border-radius: 50%; margin-right: 16px; flex-shrink: 0; }}
            .msg-content {{ width: 100%; }}
            .msg-header {{ display: flex; align-items: baseline; margin-bottom: 4px; }}
            .author {{ font-weight: 500; color: #ffffff; font-size: 16px; margin-right: 8px; }}
            .timestamp {{ color: #949ba4; font-size: 12px; }}
            .text {{ line-height: 1.5; font-size: 15px; word-wrap: break-word; white-space: pre-wrap; }}
            
            /* Embed Styling */
            .embed {{ margin-top: 8px; padding: 12px; background: #2b2d31; border-left: 4px solid #1e1f22; border-radius: 4px; max-width: 520px; }}
            .embed-title {{ color: #ffffff; font-weight: 600; margin-bottom: 4px; }}
            .embed-desc {{ color: #dbdee1; font-size: 14px; white-space: pre-wrap; }}

            /* Attachments */
            .attachment {{ margin-top: 10px; padding: 10px; background: #2b2d31; border: 1px solid #1e1f22; border-radius: 8px; display: inline-flex; align-items: center; }}
            .attachment img {{ max-width: 400px; border-radius: 4px; }}
            .attachment a {{ color: #00a8fc; text-decoration: none; font-size: 14px; }}
            .attachment a:hover {{ text-decoration: underline; }}
            
            .footer {{ text-align: center; color: #949ba4; font-size: 12px; margin-top: 50px; padding-top: 20px; border-top: 1px solid #3f4147; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <img class="header-icon" src="{guild_icon}">
                <div class="header-info">
                    <h1>Ticket Transcript: #{channel.name}</h1>
                    <p>Server: {channel.guild.name} | Total Messages: {len(messages)}</p>
                    <p>Generated: {discord.utils.utcnow().strftime("%B %d, %Y at %H:%M UTC")}</p>
                </div>
            </div>
    """

    for msg in messages:
        avatar_url = msg.author.display_avatar.url if msg.author.display_avatar else "https://cdn.discordapp.com/embed/avatars/0.png"
        timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M")
        safe_content = msg.clean_content.replace("<", "&lt;").replace(">", "&gt;")

        # Embeds HTML
        embeds_html = ""
        for embed in msg.embeds:
            border_color = f"#{embed.color.value:06x}" if embed.color else "#1e1f22"
            embed_title = f'<div class="embed-title">{embed.title}</div>' if embed.title else ""
            embed_desc = f'<div class="embed-desc">{embed.description}</div>' if embed.description else ""
            embeds_html += f'<div class="embed" style="border-left-color: {border_color}">{embed_title}{embed_desc}</div>'

        # Attachments HTML
        attachments_html = ""
        for att in msg.attachments:
            if any(att.filename.lower().endswith(ext) for ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                attachments_html += f'<div class="attachment"><img src="{att.url}" alt="Attachment"></div>'
            else:
                attachments_html += f'<div class="attachment">📄 <a href="{att.url}" target="_blank">{att.filename}</a></div>'

        html_content += f"""
            <div class="message-group">
                <img class="avatar" src="{avatar_url}">
                <div class="msg-content">
                    <div class="msg-header">
                        <span class="author">{msg.author.display_name}</span>
                        <span class="timestamp">{timestamp}</span>
                    </div>
                    <div class="text">{safe_content}</div>
                    {embeds_html}
                    {attachments_html}
                </div>
            </div>
        """

    html_content += f"""
            <div class="footer">Transcript securely generated on {discord.utils.utcnow().strftime("%Y-%m-%d")}</div>
        </div>
    </body>
    </html>
    """
    
    buffer = io.BytesIO(html_content.encode('utf-8'))
    return discord.File(buffer, filename=f"transcript_{channel.name}.html")


# ==========================================
# PUBLIC FACING PANEL (DYNAMIC & PERSISTENT)
# ==========================================
class TicketDropdown(discord.ui.Select):
    def __init__(self, panel_id: int, options_data: list):
        self.panel_id = panel_id
        
        select_options = []
        for opt in options_data:
            # opt = (option_id, label, description, emoji, category_id)
            select_options.append(discord.SelectOption(
                label=opt[1],
                description=opt[2][:100] if opt[2] else None,
                emoji=opt[3] if opt[3] else None,
                value=str(opt[0]) 
            ))
            
        super().__init__(
            placeholder="Select a category to open a ticket...",
            min_values=1, max_values=1,
            options=select_options,
            custom_id=f"ticket_dropdown_{panel_id}"
        )

    async def callback(self, interaction: discord.Interaction):
        option_id = int(self.values[0])
        guild = interaction.guild
        user = interaction.user

        await interaction.response.defer(ephemeral=True)

        try:
            # 1. Fetch Option Details
            async with aiosqlite.connect("db/ticket.db") as db:
                async with db.execute("SELECT label, category_id FROM ticket_options WHERE id = ?", (option_id,)) as cursor:
                    opt_row = await cursor.fetchone()
                    if not opt_row:
                        return await interaction.followup.send("<a:Cross_:1489174755537064046> Error: Option no longer exists.", ephemeral=True)
                    opt_label, category_id = opt_row

            # 2. Prevent Multiple Open Tickets
            async with aiosqlite.connect("db/ticket.db") as db:
                async with db.execute("SELECT channel_id FROM tickets WHERE owner_id = ? AND guild_id = ? AND status = 'open'", (user.id, guild.id)) as cursor:
                    existing = await cursor.fetchone()
                    if existing:
                        channel = guild.get_channel(existing[0])
                        if channel:
                            return await interaction.followup.send(f"<a:Cross_:1489174755537064046> You already have an open ticket: {channel.mention}", ephemeral=True)
                        else:
                            # Clean up dead DB entries
                            await db.execute("DELETE FROM tickets WHERE owner_id = ? AND guild_id = ?", (user.id, guild.id))
                            await db.commit()

            # 3. Category Logic
            category = discord.utils.get(guild.categories, id=category_id)
            if not category:
                return await interaction.followup.send("<a:Cross_:1489174755537064046> Setup Error: The category for this ticket option was deleted. Please contact an admin.", ephemeral=True)

            # 4. Setup Channel Permissions
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True, read_message_history=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, read_message_history=True)
            }

            safe_name = f"ticket-{user.name.lower().replace(' ', '-')}"

            # 5. Create Channel
            ticket_channel = await guild.create_text_channel(
                name=safe_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket Owner: {user.id} | Type: {opt_label}"
            )

            # 6. Save Ticket to DB
            async with aiosqlite.connect("db/ticket.db") as db:
                await db.execute("INSERT INTO tickets (channel_id, owner_id, guild_id, status) VALUES (?, ?, ?, 'open')", (ticket_channel.id, user.id, guild.id))
                await db.commit()

            # 7. Send Initial Control Panel
            embed = discord.Embed(
                title=f"🎫 {opt_label} Ticket",
                description=f"Welcome {user.mention}!\n\nPlease describe your issue in detail. Support will be with you shortly.\n\n*Staff: Use the buttons below to manage this ticket.*",
                color=discord.Color.green()
            )
            await ticket_channel.send(content=f"{user.mention}", embed=embed, view=TicketActiveView())
            await interaction.followup.send(f"<a:tick:1489157731393994854> Ticket created: {ticket_channel.mention}", ephemeral=True)

        except discord.Forbidden:
            await interaction.followup.send("<a:Cross_:1489174755537064046> Failed to create ticket. I do not have permissions to manage channels or roles in that category!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"<a:Cross_:1489174755537064046> Failed to create ticket due to an error: `{e}`", ephemeral=True)


class TicketPanelView(discord.ui.View):
    def __init__(self, panel_id: int, options_data: list):
        super().__init__(timeout=None)
        self.add_item(TicketDropdown(panel_id, options_data))


# ==========================================
# STAFF TICKET CONTROLS (ACTIVE / CLOSED)
# ==========================================
class TicketActiveView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, custom_id="ticket_close", emoji="<:r_Lock:1489546045754183762>")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        async with aiosqlite.connect("db/ticket.db") as db:
            async with db.execute("SELECT owner_id FROM tickets WHERE channel_id = ?", (interaction.channel.id,)) as cursor:
                row = await cursor.fetchone()
                if not row: return
                owner_id = row[0]
            await db.execute("UPDATE tickets SET status = 'closed' WHERE channel_id = ?", (interaction.channel.id,))
            await db.commit()

        owner = interaction.guild.get_member(owner_id)
        if owner:
            await interaction.channel.set_permissions(owner, read_messages=True, send_messages=False)
            
        embed = discord.Embed(title="Ticket Closed 🔒", description=f"Ticket closed by {interaction.user.mention}. Users can no longer send messages.", color=discord.Color.orange())
        await interaction.channel.send(embed=embed, view=TicketClosedView())

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, custom_id="ticket_claim", emoji="<:claim:1489545954712617090>")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("<a:Cross_:1489174755537064046> Only staff can claim tickets.", ephemeral=True)

        async with aiosqlite.connect("db/ticket.db") as db:
            async with db.execute("SELECT claimed_by FROM tickets WHERE channel_id = ?", (interaction.channel.id,)) as cursor:
                row = await cursor.fetchone()
                if row and row[0]:
                    return await interaction.response.send_message(f"<a:Cross_:1489174755537064046> This ticket is already claimed by <@{row[0]}>.", ephemeral=True)
            await db.execute("UPDATE tickets SET claimed_by = ? WHERE channel_id = ?", (interaction.user.id, interaction.channel.id))
            await db.commit()

        embed = discord.Embed(description=f"🙋‍♂️ **Ticket claimed by {interaction.user.mention}**", color=discord.Color.gold())
        await interaction.response.send_message(embed=embed)

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.secondary, custom_id="ticket_unclaim", emoji="<a:Cross_:1489174755537064046>")
    async def unclaim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("<a:Cross_:1489174755537064046> Only staff can unclaim tickets.", ephemeral=True)

        async with aiosqlite.connect("db/ticket.db") as db:
            async with db.execute("SELECT claimed_by FROM tickets WHERE channel_id = ?", (interaction.channel.id,)) as cursor:
                row = await cursor.fetchone()
                if not row or row[0] != interaction.user.id:
                    return await interaction.response.send_message("<a:Cross_:1489174755537064046> You cannot unclaim a ticket you haven't claimed.", ephemeral=True)
            await db.execute("UPDATE tickets SET claimed_by = NULL WHERE channel_id = ?", (interaction.channel.id,))
            await db.commit()

        embed = discord.Embed(description=f"<a:Cross_:1489174755537064046> **Ticket unclaimed by {interaction.user.mention}**", color=discord.Color.light_grey())
        await interaction.response.send_message(embed=embed)


class TicketClosedView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Reopen", style=discord.ButtonStyle.success, custom_id="ticket_reopen", emoji="<a:locked:1489546407768490065>")
    async def reopen_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("<a:Cross_:1489174755537064046> Only staff can reopen tickets.", ephemeral=True)

        await interaction.response.defer()
        async with aiosqlite.connect("db/ticket.db") as db:
            async with db.execute("SELECT owner_id FROM tickets WHERE channel_id = ?", (interaction.channel.id,)) as cursor:
                row = await cursor.fetchone()
                if not row: return
                owner_id = row[0]
            await db.execute("UPDATE tickets SET status = 'open' WHERE channel_id = ?", (interaction.channel.id,))
            await db.commit()

        owner = interaction.guild.get_member(owner_id)
        if owner:
            await interaction.channel.set_permissions(owner, read_messages=True, send_messages=True, attach_files=True, embed_links=True)

        embed = discord.Embed(title="Ticket Reopened 🔓", description=f"Ticket unlocked by {interaction.user.mention}.", color=discord.Color.green())
        await interaction.channel.send(embed=embed)

    @discord.ui.button(label="Transcript", style=discord.ButtonStyle.primary, custom_id="ticket_transcript", emoji="<:transcript:1489546564132409446>")
    async def transcript_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("<a:Cross_:1489174755537064046> Only staff can generate transcripts.", ephemeral=True)
        await interaction.response.defer()
        file = await generate_transcript(interaction.channel)
        await interaction.followup.send(content="<a:tick:1489157731393994854> **Ticket Transcript:**", file=file)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, custom_id="ticket_delete", emoji="<:Delete:1489546684093431888>")
    async def delete_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("<a:Cross_:1489174755537064046> Only staff can delete tickets.", ephemeral=True)
            
        await interaction.response.send_message("⛔ Generating transcript and deleting channel in 5 seconds...")
        
        try:
            transcript_file = await generate_transcript(interaction.channel)
            async with aiosqlite.connect("db/ticket.db") as db:
                async with db.execute("SELECT owner_id FROM tickets WHERE channel_id = ?", (interaction.channel.id,)) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        owner = interaction.guild.get_member(row[0])
                        if owner:
                            await owner.send(f"Your ticket `{interaction.channel.name}` from **{interaction.guild.name}** was deleted. Here is your transcript:", file=transcript_file)
        except Exception: pass

        async with aiosqlite.connect("db/ticket.db") as db:
            await db.execute("DELETE FROM tickets WHERE channel_id = ?", (interaction.channel.id,))
            await db.commit()

        import asyncio
        await asyncio.sleep(5)
        await interaction.channel.delete()


# ==========================================
# ADMIN SETUP: MODALS & GUI VIEWS
# ==========================================
class SetupMessageModal(discord.ui.Modal, title='Panel Embed Settings'):
    p_title = discord.ui.TextInput(label='Embed Title', style=discord.TextStyle.short, default="📞 Support Center")
    p_desc = discord.ui.TextInput(label='Embed Description', style=discord.TextStyle.paragraph, default="Please select an option below to open a ticket.")
    p_color = discord.ui.TextInput(label='Hex Color (e.g. #00FF00)', style=discord.TextStyle.short, default="#2b2d31")
    p_thumb = discord.ui.TextInput(label='Thumbnail URL (Optional PFP)', style=discord.TextStyle.short, required=False)
    p_image = discord.ui.TextInput(label='Banner Image URL (Optional)', style=discord.TextStyle.short, required=False)

    def __init__(self, view_obj):
        super().__init__()
        self.view_obj = view_obj
        self.p_title.default = view_obj.panel_title
        self.p_desc.default = view_obj.panel_desc
        self.p_color.default = view_obj.panel_color
        self.p_thumb.default = view_obj.panel_thumb
        self.p_image.default = view_obj.panel_image

    async def on_submit(self, interaction: discord.Interaction):
        self.view_obj.panel_title = self.p_title.value
        self.view_obj.panel_desc = self.p_desc.value
        self.view_obj.panel_color = self.p_color.value
        self.view_obj.panel_thumb = self.p_thumb.value
        self.view_obj.panel_image = self.p_image.value
        await self.view_obj.update_menu(interaction)

class SetupOptionModal(discord.ui.Modal, title='Add Ticket Option'):
    o_label = discord.ui.TextInput(label='Option Name', style=discord.TextStyle.short, placeholder="e.g. Support")
    o_desc = discord.ui.TextInput(label='Description', style=discord.TextStyle.short, required=False, placeholder="e.g. Ask a general question")
    o_emoji = discord.ui.TextInput(label='Emoji (Optional)', style=discord.TextStyle.short, required=False, placeholder="🎫")
    o_cat = discord.ui.TextInput(label='Category ID (REQUIRED)', style=discord.TextStyle.short, required=True, placeholder="123456789012345678")

    def __init__(self, view_obj):
        super().__init__()
        self.view_obj = view_obj

    async def on_submit(self, interaction: discord.Interaction):
        try: 
            cat_id = int(self.o_cat.value)
        except ValueError: 
            return await interaction.response.send_message("<a:Cross_:1489174755537064046> Category ID must be a valid number.", ephemeral=True)
            
        cat_check = interaction.guild.get_channel(cat_id)
        if not isinstance(cat_check, discord.CategoryChannel):
            return await interaction.response.send_message("<a:Cross_:1489174755537064046> The ID provided does not belong to a valid Category in this server.", ephemeral=True)

        self.view_obj.options.append({
            "label": self.o_label.value,
            "desc": self.o_desc.value,
            "emoji": self.o_emoji.value,
            "category_id": cat_id
        })
        await self.view_obj.update_menu(interaction)

class AdminSetupView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=600)
        self.bot = bot
        self.panel_title = "📞 Support Center"
        self.panel_desc = "Please select an option below to open a ticket."
        self.panel_color = "#2b2d31"
        self.panel_thumb = ""
        self.panel_image = ""
        self.options = []

    async def update_menu(self, interaction: discord.Interaction):
        try: color = discord.Color(int(self.panel_color.lstrip("#"), 16))
        except: color = discord.Color(0x2b2d31)
        
        embed = discord.Embed(title=f"PREVIEW: {self.panel_title}", description=self.panel_desc, color=color)
        if self.panel_thumb:
            embed.set_thumbnail(url=self.panel_thumb)
        if self.panel_image:
            embed.set_image(url=self.panel_image)
            
        opt_text = ""
        for i, opt in enumerate(self.options):
            opt_text += f"**{i+1}.** {opt['emoji']} `{opt['label']}` (Cat ID: {opt['category_id']})\n"
        
        embed.add_field(name=f"Dropdown Options ({len(self.options)})", value=opt_text if opt_text else "None added yet. Click 'Add Option' below.", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Edit Embed Info (Title/Image)", style=discord.ButtonStyle.primary, row=0)
    async def btn_edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SetupMessageModal(self))

    @discord.ui.button(label="Add Dropdown Option", style=discord.ButtonStyle.success, row=0)
    async def btn_add_opt(self, interaction: discord.Interaction, button: discord.ui.Button):
        if len(self.options) >= 25:
            return await interaction.response.send_message("<a:Cross_:1489174755537064046> Maximum 25 options allowed.", ephemeral=True)
        await interaction.response.send_modal(SetupOptionModal(self))

    @discord.ui.button(label="Clear Options", style=discord.ButtonStyle.danger, row=0)
    async def btn_clear(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.options = []
        await self.update_menu(interaction)

    @discord.ui.select(placeholder="Publish to Channel...", cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text, discord.ChannelType.news], row=1)
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        if not self.options:
            return await interaction.response.send_message("<a:Cross_:1489174755537064046> You must add at least 1 dropdown option before publishing.", ephemeral=True)

        selected_partial = select.values[0]
        channel = interaction.guild.get_channel(selected_partial.id)
        
        if not channel:
            return await interaction.response.send_message("<a:Cross_:1489174755537064046> Could not find that channel.", ephemeral=True)

        if not channel.permissions_for(interaction.guild.me).send_messages:
            return await interaction.response.send_message("<a:Cross_:1489174755537064046> I lack permissions to send messages there.", ephemeral=True)

        await interaction.response.send_message(f"Publishing panel to {channel.mention}...", ephemeral=True)

        try: color = discord.Color(int(self.panel_color.lstrip("#"), 16))
        except: color = discord.Color(0x2b2d31)
        panel_embed = discord.Embed(title=self.panel_title, description=self.panel_desc, color=color)
        if self.panel_thumb:
            panel_embed.set_thumbnail(url=self.panel_thumb)
        if self.panel_image:
            panel_embed.set_image(url=self.panel_image)

        async with aiosqlite.connect("db/ticket.db") as db:
            cursor = await db.execute("INSERT INTO ticket_panels (guild_id) VALUES (?)", (interaction.guild.id,))
            panel_id = cursor.lastrowid
            
            saved_options = []
            for opt in self.options:
                cur2 = await db.execute("INSERT INTO ticket_options (panel_id, label, description, emoji, category_id) VALUES (?, ?, ?, ?, ?)", 
                                 (panel_id, opt["label"], opt["desc"], opt["emoji"], opt["category_id"]))
                opt_id = cur2.lastrowid
                saved_options.append((opt_id, opt["label"], opt["desc"], opt["emoji"], opt["category_id"]))
            
            await db.commit()

        view = TicketPanelView(panel_id, saved_options)
        msg = await channel.send(embed=panel_embed, view=view)

        async with aiosqlite.connect("db/ticket.db") as db:
            await db.execute("UPDATE ticket_panels SET message_id = ? WHERE id = ?", (msg.id, panel_id))
            await db.commit()
            
        self.bot.add_view(view, message_id=msg.id)
        await interaction.edit_original_response(content=f"<a:tick:1489157731393994854> Panel published successfully in {channel.mention}!")
        self.stop()


# ==========================================
# MAIN TICKET COG
# ==========================================
class TicketSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        os.makedirs('db', exist_ok=True)
        async with aiosqlite.connect('db/ticket.db') as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS ticket_panels (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, message_id INTEGER)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS ticket_options (id INTEGER PRIMARY KEY AUTOINCREMENT, panel_id INTEGER, label TEXT, description TEXT, emoji TEXT, category_id INTEGER)''')
            await db.execute('''CREATE TABLE IF NOT EXISTS tickets (channel_id INTEGER PRIMARY KEY, owner_id INTEGER, guild_id INTEGER, status TEXT DEFAULT 'open', claimed_by INTEGER)''')
            
            # Auto-Migration
            try: await db.execute("ALTER TABLE tickets ADD COLUMN status TEXT DEFAULT 'open'")
            except: pass
            
            try: await db.execute("ALTER TABLE tickets ADD COLUMN claimed_by INTEGER")
            except: pass

            await db.commit()

            # Restore dynamic panels
            async with db.execute("SELECT id, message_id FROM ticket_panels") as cursor:
                panels = await cursor.fetchall()
                for panel_id, msg_id in panels:
                    if msg_id:
                        async with db.execute("SELECT id, label, description, emoji, category_id FROM ticket_options WHERE panel_id = ?", (panel_id,)) as opt_cursor:
                            options_data = await opt_cursor.fetchall()
                            if options_data:
                                self.bot.add_view(TicketPanelView(panel_id, options_data), message_id=msg_id)

        self.bot.add_view(TicketActiveView())
        self.bot.add_view(TicketClosedView())

    # ==========================================
    # FLAT HYBRID COMMANDS
    # ==========================================
    @commands.hybrid_command(name="ticket_setup", description="Admin: Open the interactive Ticket Setup Builder.")
    @commands.has_permissions(administrator=True)
    async def ticket_setup(self, ctx: commands.Context):
        view = AdminSetupView(self.bot)
        embed = discord.Embed(title="⚙️ Ticket Panel Setup Draft", description="Click 'Edit Embed Info' to start building.", color=discord.Color.blue())
        await ctx.send(embed=embed, view=view, ephemeral=True)
        if ctx.interaction is None:
            try: await ctx.message.delete()
            except: pass

    @commands.hybrid_command(name="ticket_add", description="Staff: Add a user to the current ticket.")
    @commands.has_permissions(manage_channels=True)
    async def ticket_add(self, ctx: commands.Context, member: discord.Member):
        async with aiosqlite.connect("db/ticket.db") as db:
            async with db.execute("SELECT 1 FROM tickets WHERE channel_id = ?", (ctx.channel.id,)) as cursor:
                if not await cursor.fetchone():
                    return await ctx.send("<a:Cross_:1489174755537064046> This command must be used inside a ticket channel.", ephemeral=True)

        await ctx.channel.set_permissions(member, read_messages=True, send_messages=True, attach_files=True, embed_links=True)
        await ctx.send(f"<a:tick:1489157731393994854> {member.mention} has been added to the ticket.")

    @commands.hybrid_command(name="ticket_remove", description="Staff: Remove a user from the current ticket.")
    @commands.has_permissions(manage_channels=True)
    async def ticket_remove(self, ctx: commands.Context, member: discord.Member):
        async with aiosqlite.connect("db/ticket.db") as db:
            async with db.execute("SELECT owner_id FROM tickets WHERE channel_id = ?", (ctx.channel.id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return await ctx.send("<a:Cross_:1489174755537064046> This command must be used inside a ticket channel.", ephemeral=True)
                if row[0] == member.id:
                    return await ctx.send("<a:Cross_:1489174755537064046> You cannot remove the ticket owner.", ephemeral=True)

        await ctx.channel.set_permissions(member, overwrite=None)
        await ctx.send(f"<a:tick:1489157731393994854> {member.mention} has been removed from the ticket.")

    @commands.hybrid_command(name="ticket_transcript", description="Staff: Manually generate an HTML transcript of this ticket.")
    @commands.has_permissions(manage_channels=True)
    async def cmd_ticket_transcript(self, ctx: commands.Context):
        async with aiosqlite.connect("db/ticket.db") as db:
            async with db.execute("SELECT 1 FROM tickets WHERE channel_id = ?", (ctx.channel.id,)) as cursor:
                if not await cursor.fetchone():
                    return await ctx.send("<a:Cross_:1489174755537064046> This command must be used inside a ticket channel.", ephemeral=True)

        await ctx.defer()
        file = await generate_transcript(ctx.channel)
        await ctx.send(content="<a:tick:1489157731393994854> **Ticket Transcript Generated**", file=file)

async def setup(bot):
    await bot.add_cog(TicketSystem(bot))