import discord
from discord.ext import commands
import random
import aiohttp
import asyncio
from cogs.utils.emoji_manager import EMOJI


class Fun(commands.Cog):
    """Lighter, non-competitive fun commands. For interactive games (Blackjack,
    Wordle, Trivia, Connect 4, etc), see cogs/games.py."""

    def __init__(self, bot):
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        if self.session and not self.session.closed:
            self.bot.loop.create_task(self.session.close())

    @commands.command()
    async def dog(self, ctx):
        """Fetch a random dog picture."""
        try:
            async with self.session.get("https://dog.ceo/api/breeds/image/random") as response:
                if response.status == 200:
                    data = await response.json()
                    embed = discord.Embed(title="🐶 Here's a Random Dog!", color=discord.Color.orange())
                    embed.set_image(url=data["message"])
                    return await ctx.send(embed=embed)
        except aiohttp.ClientError:
            pass
        await ctx.send(f"{EMOJI['error']} Could not fetch a dog picture. Try again later.")

    @commands.command()
    async def cat(self, ctx):
        """Fetch a random cat picture."""
        try:
            async with self.session.get("https://api.thecatapi.com/v1/images/search") as response:
                if response.status == 200:
                    data = await response.json()
                    embed = discord.Embed(title="🐱 Here's a Random Cat!", color=discord.Color.green())
                    embed.set_image(url=data[0]["url"])
                    return await ctx.send(embed=embed)
        except aiohttp.ClientError:
            pass
        await ctx.send(f"{EMOJI['error']} Could not fetch a cat picture. Try again later.")

    @commands.command()
    async def meme(self, ctx):
        """Get a random meme."""
        try:
            async with self.session.get("https://meme-api.com/gimme") as response:
                if response.status == 200:
                    data = await response.json()
                    embed = discord.Embed(title=data['title'], url=data['postLink'], color=discord.Color.random())
                    embed.set_image(url=data['url'])
                    embed.set_footer(text=f"👍 {data['ups']} | r/{data['subreddit']}")
                    return await ctx.send(embed=embed)
        except aiohttp.ClientError:
            pass
        await ctx.send(f"{EMOJI['error']} Could not fetch a meme. Try again later.")

    @commands.command()
    async def roast(self, ctx, member: discord.Member = None):
        """Roast a user."""
        member = member or ctx.author
        try:
            async with self.session.get("https://insult.mattbas.org/api/insult") as resp:
                roast = await resp.text()
        except aiohttp.ClientError:
            roast = "You're lucky, I couldn't come up with a roast."
        await ctx.send(f"🔥 {member.mention}, {roast}")

    @commands.command()
    async def ratewaifu(self, ctx, *, waifu: str):
        """Rate a waifu from 0 to 10."""
        embed = discord.Embed(title="🌸 Waifu Rating", description=f"I rate **{waifu}** a **{random.randint(0, 10)}/10** 😍", color=discord.Color.purple())
        await ctx.send(embed=embed)

    @commands.command()
    async def coinflip(self, ctx):
        """Flip a coin."""
        await ctx.send(f"🪙 The coin landed on: **{random.choice(['Heads 🪙', 'Tails 🦅'])}**")

    @commands.command(name="8ball")
    async def _8ball(self, ctx, *, question: str):
        """Ask the magic 8-ball a question."""
        responses = [
            "It is certain.", "It is decidedly so.", "Without a doubt.", "Yes - definitely.",
            "You may rely on it.", "As I see it, yes.", "Most likely.", "Outlook good.", "Yes.",
            "Signs point to yes.", "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
            "Cannot predict now.", "Concentrate and ask again.", "Don't count on it.", "My reply is no.",
            "My sources say no.", "Outlook not so good.", "Very doubtful.",
        ]
        embed = discord.Embed(title="🎱 Magic 8-Ball", color=discord.Color.dark_theme())
        embed.add_field(name="Question", value=question, inline=False)
        embed.add_field(name="Answer", value=random.choice(responses), inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def roll(self, ctx, sides: int = 6):
        """Roll a dice with a specific number of sides (default 6)."""
        if sides < 2:
            return await ctx.send(f"{EMOJI['error']} The dice must have at least 2 sides!")
        result = random.randint(1, sides)
        embed = discord.Embed(title="🎲 Dice Roll", description=f"{ctx.author.mention} rolled a **{result}**! (1-{sides})", color=discord.Color.teal())
        await ctx.send(embed=embed)

    @commands.command()
    async def fakehack(self, ctx, member: discord.Member = None):
        """Fake hack a user with a terminal-style animated progress bar — just for laughs."""
        member = member or ctx.author

        steps = [
            "Establishing secure connection...",
            "Bypassing firewall...",
            "Cracking encryption keys...",
            f"Locating {member.display_name}'s credentials...",
            "Extracting metadata...",
            "Deploying payload...",
            "Covering tracks...",
        ]

        class AbortView(discord.ui.View):
            def __init__(self, author):
                super().__init__(timeout=None)
                self.author = author
                self.aborted = False

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                if interaction.user != self.author:
                    await interaction.response.send_message(f"{EMOJI['error']} Only the person who ran this can abort it.", ephemeral=True)
                    return False
                return True

            @discord.ui.button(label="Abort", style=discord.ButtonStyle.danger, emoji="🛑")
            async def abort(self, interaction: discord.Interaction, button: discord.ui.Button):
                self.aborted = True
                button.disabled = True
                embed = discord.Embed(title=f"{EMOJI['no_entry']} Operation Aborted", description="The (fake) hack was cancelled.", color=discord.Color.greyple())
                await interaction.response.edit_message(embed=embed, view=self)
                self.stop()

        def bar(pct: int) -> str:
            filled = round(pct / 100 * 20)
            return "█" * filled + "░" * (20 - filled)

        view = AbortView(ctx.author)

        def build_step_embed(i: int) -> discord.Embed:
            pct = round((i + 1) / len(steps) * 100)
            embed = discord.Embed(title=f"{EMOJI['loading']} Initiating Hack Sequence", color=discord.Color.dark_red())
            embed.description = f"```\n[{bar(pct)}] {pct}%\n\n> {steps[i]}\n```"
            embed.set_footer(text=f"Target: {member.display_name} — this is a joke command, no real data is accessed")
            return embed

        msg = await ctx.send(embed=build_step_embed(0), view=view)
        for i in range(1, len(steps)):
            await asyncio.sleep(1.1)
            if view.aborted:
                return
            try:
                await msg.edit(embed=build_step_embed(i))
            except discord.HTTPException:
                return

        await asyncio.sleep(1.1)
        if view.aborted:
            return

        for child in view.children:
            child.disabled = True

        fake_browsers = ["Chrome", "Firefox", "Edge", "Brave", "Opera"]
        fake_os = ["Windows 11", "macOS Sonoma", "Ubuntu 22.04", "Windows 10"]
        result = discord.Embed(
            title=f"{EMOJI['success']} Breach Complete — {member.display_name}",
            description=f"```\n[{bar(100)}] 100%\n\n> Extraction finished.\n```",
            color=discord.Color.green(),
        )
        result.add_field(name="🌐 IP Address", value=f"`192.168.{random.randint(1,255)}.{random.randint(1,255)}`", inline=True)
        result.add_field(name="📧 Email", value=f"`hacked_{random.randint(1000,9999)}@example.com`", inline=True)
        result.add_field(name="💻 OS", value=random.choice(fake_os), inline=True)
        result.add_field(name="🌎 Browser", value=random.choice(fake_browsers), inline=True)
        result.add_field(name="🔑 Password Strength", value=f"{random.randint(10, 40)}% (weak)", inline=True)
        result.add_field(name="📁 Files Found", value=f"{random.randint(1200, 98000):,}", inline=True)
        result.set_thumbnail(url=member.display_avatar.url)
        result.set_footer(text="100% fake — no data was accessed, collected, or stored. For entertainment only.")
        await msg.edit(embed=result, view=view)


async def setup(bot):
    await bot.add_cog(Fun(bot))
