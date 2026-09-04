import discord
from discord.ext import commands
from discord import app_commands
import random
import datetime
from cogs.utils.emoji_manager import EMOJI
from cogs.utils.json_store import get_store

ECON_FILE = "economy.json"
SHOP_FILE = "shop.json"
EARN_COOLDOWN = datetime.timedelta(hours=1)


class Economy(commands.Cog):
    """Virtual coin economy: earn coins, gamble them, spend them on role rewards in the shop,
    and view a social profile card. Separate from cogs/wallet.py (real Litecoin) and
    cogs/leveling.py (XP) - this is a distinct, purely for-fun currency."""

    def __init__(self, bot):
        self.bot = bot
        self.econ = get_store(ECON_FILE, dict)
        self.shop = get_store(SHOP_FILE, dict)

    def _user(self, user_id: int) -> dict:
        data = self.econ.read()
        return data.get(str(user_id), {"coins": 0, "last_earn": None})

    def _mut_user(self, user_id: int, fn):
        def _mut(data):
            entry = data.get(str(user_id), {"coins": 0, "last_earn": None})
            fn(entry)
            data[str(user_id)] = entry
            return data
        self.econ.mutate(_mut)

    def _shop_items(self, guild_id: int) -> dict:
        return self.shop.read().get(str(guild_id), {})

    @commands.hybrid_command(name="coins", description="Check your (or someone else's) coin balance.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def coins_cmd(self, ctx: commands.Context, user: discord.User = None):
        user = user or ctx.author
        coins = self._user(user.id)["coins"]
        embed = discord.Embed(title=f"{EMOJI['coin']} Balance", description=f"{user.mention} has **{coins}** coins.", color=discord.Color.gold())
        await ctx.send(embed=embed)

    @commands.command(name="earn", description="Claim your hourly coins.")
    async def earn(self, ctx: commands.Context):
        entry = self._user(ctx.author.id)
        now = datetime.datetime.utcnow()
        if entry.get("last_earn"):
            last = datetime.datetime.fromisoformat(entry["last_earn"])
            remaining = EARN_COOLDOWN - (now - last)
            if remaining.total_seconds() > 0:
                mins = int(remaining.total_seconds() // 60)
                return await ctx.send(f"{EMOJI['clock']} Come back in **{mins}m** to earn again.")

        amount = random.randint(50, 150)
        self._mut_user(ctx.author.id, lambda e: e.update(coins=e["coins"] + amount, last_earn=now.isoformat()))
        await ctx.send(f"{EMOJI['coin']} You earned **{amount}** coins!")

    @commands.command(name="give", description="Give some of your coins to another user.")
    async def give(self, ctx: commands.Context, user: discord.User, amount: int):
        if user.bot or user.id == ctx.author.id:
            return await ctx.send(f"{EMOJI['error']} You can't send coins to that user.")
        if amount <= 0:
            return await ctx.send(f"{EMOJI['error']} Amount must be positive.")
        sender = self._user(ctx.author.id)
        if sender["coins"] < amount:
            return await ctx.send(f"{EMOJI['error']} You don't have enough coins.")

        self._mut_user(ctx.author.id, lambda e: e.update(coins=e["coins"] - amount))
        self._mut_user(user.id, lambda e: e.update(coins=e["coins"] + amount))
        await ctx.send(f"{EMOJI['success']} Sent **{amount}** coins to {user.mention}.")

    @commands.command(name="coinbet", description="Bet coins on a 50/50 coinflip — double or nothing.")
    async def coinbet(self, ctx: commands.Context, amount: int):
        if amount <= 0:
            return await ctx.send(f"{EMOJI['error']} Amount must be positive.")
        entry = self._user(ctx.author.id)
        if entry["coins"] < amount:
            return await ctx.send(f"{EMOJI['error']} You don't have enough coins.")

        won = random.random() < 0.5
        delta = amount if won else -amount
        self._mut_user(ctx.author.id, lambda e: e.update(coins=e["coins"] + delta))

        if won:
            await ctx.send(f"{EMOJI['party']} Heads! You won **{amount}** coins.")
        else:
            await ctx.send(f"{EMOJI['error']} Tails. You lost **{amount}** coins.")

    # ---------------- shop ----------------
    @commands.hybrid_command(name="shop", description="View the server's role shop.")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.guild_only()
    async def shop_cmd(self, ctx: commands.Context):
        items = self._shop_items(ctx.guild.id)
        if not items:
            return await ctx.send(f"{EMOJI['info']} No shop items configured yet.")
        embed = discord.Embed(title=f"{EMOJI['cart']} Role Shop", color=discord.Color.purple())
        for role_id, price in items.items():
            role = ctx.guild.get_role(int(role_id))
            embed.add_field(name=role.name if role else "*deleted role*", value=f"{EMOJI['coin']} {price}", inline=True)
        embed.set_footer(text="Buy with /buy <role name>")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="buy", description="Buy a role from the shop with coins.")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.guild_only()
    async def buy(self, ctx: commands.Context, *, role: discord.Role):
        items = self._shop_items(ctx.guild.id)
        price = items.get(str(role.id))
        if price is None:
            return await ctx.send(f"{EMOJI['error']} That role isn't in the shop.")

        entry = self._user(ctx.author.id)
        if entry["coins"] < price:
            return await ctx.send(f"{EMOJI['error']} You need **{price}** coins but only have **{entry['coins']}**.")
        if role in ctx.author.roles:
            return await ctx.send(f"{EMOJI['info']} You already have that role.")

        try:
            await ctx.author.add_roles(role, reason="Shop purchase")
        except discord.Forbidden:
            return await ctx.send(f"{EMOJI['error']} I can't assign that role — check role hierarchy/permissions.")

        self._mut_user(ctx.author.id, lambda e: e.update(coins=e["coins"] - price))
        await ctx.send(f"{EMOJI['success']} Purchased **{role.name}** for {price} coins!")

    @commands.command(name="shop_additem", description="Admin: add a role to the shop.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def shop_additem(self, ctx: commands.Context, role: discord.Role, price: int):
        if price <= 0:
            return await ctx.send(f"{EMOJI['error']} Price must be positive.")

        def _mut(data):
            entry = data.setdefault(str(ctx.guild.id), {})
            entry[str(role.id)] = price
            return data
        self.shop.mutate(_mut)
        await ctx.send(f"{EMOJI['success']} Added **{role.name}** to the shop for {price} coins.")

    @commands.command(name="shop_removeitem", description="Admin: remove a role from the shop.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def shop_removeitem(self, ctx: commands.Context, role: discord.Role):
        def _mut(data):
            entry = data.setdefault(str(ctx.guild.id), {})
            entry.pop(str(role.id), None)
            return data
        self.shop.mutate(_mut)
        await ctx.send(f"{EMOJI['success']} Removed **{role.name}** from the shop.")

    # ---------------- profile ----------------
    @commands.hybrid_command(name="profile", description="View a social profile card.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def profile(self, ctx: commands.Context, user: discord.User = None):
        user = user or ctx.author
        coins = self._user(user.id)["coins"]

        level, xp = None, None
        leveling_cog = self.bot.get_cog("Leveling")
        if leveling_cog:
            level, xp = leveling_cog.get_user_level(user.id)

        embed = discord.Embed(title=f"{EMOJI['id_card']} {user.name}'s Profile", color=discord.Color.blurple())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name=f"{EMOJI['coin']} Coins", value=str(coins), inline=True)
        if level is not None:
            embed.add_field(name=f"{EMOJI['trophy']} Level", value=str(level), inline=True)
            embed.add_field(name=f"{EMOJI['gem']} XP", value=str(xp), inline=True)
        embed.add_field(name=f"{EMOJI['calendar']} Account created", value=discord.utils.format_dt(user.created_at, "D"), inline=False)
        if isinstance(user, discord.Member) and user.joined_at:
            embed.add_field(name=f"{EMOJI['wave']} Joined server", value=discord.utils.format_dt(user.joined_at, "D"), inline=False)
        await ctx.send(embed=embed)

    # ---------------- pet system ----------------
    def _pet(self, user_id: int) -> dict:
        entry = self._user(user_id)
        return entry.get("pet") or {"name": None, "level": 1, "xp": 0, "last_fed": None}

    @commands.command(name="pet_adopt", description="Adopt a virtual pet.")
    async def pet_adopt(self, ctx: commands.Context, *, name: str):
        entry = self._user(ctx.author.id)
        if entry.get("pet"):
            return await ctx.send(f"{EMOJI['error']} You already have a pet named **{entry['pet']['name']}**.")
        self._mut_user(ctx.author.id, lambda e: e.update(pet={"name": name[:32], "level": 1, "xp": 0, "last_fed": None}))
        await ctx.send(f"{EMOJI['party']} You adopted **{name}**! Use `/pet_feed` to keep it happy and growing.")

    @commands.hybrid_command(name="pet_feed", description="Feed your pet (costs 20 coins, grants XP).")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def pet_feed(self, ctx: commands.Context):
        entry = self._user(ctx.author.id)
        pet = entry.get("pet")
        if not pet:
            return await ctx.send(f"{EMOJI['error']} You don't have a pet yet — use `/pet_adopt <name>`.")
        if entry["coins"] < 20:
            return await ctx.send(f"{EMOJI['error']} Feeding costs 20 coins and you don't have enough.")

        def _mut(e):
            e["coins"] -= 20
            p = e["pet"]
            p["xp"] += random.randint(10, 25)
            p["last_fed"] = datetime.datetime.utcnow().isoformat()
            while p["xp"] >= p["level"] * 50:
                p["xp"] -= p["level"] * 50
                p["level"] += 1
        self._mut_user(ctx.author.id, _mut)
        pet = self._user(ctx.author.id)["pet"]
        await ctx.send(f"{EMOJI['success']} You fed **{pet['name']}**! Now level **{pet['level']}** ({pet['xp']}/{pet['level']*50} XP).")

    @commands.hybrid_command(name="pet", description="View your (or someone else's) pet.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def pet_cmd(self, ctx: commands.Context, user: discord.User = None):
        user = user or ctx.author
        pet = self._user(user.id).get("pet")
        if not pet:
            return await ctx.send(f"{EMOJI['info']} {user.mention} doesn't have a pet.")
        embed = discord.Embed(title=f"🐾 {pet['name']}", color=discord.Color.orange())
        embed.add_field(name="Level", value=str(pet["level"]), inline=True)
        embed.add_field(name="XP", value=f"{pet['xp']}/{pet['level']*50}", inline=True)
        await ctx.send(embed=embed)

    # ---------------- duel / RPG battle ----------------
    @commands.command(name="duel", description="Challenge another user to a coin-wagering RPG duel.")
    @commands.guild_only()
    async def duel(self, ctx: commands.Context, opponent: discord.Member, wager: int = 0):
        if opponent.bot or opponent == ctx.author:
            return await ctx.send(f"{EMOJI['error']} You need a real opponent.")
        if wager < 0:
            return await ctx.send(f"{EMOJI['error']} Wager can't be negative.")
        if wager:
            challenger_coins = self._user(ctx.author.id)["coins"]
            opp_coins = self._user(opponent.id)["coins"]
            if challenger_coins < wager or opp_coins < wager:
                return await ctx.send(f"{EMOJI['error']} Both players need at least **{wager}** coins to duel for that wager.")

        # simple simulated combat: each side rolls a "power" score, best of 3 rounds
        challenger_wins = 0
        opponent_wins = 0
        log_lines = []
        for round_num in range(1, 4):
            c_roll = random.randint(1, 20)
            o_roll = random.randint(1, 20)
            if c_roll > o_roll:
                challenger_wins += 1
                log_lines.append(f"Round {round_num}: {ctx.author.display_name} rolled **{c_roll}** vs **{o_roll}** — wins!")
            elif o_roll > c_roll:
                opponent_wins += 1
                log_lines.append(f"Round {round_num}: {opponent.display_name} rolled **{o_roll}** vs **{c_roll}** — wins!")
            else:
                log_lines.append(f"Round {round_num}: tie ({c_roll} vs {c_roll}).")

        winner = ctx.author if challenger_wins > opponent_wins else (opponent if opponent_wins > challenger_wins else None)

        embed = discord.Embed(title=f"{EMOJI['crown']} Duel: {ctx.author.display_name} vs {opponent.display_name}", description="\n".join(log_lines), color=discord.Color.dark_red())
        if winner:
            embed.add_field(name="Winner", value=winner.mention, inline=False)
            if wager:
                loser = opponent if winner == ctx.author else ctx.author
                self._mut_user(winner.id, lambda e: e.update(coins=e["coins"] + wager))
                self._mut_user(loser.id, lambda e: e.update(coins=e["coins"] - wager))
                embed.add_field(name="Wager", value=f"{EMOJI['coin']} {wager} coins transferred", inline=False)
        else:
            embed.add_field(name="Result", value="It's a tie — no coins change hands.", inline=False)
        await ctx.send(embed=embed)

    # ---------------- daily challenge ----------------
    @commands.command(name="challenge", description="Claim today's random challenge for bonus coins.")
    async def challenge(self, ctx: commands.Context):
        entry = self._user(ctx.author.id)
        today = datetime.datetime.utcnow().date().isoformat()
        if entry.get("last_challenge") == today:
            return await ctx.send(f"{EMOJI['clock']} You've already completed today's challenge — come back tomorrow.")

        challenges = [
            ("Send 5 messages today", 30),
            ("React to someone's message", 20),
            ("Play any game command", 40),
            ("Chat in a voice channel", 35),
        ]
        text, reward = random.choice(challenges)
        # simplified: claiming counts as completing it (no live tracking of the actual action)
        self._mut_user(ctx.author.id, lambda e: e.update(coins=e["coins"] + reward, last_challenge=today))
        embed = discord.Embed(title=f"{EMOJI['sparkle']} Daily Challenge Complete", description=f"**{text}**\n\nReward: {EMOJI['coin']} {reward} coins", color=discord.Color.teal())
        await ctx.send(embed=embed)

    # ---------------- bank ----------------
    def _bank(self, user_id: int) -> int:
        return self._user(user_id).get("bank", 0)

    @commands.command(name="deposit")
    async def deposit(self, ctx: commands.Context, amount: int):
        """Move coins from your wallet into your bank (earns interest, safe from /rob)."""
        entry = self._user(ctx.author.id)
        if amount <= 0 or amount > entry["coins"]:
            return await ctx.send(f"{EMOJI['error']} Invalid amount — you have **{entry['coins']}** coins on hand.")
        self._mut_user(ctx.author.id, lambda e: e.update(coins=e["coins"] - amount, bank=e.get("bank", 0) + amount))
        await ctx.send(f"{EMOJI['success']} Deposited **{amount}** coins into your bank.")

    @commands.command(name="withdraw")
    async def withdraw(self, ctx: commands.Context, amount: int):
        """Move coins from your bank back to your wallet."""
        entry = self._user(ctx.author.id)
        bank = entry.get("bank", 0)
        if amount <= 0 or amount > bank:
            return await ctx.send(f"{EMOJI['error']} Invalid amount — you have **{bank}** coins banked.")
        self._mut_user(ctx.author.id, lambda e: e.update(coins=e["coins"] + amount, bank=e.get("bank", 0) - amount))
        await ctx.send(f"{EMOJI['success']} Withdrew **{amount}** coins from your bank.")

    @commands.command(name="bank")
    async def bank_cmd(self, ctx: commands.Context, user: discord.User = None):
        """View wallet + bank balance."""
        user = user or ctx.author
        entry = self._user(user.id)
        embed = discord.Embed(title=f"{EMOJI['money']} {user.name}'s Bank", color=discord.Color.gold())
        embed.add_field(name="Wallet", value=f"{EMOJI['coin']} {entry['coins']}", inline=True)
        embed.add_field(name="Bank", value=f"{EMOJI['coin']} {entry.get('bank', 0)}", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="collectinterest", aliases=['interest'])
    async def collect_interest(self, ctx: commands.Context):
        """Collect 2% daily interest on your banked coins."""
        entry = self._user(ctx.author.id)
        today = datetime.datetime.utcnow().date().isoformat()
        if entry.get("last_interest") == today:
            return await ctx.send(f"{EMOJI['clock']} You've already collected interest today.")
        bank = entry.get("bank", 0)
        if bank <= 0:
            return await ctx.send(f"{EMOJI['error']} You have nothing banked to earn interest on.")
        gain = max(1, round(bank * 0.02))
        self._mut_user(ctx.author.id, lambda e: e.update(bank=e.get("bank", 0) + gain, last_interest=today))
        await ctx.send(f"{EMOJI['success']} Earned **{gain}** coins in interest ({2}% of your bank).")

    # ---------------- rob ----------------
    @commands.command(name="rob")
    @commands.guild_only()
    async def rob(self, ctx: commands.Context, target: discord.Member):
        """Attempt to steal coins from another user's wallet — risky, can backfire."""
        if target.bot or target == ctx.author:
            return await ctx.send(f"{EMOJI['error']} Invalid target.")
        robber = self._user(ctx.author.id)
        victim = self._user(target.id)
        if victim["coins"] < 50:
            return await ctx.send(f"{EMOJI['error']} {target.display_name} doesn't have enough coins on hand to be worth robbing.")

        today_key = datetime.datetime.utcnow().date().isoformat()
        if robber.get("last_rob") == today_key:
            return await ctx.send(f"{EMOJI['clock']} You can only attempt a robbery once per day.")

        success = random.random() < 0.4
        if success:
            amount = random.randint(10, min(200, victim["coins"]))
            self._mut_user(target.id, lambda e: e.update(coins=e["coins"] - amount))
            self._mut_user(ctx.author.id, lambda e: e.update(coins=e["coins"] + amount, last_rob=today_key))
            await ctx.send(f"{EMOJI['success']} You robbed **{amount}** coins from {target.mention}!")
        else:
            fine = random.randint(10, 100)
            fine = min(fine, robber["coins"])
            self._mut_user(ctx.author.id, lambda e: e.update(coins=e["coins"] - fine, last_rob=today_key))
            await ctx.send(f"{EMOJI['error']} You got caught! Paid a **{fine}** coin fine.")

    # ---------------- lottery ----------------
    @commands.command(name="lottery_buy", aliases=['buyticket'])
    async def lottery_buy(self, ctx: commands.Context, tickets: int = 1):
        """Buy lottery tickets (10 coins each) for the weekly draw."""
        tickets = max(1, tickets)
        cost = tickets * 10
        entry = self._user(ctx.author.id)
        if entry["coins"] < cost:
            return await ctx.send(f"{EMOJI['error']} You need **{cost}** coins for {tickets} ticket(s).")
        def _buy_tickets(e):
            e["coins"] -= cost
            e["lottery_tickets"] = e.get("lottery_tickets", 0) + tickets
        self._mut_user(ctx.author.id, _buy_tickets)
        await ctx.send(f"{EMOJI['success']} Bought **{tickets}** ticket(s) for **{cost}** coins. Good luck!")

    @commands.command(name="lottery_draw")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def lottery_draw(self, ctx: commands.Context):
        """Admin: draw the weekly lottery winner from everyone with tickets."""
        data = self.econ.read()
        pool = []
        for uid, entry in data.items():
            pool.extend([uid] * entry.get("lottery_tickets", 0))
        if not pool:
            return await ctx.send(f"{EMOJI['info']} No tickets have been purchased.")

        winner_id = random.choice(pool)
        prize = len(pool) * 8

        def _mut(d):
            d[winner_id]["coins"] = d[winner_id].get("coins", 0) + prize
            for entry in d.values():
                entry["lottery_tickets"] = 0
            return d
        self.econ.mutate(_mut)

        await ctx.send(f"{EMOJI['party']} <@{winner_id}> won the lottery and takes home **{prize}** coins! ({len(pool)} total tickets)")

    # ---------------- leaderboard ----------------
    @commands.command(name="richest", aliases=['coinleaderboard'])
    async def richest(self, ctx: commands.Context):
        """Show the richest users (wallet + bank combined)."""
        data = self.econ.read()
        ranked = sorted(data.items(), key=lambda kv: kv[1].get("coins", 0) + kv[1].get("bank", 0), reverse=True)[:10]
        if not ranked:
            return await ctx.send(f"{EMOJI['info']} No one has any coins yet.")
        embed = discord.Embed(title=f"{EMOJI['trophy']} Richest Users", color=discord.Color.gold())
        for i, (uid, entry) in enumerate(ranked, start=1):
            total = entry.get("coins", 0) + entry.get("bank", 0)
            user = self.bot.get_user(int(uid))
            embed.add_field(name=f"{i}. {user.display_name if user else uid}", value=f"{EMOJI['coin']} {total:,}", inline=False)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Economy(bot))
