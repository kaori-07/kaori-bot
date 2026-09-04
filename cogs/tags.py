import discord
from discord.ext import commands
from discord import app_commands
from cogs.utils.emoji_manager import EMOJI
from cogs.utils.json_store import get_store

STORE_FILE = "tags.json"


class Tags(commands.Cog):
    """Staff-defined reusable text snippets, e.g. /tag rules -> posts the rules text."""

    def __init__(self, bot):
        self.bot = bot
        self.store = get_store(STORE_FILE, dict)

    def _guild_tags(self, guild_id: int) -> dict:
        return self.store.read().get(str(guild_id), {})

    @commands.hybrid_command(name="tag", description="Show a custom tag's content.")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.guild_only()
    async def tag(self, ctx: commands.Context, name: str):
        tags = self._guild_tags(ctx.guild.id)
        content = tags.get(name.lower())
        if not content:
            return await ctx.send(f"{EMOJI['error']} No tag named `{name}`. Use `/tag_list` to see available tags.")
        await ctx.send(content)

    @commands.command(name="tag_create", description="Create or update a tag.")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def tag_create(self, ctx: commands.Context, name: str, *, content: str):
        name = name.lower().strip()

        def _mut(data):
            data.setdefault(str(ctx.guild.id), {})[name] = content
            return data
        self.store.mutate(_mut)
        await ctx.send(f"{EMOJI['success']} Tag `{name}` saved.")

    @commands.command(name="tag_delete", description="Delete a tag.")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def tag_delete(self, ctx: commands.Context, name: str):
        name = name.lower().strip()

        def _mut(data):
            data.get(str(ctx.guild.id), {}).pop(name, None)
            return data
        self.store.mutate(_mut)
        await ctx.send(f"{EMOJI['success']} Tag `{name}` deleted (if it existed).")

    @commands.command(name="tag_list", description="List all tags in this server.")
    @commands.guild_only()
    async def tag_list(self, ctx: commands.Context):
        tags = self._guild_tags(ctx.guild.id)
        if not tags:
            return await ctx.send(f"{EMOJI['info']} No tags created yet.")
        embed = discord.Embed(title=f"{EMOJI['tag']} Tags", description=", ".join(f"`{t}`" for t in sorted(tags)), color=discord.Color.blurple())
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Tags(bot))
