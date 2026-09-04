# cogs/utils/help_view.py
"""Professional, interactive help panel: an embed + dropdown select menu
letting the user browse categories without re-running the command."""
from __future__ import annotations

import discord
from discord.ext import commands
from typing import List, Optional

from cogs.utils.emoji_manager import EMOJI
from cogs.utils.help_data import CATEGORIES, CategoryMeta, find_category

ACCENT_COLOR = discord.Color(0x7C5CFC)  # matches the dashboard's violet accent


def _available_categories(bot: commands.Bot) -> List[CategoryMeta]:
    """Only show categories whose cog is actually loaded and has visible commands."""
    out = []
    for meta in CATEGORIES:
        cog = bot.get_cog(meta.cog_name)
        if not cog:
            continue
        if any(not c.hidden for c in cog.get_commands()):
            out.append(meta)
    return out


def build_home_embed(bot: commands.Bot, prefix: str) -> discord.Embed:
    cats = _available_categories(bot)
    embed = discord.Embed(
        title=f"{EMOJI['scroll']} Help Menu",
        description=(
            f"Pick a category from the dropdown below to see its commands.\n"
            f"Prefix commands use `{prefix}`, or use `/` for slash commands."
        ),
        color=ACCENT_COLOR,
    )
    if bot.user:
        embed.set_thumbnail(url=bot.user.display_avatar.url)

    for meta in cats:
        cog = bot.get_cog(meta.cog_name)
        count = len([c for c in cog.get_commands() if not c.hidden])
        embed.add_field(
            name=f"{EMOJI[meta.emoji_slug]} {meta.display}",
            value=f"{meta.description}\n*{count} command{'s' if count != 1 else ''}*",
            inline=True,
        )

    embed.set_footer(text=f"{len(cats)} categories • {sum(len([c for c in bot.get_cog(m.cog_name).get_commands() if not c.hidden]) for m in cats)} commands total")
    return embed


def build_category_embed(bot: commands.Bot, meta: CategoryMeta, prefix: str) -> discord.Embed:
    cog = bot.get_cog(meta.cog_name)
    if not cog:
        return discord.Embed(
            title=f"{EMOJI['error']} Category unavailable",
            description=f"**{meta.display}** isn't currently loaded (it may be disabled).",
            color=discord.Color.red(),
        )

    commands_list = sorted([c for c in cog.get_commands() if not c.hidden], key=lambda c: c.name)
    embed = discord.Embed(
        title=f"{EMOJI[meta.emoji_slug]} {meta.display}",
        description=meta.description,
        color=ACCENT_COLOR,
    )

    if not commands_list:
        embed.add_field(name="No commands", value="This category has no public commands right now.", inline=False)
        return embed

    for cmd in commands_list:
        is_slash = isinstance(cmd, commands.HybridCommand) or getattr(cmd, "with_app_command", False)
        sig = cmd.signature or ""
        usage = f"/{cmd.name} {sig}".strip() if is_slash else f"{prefix}{cmd.name} {sig}".strip()
        description = (cmd.help or cmd.description or "No description provided.").strip().split("\n")[0]
        embed.add_field(
            name=f"{EMOJI['diamond_blue']} `{usage}`",
            value=description[:100],
            inline=False,
        )

    embed.set_footer(text=f"{len(commands_list)} command{'s' if len(commands_list) != 1 else ''} in {meta.display}")
    return embed


class CategorySelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot, prefix: str, author_id: int):
        self.bot = bot
        self.prefix = prefix
        self.author_id = author_id
        cats = _available_categories(bot)

        options = [discord.SelectOption(label="Home", description="Back to the category overview", value="__home__", emoji="🏠")]
        for meta in cats:
            options.append(discord.SelectOption(
                label=meta.display,
                description=meta.description[:100],
                value=meta.cog_name,
            ))

        super().__init__(placeholder="Choose a category…", min_values=1, max_values=1, options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message(
                f"{EMOJI['error']} Only the person who ran `/help` can use this menu.", ephemeral=True
            )

        value = self.values[0]
        if value == "__home__":
            embed = build_home_embed(self.bot, self.prefix)
        else:
            meta = find_category(value)
            embed = build_category_embed(self.bot, meta, self.prefix) if meta else build_home_embed(self.bot, self.prefix)

        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(discord.ui.View):
    def __init__(self, bot: commands.Bot, prefix: str, author_id: int, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.message: Optional[discord.Message] = None
        self.add_item(CategorySelect(bot, prefix, author_id))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass
