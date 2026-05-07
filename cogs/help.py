import discord
from discord.ext import commands
from typing import List, Optional

# The custom emoji prefix you requested
EMOJI_PREFIX = "<a:black_arrow:1489156337962319932>"

def build_cog_embed(cog: Optional[commands.Cog], cog_name: str) -> discord.Embed:
    if not cog:
        return discord.Embed(title="Not found", description="Category not found", color=discord.Color.red())

    commands_list = [c for c in cog.get_commands() if not c.hidden]
    embed = discord.Embed(title=f"<:folder:1489151375077150810> {cog_name} — Commands", color=discord.Color.blurple())
    
    if not commands_list:
        embed.description = "No public commands in this category."
        return embed

    for cmd in commands_list:
        sig = cmd.signature if hasattr(cmd, "signature") else ""
        description = (cmd.help or cmd.description or "No description").strip()
        # Uses the custom emoji instead of the text prefix
        embed.add_field(
            name=f"{EMOJI_PREFIX} {cmd.name} {sig}".strip(), 
            value=description or "No description", 
            inline=False
        )

    embed.set_footer(text="Use the dropdown to jump categories • Use the arrows to cycle")
    return embed

class HelpSelect(discord.ui.Select):
    def __init__(self, cog_names: List[str]):
        options = []
        for name in cog_names[:25]:
            options.append(discord.SelectOption(label=name, description=f"Show commands for {name}", value=name))
        super().__init__(placeholder="Select a category...", min_values=1, max_values=1, options=options)
        self.cog_names = cog_names

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        view: HelpView = self.view  # type: ignore
        await view.show_category(interaction, selected)

class ArrowButton(discord.ui.Button):
    def __init__(self, emoji: str, direction: int):
        super().__init__(style=discord.ButtonStyle.secondary, emoji=emoji)
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        view: HelpView = self.view  # type: ignore
        await view.advance(interaction, self.direction)

class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot, cog_names: List[str], author_id: int, timeout: int = 180):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.cog_names = cog_names
        self.author_id = author_id
        self.index = 0

        self.add_item(HelpSelect(self.cog_names))
        self.add_item(ArrowButton("<a:arrow_lefts:1489152047633797131>", -1))
        self.add_item(ArrowButton("<a:side_arrow_2:1489151786903408865>", 1))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You can't interact with this help panel — use the command yourself.", ephemeral=True)
            return False
        return True

    async def show_category(self, interaction: discord.Interaction, cog_name: str):
        cog = self.bot.get_cog(cog_name)
        if not cog:
            return await interaction.response.send_message("Category not found.", ephemeral=True)

        embed = build_cog_embed(cog, cog_name)
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            await interaction.response.send_message(embed=embed, view=self, ephemeral=False)

    async def advance(self, interaction: discord.Interaction, direction: int):
        if not self.cog_names:
            return await interaction.response.send_message("No categories available.", ephemeral=True)
        
        self.index = (self.index + direction) % len(self.cog_names)
        cog_name = self.cog_names[self.index]
        cog = self.bot.get_cog(cog_name)
        embed = build_cog_embed(cog, cog_name)
        
        try:
            await interaction.response.edit_message(embed=embed, view=self)
        except Exception:
            await interaction.response.send_message(embed=embed, view=self)

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="help", with_app_command=True, description="Shows help menu with categories and commands.")
    async def help_cmd(self, ctx: commands.Context, category: Optional[str] = None):
        """Displays the help panel. Use no args to show the interactive panel, or `/help <category>` to show a single category."""
        
        if category:
            cog = self.bot.get_cog(category.capitalize())
            if not cog:
                return await ctx.send("<a:Cross_:1489174755537064046> Category not found. Use `/help` to see available categories.")
            embed = build_cog_embed(cog, category.capitalize())
            return await ctx.send(embed=embed)

        # Build interactive view (only showing cogs that have visible commands)
        cog_names = [name for name, cog in self.bot.cogs.items() if len([c for c in cog.get_commands() if not c.hidden]) > 0]
        if not cog_names:
            return await ctx.send("No categories/commands loaded.")

        embed = discord.Embed(
            title="<:BlueScroll:1489151045933207643> Help Menu", 
            description="Choose a category from the dropdown or use arrows to cycle.\n\nTip: Use `/help <category>` to open that category directly.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Available categories", value=", ".join(cog_names[:40]) + ("" if len(cog_names) <= 40 else "…"), inline=False)
        
        # Pulling the prefix from the main bot setup for the footer info
        prefix = getattr(self.bot, "_my_prefix", "/")
        embed.set_footer(text=f"Prefix: {prefix} • Showing {len(cog_names)} categories")

        view = HelpView(bot=self.bot, cog_names=cog_names, author_id=ctx.author.id)
        
        try:
            if ctx.interaction is not None:
                await ctx.interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                await ctx.send(embed=embed, view=view)
        except Exception:
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Help(bot))