import discord
from discord.ext import commands
import random
import requests
import asyncio


class TicTacToeButton(discord.ui.Button):
    def __init__(self, x, y):
        super().__init__(style=discord.ButtonStyle.secondary, label="​", row=x)
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        assert isinstance(view, TicTacToeView)

        if interaction.user != view.current_player:
            await interaction.response.send_message("It's not your turn!", ephemeral=True)
            return

        if view.board[self.x][self.y] != "":
            await interaction.response.send_message("This spot is already taken!", ephemeral=True)
            return

        self.label = view.symbols[view.current_symbol]
        self.style = discord.ButtonStyle.success if view.current_symbol == 0 else discord.ButtonStyle.danger
        self.disabled = True
        view.board[self.x][self.y] = view.symbols[view.current_symbol]

        winner = view.check_winner()
        if winner or view.is_full():
            for child in view.children:
                child.disabled = True
            content = f"Game Over! Winner: {winner}" if winner else "Game Over! It's a tie!"
            await interaction.response.edit_message(content=content, view=view)
        else:
            view.current_symbol = 1 - view.current_symbol
            view.current_player = view.players[view.current_symbol]
            await interaction.response.edit_message(view=view)

class TicTacToeView(discord.ui.View):
    def __init__(self, player1, player2):
        super().__init__(timeout=180)
        self.players = [player1, player2]
        self.current_player = player1
        self.current_symbol = 0
        self.symbols = ["X", "O"]
        self.board = [["" for _ in range(3)] for _ in range(3)]

        for x in range(3):
            for y in range(3):
                self.add_item(TicTacToeButton(x, y))

    def is_full(self):
        return all(cell for row in self.board for cell in row)

    def check_winner(self):
        lines = self.board + list(zip(*self.board)) + [
            [self.board[i][i] for i in range(3)],
            [self.board[i][2 - i] for i in range(3)]
        ]
        for line in lines:
            if line[0] and all(cell == line[0] for cell in line):
                return line[0]
        return None


# --- Rock-Paper-Scissors ---
class RPSView(discord.ui.View):
    def __init__(self, challenger, opponent):
        super().__init__(timeout=30)
        self.challenger = challenger
        self.opponent = opponent
        self.choices = {}

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user in [self.challenger, self.opponent]

    async def on_timeout(self):
        if not self.choices.get(self.challenger) or not self.choices.get(self.opponent):
            self.stop()

    async def handle_rps(self, interaction, choice):
        self.choices[interaction.user] = choice
        await interaction.response.send_message(f"You chose **{choice}**.", ephemeral=True)

        if len(self.choices) == 2:
            c1 = self.choices[self.challenger]
            c2 = self.choices[self.opponent]
            result = self.get_result(c1, c2)
            embed = discord.Embed(
                title="🪨 Rock-Paper-Scissors Result",
                description=(
                    f"**{self.challenger.display_name}** chose **{c1}**\n"
                    f"**{self.opponent.display_name}** chose **{c2}**\n\n"
                    f"**{result}**"
                ),
                color=discord.Color.blurple()
            )
            await interaction.message.edit(content=None, embed=embed, view=None)
            self.stop()

    def get_result(self, c1, c2):
        if c1 == c2:
            return "It's a tie! 🤝"
        wins = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
        if wins[c1] == c2:
            return f"{self.challenger.mention} wins! 🏆"
        return f"{self.opponent.mention} wins! 🏆"

class RPSButton(discord.ui.Button):
    def __init__(self, label):
        super().__init__(style=discord.ButtonStyle.secondary, label=label.capitalize())
        self.choice = label

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_rps(interaction, self.choice)

# --- Connect Four ---
class ConnectButton(discord.ui.Button):
    def __init__(self, col):
        super().__init__(style=discord.ButtonStyle.secondary, label=str(col + 1))
        self.col = col

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if interaction.user != view.players[view.turn]:
            await interaction.response.send_message("It's not your turn!", ephemeral=True)
            return

        for row in reversed(range(6)):
            if view.board[row][self.col] == ".":
                view.board[row][self.col] = view.symbols[view.turn]
                break
        else:
            await interaction.response.send_message("Column full!", ephemeral=True)
            return

        view.turn = 1 - view.turn
        content, win = view.render_board(), view.check_win()
        if win:
            content += f"\nGame Over! Winner: {view.players[1 - view.turn].mention}"
            for item in view.children:
                item.disabled = True
        elif view.is_full():
            content += "\nGame Over! It's a tie!"
            for item in view.children:
                item.disabled = True

        await interaction.response.edit_message(content=content, view=view)

class ConnectView(discord.ui.View):
    def __init__(self, p1, p2):
        super().__init__(timeout=180)
        self.players = [p1, p2]
        self.symbols = [":red_circle:", ":blue_circle:"]
        self.board = [["." for _ in range(7)] for _ in range(6)]
        self.turn = 0

        for col in range(7):
            self.add_item(ConnectButton(col))

    def render_board(self):
        return "\n".join("".join(cell if cell != "." else ":white_circle:" for cell in row) for row in self.board)

    def check_win(self):
        for r in range(6):
            for c in range(7):
                if self.board[r][c] == ".":
                    continue
                if c + 3 < 7 and all(self.board[r][c + i] == self.board[r][c] for i in range(4)):
                    return True
                if r + 3 < 6 and all(self.board[r + i][c] == self.board[r][c] for i in range(4)):
                    return True
                if r + 3 < 6 and c + 3 < 7 and all(self.board[r + i][c + i] == self.board[r][c] for i in range(4)):
                    return True
                if r + 3 < 6 and c - 3 >= 0 and all(self.board[r + i][c - i] == self.board[r][c] for i in range(4)):
                    return True
        return False

    def is_full(self):
        return all(self.board[0][c] != "." for c in range(7))

# Add commands in Fun Cog
class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def rps(self, ctx, opponent: discord.Member):
        """Play Rock-Paper-Scissors with buttons."""
        if opponent.bot or opponent == ctx.author:
            return await ctx.send("Invalid opponent!")
        view = RPSView(ctx.author, opponent)
        for label in ["rock", "paper", "scissors"]:
            view.add_item(RPSButton(label))
        await ctx.send(f"**RPS Match:** {ctx.author.mention} vs {opponent.mention}\nPick your move!", view=view)

    @commands.command()
    async def connect4(self, ctx, opponent: discord.Member):
        """Play Connect Four with a friend."""
        if opponent.bot or opponent == ctx.author:
            return await ctx.send("You can't play against yourself or a bot!")
        view = ConnectView(ctx.author, opponent)
        await ctx.send(f"**Connect Four**: {ctx.author.mention} (🔴) vs {opponent.mention} (🔵)\n{view.render_board()}", view=view)

    @commands.command()
    async def dog(self, ctx):
        """Fetch a random dog picture."""
        response = requests.get("https://dog.ceo/api/breeds/image/random")
        if response.status_code == 200:
            embed = discord.Embed(title="🐶 Here's a Random Dog!", color=discord.Color.orange())
            embed.set_image(url=response.json()["message"])
            return await ctx.send(embed=embed)
        await ctx.send("<a:Cross_:1489174755537064046> Could not fetch a dog picture. Try again later.")

    @commands.command()
    async def cat(self, ctx):
        """Fetch a random cat picture."""
        response = requests.get("https://api.thecatapi.com/v1/images/search")
        if response.status_code == 200:
            embed = discord.Embed(title="🐱 Here's a Random Cat!", color=discord.Color.green())
            embed.set_image(url=response.json()[0]["url"])
            return await ctx.send(embed=embed)
        await ctx.send("<a:Cross_:1489174755537064046> Could not fetch a cat picture. Try again later.")

    @commands.command()
    async def coinflip(self, ctx):
        """Flip a coin."""
        await ctx.send(f"🪙 The coin landed on: **{random.choice(['Heads 🪙', 'Tails 🎝'])}**")
 
    @commands.command()
    async def ttt(self, ctx, opponent: discord.Member):
        """Play Tic-Tac-Toe against another user."""
        if opponent.bot or opponent == ctx.author:
            return await ctx.send("You can't play against yourself or a bot!")

        view = TicTacToeView(ctx.author, opponent)
        await ctx.send(f"Tic-Tac-Toe: {ctx.author.mention} (X) vs {opponent.mention} (O)", view=view)


    @commands.command()
    async def fakehack(self, ctx, member: discord.Member = None):
        """Fake hack a user with progressive stages and random info."""
        member = member or ctx.author
        steps = [
            f"Connecting to Discord servers...",
            f"Bypassing 2FA for {member.display_name}...",
            f"Accessing message history...",
            f"Retrieving IP address...",
            f"Locating credentials in database..."
        ]

        for step in steps:
            await ctx.send(f"🔹 {step}")
            await asyncio.sleep(2)

        fake_ip = f"{random.randint(1, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}.{random.randint(0, 255)}"
        fake_email = f"{member.name.lower()}_{random.randint(100,999)}@gmail.com"
        fake_password = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz1234567890', k=8))
        fake_token = ''.join(random.choices('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=59))

        embed = discord.Embed(title=f"🔧 {member.display_name} Hacked Successfully!", color=discord.Color.red())
        embed.add_field(name="IP Address", value=fake_ip, inline=False)
        embed.add_field(name="Email", value=fake_email, inline=False)
        embed.add_field(name="Password", value=fake_password, inline=False)
        embed.add_field(name="Token", value=fake_token, inline=False)
        embed.set_footer(text="Totally real. Definitely not a joke. 😉")
        await ctx.send(embed=embed)
        await ctx.send(embed=embed)

    @commands.command()
    async def meme(self, ctx):
        """Get a random meme using Meme API."""
        response = requests.get("https://meme-api.com/gimme")
        if response.status_code == 200:
            data = response.json()
            embed = discord.Embed(title=data['title'], url=data['postLink'], color=discord.Color.random())
            embed.set_image(url=data['url'])
            embed.set_footer(text=f"👍 {data['ups']} | r/{data['subreddit']}")
            await ctx.send(embed=embed)
        else:
            await ctx.send("Could not fetch a meme. Try again later.")

    @commands.command()
    async def ratewaifu(self, ctx, *, waifu: str):
        """Rate a waifu from 0 to 10 using an external API."""
        score = random.randint(0, 10)
        embed = discord.Embed(
            title=f"🌸 Waifu Rating",
            description=f"I rate **{waifu}** a **{score}/10** 😍",
            color=discord.Color.purple()
        )
        embed.set_footer(text="Don't take it personally, it's just the bot's taste!")
        await ctx.send(embed=embed)

    @commands.command()
    async def roast(self, ctx, member: discord.Member = None):
        """Roast a user using an API."""
        member = member or ctx.author
        try:
            response = requests.get("https://insult.mattbas.org/api/insult")
            roast = response.text
        except:
            roast = "You're lucky, I couldn't come up with a roast."
        await ctx.send(f"🔥 {member.mention}, {roast}")

# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(Fun(bot))
