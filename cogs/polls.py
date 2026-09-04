import discord
from discord.ext import commands
from discord import app_commands
from cogs.utils.emoji_manager import EMOJI

BAR_LEN = 12


def _bar(pct: float) -> str:
    filled = round(pct / 100 * BAR_LEN)
    return "█" * filled + "░" * (BAR_LEN - filled)


class PollButton(discord.ui.Button):
    def __init__(self, label: str, index: int, row: int):
        super().__init__(style=discord.ButtonStyle.secondary, label=label[:80], row=row)
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        await self.view.vote(interaction, self.index)


class PollView(discord.ui.View):
    def __init__(self, question: str, options: list, author: discord.abc.User):
        super().__init__(timeout=600)
        self.question = question
        self.options = options
        self.author = author
        self.votes: dict = {}  # user_id -> option index
        self.message = None
        for i, opt in enumerate(options):
            self.add_item(PollButton(opt, i, row=i // 5))

    def build_embed(self) -> discord.Embed:
        total = len(self.votes)
        counts = [0] * len(self.options)
        for idx in self.votes.values():
            counts[idx] += 1

        embed = discord.Embed(title=f"{EMOJI['bar_chart']} {self.question}", color=discord.Color.blurple())
        for i, opt in enumerate(self.options):
            pct = (counts[i] / total * 100) if total else 0
            embed.add_field(name=opt, value=f"{_bar(pct)} {pct:.0f}% ({counts[i]})", inline=False)
        embed.set_footer(text=f"{total} vote{'s' if total != 1 else ''} • Started by {self.author.display_name}")
        return embed

    async def vote(self, interaction: discord.Interaction, index: int):
        self.votes[interaction.user.id] = index
        await interaction.response.edit_message(embed=self.build_embed())

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class Polls(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="poll", description="Start a button-voting poll (2-5 options).")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def poll(self, ctx: commands.Context, question: str, option1: str, option2: str,
                   option3: str = None, option4: str = None, option5: str = None):
        options = [o for o in [option1, option2, option3, option4, option5] if o]
        if len(options) < 2:
            return await ctx.send(f"{EMOJI['error']} You need at least 2 options.")

        view = PollView(question, options, ctx.author)
        embed = view.build_embed()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg


async def setup(bot):
    await bot.add_cog(Polls(bot))
