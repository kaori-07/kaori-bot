import discord
from discord.ext import commands
from discord import app_commands
import json
from cogs.utils.emoji_manager import EMOJI

# ==========================================
# UI MODALS FOR EMBED BUILDER
# ==========================================

class EmbedBasicModal(discord.ui.Modal, title='Edit Basic Info'):
    emb_title = discord.ui.TextInput(label='Title', style=discord.TextStyle.short, required=False, max_length=256)
    emb_desc = discord.ui.TextInput(label='Description', style=discord.TextStyle.paragraph, required=False, max_length=4000)
    emb_color = discord.ui.TextInput(label='Hex Color (e.g. #FF0000)', style=discord.TextStyle.short, required=False, max_length=7)

    def __init__(self, view: "EmbedBuilderView"):
        super().__init__()
        self.view_obj = view
        self.emb_title.default = view.embed_draft.title if view.embed_draft.title else ""
        self.emb_desc.default = view.embed_draft.description if view.embed_draft.description else ""
        self.emb_color.default = f"#{view.embed_draft.color.value:06x}" if view.embed_draft.color else ""

    async def on_submit(self, interaction: discord.Interaction):
        self.view_obj.embed_draft.title = self.emb_title.value if self.emb_title.value else None
        self.view_obj.embed_draft.description = self.emb_desc.value if self.emb_desc.value else None
        
        if self.emb_color.value:
            try:
                color_val = int(self.emb_color.value.lstrip("#"), 16)
                self.view_obj.embed_draft.color = discord.Color(color_val)
            except ValueError:
                pass # Ignore invalid color
                
        await self.view_obj.update_preview(interaction)

class EmbedAuthorModal(discord.ui.Modal, title='Edit Author'):
    a_name = discord.ui.TextInput(label='Author Name', style=discord.TextStyle.short, required=False, max_length=256)
    a_url = discord.ui.TextInput(label='Author URL', style=discord.TextStyle.short, required=False)
    a_icon = discord.ui.TextInput(label='Author Icon URL', style=discord.TextStyle.short, required=False)

    def __init__(self, view: "EmbedBuilderView"):
        super().__init__()
        self.view_obj = view
        if view.embed_draft.author:
            self.a_name.default = view.embed_draft.author.name or ""
            self.a_url.default = view.embed_draft.author.url or ""
            self.a_icon.default = view.embed_draft.author.icon_url or ""

    async def on_submit(self, interaction: discord.Interaction):
        if self.a_name.value:
            self.view_obj.embed_draft.set_author(
                name=self.a_name.value, 
                url=self.a_url.value if self.a_url.value else None, 
                icon_url=self.a_icon.value if self.a_icon.value else None
            )
        else:
            self.view_obj.embed_draft.remove_author()
        await self.view_obj.update_preview(interaction)

class EmbedImagesModal(discord.ui.Modal, title='Edit Images'):
    thumb_url = discord.ui.TextInput(label='Thumbnail URL', style=discord.TextStyle.short, required=False)
    img_url = discord.ui.TextInput(label='Large Image URL', style=discord.TextStyle.short, required=False)

    def __init__(self, view: "EmbedBuilderView"):
        super().__init__()
        self.view_obj = view
        self.thumb_url.default = view.embed_draft.thumbnail.url if view.embed_draft.thumbnail else ""
        self.img_url.default = view.embed_draft.image.url if view.embed_draft.image else ""

    async def on_submit(self, interaction: discord.Interaction):
        if self.thumb_url.value:
            self.view_obj.embed_draft.set_thumbnail(url=self.thumb_url.value)
        else:
            self.view_obj.embed_draft.set_thumbnail(url=None)
            
        if self.img_url.value:
            self.view_obj.embed_draft.set_image(url=self.img_url.value)
        else:
            self.view_obj.embed_draft.set_image(url=None)
            
        await self.view_obj.update_preview(interaction)

class EmbedFooterModal(discord.ui.Modal, title='Edit Footer'):
    f_text = discord.ui.TextInput(label='Footer Text', style=discord.TextStyle.short, required=False, max_length=2048)
    f_icon = discord.ui.TextInput(label='Footer Icon URL', style=discord.TextStyle.short, required=False)

    def __init__(self, view: "EmbedBuilderView"):
        super().__init__()
        self.view_obj = view
        if view.embed_draft.footer:
            self.f_text.default = view.embed_draft.footer.text or ""
            self.f_icon.default = view.embed_draft.footer.icon_url or ""

    async def on_submit(self, interaction: discord.Interaction):
        if self.f_text.value:
            self.view_obj.embed_draft.set_footer(
                text=self.f_text.value, 
                icon_url=self.f_icon.value if self.f_icon.value else None
            )
        else:
            self.view_obj.embed_draft.remove_footer()
        await self.view_obj.update_preview(interaction)

# ==========================================
# INTERACTIVE VIEW FOR BUILDER
# ==========================================

class EmbedBuilderView(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=900)
        self.ctx = ctx
        self.embed_draft = discord.Embed(title="My Custom Embed", description="Click the buttons below to edit me!", color=discord.Color.blurple())
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("Only the command author can use these buttons.", ephemeral=True)
            return False
        return True

    async def update_preview(self, interaction: discord.Interaction):
        try:
            await interaction.response.edit_message(embed=self.embed_draft, view=self)
        except discord.HTTPException:
            pass

    @discord.ui.button(label="Basic Info", style=discord.ButtonStyle.primary, row=0)
    async def btn_basic(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedBasicModal(self))

    @discord.ui.button(label="Author", style=discord.ButtonStyle.secondary, row=0)
    async def btn_author(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedAuthorModal(self))

    @discord.ui.button(label="Images", style=discord.ButtonStyle.secondary, row=0)
    async def btn_images(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedImagesModal(self))

    @discord.ui.button(label="Footer", style=discord.ButtonStyle.secondary, row=0)
    async def btn_footer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(EmbedFooterModal(self))

    @discord.ui.select(placeholder="Select channel to send to...", cls=discord.ui.ChannelSelect, channel_types=[discord.ChannelType.text, discord.ChannelType.news], row=1)
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        selected_item = select.values[0]
        
        # 1. Resolve the selected AppCommandChannel into a full GuildChannel object
        channel = interaction.guild.get_channel(selected_item.id)
        
        # Fallback if the channel somehow can't be resolved
        if not channel:
            return await interaction.response.send_message(f"{EMOJI['error']} Error: Could not fully resolve the selected channel.", ephemeral=True)

        # 2. Check permissions on the newly resolved channel object
        if not channel.permissions_for(interaction.guild.me).send_messages:
            return await interaction.response.send_message(f"{EMOJI['error']} I don't have permission to send messages in {channel.mention}.", ephemeral=True)
        
        # 3. Attempt to send the embed
        try:
            await channel.send(embed=self.embed_draft)
            await interaction.response.send_message(f"{EMOJI['success']} Embed successfully sent to {channel.mention}!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"{EMOJI['error']} Failed to send: {e}", ephemeral=True)

# ==========================================
# MAIN COG CLASS
# ==========================================

class EmbedManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="embed_builder", description="Open the interactive GUI to build an embed.")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def embed_builder(self, ctx: commands.Context):
        view = EmbedBuilderView(ctx)
        view.message = await ctx.send("### 🛠️ Interactive Embed Builder", embed=view.embed_draft, view=view)

    @commands.hybrid_command(name="embed_quick", description="Quickly send a simple embed to a channel.")
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.has_permissions(manage_messages=True)
    async def embed_quick(self, ctx: commands.Context, channel: discord.TextChannel, title: str, description: str, hex_color: str = "#2f3136"):
        try:
            color_val = int(hex_color.lstrip("#"), 16)
            color = discord.Color(color_val)
        except ValueError:
            color = discord.Color(0x2f3136)
            
        embed = discord.Embed(title=title, description=description, color=color)
        
        try:
            await channel.send(embed=embed)
            await ctx.send(f"{EMOJI['success']} Quick embed sent to {channel.mention}.", ephemeral=True)
        except discord.Forbidden:
            await ctx.send(f"{EMOJI['error']} I don't have permissions to send messages in {channel.mention}.", ephemeral=True)

    @commands.command(name="embed_json", description="Send an advanced embed using JSON format.")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def embed_json(self, ctx: commands.Context, channel: discord.TextChannel, *, json_data: str):
        # Strip codeblocks if user provided them
        if json_data.startswith("```"):
            json_data = "\n".join(json_data.split("\n")[1:-1])
            
        try:
            data = json.loads(json_data)
            embed = discord.Embed.from_dict(data)
            await channel.send(embed=embed)
            await ctx.send(f"{EMOJI['success']} JSON Embed successfully sent to {channel.mention}.", ephemeral=True)
        except json.JSONDecodeError as e:
            await ctx.send(f"{EMOJI['error']} Invalid JSON format:\n```py\n{e}\n```", ephemeral=True)
        except Exception as e:
            await ctx.send(f"{EMOJI['error']} An error occurred:\n```py\n{e}\n```", ephemeral=True)

    @commands.command(name="embed_edit", description="Edit an existing embed sent by the bot using a message link and JSON.")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def embed_edit(self, ctx: commands.Context, message_link: str, *, json_data: str):
        try:
            # Parse the message link (Format: [https://discord.com/channels/GUILD_ID/CHANNEL_ID/MESSAGE_ID](https://discord.com/channels/GUILD_ID/CHANNEL_ID/MESSAGE_ID))
            parts = message_link.split("/")
            channel_id = int(parts[-2])
            message_id = int(parts[-1])
            
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return await ctx.send(f"{EMOJI['error']} Could not find the channel from that link.", ephemeral=True)

            if getattr(channel, "guild", None) is None or channel.guild.id != ctx.guild.id:
                return await ctx.send(f"{EMOJI['error']} That message isn't in this server.", ephemeral=True)

            msg = await channel.fetch_message(message_id)
            if msg.author != self.bot.user:
                return await ctx.send(f"{EMOJI['error']} I can only edit messages that were sent by me.", ephemeral=True)

            # Clean JSON
            if json_data.startswith("```"):
                json_data = "\n".join(json_data.split("\n")[1:-1])
                
            data = json.loads(json_data)
            embed = discord.Embed.from_dict(data)
            
            await msg.edit(embed=embed)
            await ctx.send(f"{EMOJI['success']} Embed edited successfully! [Jump to Message]({message_link})", ephemeral=True)
            
        except ValueError:
            await ctx.send(f"{EMOJI['error']} Invalid message link provided.", ephemeral=True)
        except discord.NotFound:
            await ctx.send(f"{EMOJI['error']} Message not found.", ephemeral=True)
        except json.JSONDecodeError as e:
            await ctx.send(f"{EMOJI['error']} Invalid JSON format:\n```py\n{e}\n```", ephemeral=True)
        except Exception as e:
            await ctx.send(f"{EMOJI['error']} An error occurred:\n```py\n{e}\n```", ephemeral=True)

async def setup(bot):
    await bot.add_cog(EmbedManager(bot))