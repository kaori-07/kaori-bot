import discord
from discord.ext import commands
import random
import requests
import asyncio
import html

# ==========================================
#              OLD GAMES (UPGRADED UI)
# ==========================================

class TicTacToeButton(discord.ui.Button):
    def __init__(self, x, y):
        super().__init__(style=discord.ButtonStyle.secondary, label="​", row=x)
        self.x = x
        self.y = y

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if interaction.user != view.current_player:
            return await interaction.response.send_message("It's not your turn!", ephemeral=True)

        if view.board[self.x][self.y] != "":
            return await interaction.response.send_message("This spot is already taken!", ephemeral=True)

        self.label = view.symbols[view.current_symbol]
        self.style = discord.ButtonStyle.success if view.current_symbol == 0 else discord.ButtonStyle.danger
        self.disabled = True
        view.board[self.x][self.y] = view.symbols[view.current_symbol]

        winner = view.check_winner()
        if winner or view.is_full():
            for child in view.children:
                child.disabled = True
            
            win_text = f"🏆 {view.current_player.mention} wins!" if winner else "🤝 It's a tie!"
            embed = discord.Embed(title="🎮 Tic-Tac-Toe - Game Over", description=win_text, color=discord.Color.gold())
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            view.current_symbol = 1 - view.current_symbol
            view.current_player = view.players[view.current_symbol]
            embed = discord.Embed(
                title="🎮 Tic-Tac-Toe", 
                description=f"It is now {view.current_player.mention}'s turn ({view.symbols[view.current_symbol]})", 
                color=discord.Color.blue()
            )
            await interaction.response.edit_message(embed=embed, view=view)

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
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.choices = {}

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user not in [self.challenger, self.opponent]:
            await interaction.response.send_message("You are not in this game!", ephemeral=True)
            return False
        return True

    async def handle_rps(self, interaction, choice):
        if interaction.user in self.choices:
            return await interaction.response.send_message("You already made your choice!", ephemeral=True)
            
        self.choices[interaction.user] = choice
        await interaction.response.send_message(f"You quietly chose **{choice}**.", ephemeral=True)

        if len(self.choices) == 2:
            c1, c2 = self.choices[self.challenger], self.choices[self.opponent]
            result, color = self.get_result(c1, c2)
            
            embed = discord.Embed(title="🪨📄✂️ Rock-Paper-Scissors Result", description=result, color=color)
            embed.add_field(name=self.challenger.display_name, value=c1.capitalize(), inline=True)
            embed.add_field(name=self.opponent.display_name, value=c2.capitalize(), inline=True)
            
            await interaction.message.edit(embed=embed, view=None)
            self.stop()

    def get_result(self, c1, c2):
        if c1 == c2: return ("It's a tie! 🤝", discord.Color.light_grey())
        wins = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
        if wins[c1] == c2: return (f"🏆 {self.challenger.mention} wins!", discord.Color.green())
        return (f"🏆 {self.opponent.mention} wins!", discord.Color.red())

class RPSButton(discord.ui.Button):
    def __init__(self, label, emoji):
        super().__init__(style=discord.ButtonStyle.primary, label=label.capitalize(), emoji=emoji)
        self.choice = label

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_rps(interaction, self.choice)

# --- Connect Four ---
class ConnectButton(discord.ui.Button):
    def __init__(self, col):
        # Discord allows max 5 buttons per row. So columns 0-4 are row 0, 5-6 are row 1
        super().__init__(style=discord.ButtonStyle.secondary, label=str(col + 1), row=0 if col < 5 else 1)
        self.col = col

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if interaction.user != view.players[view.turn]:
            return await interaction.response.send_message("It's not your turn!", ephemeral=True)

        for row in reversed(range(6)):
            if view.board[row][self.col] == "⚫":
                view.board[row][self.col] = view.symbols[view.turn]
                break
        else:
            return await interaction.response.send_message("This column is full!", ephemeral=True)

        view.turn = 1 - view.turn
        win = view.check_win()
        
        desc = view.render_board()
        color = discord.Color.blue() if view.turn == 0 else discord.Color.red()
        
        if win:
            desc += f"\n\n🏆 {view.players[1 - view.turn].mention} wins!"
            for item in view.children: item.disabled = True
            color = discord.Color.gold()
        elif view.is_full():
            desc += "\n\n🤝 It's a tie!"
            for item in view.children: item.disabled = True
            color = discord.Color.light_grey()
        else:
            desc += f"\n\nIt's {view.players[view.turn].mention}'s turn ({view.symbols[view.turn]})"

        embed = discord.Embed(title="🔴 Connect 4 🔵", description=desc, color=color)
        await interaction.response.edit_message(embed=embed, view=view)

class ConnectView(discord.ui.View):
    def __init__(self, p1, p2):
        super().__init__(timeout=300)
        self.players = [p1, p2]
        self.symbols = ["🔴", "🔵"]
        self.board = [["⚫" for _ in range(7)] for _ in range(6)]
        self.turn = 0
        for col in range(7):
            self.add_item(ConnectButton(col))

    def render_board(self):
        return "\n".join("".join(cell for cell in row) for row in self.board)

    def check_win(self):
        for r in range(6):
            for c in range(7):
                if self.board[r][c] == "⚫": continue
                if c + 3 < 7 and all(self.board[r][c + i] == self.board[r][c] for i in range(4)): return True
                if r + 3 < 6 and all(self.board[r + i][c] == self.board[r][c] for i in range(4)): return True
                if r + 3 < 6 and c + 3 < 7 and all(self.board[r + i][c + i] == self.board[r][c] for i in range(4)): return True
                if r + 3 < 6 and c - 3 >= 0 and all(self.board[r + i][c - i] == self.board[r][c] for i in range(4)): return True
        return False

    def is_full(self):
        return all(self.board[0][c] != "⚫" for c in range(7))


# ==========================================
#         NEW MULTIPLAYER GUESS BATTLE
# ==========================================
class GuessNumberModal(discord.ui.Modal):
    def __init__(self, game_view, is_setting_secret: bool):
        super().__init__(title="Set Secret" if is_setting_secret else "Make a Guess")
        self.game_view = game_view
        self.is_setting_secret = is_setting_secret
        self.number = discord.ui.TextInput(
            label="Enter a number (1-100)",
            style=discord.TextStyle.short,
            min_length=1, max_length=3
        )
        self.add_item(self.number)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.number.value)
            if not (1 <= val <= 100): raise ValueError
        except:
            return await interaction.response.send_message("Please enter a valid number between 1 and 100!", ephemeral=True)

        if self.is_setting_secret:
            await self.game_view.handle_secret(interaction, val)
        else:
            await self.game_view.handle_guess(interaction, val)

class GuessBattleView(discord.ui.View):
    def __init__(self, p1, p2):
        super().__init__(timeout=300)
        self.players = [p1, p2]
        self.secrets = {p1: None, p2: None}
        self.turn = 0
        self.game_log = []

    def get_embed(self):
        if None in self.secrets.values():
            embed = discord.Embed(title="🔢 Guess Battle", description="Waiting for both players to set their secret numbers (1-100)...", color=discord.Color.blurple())
            p1_status = "✅ Ready" if self.secrets[self.players[0]] else "⏳ Setting..."
            p2_status = "✅ Ready" if self.secrets[self.players[1]] else "⏳ Setting..."
            embed.add_field(name=self.players[0].display_name, value=p1_status)
            embed.add_field(name=self.players[1].display_name, value=p2_status)
            return embed
        
        current_player = self.players[self.turn]
        opponent = self.players[1 - self.turn]
        
        desc = f"**{current_player.mention}'s turn to guess {opponent.display_name}'s number!**\n\n"
        if self.game_log:
            desc += "**Recent Guesses:**\n" + "\n".join(self.game_log[-5:])
            
        embed = discord.Embed(title="🔢 Guess Battle", description=desc, color=discord.Color.green())
        return embed

    @discord.ui.button(label="Set Secret Number", style=discord.ButtonStyle.primary, custom_id="btn_set")
    async def btn_set(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user not in self.players:
            return await interaction.response.send_message("You're not in this game!", ephemeral=True)
        if self.secrets[interaction.user] is not None:
            return await interaction.response.send_message("You already set your secret!", ephemeral=True)
            
        await interaction.response.send_modal(GuessNumberModal(self, is_setting_secret=True))

    @discord.ui.button(label="Make a Guess", style=discord.ButtonStyle.success, custom_id="btn_guess", disabled=True)
    async def btn_guess(self, interaction: discord.Interaction, button: discord.ui.Button):
        if None in self.secrets.values():
            return await interaction.response.send_message("Still waiting for secrets to be set!", ephemeral=True)
        if interaction.user != self.players[self.turn]:
            return await interaction.response.send_message("It's not your turn!", ephemeral=True)
            
        await interaction.response.send_modal(GuessNumberModal(self, is_setting_secret=False))

    async def handle_secret(self, interaction, value):
        self.secrets[interaction.user] = value
        
        if None not in self.secrets.values():
            self.children[0].disabled = True # Disable Set
            self.children[1].disabled = False # Enable Guess
            
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def handle_guess(self, interaction, guess):
        opponent = self.players[1 - self.turn]
        secret = self.secrets[opponent]
        
        if guess == secret:
            embed = discord.Embed(title="🎉 We have a Winner!", description=f"{interaction.user.mention} correctly guessed **{secret}** and won the game!\n\n({opponent.display_name}'s number was {secret}, {interaction.user.display_name}'s number was {self.secrets[interaction.user]})", color=discord.Color.gold())
            for item in self.children: item.disabled = True
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
        else:
            hint = "🔼 HIGHER" if guess < secret else "🔽 LOWER"
            self.game_log.append(f"{interaction.user.display_name} guessed **{guess}** ➔ {hint}")
            self.turn = 1 - self.turn
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

# ==========================================
#               TRIVIA GAME
# ==========================================
class TriviaView(discord.ui.View):
    def __init__(self, player, question_data):
        super().__init__(timeout=30)
        self.player = player
        self.correct_answer = html.unescape(question_data['correct_answer'])
        options = question_data['incorrect_answers'] + [question_data['correct_answer']]
        random.shuffle(options)
        
        for option in options:
            label = html.unescape(option)[:80]
            self.add_item(discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, custom_id=label))

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user != self.player:
            await interaction.response.send_message("Start your own trivia game!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children: child.disabled = True
        try:
            await self.message.edit(content=f"⏰ Time's up! The correct answer was **{self.correct_answer}**.", view=self)
        except: pass

class TriviaButtonListener:
    # Handled inside View generically
    pass


# ==========================================
#                 FUN COG
# ==========================================
class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ---------------- OLD GAMES ----------------
    @commands.command()
    async def rps(self, ctx, opponent: discord.Member):
        """Play Rock-Paper-Scissors with buttons."""
        if opponent.bot or opponent == ctx.author:
            return await ctx.send("Invalid opponent!")
        view = RPSView(ctx.author, opponent)
        view.add_item(RPSButton("rock", "🪨"))
        view.add_item(RPSButton("paper", "📄"))
        view.add_item(RPSButton("scissors", "✂️"))
        
        embed = discord.Embed(title="🪨📄✂️ Rock Paper Scissors", description=f"{ctx.author.mention} challenged {opponent.mention}!\n\nClick a button below to make your choice secretly.", color=discord.Color.blurple())
        await ctx.send(embed=embed, view=view)

    @commands.command()
    async def connect4(self, ctx, opponent: discord.Member):
        """Play Connect Four with a friend."""
        if opponent.bot or opponent == ctx.author:
            return await ctx.send("Invalid opponent!")
        view = ConnectView(ctx.author, opponent)
        embed = discord.Embed(title="🔴 Connect 4 🔵", description=f"{ctx.author.mention} (🔴) vs {opponent.mention} (🔵)\n\nIt's {ctx.author.mention}'s turn!\n\n{view.render_board()}", color=discord.Color.blue())
        await ctx.send(embed=embed, view=view)

    @commands.command()
    async def ttt(self, ctx, opponent: discord.Member):
        """Play Tic-Tac-Toe against another user."""
        if opponent.bot or opponent == ctx.author:
            return await ctx.send("Invalid opponent!")
        view = TicTacToeView(ctx.author, opponent)
        embed = discord.Embed(title="🎮 Tic-Tac-Toe", description=f"{ctx.author.mention} (X) vs {opponent.mention} (O)\n\nIt is {ctx.author.mention}'s turn!", color=discord.Color.blue())
        await ctx.send(embed=embed, view=view)


    # ---------------- NEW GAMES ----------------

    @commands.command(aliases=['gb', 'guess'])
    async def guessbattle(self, ctx, opponent: discord.Member):
        """Play Multiplayer Guess the Number!"""
        if opponent.bot or opponent == ctx.author:
            return await ctx.send("You need a real opponent to play this!")
            
        view = GuessBattleView(ctx.author, opponent)
        await ctx.send(content=f"{opponent.mention}, you have been challenged by {ctx.author.mention}!", embed=view.get_embed(), view=view)

    @commands.command()
    async def trivia(self, ctx):
        """Answer a random trivia question."""
        res = requests.get("https://opentdb.com/api.php?amount=1&type=multiple")
        if res.status_code != 200:
            return await ctx.send("Couldn't fetch a trivia question right now!")
            
        data = res.json()['results'][0]
        question = html.unescape(data['question'])
        category = html.unescape(data['category'])
        difficulty = data['difficulty'].capitalize()

        view = TriviaView(ctx.author, data)
        embed = discord.Embed(title="🧠 Trivia Time!", description=f"**Category:** {category}\n**Difficulty:** {difficulty}\n\n**{question}**", color=discord.Color.purple())
        
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

        # We inject the button callback here dynamically
        async def button_callback(interaction: discord.Interaction):
            if interaction.user != ctx.author: return
            for child in view.children: child.disabled = True
            
            selected = interaction.data["custom_id"]
            if selected == view.correct_answer:
                embed.color = discord.Color.green()
                embed.description += f"\n\n✅ **Correct!** The answer was {view.correct_answer}."
            else:
                embed.color = discord.Color.red()
                embed.description += f"\n\n❌ **Wrong!** You chose {selected}. The correct answer was **{view.correct_answer}**."
            
            await interaction.response.edit_message(embed=embed, view=view)
            view.stop()

        for child in view.children:
            child.callback = button_callback

    @commands.command()
    async def scramble(self, ctx):
        """First person to unscramble the word wins!"""
        words = ["discord", "computer", "developer", "keyboard", "python", "javascript", "internet", "robot", "server", "message"]
        word = random.choice(words)
        scrambled = "".join(random.sample(word, len(word)))
        
        embed = discord.Embed(title="🔀 Word Scramble!", description=f"Unscramble this word: **`{scrambled}`**\n\nFirst person to type the correct answer in chat wins!", color=discord.Color.orange())
        await ctx.send(embed=embed)

        def check(m):
            return m.channel == ctx.channel and m.content.lower() == word

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=30.0)
            await ctx.send(f"🎉 **{msg.author.display_name}** got it! The word was **{word}**.")
        except asyncio.TimeoutError:
            await ctx.send(f"⏰ Time's up! Nobody guessed it. The word was **{word}**.")

    @commands.command()
    async def slots(self, ctx):
        """Play the slot machine."""
        emojis = ["🍎", "🍊", "🍇", "🍒", "💎", "🎰", "⭐"]
        embed = discord.Embed(title="🎰 Slot Machine", description="Spinning... 🌀", color=discord.Color.gold())
        msg = await ctx.send(embed=embed)
        
        for _ in range(3):
            await asyncio.sleep(0.5)
            slot1, slot2, slot3 = random.choice(emojis), random.choice(emojis), random.choice(emojis)
            embed.description = f"| {slot1} | {slot2} | {slot3} |"
            await msg.edit(embed=embed)

        if slot1 == slot2 == slot3:
            embed.color = discord.Color.green()
            embed.add_field(name="Result", value="🎉 **JACKPOT!** You win!")
        elif slot1 == slot2 or slot2 == slot3 or slot1 == slot3:
            embed.color = discord.Color.orange()
            embed.add_field(name="Result", value="💸 Close one! Two matched.")
        else:
            embed.color = discord.Color.red()
            embed.add_field(name="Result", value="❌ Better luck next time.")
        
        await msg.edit(embed=embed)

    @commands.command(aliases=['ms'])
    async def minesweeper(self, ctx):
        """Play minesweeper in chat!"""
        size = 8
        bombs = 10
        grid = [[0 for _ in range(size)] for _ in range(size)]
        
        # Place bombs
        b_placed = 0
        while b_placed < bombs:
            x, y = random.randint(0, size-1), random.randint(0, size-1)
            if grid[x][y] != -1:
                grid[x][y] = -1
                b_placed += 1

        # Calculate numbers
        for x in range(size):
            for y in range(size):
                if grid[x][y] == -1: continue
                for dx in [-1, 0, 1]:
                    for dy in [-1, 0, 1]:
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < size and 0 <= ny < size and grid[nx][ny] == -1:
                            grid[x][y] += 1

        # Format mapping
        tiles = {-1: "💥", 0: "⬜", 1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣"}
        
        output = "**Minesweeper**\n"
        for row in grid:
            output += "".join(f"||{tiles[cell]}||" for cell in row) + "\n"
            
        await ctx.send(output)

    @commands.command()
    async def tod(self, ctx):
        """Play Truth or Dare."""
        class TODView(discord.ui.View):
            def __init__(self, user):
                super().__init__(timeout=60)
                self.user = user

            @discord.ui.button(label="Truth", style=discord.ButtonStyle.primary, emoji="😇")
            async def b_truth(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user != self.user: return
                truths = ["What's your biggest fear?", "Who is your secret crush?", "What's the most embarrassing thing you've ever done?", "What is a secret you've kept from your parents?"]
                await interaction.response.edit_message(content=f"**Truth for {interaction.user.mention}:**\n> {random.choice(truths)}", view=None)

            @discord.ui.button(label="Dare", style=discord.ButtonStyle.danger, emoji="😈")
            async def b_dare(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user != self.user: return
                dares = ["Send a voice message barking like a dog.", "Do 10 pushups right now.", "Show the last photo saved in your camera roll.", "Type your next 5 messages with your eyes closed."]
                await interaction.response.edit_message(content=f"**Dare for {interaction.user.mention}:**\n> {random.choice(dares)}", view=None)

        await ctx.send(f"{ctx.author.mention}, choose your fate!", view=TODView(ctx.author))

    @commands.command(name="8ball")
    async def _8ball(self, ctx, *, question: str):
        """Ask the magic 8-ball a question."""
        responses = ["It is certain.", "It is decidedly so.", "Without a doubt.", "Yes - definitely.", "You may rely on it.", "As I see it, yes.", "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.", "Reply hazy, try again.", "Ask again later.", "Better not tell you now.", "Cannot predict now.", "Concentrate and ask again.", "Don't count on it.", "My reply is no.", "My sources say no.", "Outlook not so good.", "Very doubtful."]
        
        embed = discord.Embed(title="🎱 Magic 8-Ball", color=discord.Color.dark_theme())
        embed.add_field(name="Question", value=question, inline=False)
        embed.add_field(name="Answer", value=random.choice(responses), inline=False)
        await ctx.send(embed=embed)

    @commands.command()
    async def roll(self, ctx, sides: int = 6):
        """Roll a dice with a specific number of sides (default 6)."""
        if sides < 2:
            return await ctx.send("The dice must have at least 2 sides!")
        result = random.randint(1, sides)
        embed = discord.Embed(title="🎲 Dice Roll", description=f"{ctx.author.mention} rolled a **{result}**! (1-{sides})", color=discord.Color.teal())
        await ctx.send(embed=embed)


    # ---------------- MISC (Existing kept) ----------------
    
    @commands.command()
    async def dog(self, ctx):
        """Fetch a random dog picture."""
        response = requests.get("https://dog.ceo/api/breeds/image/random")
        if response.status_code == 200:
            embed = discord.Embed(title="🐶 Here's a Random Dog!", color=discord.Color.orange())
            embed.set_image(url=response.json()["message"])
            return await ctx.send(embed=embed)
        await ctx.send("Could not fetch a dog picture. Try again later.")

    @commands.command()
    async def cat(self, ctx):
        """Fetch a random cat picture."""
        response = requests.get("https://api.thecatapi.com/v1/images/search")
        if response.status_code == 200:
            embed = discord.Embed(title="🐱 Here's a Random Cat!", color=discord.Color.green())
            embed.set_image(url=response.json()[0]["url"])
            return await ctx.send(embed=embed)
        await ctx.send("Could not fetch a cat picture. Try again later.")

    @commands.command()
    async def coinflip(self, ctx):
        """Flip a coin."""
        await ctx.send(f"🪙 The coin landed on: **{random.choice(['Heads 🪙', 'Tails 🦅'])}**")

    @commands.command()
    async def fakehack(self, ctx, member: discord.Member = None):
        """Fake hack a user with progressive stages."""
        member = member or ctx.author
        steps = ["Connecting to Discord servers...", f"Bypassing 2FA for {member.display_name}...", "Accessing message history...", "Locating credentials..."]

        msg = await ctx.send(f"🔹 {steps[0]}")
        for step in steps[1:]:
            await asyncio.sleep(1.5)
            await msg.edit(content=f"🔹 {step}")

        await asyncio.sleep(1.5)
        embed = discord.Embed(title=f"🔧 {member.display_name} Hacked Successfully!", color=discord.Color.red())
        embed.add_field(name="IP Address", value=f"192.168.{random.randint(1,255)}.{random.randint(1,255)}", inline=False)
        embed.add_field(name="Email", value=f"hacked_{random.randint(100,999)}@gmail.com", inline=False)
        embed.set_footer(text="Totally real. Definitely not a joke. 😉")
        await msg.edit(content=None, embed=embed)

    @commands.command()
    async def meme(self, ctx):
        """Get a random meme."""
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
        """Rate a waifu from 0 to 10."""
        embed = discord.Embed(title=f"🌸 Waifu Rating", description=f"I rate **{waifu}** a **{random.randint(0, 10)}/10** 😍", color=discord.Color.purple())
        await ctx.send(embed=embed)

    @commands.command()
    async def roast(self, ctx, member: discord.Member = None):
        """Roast a user."""
        member = member or ctx.author
        try:
            roast = requests.get("https://insult.mattbas.org/api/insult").text
        except:
            roast = "You're lucky, I couldn't come up with a roast."
        await ctx.send(f"🔥 {member.mention}, {roast}")

# Setup function to add the cog to the bot
async def setup(bot):
    await bot.add_cog(Fun(bot))