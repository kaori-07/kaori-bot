import discord
from discord.ext import commands
from discord import app_commands
from cogs.utils.emoji_manager import EMOJI
from cogs.utils.json_store import get_store

STORE_FILE = "starboard.json"
DEFAULT_CFG = {"channel_id": None, "threshold": 3, "emoji": "⭐", "posted": {}}


class Starboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.store = get_store(STORE_FILE, dict)

    @property
    def data(self) -> dict:
        return self.store.read()

    def _guild_cfg(self, guild_id: int) -> dict:
        entry = self.data.get(str(guild_id))
        if not entry:
            return {**DEFAULT_CFG, "posted": {}}
        return {**DEFAULT_CFG, **entry}

    def _mut_cfg(self, guild_id: int, fn):
        def _mut(data):
            entry = {**DEFAULT_CFG, **data.get(str(guild_id), {}), "posted": data.get(str(guild_id), {}).get("posted", {})}
            fn(entry)
            data[str(guild_id)] = entry
            return data
        self.store.mutate(_mut)

    @commands.hybrid_command(name="starboard_setup", description="Configure the starboard channel and threshold.")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def starboard_setup(self, ctx: commands.Context, channel: discord.TextChannel, threshold: int = 3, emoji: str = "⭐"):
        threshold = max(1, threshold)
        self._mut_cfg(ctx.guild.id, lambda e: e.update(channel_id=channel.id, threshold=threshold, emoji=emoji))
        await ctx.send(f"{EMOJI['star']} Starboard set to {channel.mention}, threshold **{threshold}** {emoji}.")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        cfg = self._guild_cfg(payload.guild_id)
        if not cfg["channel_id"] or str(payload.emoji) != cfg["emoji"]:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        channel = guild.get_channel(payload.channel_id)
        if not channel:
            return
        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.HTTPException:
            return
        if message.author.bot:
            return

        reaction = discord.utils.get(message.reactions, emoji=cfg["emoji"])
        count = reaction.count if reaction else 0
        if count < cfg["threshold"]:
            return

        star_channel = guild.get_channel(cfg["channel_id"])
        if not star_channel:
            return

        key = str(message.id)
        posted_id = cfg["posted"].get(key)

        embed = discord.Embed(description=message.content or "*(no text content)*", color=discord.Color.gold(), timestamp=message.created_at)
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.add_field(name="Source", value=f"[Jump to message]({message.jump_url})", inline=False)
        if message.attachments:
            embed.set_image(url=message.attachments[0].url)
        embed.set_footer(text=f"{cfg['emoji']} {count} · #{channel.name}")

        if posted_id:
            try:
                star_msg = await star_channel.fetch_message(int(posted_id))
                await star_msg.edit(embed=embed)
                return
            except discord.HTTPException:
                pass

        try:
            star_msg = await star_channel.send(embed=embed)
        except discord.HTTPException:
            return

        self._mut_cfg(payload.guild_id, lambda e: e["posted"].update({key: star_msg.id}))


async def setup(bot):
    await bot.add_cog(Starboard(bot))
