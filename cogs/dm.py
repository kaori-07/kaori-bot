import discord
from discord.ext import commands
import os
import asyncio
import time
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

OWNER_ID = int(os.getenv('OWNER_ID', '1336609172791365678'))
DEFAULT_PREFIX = os.getenv('DISCORD_PREFIX', ',')
ACCS_FILE = 'accs.json'

# --- JSON Handling for Whitelist ---
def load_accs():
    if not os.path.exists(ACCS_FILE):
        with open(ACCS_FILE, 'w') as f:
            json.dump({"whitelisted": []}, f)
    with open(ACCS_FILE, 'r') as f:
        return json.load(f)

def save_accs(data):
    with open(ACCS_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# Custom check to see if user is Owner OR Whitelisted
def is_allowed():
    async def predicate(ctx):
        if ctx.author.id == OWNER_ID:
            return True
        data = load_accs()
        if ctx.author.id in data.get("whitelisted", []):
            return True
        raise commands.CheckFailure("<a:Cross_:1489174755537064046> You do not have permission to use this command.")
    return commands.check(predicate)


# --- Helper Functions ---
async def send_dm(member, message, retries=3):
    for attempt in range(retries):
        try:
            await member.send(message)
            return True
        except discord.Forbidden:
            return False
        except discord.HTTPException as e:
            if e.status == 429:
                retry_after = e.response.headers.get('Retry-After')
                sleep_time = float(retry_after) + 1 if retry_after else 5.0
                print(f"Rate limited on {member.name}. Sleeping for {sleep_time}s...")
                await asyncio.sleep(sleep_time)
            else:
                return False
        except Exception:
            return False
    return False

def get_progress_bar(done, total, length=20):
    if total == 0: return f"[{'█' * length}] 0/0"
    filled = int(length * done / total)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}] {done}/{total}"

# --- Cog Definition ---
class dm(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        show_banner()
        await self.bot.tree.sync() 
        print(f"Logged in as {self.bot.user} | Prefix: {DEFAULT_PREFIX}")
        print("Slash commands synced!")

    @commands.hybrid_command(name='white', description="Whitelist a user to use the bot.")
    async def whitelist_user(self, ctx, user: discord.Member):
        if ctx.author.id != OWNER_ID:
            return await ctx.send("<a:Cross_:1489174755537064046> Only the main bot owner can use this command.", ephemeral=True)
        
        data = load_accs()
        if user.id not in data["whitelisted"]:
            data["whitelisted"].append(user.id)
            save_accs(data)
            await ctx.send(f"<a:tick:1489157731393994854> {user.mention} has been added to the whitelist.")
        else:
            await ctx.send(f"<a:Alert1:1489188698191822908> {user.mention} is already whitelisted.")

    @commands.hybrid_command(name='black', description="Remove a user from the whitelist.")
    async def blacklist_user(self, ctx, user: discord.Member):
        if ctx.author.id != OWNER_ID:
            return await ctx.send("<a:Cross_:1489174755537064046> Only the main bot owner can use this command.", ephemeral=True)
        
        data = load_accs()
        if user.id in data["whitelisted"]:
            data["whitelisted"].remove(user.id)
            save_accs(data)
            await ctx.send(f"<a:tick:1489157731393994854> {user.mention} has been removed from the whitelist.")
        else:
            await ctx.send(f"<a:Alert1:1489188698191822908> {user.mention} is not currently whitelisted.")

    # FIX: Renamed from 'help' to 'dmhelp' to avoid conflicts with Discord's default help command
    @commands.hybrid_command(name='dmhelp', description="Shows the mass DM help panel.")
    async def help_panel(self, ctx):
        embed = discord.Embed(
            title="Bot Commands",
            color=discord.Color.blurple(),
            description="List of available commands (Works as Prefix and Slash commands)"
        )
        embed.add_field(name=f"{DEFAULT_PREFIX}white @user", value="Whitelist a user (Owner Only)", inline=False)
        embed.add_field(name=f"{DEFAULT_PREFIX}black @user", value="Blacklist a user (Owner Only)", inline=False)
        embed.add_field(name=f"{DEFAULT_PREFIX}dmall <message>", value="DM all non-bot members", inline=False)
        embed.add_field(name=f"{DEFAULT_PREFIX}dmrole @role <message>", value="DM all members with a role", inline=False)
        embed.add_field(name=f"{DEFAULT_PREFIX}dm @user <message>", value="DM a specific user", inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name='dmall', description="Mass DM all non-bot members.")
    @is_allowed()
    async def dmall(self, ctx, *, message: str):
        await ctx.defer() 

        members = [m for m in ctx.guild.members if not m.bot]
        total = len(members)
        success = failed = 0

        progress_embed = discord.Embed(
            title="Mass DM Progress",
            color=discord.Color.blue(),
            description=get_progress_bar(0, total)
        )
        progress_msg = await ctx.send(embed=progress_embed)

        last_edit_time = time.time()

        for i, member in enumerate(members, start=1):
            ok = await send_dm(member, message)
            success += ok
            failed += (not ok)

            if time.time() - last_edit_time > 3:
                progress_embed.description = get_progress_bar(i, total)
                try:
                    await progress_msg.edit(embed=progress_embed)
                    last_edit_time = time.time()
                except discord.HTTPException:
                    pass 

            await asyncio.sleep(2)

        final_embed = discord.Embed(
            title="Mass DM Completed",
            color=discord.Color.green(),
            description=f"<a:tick:1489157731393994854> Success: **{success}**\n<a:Cross_:1489174755537064046> Failed: **{failed}**\n*Note: Failures are usually users who have server DMs disabled.*"
        )
        await progress_msg.edit(embed=final_embed)

    @commands.hybrid_command(name='dmrole', description="Mass DM to a specific role.")
    @is_allowed()
    async def dmrole(self, ctx, role: discord.Role, *, message: str):
        await ctx.defer()

        members = [m for m in ctx.guild.members if role in m.roles and not m.bot]
        total = len(members)
        success = failed = 0

        progress_embed = discord.Embed(
            title=f"DM Role: {role.name}",
            color=discord.Color.purple(),
            description=get_progress_bar(0, total)
        )
        progress_msg = await ctx.send(embed=progress_embed)

        last_edit_time = time.time()

        for i, member in enumerate(members, start=1):
            ok = await send_dm(member, message)
            success += ok
            failed += (not ok)

            if time.time() - last_edit_time > 3:
                progress_embed.description = get_progress_bar(i, total)
                try:
                    await progress_msg.edit(embed=progress_embed)
                    last_edit_time = time.time()
                except discord.HTTPException:
                    pass 

            await asyncio.sleep(2)

        final_embed = discord.Embed(
            title="Role DM Completed",
            color=discord.Color.green(),
            description=f"<a:tick:1489157731393994854> Success: **{success}**\n<a:Cross_:1489174755537064046> Failed: **{failed}**"
        )
        await progress_msg.edit(embed=final_embed)

    @commands.hybrid_command(name='dm', description="DM a specific user.")
    @is_allowed()
    async def dm_user(self, ctx, user: discord.User, *, message: str):
        await ctx.defer()
        if await send_dm(user, message):
            await ctx.send(f"<a:tick:1489157731393994854> Message sent to {user.name}.")
        else:
            await ctx.send(f"<a:Cross_:1489174755537064046> Failed to send message to {user.name}. They likely have DMs disabled.")

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"<a:Cross_:1489174755537064046> Missing argument: {error.param.name}")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("<a:Cross_:1489174755537064046> Invalid argument. Please check your input.")
        elif isinstance(error, commands.CheckFailure):
            await ctx.send(str(error)) 
        else:
            print(f"Ignoring exception in command {ctx.command}: {error}")

async def setup(bot):
    await bot.add_cog(dm(bot))