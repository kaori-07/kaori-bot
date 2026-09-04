import discord
from discord.ext import commands
from discord import app_commands
from cogs.utils.emoji_manager import EMOJI
from cogs.utils.json_store import get_store

STORE_FILE = "verification.json"


class VerifyView(discord.ui.View):
    def __init__(self, role_id: int):
        super().__init__(timeout=None)
        self.role_id = role_id

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.success, emoji="✅", custom_id="verify_button")
    async def verify(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            return await interaction.response.send_message(f"{EMOJI['error']} Verification role no longer exists — contact staff.", ephemeral=True)
        if role in interaction.user.roles:
            return await interaction.response.send_message(f"{EMOJI['info']} You're already verified.", ephemeral=True)
        try:
            await interaction.user.add_roles(role, reason="Self-verification")
        except discord.Forbidden:
            return await interaction.response.send_message(f"{EMOJI['error']} I couldn't assign the role — check my permissions.", ephemeral=True)
        await interaction.response.send_message(f"{EMOJI['success']} You're verified! Welcome.", ephemeral=True)


class Verification(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.store = get_store(STORE_FILE, dict)

    async def cog_load(self):
        # re-register persistent verify buttons for every configured guild so they
        # keep working across restarts
        for guild_id, entry in self.store.read().items():
            role_id = entry.get("role_id")
            if role_id:
                self.bot.add_view(VerifyView(role_id))

    @commands.hybrid_command(name="verification_setup", description="Post a verification panel that grants a role on click.")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def verification_setup(self, ctx: commands.Context, role: discord.Role, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        if role >= ctx.guild.me.top_role:
            return await ctx.send(f"{EMOJI['error']} I can't assign a role higher than or equal to my own top role.")

        def _mut(data):
            data[str(ctx.guild.id)] = {"role_id": role.id}
            return data
        self.store.mutate(_mut)

        embed = discord.Embed(
            title=f"{EMOJI['shield_check']} Verification",
            description="Click the button below to verify yourself and gain access to the server.",
            color=discord.Color.green(),
        )
        view = VerifyView(role.id)
        self.bot.add_view(view)
        await channel.send(embed=embed, view=view)
        await ctx.send(f"{EMOJI['success']} Verification panel posted in {channel.mention}.")


async def setup(bot):
    await bot.add_cog(Verification(bot))
