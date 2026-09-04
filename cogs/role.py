import discord
from discord.ext import commands
from discord import app_commands
from cogs.utils.emoji_manager import EMOJI

class Role(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Add role to a member
    @commands.hybrid_command(name="addrole", description="Assign a role to a member.")
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.has_permissions(manage_roles=True)
    async def addrole(self, ctx: commands.Context, member: discord.Member, role: discord.Role):
        try:
            await member.add_roles(role)
        except discord.Forbidden:
            return await ctx.send(f"{EMOJI['error']} I can't assign **{role.name}** — check role hierarchy/permissions.")
        except discord.HTTPException as e:
            return await ctx.send(f"{EMOJI['error']} Failed to add role: {e}")
        embed = discord.Embed(
            title=f"{EMOJI['success']} Role Added",
            description=f"The role **{role.name}** has been added to **{member.name}**.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    # Remove role from a member
    @commands.hybrid_command(name="removerole", description="Remove a role from a member.")
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.has_permissions(manage_roles=True)
    async def removerole(self, ctx: commands.Context, member: discord.Member, role: discord.Role):
        try:
            await member.remove_roles(role)
        except discord.Forbidden:
            return await ctx.send(f"{EMOJI['error']} I can't remove **{role.name}** — check role hierarchy/permissions.")
        except discord.HTTPException as e:
            return await ctx.send(f"{EMOJI['error']} Failed to remove role: {e}")
        embed = discord.Embed(
            title=f"{EMOJI['success']} Role Removed",
            description=f"The role **{role.name}** has been removed from **{member.name}**.",
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

    # Create a new role
    @commands.command(name="createrole", description="Create a new role with a name and optional color.")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def createrole(self, ctx: commands.Context, role_name: str, color: str = "blue"):
        try:
            role_color = getattr(discord.Color, color.lower())()
        except AttributeError:
            role_color = discord.Color.blue()  # Default to blue if invalid color

        role = await ctx.guild.create_role(name=role_name, color=role_color)
        embed = discord.Embed(
            title=f"{EMOJI['success']} Role Created",
            description=f"The role **{role.name}** has been successfully created.",
            color=role.color
        )
        await ctx.send(embed=embed)

    # List all roles
    @commands.command(name="listroles", description="List all roles in the server.")
    @commands.guild_only()
    async def listroles(self, ctx: commands.Context):
        roles = [role.name for role in ctx.guild.roles if role.name != "@everyone"]
        embed = discord.Embed(
            title=f"{EMOJI['masks']} Server Roles",
            description="\n".join(roles) if roles else "No roles available.",
            color=discord.Color.purple()
        )
        await ctx.send(embed=embed)

    # Role info command
    @commands.command(name="roleinfo", description="Get details about a specific role.")
    @commands.guild_only()
    async def roleinfo(self, ctx: commands.Context, role: discord.Role):
        embed = discord.Embed(title=f"{EMOJI['tools']} Role Info: {role.name}", color=role.color)
        embed.add_field(name="Role Name", value=role.name, inline=True)
        embed.add_field(name="Role ID", value=role.id, inline=True)
        embed.add_field(name="Created At", value=role.created_at.strftime("%b %d, %Y"), inline=True)
        embed.add_field(name="Color", value=str(role.color), inline=True)
        embed.add_field(name="Hoisted", value=f"{EMOJI['success']}" if role.hoist else f"{EMOJI['error']}", inline=True)
        embed.add_field(name="Position", value=role.position, inline=True)
        embed.add_field(name="Mentionable", value=f"{EMOJI['success']}" if role.mentionable else f"{EMOJI['error']}", inline=True)
        embed.add_field(name="Members", value=len(role.members), inline=True)
        await ctx.send(embed=embed)

    # Give role to all members
    @commands.command(name="giveroleall", description="Assign a role to all members.")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    async def giveroleall(self, ctx: commands.Context, role: discord.Role):
        members_without_role = [member for member in ctx.guild.members if role not in member.roles]

        if not members_without_role:
            return await ctx.send(f"{EMOJI['success']} All members already have the **{role.name}** role.")

        embed = discord.Embed(
            title=f"{EMOJI['success']} Role Assignment in Progress",
            description=f"Assigning **{role.name}** to **{len(members_without_role)}** members...",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

        for member in members_without_role:
            try:
                await member.add_roles(role)
            except discord.Forbidden:
                await ctx.send(f"{EMOJI['error']} Could not add role to **{member.name}** (Missing Permissions).")

        embed = discord.Embed(
            title=f"{EMOJI['success']} Role Assigned to All",
            description=f"The role **{role.name}** has been assigned to **{len(members_without_role)}** members.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(Role(bot))
