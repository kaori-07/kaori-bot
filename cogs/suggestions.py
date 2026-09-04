import discord
from discord.ext import commands
from discord import app_commands
from cogs.utils.emoji_manager import EMOJI
from cogs.utils.json_store import get_store

STORE_FILE = "suggestions.json"
UPVOTE = "👍"
DOWNVOTE = "👎"


class SuggestionActionView(discord.ui.View):
    def __init__(self, cog: "Suggestions", suggestion_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.suggestion_id = suggestion_id

    async def _resolve(self, interaction: discord.Interaction, status: str, color: discord.Color):
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message(f"{EMOJI['error']} You need Manage Server to do that.", ephemeral=True)

        embed = interaction.message.embeds[0]
        embed.color = color
        embed.set_footer(text=f"{status} by {interaction.user.display_name}")
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, "Approved", discord.Color.green())

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, emoji="❌")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._resolve(interaction, "Denied", discord.Color.red())


class Suggestions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.store = get_store(STORE_FILE, dict)

    @commands.command(name="suggestions_setchannel", description="Set the channel suggestions get posted to.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def suggestions_setchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        def _mut(data):
            data[str(ctx.guild.id)] = channel.id
            return data
        self.store.mutate(_mut)
        await ctx.send(f"{EMOJI['success']} Suggestions will now be posted to {channel.mention}.")

    @commands.hybrid_command(name="suggest", description="Submit a suggestion for staff to review.")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.guild_only()
    async def suggest(self, ctx: commands.Context, *, suggestion: str):
        channel_id = self.store.read().get(str(ctx.guild.id))
        if not channel_id:
            return await ctx.send(f"{EMOJI['error']} No suggestions channel configured. Ask an admin to run `/suggestions_setchannel`.")
        channel = ctx.guild.get_channel(channel_id)
        if not channel:
            return await ctx.send(f"{EMOJI['error']} Configured suggestions channel no longer exists.")

        embed = discord.Embed(title=f"{EMOJI['sparkle']} New Suggestion", description=suggestion, color=discord.Color.blurple())
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        embed.set_footer(text="Pending review")

        view = SuggestionActionView(self, "")
        msg = await channel.send(embed=embed, view=view)
        try:
            await msg.add_reaction(UPVOTE)
            await msg.add_reaction(DOWNVOTE)
        except discord.HTTPException:
            pass

        await ctx.send(f"{EMOJI['success']} Suggestion submitted in {channel.mention}!")


async def setup(bot):
    await bot.add_cog(Suggestions(bot))
