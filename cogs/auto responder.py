import discord
from discord.ext import commands

class AutoResponder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Temporary storage. Resets on bot restart.
        self.responses = {}

    @commands.Cog.listener()
    async def on_message(self, message):
        # Prevent bots from triggering each other
        if message.author.bot:
            return

        # Check if the message content exactly matches a trigger
        content = message.content.lower()
        if content in self.responses:
            # 1. Send the saved auto-response
            await message.channel.send(self.responses[content])
            
            # 2. Delete the user's trigger message
            try:
                await message.delete()
            except discord.Forbidden:
                print(f"Failed to delete message in {message.channel.name}. Missing 'Manage Messages' permission.")
            except discord.NotFound:
                pass

    # --- STANDALONE HYBRID COMMANDS ---

    @commands.hybrid_command(
        name="addar", 
        description="Add a response. Slash: Fill boxes. Prefix: Use quotes (e.g., !addar \"bad word\" \"Don't say that!\")"
    )
    @commands.has_permissions(manage_messages=True)
    async def addar(self, ctx: commands.Context, trigger: str, response: str):
        """
        Adds a new auto-response.
        Slash Command Usage: Select the command and fill in the 'trigger' and 'response' boxes.
        Prefix Command Usage: You MUST wrap multi-word phrases in quotes. 
        Example: !addar "hello bot" "Hello there, human!"
        """
        # Save it to our dictionary
        self.responses[trigger.lower().strip()] = response.strip()
        
        await ctx.send(f"<a:tick:1489157731393994854> Successfully added auto-response for **{trigger.strip()}**. I will auto-delete this trigger when used.")

    @commands.hybrid_command(
        name="removear", 
        description="Remove a response. Slash: Fill box. Prefix: Use quotes (e.g., !removear \"bad word\")"
    )
    @commands.has_permissions(manage_messages=True)
    async def removear(self, ctx: commands.Context, trigger: str):
        """
        Removes an existing auto-response.
        Slash Command Usage: Select the command and type the trigger to remove.
        Prefix Command Usage: Wrap multi-word triggers in quotes.
        Example: !removear "hello bot"
        """
        trigger = trigger.lower().strip()
        
        if trigger in self.responses:
            del self.responses[trigger]
            await ctx.send(f"<a:tick:1489157731393994854> Removed auto-response for **{trigger}**.")
        else:
            await ctx.send(f"<a:Cross_:1489174755537064046> No auto-response found for **{trigger}**.")

    @commands.hybrid_command(
        name="listar", 
        description="Displays a list of all active auto-responses currently saved."
    )
    async def listar(self, ctx: commands.Context):
        """
        Lists all active auto-responses.
        Usage: /listar or !listar
        """
        if not self.responses:
            return await ctx.send("There are currently no auto-responses set up.")

        embed = discord.Embed(title="Active Auto-Responses", color=discord.Color.blue())
        for trigger, response in self.responses.items():
            # Truncate response if it's too long for the embed field limits
            display_response = response if len(response) < 100 else response[:97] + "..."
            embed.add_field(name=f"Trigger: {trigger}", value=f"Reply: {display_response}", inline=False)
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(AutoResponder(bot))