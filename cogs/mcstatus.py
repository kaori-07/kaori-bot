import discord
from discord.ext import commands, tasks
from mcstatus import JavaServer
from datetime import datetime

class MCStatus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Default Configurations
        self.server_ip = "play.mythicalnetwork.fun:25584"
        self.status_channel_id = 135067128134373536
        self.thumbnail_url = "https://cdn.discordapp.com/attachments/1357215993742495787/1363197770420191522/image0-1.png"
        
        # State Tracking
        self.auto_update_enabled = True
        self.status_message_id = None 

        # Start the background task properly
        self.update_status_loop.start()

    def cog_unload(self):
        self.update_status_loop.cancel()

    def build_embed(self, status=None, error=None):
        """Helper method to construct the embed cleanly."""
        if error:
            embed = discord.Embed(
                title="Kaori Minecraft Server Status",
                description="**MYTHICAL NETWORK | FFA SERVER**",
                color=discord.Color.red()
            )
            embed.add_field(name="Status", value="🔴 Offline", inline=True)
            embed.add_field(name="Error", value=f"```\n{error}\n```", inline=False)
        else:
            embed = discord.Embed(
                title="Kaori Minecraft Server Status",
                description="**MYTHICAL NETWORK | Ls X FFA SERVER**\nRemake of GrandMC — Join now!",
                color=discord.Color.green()
            )
            
            # Basic Stats
            embed.add_field(name="Status", value="🟢 Online", inline=True)
            embed.add_field(name="Players Online", value=f"{status.players.online}/{status.players.max}", inline=True)
            embed.add_field(name="Ping", value=f"{round(status.latency)}ms", inline=True)
            
            # Details
            embed.add_field(name="Minecraft Version", value=status.version.name, inline=True)
            
            # Clean MOTD (Strip formatting codes)
            motd = status.motd.to_plain() if status.motd else "No MOTD provided."
            embed.add_field(name="MOTD", value=f"```{motd}```", inline=False)

            # Safely handle player lists (Discord caps embed fields at 1024 characters)
            if status.players.sample:
                players = ", ".join(player.name for player in status.players.sample)
                if len(players) > 1000:
                    players = players[:1000] + "... (truncated)"
                embed.add_field(name="Online Players", value=players, inline=False)
            else:
                embed.add_field(name="Online Players", value="No players currently online.", inline=False)

        # Footer & Static info applied to both success and error states
        embed.add_field(name="Server IP", value=f"`{self.server_ip}`", inline=False)
        embed.add_field(name="Community", value="[Join Kaori Discord](https://discord.gg/scratchmc)", inline=False)
        embed.set_thumbnail(url=self.thumbnail_url)
        embed.set_footer(text=f"🕒 Last updated • {datetime.now().strftime('%d %b %Y • %I:%M %p')}")
        
        return embed

    @tasks.loop(minutes=5)
    async def update_status_loop(self):
        if not self.auto_update_enabled:
            return
        await self._perform_update()

    @update_status_loop.before_loop
    async def before_update_status(self):
        """Ensure the bot is fully ready before attempting to fetch channels."""
        await self.bot.wait_until_ready()

    async def _perform_update(self, ctx_for_reply=None):
        """Core logic to fetch data and update the channel."""
        channel = self.bot.get_channel(self.status_channel_id)
        if not channel:
            if ctx_for_reply:
                await ctx_for_reply.send("<a:Cross_:1489174755537064046> Status channel not found. Ensure the ID is correct.")
            return

        # Fetch Data Asynchronously
        try:
            server = JavaServer.lookup(self.server_ip)
            status = await server.async_status()
            embed = self.build_embed(status=status)
        except Exception as e:
            print(f"[KAORI STATUS ERROR] {e}")
            embed = self.build_embed(error="Unable to fetch server status. It may be offline.")

        # Update or Send Message
        if self.status_message_id:
            try:
                msg = await channel.fetch_message(self.status_message_id)
                await msg.edit(embed=embed)
                if ctx_for_reply:
                    await ctx_for_reply.send("<a:tick:1489157731393994854> Status panel updated.")
                return
            except discord.NotFound:
                self.status_message_id = None # Message deleted, fall through to send a new one
            except discord.Forbidden:
                pass 

        try:
            # Clean up old bot messages before anchoring a new panel
            async for message in channel.history(limit=10):
                if message.author == self.bot.user:
                    await message.delete()

            new_msg = await channel.send(embed=embed)
            self.status_message_id = new_msg.id
            if ctx_for_reply:
                await ctx_for_reply.send("<a:tick:1489157731393994854> Sent a new status panel.")
        except Exception as e:
            if ctx_for_reply:
                await ctx_for_reply.send(f"<a:Cross_:1489174755537064046> Failed to send panel: {e}")

    # ==========================
    #       COMMAND GROUP
    # ==========================

    @commands.group(invoke_without_command=True, aliases=['mcstatus'])
    async def mc(self, ctx):
        """Base command for Minecraft status. Use `,help mc` for subcommands."""
        await ctx.send_help(ctx.command)

    @mc.command(name="info")
    async def mc_info(self, ctx):
        """Fetch and display the server status right here."""
        loading_msg = await ctx.send("🔍 Fetching server data...")
        try:
            server = JavaServer.lookup(self.server_ip)
            status = await server.async_status()
            embed = self.build_embed(status=status)
            await loading_msg.edit(content=None, embed=embed)
        except Exception as e:
            embed = self.build_embed(error=str(e))
            await loading_msg.edit(content=None, embed=embed)

    @mc.command(name="force")
    @commands.has_permissions(manage_messages=True)
    async def mc_force(self, ctx):
        """Force an immediate update of the main status panel."""
        await self._perform_update(ctx_for_reply=ctx)

    @mc.command(name="toggle")
    @commands.has_permissions(manage_guild=True)
    async def mc_toggle(self, ctx):
        """Toggle the 5-minute auto-updating on or off."""
        self.auto_update_enabled = not self.auto_update_enabled
        state = "**enabled**" if self.auto_update_enabled else "**disabled**"
        await ctx.send(f"⚙️ Kaori auto-updates are now {state}.")
        if self.auto_update_enabled:
            await self._perform_update()

    @mc.command(name="setip")
    @commands.has_permissions(manage_guild=True)
    async def mc_setip(self, ctx, ip: str):
        """Change the target server IP dynamically."""
        self.server_ip = ip
        await ctx.send(f"<a:tick:1489157731393994854> Server IP updated to `{self.server_ip}`. Run `,mc force` to update the panel.")

    @mc.command(name="setchannel")
    @commands.has_permissions(manage_guild=True)
    async def mc_setchannel(self, ctx, channel: discord.TextChannel = None):
        """Set the channel for automatic updates (defaults to current channel)."""
        target_channel = channel or ctx.channel
        self.status_channel_id = target_channel.id
        self.status_message_id = None # Reset so it anchors a new message in the new channel
        await ctx.send(f"<a:tick:1489157731393994854> Auto-updates will now be sent to {target_channel.mention}.")
        await self._perform_update(ctx_for_reply=ctx)

async def setup(bot):
    await bot.add_cog(MCStatus(bot))