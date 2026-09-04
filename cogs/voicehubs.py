import discord
from discord.ext import commands
from discord import app_commands
from cogs.utils.emoji_manager import EMOJI
from cogs.utils.json_store import get_store

STORE_FILE = "voicehubs.json"


class VoiceHubs(commands.Cog):
    """'Join to Create' temp voice channels: joining the configured hub channel
    spawns a fresh voice channel owned by that user, auto-deleted when empty."""

    def __init__(self, bot):
        self.bot = bot
        self.store = get_store(STORE_FILE, dict)
        self._temp_channels: set[int] = set()

    def _guild_cfg(self, guild_id: int) -> dict:
        return self.store.read().get(str(guild_id), {})

    @commands.hybrid_command(name="voicehub_setup", description="Set the 'Join to Create' hub channel.")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def voicehub_setup(self, ctx: commands.Context, hub_channel: discord.VoiceChannel):
        def _mut(data):
            data[str(ctx.guild.id)] = {"hub_id": hub_channel.id, "category_id": hub_channel.category_id}
            return data
        self.store.mutate(_mut)
        await ctx.send(f"{EMOJI['success']} Joining **{hub_channel.name}** now spawns a personal voice channel.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        cfg = self._guild_cfg(member.guild.id)
        hub_id = cfg.get("hub_id")

        # joined the hub -> create a temp channel and move them into it
        if hub_id and after.channel and after.channel.id == hub_id:
            category = member.guild.get_channel(cfg.get("category_id")) if cfg.get("category_id") else after.channel.category
            try:
                new_channel = await member.guild.create_voice_channel(
                    name=f"{member.display_name}'s Room",
                    category=category,
                    reason="Temp voice channel (Join to Create)",
                )
                await new_channel.set_permissions(member, manage_channels=True, move_members=True)
                await member.move_to(new_channel)
                self._temp_channels.add(new_channel.id)
            except discord.HTTPException:
                pass

        # left a temp channel that's now empty -> delete it
        if before.channel and before.channel.id in self._temp_channels and len(before.channel.members) == 0:
            try:
                await before.channel.delete(reason="Temp voice channel emptied")
            except discord.HTTPException:
                pass
            self._temp_channels.discard(before.channel.id)


async def setup(bot):
    await bot.add_cog(VoiceHubs(bot))
