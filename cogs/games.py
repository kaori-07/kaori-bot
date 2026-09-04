import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import html
import time
from cogs.utils.emoji_manager import EMOJI

# ==========================================
#            TIC-TAC-TOE (2 players)
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
            win_text = f"{EMOJI['trophy']} {view.current_player.mention} wins!" if winner else f"{EMOJI['handshake']} It's a tie!"
            embed = discord.Embed(title="🎮 Tic-Tac-Toe — Game Over", description=win_text, color=discord.Color.gold())
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
            [self.board[i][2 - i] for i in range(3)],
        ]
        for line in lines:
            if line[0] and all(cell == line[0] for cell in line):
                return line[0]
        return None


# ==========================================
#        ROCK PAPER SCISSORS (2 players)
# ==========================================
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
        if c1 == c2:
            return ("It's a tie! 🤝", discord.Color.light_grey())
        wins = {"rock": "scissors", "scissors": "paper", "paper": "rock"}
        if wins[c1] == c2:
            return (f"{EMOJI['trophy']} {self.challenger.mention} wins!", discord.Color.green())
        return (f"{EMOJI['trophy']} {self.opponent.mention} wins!", discord.Color.red())


class RPSButton(discord.ui.Button):
    def __init__(self, label, emoji):
        super().__init__(style=discord.ButtonStyle.primary, label=label.capitalize(), emoji=emoji)
        self.choice = label

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_rps(interaction, self.choice)


# ==========================================
#              CONNECT 4 (2 players)
# ==========================================
class ConnectButton(discord.ui.Button):
    def __init__(self, col):
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
            desc += f"\n\n{EMOJI['trophy']} {view.players[1 - view.turn].mention} wins!"
            for item in view.children:
                item.disabled = True
            color = discord.Color.gold()
        elif view.is_full():
            desc += f"\n\n{EMOJI['handshake']} It's a tie!"
            for item in view.children:
                item.disabled = True
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
                if self.board[r][c] == "⚫":
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
        return all(self.board[0][c] != "⚫" for c in range(7))


# ==========================================
#         GUESS BATTLE (1v1 duel)
# ==========================================
# NOTE: previously crashed with a TypeError whenever either player clicked
# "Set Secret Number" or "Make a Guess" - this game used to live inside
# fun.py alongside a *second, unrelated* class also named `GuessNumberModal`
# (for the multiplayer /guessnumber game below). Python let the second
# definition silently overwrite the first at import time, so this view ended
# up calling the wrong modal's __init__ signature. Renamed to
# `GuessBattleModal` to fix it for good - each game now owns its own,
# uniquely-named modal class.
class GuessBattleModal(discord.ui.Modal):
    def __init__(self, game_view: "GuessBattleView", is_setting_secret: bool):
        super().__init__(title="Set Secret" if is_setting_secret else "Make a Guess")
        self.game_view = game_view
        self.is_setting_secret = is_setting_secret
        self.number = discord.ui.TextInput(label="Enter a number (1-100)", style=discord.TextStyle.short, min_length=1, max_length=3)
        self.add_item(self.number)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.number.value)
            if not (1 <= val <= 100):
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("Please enter a valid number between 1 and 100!", ephemeral=True)

        if self.is_setting_secret:
            await self.game_view.handle_secret(interaction, val)
        else:
            await self.game_view.handle_guess(interaction, val)


class GuessBattleView(discord.ui.View):
    """A 1v1 duel: each player secretly picks a number, then takes turns
    guessing the other's. For an unlimited-player version of this idea, see
    /guessnumber below - a duel is inherently two-sided, so this one stays
    2-player by design."""

    def __init__(self, p1, p2):
        super().__init__(timeout=300)
        self.players = [p1, p2]
        self.secrets = {p1: None, p2: None}
        self.turn = 0
        self.game_log = []

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user not in self.players:
            await interaction.response.send_message(f"{EMOJI['error']} This isn't your game — start your own with `/guessbattle`.", ephemeral=True)
            return False
        return True

    def get_embed(self):
        if None in self.secrets.values():
            embed = discord.Embed(title="🔢 Guess Battle", description="Waiting for both players to set their secret numbers (1-100)...", color=discord.Color.blurple())
            p1_status = f"{EMOJI['success']} Ready" if self.secrets[self.players[0]] else f"{EMOJI['loading']} Setting..."
            p2_status = f"{EMOJI['success']} Ready" if self.secrets[self.players[1]] else f"{EMOJI['loading']} Setting..."
            embed.add_field(name=self.players[0].display_name, value=p1_status)
            embed.add_field(name=self.players[1].display_name, value=p2_status)
            return embed

        current_player = self.players[self.turn]
        opponent = self.players[1 - self.turn]
        desc = f"**{current_player.mention}'s turn to guess {opponent.display_name}'s number!**\n\n"
        if self.game_log:
            desc += "**Recent Guesses:**\n" + "\n".join(self.game_log[-5:])
        return discord.Embed(title="🔢 Guess Battle", description=desc, color=discord.Color.green())

    @discord.ui.button(label="Set Secret Number", style=discord.ButtonStyle.primary, custom_id="btn_set")
    async def btn_set(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.secrets[interaction.user] is not None:
            return await interaction.response.send_message("You already set your secret!", ephemeral=True)
        await interaction.response.send_modal(GuessBattleModal(self, is_setting_secret=True))

    @discord.ui.button(label="Make a Guess", style=discord.ButtonStyle.success, custom_id="btn_guess", disabled=True)
    async def btn_guess(self, interaction: discord.Interaction, button: discord.ui.Button):
        if None in self.secrets.values():
            return await interaction.response.send_message("Still waiting for secrets to be set!", ephemeral=True)
        if interaction.user != self.players[self.turn]:
            return await interaction.response.send_message("It's not your turn!", ephemeral=True)
        await interaction.response.send_modal(GuessBattleModal(self, is_setting_secret=False))

    async def handle_secret(self, interaction, value):
        self.secrets[interaction.user] = value
        if None not in self.secrets.values():
            self.children[0].disabled = True
            self.children[1].disabled = False
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def handle_guess(self, interaction, guess):
        opponent = self.players[1 - self.turn]
        secret = self.secrets[opponent]

        if guess == secret:
            embed = discord.Embed(
                title=f"{EMOJI['party']} We have a Winner!",
                description=(
                    f"{interaction.user.mention} correctly guessed **{secret}** and won the game!\n\n"
                    f"({opponent.display_name}'s number was {secret}, "
                    f"{interaction.user.display_name}'s number was {self.secrets[interaction.user]})"
                ),
                color=discord.Color.gold(),
            )
            for item in self.children:
                item.disabled = True
            await interaction.response.edit_message(embed=embed, view=self)
            self.stop()
        else:
            hint = "🔼 HIGHER" if guess < secret else "🔽 LOWER"
            self.game_log.append(f"{interaction.user.display_name} guessed **{guess}** ➔ {hint}")
            self.turn = 1 - self.turn
            await interaction.response.edit_message(embed=self.get_embed(), view=self)


# ==========================================
#         GUESS THE NUMBER (unlimited players)
# ==========================================
class GuessNumberModal(discord.ui.Modal, title="Your guess"):
    guess = discord.ui.TextInput(label="Enter a whole number", max_length=20)

    def __init__(self, view: "GuessNumberMultiView"):
        super().__init__()
        self.view_obj = view

    async def on_submit(self, interaction: discord.Interaction):
        await self.view_obj.submit_guess(interaction, self.guess.value)


class GuessNumberMultiView(discord.ui.View):
    """Unlimited-player number guessing game. The host picks a min/max range,
    the bot secretly picks a number in that range, and anyone can join in and
    guess via the button below - no seat limit, no turn order."""

    def __init__(self, host: discord.abc.User, min_val: int, max_val: int):
        super().__init__(timeout=300)
        self.host = host
        self.min_val = min_val
        self.max_val = max_val
        self.secret = random.randint(min_val, max_val)
        self.message = None
        self.participants = {}
        self.total_guesses = 0
        self.finished = False

    def build_embed(self, status=None) -> discord.Embed:
        embed = discord.Embed(
            title="🔢 Guess the Number",
            description=(
                f"I'm thinking of a number between **{self.min_val}** and **{self.max_val}**.\n"
                f"Anyone can join - click **Guess** below!"
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Host", value=self.host.mention, inline=True)
        embed.add_field(name="Players", value=str(len(self.participants)), inline=True)
        embed.add_field(name="Total guesses", value=str(self.total_guesses), inline=True)
        if status:
            embed.add_field(name="Result", value=status, inline=False)
        return embed

    async def on_timeout(self):
        if self.finished:
            return
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(
                    embed=self.build_embed(f"⏰ Time's up! Nobody guessed it. The number was **{self.secret}**."),
                    view=self,
                )
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Guess", style=discord.ButtonStyle.primary, emoji="🔢")
    async def guess_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.finished:
            return await interaction.response.send_message("This round already ended.", ephemeral=True)
        await interaction.response.send_modal(GuessNumberModal(self))

    async def submit_guess(self, interaction: discord.Interaction, raw: str):
        if self.finished:
            return await interaction.response.send_message("This round already ended.", ephemeral=True)
        try:
            guess = int(raw.strip())
        except ValueError:
            return await interaction.response.send_message("Please enter a whole number.", ephemeral=True)
        if guess < self.min_val or guess > self.max_val:
            return await interaction.response.send_message(
                f"Your guess must be between **{self.min_val}** and **{self.max_val}**.", ephemeral=True
            )

        self.participants[interaction.user.id] = self.participants.get(interaction.user.id, 0) + 1
        self.total_guesses += 1

        if guess == self.secret:
            self.finished = True
            for child in self.children:
                child.disabled = True
            result = (
                f"{EMOJI['party']} {interaction.user.mention} guessed it! The number was **{self.secret}** "
                f"({self.total_guesses} total guesses across {len(self.participants)} "
                f"player{'s' if len(self.participants) != 1 else ''})."
            )
            embed = self.build_embed(result)
            embed.color = discord.Color.gold()
            return await interaction.response.edit_message(embed=embed, view=self)

        hint = "📈 Higher!" if guess < self.secret else "📉 Lower!"
        await interaction.response.send_message(f"{hint} (you guessed {guess})", ephemeral=True)
        if self.message:
            try:
                await self.message.edit(embed=self.build_embed())
            except discord.HTTPException:
                pass


# ==========================================
#         TRIVIA (unlimited players)
# ==========================================
class TriviaView(discord.ui.View):
    """Anyone in the channel can answer - first correct answer wins the round."""

    def __init__(self, question_data):
        super().__init__(timeout=30)
        self.correct_answer = html.unescape(question_data['correct_answer'])
        self.message = None
        self.finished = False
        options = question_data['incorrect_answers'] + [question_data['correct_answer']]
        random.shuffle(options)
        for option in options:
            label = html.unescape(option)[:80]
            btn = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary, custom_id=label)
            btn.callback = self._make_callback(label)
            self.add_item(btn)

    def _make_callback(self, label: str):
        async def callback(interaction: discord.Interaction):
            if self.finished:
                return await interaction.response.send_message("This round already ended.", ephemeral=True)

            if label == self.correct_answer:
                self.finished = True
                for child in self.children:
                    child.disabled = True
                embed = interaction.message.embeds[0]
                embed.color = discord.Color.green()
                embed.description += f"\n\n{EMOJI['success']} **{interaction.user.display_name}** got it! The answer was **{self.correct_answer}**."
                await interaction.response.edit_message(embed=embed, view=self)
                self.stop()

                from cogs.utils.json_store import get_store
                store = get_store("trivia_stats.json", dict)

                def _mut(data):
                    uid = str(interaction.user.id)
                    data[uid] = data.get(uid, 0) + 1
                    return data
                store.mutate(_mut)
            else:
                await interaction.response.send_message(f"{EMOJI['error']} Not quite - try again!", ephemeral=True)
        return callback

    async def on_timeout(self):
        if self.finished:
            return
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content=f"⏰ Time's up! The correct answer was **{self.correct_answer}**.", view=self)
            except discord.HTTPException:
                pass


# ==========================================
#              BLACKJACK (solo vs dealer)
# ==========================================
SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def _new_deck():
    deck = [f"{r}{s}" for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck


def _card_value(card: str) -> int:
    rank = card[:-1]
    if rank == "A":
        return 11
    if rank in ("J", "Q", "K"):
        return 10
    return int(rank)


def _hand_total(hand: list) -> int:
    total = sum(_card_value(c) for c in hand)
    aces = sum(1 for c in hand if c.startswith("A"))
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def _hand_str(hand: list) -> str:
    return " ".join(f"`{c}`" for c in hand)


class BlackjackView(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=60)
        self.player = player
        self.message = None
        self.deck = _new_deck()
        self.player_hand = [self.deck.pop(), self.deck.pop()]
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]
        self.finished = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.player:
            await interaction.response.send_message("Start your own game with the blackjack command!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        if self.finished:
            return
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⏰ Game timed out.", view=self)
            except discord.HTTPException:
                pass

    def render(self, reveal_dealer: bool = False) -> discord.Embed:
        p_total = _hand_total(self.player_hand)
        embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.dark_green())
        embed.add_field(name=f"Your hand ({p_total})", value=_hand_str(self.player_hand), inline=False)
        if reveal_dealer:
            d_total = _hand_total(self.dealer_hand)
            embed.add_field(name=f"Dealer's hand ({d_total})", value=_hand_str(self.dealer_hand), inline=False)
        else:
            embed.add_field(name="Dealer's hand", value=f"`{self.dealer_hand[0]}` `??`", inline=False)
        return embed

    async def end_game(self, interaction: discord.Interaction, result_text: str, color: discord.Color):
        self.finished = True
        for child in self.children:
            child.disabled = True
        embed = self.render(reveal_dealer=True)
        embed.color = color
        embed.add_field(name="Result", value=result_text, inline=False)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, emoji="🃏")
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player_hand.append(self.deck.pop())
        total = _hand_total(self.player_hand)
        if total > 21:
            return await self.end_game(interaction, f"💥 Bust! You went over 21 with **{total}**. Dealer wins.", discord.Color.red())
        if total == 21:
            return await self.stand.callback(interaction)
        await interaction.response.edit_message(embed=self.render(), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary, emoji="✋")
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        while _hand_total(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.pop())

        p_total = _hand_total(self.player_hand)
        d_total = _hand_total(self.dealer_hand)

        if d_total > 21:
            text, color = f"Dealer busts with **{d_total}**! You win with **{p_total}**. 🎉", discord.Color.green()
        elif p_total > d_total:
            text, color = f"You win! **{p_total}** beats dealer's **{d_total}**. 🎉", discord.Color.green()
        elif p_total < d_total:
            text, color = f"Dealer wins. **{d_total}** beats your **{p_total}**.", discord.Color.red()
        else:
            text, color = f"Push — both have **{p_total}**. Bet returned.", discord.Color.gold()

        await self.end_game(interaction, text, color)


# ==========================================
#                  WORDLE
# ==========================================
WORDLE_WORDS = [
    "apple", "beach", "chair", "dance", "eagle", "flame", "grape", "house",
    "input", "joker", "knife", "lemon", "mango", "night", "ocean", "piano",
    "queen", "river", "storm", "table", "unity", "vivid", "water", "youth",
    "zebra", "cloud", "brave", "crown", "dream", "earth", "fable", "ghost",
]


class WordleGuessModal(discord.ui.Modal, title="Guess the word"):
    guess = discord.ui.TextInput(label="Your 5-letter guess", min_length=5, max_length=5)

    def __init__(self, view: "WordleView"):
        super().__init__()
        self.view_obj = view

    async def on_submit(self, interaction: discord.Interaction):
        await self.view_obj.submit_guess(interaction, self.guess.value)


class WordleView(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=300)
        self.player = player
        self.message = None
        self.word = random.choice(WORDLE_WORDS)
        self.guesses = []
        self.max_attempts = 6

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.player:
            await interaction.response.send_message("Start your own game with the wordle command!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content=f"⏰ Time's up! The word was **{self.word.upper()}**.", view=self)
            except discord.HTTPException:
                pass

    def render_row(self, guess: str) -> str:
        row = []
        for i, ch in enumerate(guess):
            if ch == self.word[i]:
                row.append("🟩")
            elif ch in self.word:
                row.append("🟨")
            else:
                row.append("⬛")
        return "".join(row) + "   " + " ".join(guess.upper())

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(title="🟩 Wordle", description="Guess the 5-letter word!", color=discord.Color.green())
        board = "\n".join(self.render_row(g) for g in self.guesses) or "*No guesses yet.*"
        embed.add_field(name=f"Board ({len(self.guesses)}/{self.max_attempts})", value=board, inline=False)
        return embed

    @discord.ui.button(label="Guess", style=discord.ButtonStyle.primary, emoji="✍️")
    async def guess_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(WordleGuessModal(self))

    async def submit_guess(self, interaction: discord.Interaction, raw_guess: str):
        guess = raw_guess.strip().lower()
        if len(guess) != 5 or not guess.isalpha():
            return await interaction.response.send_message("Guesses must be exactly 5 letters.", ephemeral=True)

        self.guesses.append(guess)

        if guess == self.word:
            for child in self.children:
                child.disabled = True
            embed = self.build_embed()
            embed.color = discord.Color.gold()
            embed.add_field(name="Result", value=f"🎉 You got it in **{len(self.guesses)}** guess{'es' if len(self.guesses) != 1 else ''}!", inline=False)
            return await interaction.response.edit_message(embed=embed, view=self)

        if len(self.guesses) >= self.max_attempts:
            for child in self.children:
                child.disabled = True
            embed = self.build_embed()
            embed.color = discord.Color.red()
            embed.add_field(name="Result", value=f"💀 Out of guesses! The word was **{self.word.upper()}**.", inline=False)
            return await interaction.response.edit_message(embed=embed, view=self)

        await interaction.response.edit_message(embed=self.build_embed(), view=self)


# ==========================================
#              MEMORY MATCH
# ==========================================
MEMORY_SYMBOLS = ["🍎", "🍌", "🍇", "🍉", "🍓", "🍒", "🍍", "🥝"]


class MemoryButton(discord.ui.Button):
    def __init__(self, index: int, row: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="❔", row=row)
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_pick(interaction, self.index)


class MemoryView(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=180)
        self.player = player
        self.message = None
        symbols = MEMORY_SYMBOLS * 2
        random.shuffle(symbols)
        self.board = symbols
        self.matched = set()
        self.flipped = []
        self.attempts = 0
        self.busy = False
        for i in range(16):
            self.add_item(MemoryButton(i, row=i // 4))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.player:
            await interaction.response.send_message("Start your own game with the memory command!", ephemeral=True)
            return False
        if self.busy:
            await interaction.response.send_message("Wait a moment for the current pair to resolve.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⏰ Game timed out.", view=self)
            except discord.HTTPException:
                pass

    def _sync_buttons(self):
        for child in self.children:
            if not isinstance(child, MemoryButton):
                continue
            if child.index in self.matched:
                child.label = self.board[child.index]
                child.style = discord.ButtonStyle.success
                child.disabled = True
            elif child.index in self.flipped:
                child.label = self.board[child.index]
                child.style = discord.ButtonStyle.primary
            else:
                child.label = "❔"
                child.style = discord.ButtonStyle.secondary

    def build_embed(self, status: str = "Pick two cards to find a match!") -> discord.Embed:
        embed = discord.Embed(title="🧠 Memory Match", description=status, color=discord.Color.blurple())
        embed.add_field(name="Pairs found", value=f"{len(self.matched) // 2} / 8", inline=True)
        embed.add_field(name="Attempts", value=str(self.attempts), inline=True)
        return embed

    async def handle_pick(self, interaction: discord.Interaction, index: int):
        if index in self.matched or index in self.flipped:
            return await interaction.response.defer()

        self.flipped.append(index)
        if len(self.flipped) == 1:
            self._sync_buttons()
            return await interaction.response.edit_message(embed=self.build_embed(), view=self)

        self.attempts += 1
        self._sync_buttons()
        a, b = self.flipped
        is_match = self.board[a] == self.board[b]
        status = "✨ Match!" if is_match else "❌ No match — resetting…"
        await interaction.response.edit_message(embed=self.build_embed(status), view=self)

        if is_match:
            self.matched.update(self.flipped)
            self.flipped = []
            self._sync_buttons()
            if len(self.matched) == 16:
                for child in self.children:
                    child.disabled = True
                embed = self.build_embed(f"🎉 You matched every pair in **{self.attempts}** attempts!")
                embed.color = discord.Color.gold()
                if self.message:
                    await self.message.edit(embed=embed, view=self)
            elif self.message:
                await self.message.edit(embed=self.build_embed(), view=self)
        else:
            self.busy = True
            await asyncio.sleep(1.4)
            self.flipped = []
            self.busy = False
            self._sync_buttons()
            if self.message:
                try:
                    await self.message.edit(embed=self.build_embed(), view=self)
                except discord.HTTPException:
                    pass


# ==========================================
#                  HANGMAN
# ==========================================
HANGMAN_WORDS = [
    "python", "discord", "keyboard", "guitar", "mountain", "elephant",
    "rainbow", "castle", "diamond", "volcano", "penguin", "dolphin",
    "biscuit", "carnival", "lantern", "whisper", "thunder", "compass",
]
HANGMAN_STAGES = [
    "```\n  +---+\n  |   |\n      |\n      |\n      |\n      |\n=========\n```",
    "```\n  +---+\n  |   |\n  O   |\n      |\n      |\n      |\n=========\n```",
    "```\n  +---+\n  |   |\n  O   |\n  |   |\n      |\n      |\n=========\n```",
    "```\n  +---+\n  |   |\n  O   |\n /|   |\n      |\n      |\n=========\n```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n      |\n      |\n=========\n```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n /    |\n      |\n=========\n```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n / \\  |\n      |\n=========\n```",
]


class HangmanGuessModal(discord.ui.Modal, title="Guess a letter"):
    letter = discord.ui.TextInput(label="One letter", min_length=1, max_length=1)

    def __init__(self, view: "HangmanView"):
        super().__init__()
        self.view_obj = view

    async def on_submit(self, interaction: discord.Interaction):
        await self.view_obj.submit_letter(interaction, self.letter.value)


class HangmanView(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=300)
        self.player = player
        self.message = None
        self.word = random.choice(HANGMAN_WORDS)
        self.guessed = set()
        self.wrong = 0
        self.max_wrong = 6

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.player:
            await interaction.response.send_message("Start your own game with the hangman command!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content=f"⏰ Time's up! The word was **{self.word.upper()}**.", view=self)
            except discord.HTTPException:
                pass

    def display_word(self) -> str:
        return " ".join(ch.upper() if ch in self.guessed else "\\_" for ch in self.word)

    def build_embed(self, status=None) -> discord.Embed:
        embed = discord.Embed(title="🪢 Hangman", color=discord.Color.orange())
        embed.description = HANGMAN_STAGES[min(self.wrong, self.max_wrong)]
        embed.add_field(name="Word", value=f"`{self.display_word()}`", inline=False)
        wrong_letters = sorted(l for l in self.guessed if l not in self.word)
        embed.add_field(name="Wrong guesses", value=(", ".join(wrong_letters).upper() or "None"), inline=True)
        embed.add_field(name="Lives left", value=str(self.max_wrong - self.wrong), inline=True)
        if status:
            embed.add_field(name="Result", value=status, inline=False)
        return embed

    @discord.ui.button(label="Guess Letter", style=discord.ButtonStyle.primary, emoji="🔤")
    async def guess_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(HangmanGuessModal(self))

    async def submit_letter(self, interaction: discord.Interaction, raw_letter: str):
        letter = raw_letter.strip().lower()
        if not letter.isalpha() or len(letter) != 1:
            return await interaction.response.send_message("Please guess a single letter.", ephemeral=True)
        if letter in self.guessed:
            return await interaction.response.send_message(f"You already guessed **{letter.upper()}**.", ephemeral=True)

        self.guessed.add(letter)
        if letter not in self.word:
            self.wrong += 1

        won = all(ch in self.guessed for ch in self.word)
        lost = self.wrong >= self.max_wrong

        if won or lost:
            for child in self.children:
                child.disabled = True
            status = f"🎉 You won! The word was **{self.word.upper()}**." if won else f"💀 You lost! The word was **{self.word.upper()}**."
            embed = self.build_embed(status)
            embed.color = discord.Color.gold() if won else discord.Color.red()
            return await interaction.response.edit_message(embed=embed, view=self)

        await interaction.response.edit_message(embed=self.build_embed(), view=self)


# ==========================================
#     WOULD YOU RATHER (unlimited players)
# ==========================================
WYR_PROMPTS = [
    ("Have the ability to fly", "Have the ability to turn invisible"),
    ("Always be 10 minutes late", "Always be 20 minutes early"),
    ("Give up your phone for a month", "Give up your favorite food forever"),
    ("Fight one horse-sized duck", "Fight 100 duck-sized horses"),
    ("Know when you're going to die", "Know how you're going to die"),
    ("Have unlimited money but no friends", "Have amazing friends but be broke"),
]


class WouldYouRatherView(discord.ui.View):
    def __init__(self, option_a: str, option_b: str):
        super().__init__(timeout=120)
        self.option_a = option_a
        self.option_b = option_b
        self.votes = {}
        self.message = None

    def build_embed(self) -> discord.Embed:
        total = len(self.votes)
        a_count = sum(1 for v in self.votes.values() if v == "a")
        b_count = total - a_count
        a_pct = (a_count / total * 100) if total else 0
        b_pct = 100 - a_pct if total else 0
        embed = discord.Embed(title="🤔 Would You Rather", color=discord.Color.blurple())
        embed.add_field(name="A", value=f"{self.option_a}\n**{a_pct:.0f}%** ({a_count})", inline=True)
        embed.add_field(name="B", value=f"{self.option_b}\n**{b_pct:.0f}%** ({b_count})", inline=True)
        embed.set_footer(text=f"{total} vote{'s' if total != 1 else ''} — anyone can vote")
        return embed

    async def _vote(self, interaction: discord.Interaction, choice: str):
        self.votes[interaction.user.id] = choice
        await interaction.response.edit_message(embed=self.build_embed())

    @discord.ui.button(label="Option A", style=discord.ButtonStyle.primary, emoji="🅰️")
    async def option_a_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._vote(interaction, "a")

    @discord.ui.button(label="Option B", style=discord.ButtonStyle.danger, emoji="🅱️")
    async def option_b_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._vote(interaction, "b")

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


# ==========================================
#      REACTION SPEED (unlimited players)
# ==========================================
class ReactionSpeedView(discord.ui.View):
    """Everyone waits for the button to actually turn green, then races to
    click it first. Clicking too early gets called out."""

    def __init__(self):
        super().__init__(timeout=30)
        self.started_at = None
        self.winner = None
        self.click_btn.disabled = True

    @discord.ui.button(label="Wait for it…", style=discord.ButtonStyle.secondary, emoji="⏳")
    async def click_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.winner is not None:
            return await interaction.response.send_message("Already over!", ephemeral=True)
        if self.started_at is None:
            return await interaction.response.send_message("Too early! Wait for green.", ephemeral=True)

        self.winner = interaction.user
        elapsed = time.monotonic() - self.started_at
        button.disabled = True
        button.label = "Finished!"
        embed = discord.Embed(
            title="⚡ Reaction Speed",
            description=f"{EMOJI['trophy']} **{interaction.user.mention}** won in **{elapsed:.3f}s**!",
            color=discord.Color.gold(),
        )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()

    async def go_green(self, message: discord.Message):
        self.started_at = time.monotonic()
        self.click_btn.disabled = False
        self.click_btn.style = discord.ButtonStyle.success
        self.click_btn.label = "CLICK NOW!"
        self.click_btn.emoji = "⚡"
        try:
            await message.edit(
                embed=discord.Embed(title="⚡ Reaction Speed", description="**GO!** Click the button!", color=discord.Color.green()),
                view=self,
            )
        except discord.HTTPException:
            pass


# ==========================================
#         TYPING RACE (unlimited players)
# ==========================================
TYPING_PHRASES = [
    "the quick brown fox jumps over the lazy dog",
    "discord bots make servers more fun",
    "practice makes perfect every single day",
    "sphinx of black quartz judge my vow",
    "pack my box with five dozen liquor jugs",
]


# ==========================================
#              BATTLESHIP (2 players)
# ==========================================
SHIP_SIZES = [5, 4, 3, 3, 2]


def _random_ship_placement():
    grid = [["water" for _ in range(8)] for _ in range(8)]
    for size in SHIP_SIZES:
        placed = False
        while not placed:
            horizontal = random.choice([True, False])
            r = random.randint(0, 7)
            c = random.randint(0, 7)
            cells = [(r, c + i) for i in range(size)] if horizontal else [(r + i, c) for i in range(size)]
            if all(0 <= rr < 8 and 0 <= cc < 8 and grid[rr][cc] == "water" for rr, cc in cells):
                for rr, cc in cells:
                    grid[rr][cc] = "ship"
                placed = True
    return grid


class BattleshipButton(discord.ui.Button):
    def __init__(self, row_i: int, col_i: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="🌊", row=row_i)
        self.row_i = row_i
        self.col_i = col_i

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_shot(interaction, self.row_i, self.col_i)


class BattleshipView(discord.ui.View):
    """2-player Battleship. Each shoots at the OTHER player's hidden board,
    shown as their own 8x8 grid of buttons."""

    def __init__(self, players: list):
        super().__init__(timeout=600)
        self.players = players  # [p1, p2]
        self.boards = {players[0].id: _random_ship_placement(), players[1].id: _random_ship_placement()}
        self.shots = {players[0].id: set(), players[1].id: set()}
        self.turn = 0
        self.message = None
        for r in range(8):
            for c in range(8):
                self.add_item(BattleshipButton(r, c))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user not in self.players:
            await interaction.response.send_message(f"{EMOJI['error']} You're not in this game.", ephemeral=True)
            return False
        if interaction.user != self.players[self.turn]:
            await interaction.response.send_message(f"{EMOJI['error']} It's not your turn.", ephemeral=True)
            return False
        return True

    def _opponent(self, user):
        return self.players[1] if user == self.players[0] else self.players[0]

    def _sync_buttons_for_shooter(self):
        opponent = self._opponent(self.players[self.turn])
        opp_board = self.boards[opponent.id]
        my_shots = self.shots[self.players[self.turn].id]
        for child in self.children:
            if not isinstance(child, BattleshipButton):
                continue
            pos = (child.row_i, child.col_i)
            if pos in my_shots:
                hit = opp_board[child.row_i][child.col_i] == "ship"
                child.label = "🔥" if hit else "❌"
                child.style = discord.ButtonStyle.danger if hit else discord.ButtonStyle.secondary
                child.disabled = True
            else:
                child.label = "🌊"
                child.style = discord.ButtonStyle.secondary
                child.disabled = False

    def build_embed(self) -> discord.Embed:
        current = self.players[self.turn]
        embed = discord.Embed(title="🚢 Battleship", description=f"{current.mention}'s turn — fire at the grid below!", color=discord.Color.blue())
        embed.set_footer(text=f"{self.players[0].display_name} vs {self.players[1].display_name}")
        return embed

    async def handle_shot(self, interaction: discord.Interaction, r: int, c: int):
        shooter = self.players[self.turn]
        opponent = self._opponent(shooter)
        my_shots = self.shots[shooter.id]
        if (r, c) in my_shots:
            return await interaction.response.send_message("You already shot there.", ephemeral=True)

        my_shots.add((r, c))
        opp_board = self.boards[opponent.id]
        hit = opp_board[r][c] == "ship"

        remaining_ships = sum(1 for row in opp_board for cell in row if cell == "ship") - sum(
            1 for (rr, cc) in my_shots if opp_board[rr][cc] == "ship"
        )

        if remaining_ships <= 0:
            for child in self.children:
                child.disabled = True
            self._sync_buttons_for_shooter()
            embed = discord.Embed(title="🚢 Battleship — Game Over", description=f"{EMOJI['trophy']} {shooter.mention} sank {opponent.mention}'s whole fleet!", color=discord.Color.gold())
            return await interaction.response.edit_message(embed=embed, view=self)

        self.turn = 1 - self.turn
        self._sync_buttons_for_shooter()
        result_note = "🔥 HIT!" if hit else "❌ Miss."
        embed = self.build_embed()
        embed.add_field(name="Last shot", value=f"{shooter.mention}: {result_note}", inline=False)
        await interaction.response.edit_message(embed=embed, view=self)


# ==========================================
#              EMOJI RIDDLE
# ==========================================
EMOJI_RIDDLES = [
    ("🦁👑", "lion king"),
    ("🕷️👨", "spider man"),
    ("🧊👸", "frozen"),
    ("🌟⚔️", "star wars"),
    ("🐠🔍", "finding nemo"),
    ("👻🚫", "ghostbusters"),
    ("🍫🏭", "willy wonka"),
    ("🦈", "jaws"),
]


# ==========================================
#               SIMON SAYS
# ==========================================
SIMON_COLORS = [("🔴", discord.ButtonStyle.danger), ("🟢", discord.ButtonStyle.success), ("🔵", discord.ButtonStyle.primary), ("🟡", discord.ButtonStyle.secondary)]


class SimonSaysView(discord.ui.View):
    def __init__(self, player: discord.abc.User):
        super().__init__(timeout=60)
        self.player = player
        self.message = None
        self.sequence = [random.randint(0, 3)]
        self.player_index = 0
        self.showing = True
        for i, (emoji, style) in enumerate(SIMON_COLORS):
            btn = discord.ui.Button(emoji=emoji, style=style, row=0, disabled=True)
            btn.callback = self._make_callback(i)
            self.add_item(btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.player:
            await interaction.response.send_message("Start your own game with the simon command!", ephemeral=True)
            return False
        return True

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            await self.handle_pick(interaction, index)
        return callback

    def build_embed(self, status: str = None) -> discord.Embed:
        embed = discord.Embed(title="🎵 Simon Says", description=f"Round **{len(self.sequence)}** — watch, then repeat the pattern!", color=discord.Color.purple())
        if status:
            embed.add_field(name="Status", value=status, inline=False)
        return embed

    async def start(self, message: discord.Message):
        self.message = message
        await self._flash_sequence()

    async def _flash_sequence(self):
        for child in self.children:
            child.disabled = True
        for i in self.sequence:
            emoji, style = SIMON_COLORS[i]
            try:
                await self.message.edit(embed=self.build_embed(f"{emoji} ..."), view=self)
            except discord.HTTPException:
                return
            await asyncio.sleep(0.7)
            try:
                await self.message.edit(embed=self.build_embed("Watching..."), view=self)
            except discord.HTTPException:
                return
            await asyncio.sleep(0.3)

        for child in self.children:
            child.disabled = False
        self.player_index = 0
        try:
            await self.message.edit(embed=self.build_embed("Your turn — repeat the pattern!"), view=self)
        except discord.HTTPException:
            pass

    async def handle_pick(self, interaction: discord.Interaction, index: int):
        if index != self.sequence[self.player_index]:
            for child in self.children:
                child.disabled = True
            embed = self.build_embed(f"❌ Wrong! You reached round **{len(self.sequence)}**.")
            embed.color = discord.Color.red()
            return await interaction.response.edit_message(embed=embed, view=self)

        self.player_index += 1
        if self.player_index == len(self.sequence):
            self.sequence.append(random.randint(0, 3))
            await interaction.response.edit_message(embed=self.build_embed("✅ Correct! Next round..."), view=self)
            await asyncio.sleep(1)
            await self._flash_sequence()
        else:
            await interaction.response.edit_message(embed=self.build_embed("Keep going..."), view=self)


class Games(commands.Cog):
    """All of the bot's interactive games live here - separate from the
    lighter, non-competitive commands in cogs/fun.py."""

    def __init__(self, bot):
        self.bot = bot
        self.session = None

    async def cog_load(self):
        import aiohttp
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        if self.session and not self.session.closed:
            self.bot.loop.create_task(self.session.close())

    @commands.command(name="battleship", aliases=['bs'])
    async def battleship(self, ctx, opponent: discord.Member):
        """Battleship — 2 players, each with a hidden 8x8 fleet."""
        if opponent.bot or opponent == ctx.author:
            return await ctx.send(f"{EMOJI['error']} Invalid opponent.")
        view = BattleshipView([ctx.author, opponent])
        msg = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg

    @commands.command(name="triviatop", aliases=['trivialb'])
    async def trivia_leaderboard(self, ctx):
        """Show the trivia leaderboard for this bot."""
        from cogs.utils.json_store import get_store
        store = get_store("trivia_stats.json", dict)
        stats = sorted(store.read().items(), key=lambda x: x[1], reverse=True)[:10]
        if not stats:
            return await ctx.send(f"{EMOJI['info']} No trivia wins recorded yet.")
        embed = discord.Embed(title=f"{EMOJI['trophy']} Trivia Leaderboard", color=discord.Color.gold())
        for i, (uid, wins) in enumerate(stats, start=1):
            user = self.bot.get_user(int(uid))
            embed.add_field(name=f"{i}. {user.display_name if user else uid}", value=f"{wins} win(s)", inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="emojiriddle", aliases=['riddle'])
    async def emoji_riddle(self, ctx):
        """Guess the movie/phrase from emoji — first correct answer in chat wins."""
        emojis, answer = random.choice(EMOJI_RIDDLES)
        embed = discord.Embed(title="🧩 Emoji Riddle", description=f"# {emojis}\n\nGuess what this represents! First correct answer wins.", color=discord.Color.purple())
        await ctx.send(embed=embed)

        def check(m):
            return m.channel == ctx.channel and m.content.lower().strip() == answer

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=30.0)
            await ctx.send(f"{EMOJI['success']} **{msg.author.display_name}** got it! The answer was **{answer}**.")
        except asyncio.TimeoutError:
            await ctx.send(f"{EMOJI['clock']} Time's up! The answer was **{answer}**.")

    # ---------------- 2-player games ----------------
    @commands.command()
    async def rps(self, ctx, opponent: discord.Member):
        """Rock-Paper-Scissors with buttons — 2 players."""
        if opponent.bot or opponent == ctx.author:
            return await ctx.send(f"{EMOJI['error']} Invalid opponent — pick a real, non-bot user who isn't you.")
        view = RPSView(ctx.author, opponent)
        view.add_item(RPSButton("rock", "🪨"))
        view.add_item(RPSButton("paper", "📄"))
        view.add_item(RPSButton("scissors", "✂️"))
        embed = discord.Embed(title="🪨📄✂️ Rock Paper Scissors", description=f"{ctx.author.mention} challenged {opponent.mention}!\n\nClick a button below to make your choice secretly.", color=discord.Color.blurple())
        await ctx.send(embed=embed, view=view)

    @commands.command()
    async def connect4(self, ctx, opponent: discord.Member):
        """Connect Four — 2 players."""
        if opponent.bot or opponent == ctx.author:
            return await ctx.send(f"{EMOJI['error']} Invalid opponent — pick a real, non-bot user who isn't you.")
        view = ConnectView(ctx.author, opponent)
        embed = discord.Embed(title="🔴 Connect 4 🔵", description=f"{ctx.author.mention} (🔴) vs {opponent.mention} (🔵)\n\nIt's {ctx.author.mention}'s turn!\n\n{view.render_board()}", color=discord.Color.blue())
        await ctx.send(embed=embed, view=view)

    @commands.command()
    async def ttt(self, ctx, opponent: discord.Member):
        """Tic-Tac-Toe — 2 players."""
        if opponent.bot or opponent == ctx.author:
            return await ctx.send(f"{EMOJI['error']} Invalid opponent — pick a real, non-bot user who isn't you.")
        view = TicTacToeView(ctx.author, opponent)
        embed = discord.Embed(title="🎮 Tic-Tac-Toe", description=f"{ctx.author.mention} (X) vs {opponent.mention} (O)\n\nIt is {ctx.author.mention}'s turn!", color=discord.Color.blue())
        await ctx.send(embed=embed, view=view)

    @commands.command(aliases=['gb', 'guess'])
    async def guessbattle(self, ctx, opponent: discord.Member):
        """1v1 number-guessing duel — each of you secretly picks a number, then take turns guessing the other's."""
        if opponent.bot or opponent == ctx.author:
            return await ctx.send(f"{EMOJI['error']} You need a real opponent to play this!")
        view = GuessBattleView(ctx.author, opponent)
        await ctx.send(content=f"{opponent.mention}, you have been challenged by {ctx.author.mention}!", embed=view.get_embed(), view=view)

    # ---------------- unlimited-player games ----------------
    @commands.command(name="guessnumber", aliases=['gtn'])
    async def guessnumber(self, ctx, min_val: int, max_val: int):
        """Multiplayer number guessing — anyone can join. Usage: .guessnumber <min> <max>"""
        if min_val >= max_val:
            return await ctx.send(f"{EMOJI['error']} The minimum must be less than the maximum.")
        if max_val - min_val > 1_000_000:
            return await ctx.send(f"{EMOJI['error']} Please keep the range to 1,000,000 or less.")
        view = GuessNumberMultiView(ctx.author, min_val, max_val)
        msg = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg

    @commands.command()
    async def trivia(self, ctx):
        """Multiplayer trivia — anyone in the channel can answer, first correct wins."""
        try:
            async with self.session.get("https://opentdb.com/api.php?amount=1&type=multiple") as res:
                if res.status != 200:
                    return await ctx.send(f"{EMOJI['error']} Couldn't fetch a trivia question right now — try again shortly.")
                payload = await res.json(content_type=None)
        except Exception:
            return await ctx.send(f"{EMOJI['error']} Couldn't fetch a trivia question right now — try again shortly.")

        data = payload['results'][0]
        question = html.unescape(data['question'])
        category = html.unescape(data['category'])
        difficulty = data['difficulty'].capitalize()

        view = TriviaView(data)
        embed = discord.Embed(title="🧠 Trivia Time!", description=f"**Category:** {category}\n**Difficulty:** {difficulty}\n\n**{question}**", color=discord.Color.purple())
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.command()
    async def scramble(self, ctx):
        """Word Scramble — first person to type the correct word in chat wins. Anyone can play."""
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

    @commands.command(name="wyr", aliases=['wouldyourather'])
    async def would_you_rather(self, ctx):
        """Would You Rather — everyone votes, results update live."""
        a, b = random.choice(WYR_PROMPTS)
        view = WouldYouRatherView(a, b)
        msg = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg

    @commands.command(name="reactiontest", aliases=['reaction'])
    async def reaction_speed(self, ctx):
        """Reaction speed test — whoever clicks first once it turns green wins. Anyone can join."""
        view = ReactionSpeedView()
        embed = discord.Embed(title="⚡ Reaction Speed", description="Get ready... the button will turn green soon!", color=discord.Color.orange())
        msg = await ctx.send(embed=embed, view=view)
        await asyncio.sleep(random.uniform(2.0, 5.0))
        await view.go_green(msg)

    @commands.command(name="typerace", aliases=['typing'])
    async def typing_race(self, ctx):
        """Typing race — everyone types the phrase, fastest correct message wins. Anyone can join."""
        phrase = random.choice(TYPING_PHRASES)
        embed = discord.Embed(title="⌨️ Typing Race", description=f"Type this phrase exactly, as fast as you can:\n\n> **{phrase}**", color=discord.Color.teal())
        await ctx.send(embed=embed)
        start = time.monotonic()

        def check(m):
            return m.channel == ctx.channel and m.content.strip().lower() == phrase

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=45.0)
            elapsed = time.monotonic() - start
            wpm = round((len(phrase.split()) / elapsed) * 60, 1)
            await ctx.send(f"{EMOJI['trophy']} **{msg.author.display_name}** finished in **{elapsed:.2f}s** (~{wpm} WPM)!")
        except asyncio.TimeoutError:
            await ctx.send(f"{EMOJI['clock']} Nobody finished in time!")

    # ---------------- solo games ----------------
    @commands.command(aliases=['bj'])
    async def blackjack(self, ctx):
        """Blackjack against the dealer."""
        view = BlackjackView(ctx.author)
        embed = view.render()
        p_total = _hand_total(view.player_hand)
        if p_total == 21:
            for child in view.children:
                child.disabled = True
            view.finished = True
            embed = view.render(reveal_dealer=True)
            embed.color = discord.Color.gold()
            embed.add_field(name="Result", value="🎉 Blackjack! Natural 21 — you win!", inline=False)
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg
            return
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.command()
    async def wordle(self, ctx):
        """Guess the secret 5-letter word in 6 tries."""
        view = WordleView(ctx.author)
        msg = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg

    @commands.command(aliases=['matchgame'])
    async def memory(self, ctx):
        """Flip cards and find all 8 matching pairs."""
        view = MemoryView(ctx.author)
        msg = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg

    @commands.command()
    async def hangman(self, ctx):
        """Classic Hangman — guess the word one letter at a time."""
        view = HangmanView(ctx.author)
        msg = await ctx.send(embed=view.build_embed(), view=view)
        view.message = msg

    @commands.command()
    async def slots(self, ctx):
        """Slot machine."""
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
        """Minesweeper in chat (spoilered tiles)."""
        size, bombs = 8, 10
        grid = [[0 for _ in range(size)] for _ in range(size)]
        placed = 0
        while placed < bombs:
            x, y = random.randint(0, size - 1), random.randint(0, size - 1)
            if grid[x][y] != -1:
                grid[x][y] = -1
                placed += 1
        for x in range(size):
            for y in range(size):
                if grid[x][y] == -1:
                    continue
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < size and 0 <= ny < size and grid[nx][ny] == -1:
                            grid[x][y] += 1
        tiles = {-1: "💥", 0: "⬜", 1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣"}
        output = "**Minesweeper**\n"
        for row in grid:
            output += "".join(f"||{tiles[cell]}||" for cell in row) + "\n"
        await ctx.send(output)

    @commands.command()
    async def tod(self, ctx):
        """Truth or Dare."""
        class TODView(discord.ui.View):
            def __init__(self, user):
                super().__init__(timeout=60)
                self.user = user

            @discord.ui.button(label="Truth", style=discord.ButtonStyle.primary, emoji="😇")
            async def b_truth(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user != self.user:
                    return
                truths = ["What's your biggest fear?", "Who is your secret crush?", "What's the most embarrassing thing you've ever done?", "What is a secret you've kept from your parents?"]
                await interaction.response.edit_message(content=f"**Truth for {interaction.user.mention}:**\n> {random.choice(truths)}", view=None)

            @discord.ui.button(label="Dare", style=discord.ButtonStyle.danger, emoji="😈")
            async def b_dare(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user != self.user:
                    return
                dares = ["Send a voice message barking like a dog.", "Do 10 pushups right now.", "Show the last photo saved in your camera roll.", "Type your next 5 messages with your eyes closed."]
                await interaction.response.edit_message(content=f"**Dare for {interaction.user.mention}:**\n> {random.choice(dares)}", view=None)

        await ctx.send(f"{ctx.author.mention}, choose your fate!", view=TODView(ctx.author))

    @commands.command(name="wordchain", aliases=['chain'])
    async def wordchain(self, ctx, rounds: int = 10):
        """Word Chain — each word must start with the last letter of the previous one. Anyone can play."""
        rounds = max(3, min(rounds, 30))
        used = set()
        current_word = random.choice(["apple", "dog", "orange", "table", "elephant"])
        used.add(current_word)
        await ctx.send(f"{EMOJI['sparkle']} Word Chain started! First word: **{current_word}**\nNext word must start with **{current_word[-1].upper()}**. Anyone can play — {rounds} rounds.")

        for round_num in range(rounds):
            def check(m):
                return (
                    m.channel == ctx.channel and not m.author.bot
                    and m.content.strip().isalpha()
                    and m.content.strip().lower().startswith(current_word[-1].lower())
                    and m.content.strip().lower() not in used
                )
            try:
                msg = await self.bot.wait_for('message', check=check, timeout=20.0)
            except asyncio.TimeoutError:
                return await ctx.send(f"{EMOJI['clock']} Chain broken — no one continued it in time! Final word: **{current_word}**")
            current_word = msg.content.strip().lower()
            used.add(current_word)
            await msg.add_reaction("✅")

        await ctx.send(f"{EMOJI['trophy']} Chain complete! {rounds} words strong, ending on **{current_word}**.")

    @commands.command(name="anagram")
    async def anagram(self, ctx):
        """Unscramble the anagram — first correct answer in chat wins."""
        words = ["listen", "silent", "garden", "planet", "stream", "candle", "bridge", "orange"]
        word = random.choice(words)
        scrambled = "".join(random.sample(word, len(word)))
        while scrambled == word:
            scrambled = "".join(random.sample(word, len(word)))
        embed = discord.Embed(title="🔤 Anagram", description=f"Unscramble: **`{scrambled.upper()}`**", color=discord.Color.blue())
        await ctx.send(embed=embed)

        def check(m):
            return m.channel == ctx.channel and m.content.lower().strip() == word

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=20.0)
            await ctx.send(f"{EMOJI['success']} **{msg.author.display_name}** got it! The word was **{word}**.")
        except asyncio.TimeoutError:
            await ctx.send(f"{EMOJI['clock']} Time's up! The word was **{word}**.")

    @commands.command(name="ship")
    async def ship(self, ctx, user1: discord.Member, user2: discord.Member = None):
        """See the compatibility % between two users (or you and someone else)."""
        user2 = user2 or ctx.author
        if user1 == user2:
            return await ctx.send(f"{EMOJI['error']} Pick two different people.")
        seed = hash((min(user1.id, user2.id), max(user1.id, user2.id)))
        pct = seed % 101
        bar_filled = round(pct / 10)
        bar = "💖" * bar_filled + "🖤" * (10 - bar_filled)
        embed = discord.Embed(title=f"{EMOJI['gem']} Ship Compatibility", description=f"{user1.mention} 💕 {user2.mention}\n\n{bar}\n**{pct}%**", color=discord.Color.pink())
        await ctx.send(embed=embed)

    @commands.command(name="speedmath", aliases=['mathrace'])
    async def speedmath(self, ctx):
        """Solve the math problem as fast as you can — first correct answer wins."""
        a, b = random.randint(2, 50), random.randint(2, 50)
        op = random.choice(["+", "-", "*"])
        answer = {"+": a + b, "-": a - b, "*": a * b}[op]
        embed = discord.Embed(title="🧮 Speed Math", description=f"Solve: **{a} {op} {b} = ?**", color=discord.Color.orange())
        await ctx.send(embed=embed)
        start = time.monotonic()

        def check(m):
            return m.channel == ctx.channel and m.content.strip().lstrip("-").isdigit() and int(m.content.strip()) == answer

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=20.0)
            elapsed = time.monotonic() - start
            await ctx.send(f"{EMOJI['trophy']} **{msg.author.display_name}** solved it in **{elapsed:.2f}s**! Answer: {answer}")
        except asyncio.TimeoutError:
            await ctx.send(f"{EMOJI['clock']} Time's up! The answer was **{answer}**.")

    @commands.command(name="simon")
    async def simon(self, ctx):
        """Simon Says — memorize and repeat the growing color sequence."""
        view = SimonSaysView(ctx.author)
        msg = await ctx.send(embed=view.build_embed("Get ready..."), view=view)
        await view.start(msg)

    @commands.command(name="20q", aliases=['twentyquestions'])
    async def twenty_questions(self, ctx):
        """20 Questions — the bot picks a thing, ask yes/no questions to guess it (you track your own question count)."""
        subjects = ["a banana", "a smartphone", "the moon", "a guitar", "a penguin", "an umbrella", "a volcano", "a spaceship"]
        subject = random.choice(subjects)
        await ctx.author.send(f"{EMOJI['loading']} I'm thinking of: **{subject}** (this DM is just for you to check answers — don't share it!)")
        embed = discord.Embed(
            title="❓ 20 Questions",
            description=f"{ctx.author.mention} started a round! I've picked something and DMed {ctx.author.mention} the answer.\nAsk **{ctx.author.display_name}** yes/no questions in chat to guess it — you get 20 questions total.",
            color=discord.Color.blurple(),
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Games(bot))
