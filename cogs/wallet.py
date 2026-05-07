# cogs/wallet.py
import discord
from discord.ext import commands
import aiohttp
import json
import os
import asyncio
from typing import Optional

WALLET_FILE = "wallet.json"
LTC_BALANCE_API = "https://api.blockcypher.com/v1/ltc/main/addrs/"
LTC_PRICE_API = "https://api.coingecko.com/api/v3/simple/price?ids=litecoin&vs_currencies=usd"

class Wallet(commands.Cog):
    """Wallet & balance commands (reads/writes wallet.json)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = aiohttp.ClientSession()
        self._lock = asyncio.Lock()
        self.data = self._load_file()

    def cog_unload(self):
        # close session when cog is removed
        self.bot.loop.create_task(self.session.close())

    # -------------------------
    # File helpers (thread-safe)
    # -------------------------
    def _load_file(self) -> dict:
        if os.path.exists(WALLET_FILE):
            try:
                with open(WALLET_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    async def _save_file(self) -> None:
        async with self._lock:
            with open(WALLET_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4)

    # -------------------------
    # Internal helpers
    # -------------------------
    async def _get_ltc_price(self) -> Optional[float]:
        try:
            async with self.session.get(LTC_PRICE_API, timeout=20) as r:
                if r.status != 200:
                    return None
                j = await r.json()
                return float(j.get("litecoin", {}).get("usd", 0))
        except Exception:
            return None

    async def _get_balance_from_api(self, address: str) -> Optional[dict]:
        try:
            async with self.session.get(f"{LTC_BALANCE_API}{address}", timeout=20) as r:
                if r.status != 200:
                    return None
                j = await r.json()
            # blockcypher amounts are satoshi-like (1e8)
            total_received = j.get("total_received", 0) / 1e8
            confirmed_balance = j.get("balance", 0) / 1e8
            unconfirmed_balance = j.get("unconfirmed_balance", 0) / 1e8
            price = await self._get_ltc_price()
            if price is None:
                usd = None
            else:
                usd = {
                    "total_received": round(total_received * price, 2),
                    "confirmed_balance": round(confirmed_balance * price, 2),
                    "unconfirmed_balance": round(unconfirmed_balance * price, 2),
                }
            return {
                "total_received": total_received,
                "confirmed_balance": confirmed_balance,
                "unconfirmed_balance": unconfirmed_balance,
                "usd": usd,
                "raw": j
            }
        except Exception:
            return None

    # -------------------------
    # Read-only view commands
    # -------------------------
    @commands.hybrid_command(name="ltc", description="Show current LTC price (USD).")
    async def ltc(self, ctx):
        price = await self._get_ltc_price()
        if price is None:
            return await ctx.send(embed=discord.Embed(title="<a:Cross_:1489174755537064046> Error", description="Couldn't fetch LTC price right now.", color=discord.Color.red()))
        embed = discord.Embed(title="💱 Litecoin Price", description=f"**1 LTC = ${price} USD**", color=discord.Color.gold())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="balance", description="Fetch LTC balance for any LTC address.")
    async def balance(self, ctx, address: str):
        """Generic balance check for any LTC address."""
        await ctx.defer()
        res = await self._get_balance_from_api(address)
        if res is None:
            return await ctx.send(embed=discord.Embed(title="<a:Cross_:1489174755537064046> Error", description="Failed to fetch address data.", color=discord.Color.red()))
        price_info = res["usd"]
        desc = (f"**Address:** `{address}`\n\n"
                f"**Total Received:** {res['total_received']} LTC\n"
                f"**Confirmed Balance:** {res['confirmed_balance']} LTC\n"
                f"**Unconfirmed Balance:** {res['unconfirmed_balance']} LTC\n")
        if price_info:
            desc += ("\n**USD:**\n"
                     f"Total Received: ${price_info['total_received']}\n"
                     f"Confirmed: ${price_info['confirmed_balance']}\n"
                     f"Unconfirmed: ${price_info['unconfirmed_balance']}\n")
        embed = discord.Embed(title="💰 Litecoin Address Info", description=desc, color=discord.Color.green())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="mybal", description="Show your primary LTC address balance.")
    async def mybal(self, ctx):
        """Shows balance for user's primary saved address."""
        uid = str(ctx.author.id)
        user = self.data.get("users", {}).get(uid, {})
        addr = user.get("addy")
        if not addr:
            return await ctx.send(embed=discord.Embed(title="<a:Cross_:1489174755537064046> No Address", description="You don't have a primary address set. Use `/setaddy <address>` in config cog.", color=discord.Color.red()))
        await ctx.invoke(self.bot.get_command("balance"), address=addr)

    @commands.hybrid_command(name="mybal2", description="Show your secondary LTC address balance.")
    async def mybal2(self, ctx):
        uid = str(ctx.author.id)
        user = self.data.get("users", {}).get(uid, {})
        addr = user.get("addy2")
        if not addr:
            return await ctx.send(embed=discord.Embed(title="<a:Cross_:1489174755537064046> No Address", description="You don't have a secondary address set. Use `/setaddy2 <address>` in config cog.", color=discord.Color.red()))
        await ctx.invoke(self.bot.get_command("balance"), address=addr)

    @commands.hybrid_command(name="ltcdetail", description="Show raw data for an LTC address (admins only).")
    @commands.has_permissions(administrator=True)
    async def ltcdetail(self, ctx, address: str):
        """Admin helper: show raw JSON returned by blockcypher (truncated)."""
        res = await self._get_balance_from_api(address)
        if res is None:
            return await ctx.send(embed=discord.Embed(title="<a:Cross_:1489174755537064046> Error", description="Failed to fetch address data.", color=discord.Color.red()))
        raw = json.dumps(res["raw"], indent=2)
        # If too long, send as file
        if len(raw) > 1900:
            with open("ltc_raw.json", "w", encoding="utf-8") as f:
                f.write(raw)
            await ctx.send(file=discord.File("ltc_raw.json"))
            os.remove("ltc_raw.json")
        else:
            await ctx.send(f"```json\n{raw}\n```")

    # -------------------------
    # Utility / export
    # -------------------------
    @commands.hybrid_command(name="wallets_export", description="Export wallet.json (admins only).")
    @commands.has_permissions(administrator=True)
    async def wallets_export(self, ctx):
        """Attaches the wallet.json for admins to download."""
        if not os.path.exists(WALLET_FILE):
            return await ctx.send(embed=discord.Embed(title="<a:Cross_:1489174755537064046> Not Found", description="No wallet file exists.", color=discord.Color.red()))
        await ctx.send(file=discord.File(WALLET_FILE))

    @commands.hybrid_command(name="addr", description="Show your saved address (primary).")
    async def addr(self, ctx):
        uid = str(ctx.author.id)
        addr = self.data.get("users", {}).get(uid, {}).get("addy")
        if not addr:
            return await ctx.send(embed=discord.Embed(title="<a:Cross_:1489174755537064046> No Address", description="Primary address not set. Use `/setaddy <address>` in config cog.", color=discord.Color.red()))
        embed = discord.Embed(title="📌 Your Primary LTC Address", description=f"```{addr}```", color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="addr2", description="Show your saved address (secondary).")
    async def addr2(self, ctx):
        uid = str(ctx.author.id)
        addr = self.data.get("users", {}).get(uid, {}).get("addy2")
        if not addr:
            return await ctx.send(embed=discord.Embed(title="<a:Cross_:1489174755537064046> No Address", description="Secondary address not set. Use `/setaddy2 <address>` in config cog.", color=discord.Color.red()))
        embed = discord.Embed(title="📌 Your Secondary LTC Address", description=f"```{addr}```", color=discord.Color.blue())
        await ctx.send(embed=embed)

    # -------------------------
    # Setup
    # -------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Wallet(bot))
