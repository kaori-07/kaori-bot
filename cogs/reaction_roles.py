import discord
from discord.ext import commands
from discord import app_commands
from cogs.utils.emoji_manager import EMOJI
from cogs.utils.json_store import get_store

STORE_FILE = "reaction_roles.json"


class ReactionRoles(commands.Cog):
    """Self-assign roles by reacting to a message."""

    def __init__(self, bot):
        self.bot = bot
        self.store = get_store(STORE_FILE, dict)

    @property
    def data(self) -> dict:
        return self.store.read()

    def _key(self, message_id: int) -> str:
        return str(message_id)

    @commands.hybrid_command(name="reactionrole_add", description="Bind an emoji on a message to a role.")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def reactionrole_add(self, ctx: commands.Context, message_id: str, emoji: str, role: discord.Role):
        try:
            msg_id = int(message_id)
        except ValueError:
            return await ctx.send(f"{EMOJI['error']} That doesn't look like a valid message ID.")

        channel = ctx.channel
        try:
            message = await channel.fetch_message(msg_id)
        except discord.NotFound:
            return await ctx.send(f"{EMOJI['error']} Message not found in this channel.")

        if role >= ctx.guild.me.top_role:
            return await ctx.send(f"{EMOJI['error']} I can't assign a role higher than or equal to my own top role.")

        try:
            await message.add_reaction(emoji)
        except discord.HTTPException:
            return await ctx.send(f"{EMOJI['error']} I couldn't react with that emoji — is it valid?")

        data = self.data
        entry = data.setdefault(self._key(msg_id), {"channel_id": channel.id, "guild_id": ctx.guild.id, "roles": {}})
        entry["roles"][emoji] = role.id
        self.store.save(data)

        await ctx.send(f"{EMOJI['success']} Reacting with {emoji} on that message now toggles **{role.name}**.")

    @commands.command(name="reactionrole_remove", description="Unbind an emoji from a reaction-role message.")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def reactionrole_remove(self, ctx: commands.Context, message_id: str, emoji: str):
        data = self.data
        entry = data.get(self._key(message_id))
        if not entry or emoji not in entry.get("roles", {}):
            return await ctx.send(f"{EMOJI['error']} No binding found for that emoji on that message.")
        del entry["roles"][emoji]
        if not entry["roles"]:
            del data[self._key(message_id)]
        self.store.save(data)
        await ctx.send(f"{EMOJI['success']} Removed that binding.")

    @commands.command(name="reactionrole_list", description="List reaction-role bindings in this server.")
    @commands.guild_only()
    async def reactionrole_list(self, ctx: commands.Context):
        entries = [(mid, e) for mid, e in self.data.items() if e.get("guild_id") == ctx.guild.id]
        if not entries:
            return await ctx.send(f"{EMOJI['info']} No reaction roles set up in this server.")

        embed = discord.Embed(title=f"{EMOJI['tag']} Reaction Roles", color=discord.Color.blurple())
        for mid, e in entries[:20]:
            role_lines = []
            for emoji, role_id in e.get("roles", {}).items():
                role = ctx.guild.get_role(role_id)
                role_lines.append(f"{emoji} → {role.mention if role else '*deleted role*'}")
            embed.add_field(name=f"Message {mid}", value="\n".join(role_lines) or "—", inline=False)
        await ctx.send(embed=embed)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member is None or payload.member.bot:
            return
        entry = self.data.get(str(payload.message_id))
        if not entry:
            return
        emoji_key = str(payload.emoji)
        role_id = entry.get("roles", {}).get(emoji_key)
        if not role_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        role = guild.get_role(role_id)
        if not role:
            return
        try:
            await payload.member.add_roles(role, reason="Reaction role")
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        entry = self.data.get(str(payload.message_id))
        if not entry:
            return
        emoji_key = str(payload.emoji)
        role_id = entry.get("roles", {}).get(emoji_key)
        if not role_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        role = guild.get_role(role_id)
        if not member or not role or member.bot:
            return
        try:
            await member.remove_roles(role, reason="Reaction role")
        except discord.HTTPException:
            pass


async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))
