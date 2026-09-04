# cogs/wallet.py
import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import json
import os
import asyncio
import datetime
from typing import Optional
from cogs.utils.emoji_manager import EMOJI
from cogs.utils.json_store import get_store

WALLET_FILE = "wallet.json"
LTC_BALANCE_API = "https://api.blockcypher.com/v1/ltc/main/addrs/"
LTC_PRICE_API = (
    "https://api.coingecko.com/api/v3/simple/price"
    "?ids=litecoin&vs_currencies=usd"
    "&include_24hr_change=true&include_market_cap=true&include_24hr_vol=true&include_last_updated_at=true"
)
LTC_EXPLORER_URL = "https://live.blockcypher.com/ltc/address/{}/"

class Wallet(commands.Cog):
    """Wallet & balance commands (reads/writes wallet.json via a shared store,
    kept in sync with cogs/config.py which also touches this file)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        self._lock = asyncio.Lock()
        self.store = get_store(WALLET_FILE, dict)

    @property
    def data(self) -> dict:
        return self.store.read()

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        if self.session and not self.session.closed:
            self.bot.loop.create_task(self.session.close())

    # -------------------------
    # File helpers (thread-safe, shared across cogs)
    # -------------------------
    async def _save_file(self) -> None:
        async with self._lock:
            self.store.save(self.data)

    # -------------------------
    # Internal helpers
    # -------------------------
    async def _get_ltc_price(self) -> Optional[dict]:
        try:
            async with self.session.get(LTC_PRICE_API, timeout=20) as r:
                if r.status != 200:
                    return None
                j = await r.json()
                data = j.get("litecoin", {})
                if "usd" not in data:
                    return None
                return {
                    "usd": float(data.get("usd", 0)),
                    "usd_24h_change": data.get("usd_24h_change"),
                    "usd_market_cap": data.get("usd_market_cap"),
                    "usd_24h_vol": data.get("usd_24h_vol"),
                    "last_updated_at": data.get("last_updated_at"),
                }
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
            price_info = await self._get_ltc_price()
            if price_info is None:
                usd = None
            else:
                price = price_info["usd"]
                usd = {
                    "total_received": round(total_received * price, 2),
                    "confirmed_balance": round(confirmed_balance * price, 2),
                    "unconfirmed_balance": round(unconfirmed_balance * price, 2),
                }
            return {
                "total_received": total_received,
                "confirmed_balance": confirmed_balance,
                "unconfirmed_balance": unconfirmed_balance,
                "n_tx": j.get("n_tx", 0),
                "unconfirmed_n_tx": j.get("unconfirmed_n_tx", 0),
                "usd": usd,
                "raw": j,
            }
        except Exception:
            return None

    # -------------------------
    # Read-only view commands
    # -------------------------
    @commands.hybrid_command(name="ltc", description="Show current LTC price (USD).")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def ltc(self, ctx):
        price_info = await self._get_ltc_price()
        if price_info is None:
            return await ctx.send(embed=discord.Embed(title=f"{EMOJI['error']} Error", description="Couldn't fetch LTC price right now.", color=discord.Color.red()))

        change = price_info.get("usd_24h_change")
        if change is not None:
            trend_emoji = "📈" if change >= 0 else "📉"
            change_str = f"{trend_emoji} {change:+.2f}%"
            color = discord.Color.green() if change >= 0 else discord.Color.red()
        else:
            change_str = "—"
            color = discord.Color.gold()

        embed = discord.Embed(title=f"{EMOJI['currency']} Litecoin (LTC)", color=color)
        embed.add_field(name="Price (USD)", value=f"**${price_info['usd']:,.2f}**", inline=True)
        embed.add_field(name="24h Change", value=change_str, inline=True)
        if price_info.get("usd_market_cap"):
            embed.add_field(name="Market Cap", value=f"${price_info['usd_market_cap']:,.0f}", inline=True)
        if price_info.get("usd_24h_vol"):
            embed.add_field(name="24h Volume", value=f"${price_info['usd_24h_vol']:,.0f}", inline=True)
        embed.set_footer(text="Data from CoinGecko")
        if price_info.get("last_updated_at"):
            embed.timestamp = datetime.datetime.fromtimestamp(price_info["last_updated_at"], tz=datetime.timezone.utc)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="balance", description="Fetch LTC balance for any LTC address.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def balance(self, ctx, address: str):
        """Generic balance check for any LTC address."""
        await ctx.defer()
        res = await self._get_balance_from_api(address)
        if res is None:
            return await ctx.send(embed=discord.Embed(title=f"{EMOJI['error']} Error", description="Failed to fetch address data. Double-check the address is a valid Litecoin address.", color=discord.Color.red()))

        embed = discord.Embed(title=f"{EMOJI['money']} Litecoin Address", color=discord.Color.green())
        embed.description = f"[`{address}`]({LTC_EXPLORER_URL.format(address)})"

        price_info = res["usd"]
        embed.add_field(
            name="Confirmed Balance",
            value=f"**{res['confirmed_balance']:.8f} LTC**" + (f"\n≈ ${price_info['confirmed_balance']:,.2f}" if price_info else ""),
            inline=True,
        )
        embed.add_field(
            name="Unconfirmed",
            value=f"{res['unconfirmed_balance']:.8f} LTC" + (f"\n≈ ${price_info['unconfirmed_balance']:,.2f}" if price_info else ""),
            inline=True,
        )
        embed.add_field(
            name="Total Received",
            value=f"{res['total_received']:.8f} LTC" + (f"\n≈ ${price_info['total_received']:,.2f}" if price_info else ""),
            inline=True,
        )
        embed.add_field(name="Transactions", value=str(res["n_tx"]), inline=True)
        if res["unconfirmed_n_tx"]:
            embed.add_field(name="Pending Tx", value=str(res["unconfirmed_n_tx"]), inline=True)
        embed.set_footer(text="Balance from BlockCypher • tap the address to view on the explorer")
        await ctx.send(embed=embed)

    @commands.command(name="mybal", description="Show your primary LTC address balance.")
    async def mybal(self, ctx):
        """Shows balance for user's primary saved address."""
        uid = str(ctx.author.id)
        user = self.data.get("users", {}).get(uid, {})
        addr = user.get("addy")
        if not addr:
            return await ctx.send(embed=discord.Embed(title=f"{EMOJI['error']} No Address", description="You don't have a primary address set. Use `/setaddy <address>` in config cog.", color=discord.Color.red()))
        await ctx.invoke(self.bot.get_command("balance"), address=addr)

    @commands.command(name="mybal2", description="Show your secondary LTC address balance.")
    async def mybal2(self, ctx):
        uid = str(ctx.author.id)
        user = self.data.get("users", {}).get(uid, {})
        addr = user.get("addy2")
        if not addr:
            return await ctx.send(embed=discord.Embed(title=f"{EMOJI['error']} No Address", description="You don't have a secondary address set. Use `/setaddy2 <address>` in config cog.", color=discord.Color.red()))
        await ctx.invoke(self.bot.get_command("balance"), address=addr)

    @commands.hybrid_command(name="ltcdetail", description="Show raw data for an LTC address (admins only).")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @commands.has_permissions(administrator=True)
    async def ltcdetail(self, ctx, address: str):
        """Admin helper: show raw JSON returned by blockcypher (truncated)."""
        res = await self._get_balance_from_api(address)
        if res is None:
            return await ctx.send(embed=discord.Embed(title=f"{EMOJI['error']} Error", description="Failed to fetch address data.", color=discord.Color.red()))
        raw = json.dumps(res["raw"], indent=2)
        # If too long, send as file
        if len(raw) > 1900:
            import tempfile
            fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix="ltc_raw_")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(raw)
                await ctx.send(file=discord.File(tmp_path, filename="ltc_raw.json"))
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
        else:
            await ctx.send(f"```json\n{raw}\n```")

    # -------------------------
    # Utility / export
    # -------------------------
    @commands.hybrid_command(name="wallets_export", description="Export wallet.json (admins only).")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @commands.has_permissions(administrator=True)
    async def wallets_export(self, ctx):
        """Attaches the wallet.json for admins to download."""
        if not os.path.exists(WALLET_FILE):
            return await ctx.send(embed=discord.Embed(title=f"{EMOJI['error']} Not Found", description="No wallet file exists.", color=discord.Color.red()))
        await ctx.send(file=discord.File(WALLET_FILE))

    @commands.hybrid_command(name="addr", description="Show your saved address (primary).")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def addr(self, ctx):
        uid = str(ctx.author.id)
        addr = self.data.get("users", {}).get(uid, {}).get("addy")
        if not addr:
            return await ctx.send(embed=discord.Embed(title=f"{EMOJI['error']} No Address", description="Primary address not set. Use `/setaddy <address>` in config cog.", color=discord.Color.red()))
        embed = discord.Embed(title=f"{EMOJI['pin']} Your Primary LTC Address", description=f"```{addr}```", color=discord.Color.blue())
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="addr2", description="Show your saved address (secondary).")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def addr2(self, ctx):
        uid = str(ctx.author.id)
        addr = self.data.get("users", {}).get(uid, {}).get("addy2")
        if not addr:
            return await ctx.send(embed=discord.Embed(title=f"{EMOJI['error']} No Address", description="Secondary address not set. Use `/setaddy2 <address>` in config cog.", color=discord.Color.red()))
        embed = discord.Embed(title=f"{EMOJI['pin']} Your Secondary LTC Address", description=f"```{addr}```", color=discord.Color.blue())
        await ctx.send(embed=embed)

    # -------------------------
    # Setup
    # -------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Wallet(bot))
