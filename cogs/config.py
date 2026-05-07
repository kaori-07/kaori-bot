# cogs/config.py
import discord
from discord.ext import commands
import json
import os
import asyncio
from typing import Optional

WALLET_FILE = "wallet.json"

class Config(commands.Cog):
    """Set / remove / view commands for addresses, QR, shop and guild-level settings."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._lock = asyncio.Lock()
        self.data = self._load_file()

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
    # User level setters (wallet addresses)
    # -------------------------
    @commands.hybrid_command(name="setaddy", description="Set your primary LTC address.")
    async def setaddy(self, ctx, address: str):
        uid = str(ctx.author.id)
        users = self.data.setdefault("users", {})
        users.setdefault(uid, {})
        users[uid]["addy"] = address
        await self._save_file()
        await ctx.send(embed=discord.Embed(title="<a:tick:1489157731393994854> Saved", description="Primary address saved.", color=discord.Color.green()))

    @commands.hybrid_command(name="setaddy2", description="Set your secondary LTC address.")
    async def setaddy2(self, ctx, address: str):
        uid = str(ctx.author.id)
        users = self.data.setdefault("users", {})
        users.setdefault(uid, {})
        users[uid]["addy2"] = address
        await self._save_file()
        await ctx.send(embed=discord.Embed(title="<a:tick:1489157731393994854> Saved", description="Secondary address saved.", color=discord.Color.green()))

    @commands.hybrid_command(name="removeaddy", description="Remove your primary address.")
    async def removeaddy(self, ctx):
        uid = str(ctx.author.id)
        user = self.data.get("users", {}).get(uid, {})
        if not user or "addy" not in user:
            return await ctx.send(embed=discord.Embed(title="<a:Cross_:1489174755537064046> Not Found", description="Primary address not found.", color=discord.Color.red()))
        user.pop("addy")
        await self._save_file()
        await ctx.send(embed=discord.Embed(title="<a:tick:1489157731393994854> Removed", description="Primary address removed.", color=discord.Color.green()))

    @commands.hybrid_command(name="removeaddy2", description="Remove your secondary address.")
    async def removeaddy2(self, ctx):
        uid = str(ctx.author.id)
        user = self.data.get("users", {}).get(uid, {})
        if not user or "addy2" not in user:
            return await ctx.send(embed=discord.Embed(title="<a:Cross_:1489174755537064046> Not Found", description="Secondary address not found.", color=discord.Color.red()))
        user.pop("addy2")
        await self._save_file()
        await ctx.send(embed=discord.Embed(title="<a:tick:1489157731393994854> Removed", description="Secondary address removed.", color=discord.Color.green()))

    # -------------------------
    # Guild level setters (QR/shop)
    # -------------------------
    def _ensure_guild(self, guild_id: str) -> dict:
        guilds = self.data.setdefault("guilds", {})
        return guilds.setdefault(guild_id, {})

    @commands.hybrid_command(name="setqr", description="Set the guild's primary QR image URL.")
    @commands.has_permissions(manage_guild=True)
    async def setqr(self, ctx, qr_url: str):
        g = self._ensure_guild(str(ctx.guild.id))
        g["qr"] = qr_url
        await self._save_file()
        await ctx.send(embed=discord.Embed(title="<a:tick:1489157731393994854> QR Set", description="Primary QR set for this server.", color=discord.Color.green()))

    @commands.hybrid_command(name="setqr2", description="Set the guild's secondary QR image URL.")
    @commands.has_permissions(manage_guild=True)
    async def setqr2(self, ctx, qr_url: str):
        g = self._ensure_guild(str(ctx.guild.id))
        g["qr2"] = qr_url
        await self._save_file()
        await ctx.send(embed=discord.Embed(title="<a:tick:1489157731393994854> QR Set", description="Secondary QR set for this server.", color=discord.Color.green()))

    @commands.hybrid_command(name="setshop", description="Set a server-level shop / payment link.")
    @commands.has_permissions(manage_guild=True)
    async def setshop(self, ctx, link: str):
        g = self._ensure_guild(str(ctx.guild.id))
        g["shop"] = link
        await self._save_file()
        await ctx.send(embed=discord.Embed(title="<a:tick:1489157731393994854> Shop Set", description="Shop link saved for this server.", color=discord.Color.green()))

    @commands.hybrid_command(name="showconfig", description="Show this server's configured QR/shop (admins only).")
    @commands.has_permissions(manage_guild=True)
    async def showconfig(self, ctx):
        g = self.data.get("guilds", {}).get(str(ctx.guild.id), {})
        embed = discord.Embed(title=f"⚙️ Server Config for {ctx.guild.name}", color=discord.Color.blurple())
        embed.add_field(name="QR (primary)", value=g.get("qr", "Not set"), inline=False)
        embed.add_field(name="QR (secondary)", value=g.get("qr2", "Not set"), inline=False)
        embed.add_field(name="Shop link", value=g.get("shop", "Not set"), inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="removeqr", description="Remove this server's primary QR.")
    @commands.has_permissions(manage_guild=True)
    async def removeqr(self, ctx):
        g = self.data.get("guilds", {}).get(str(ctx.guild.id), {})
        if not g or "qr" not in g:
            return await ctx.send(embed=discord.Embed(title="<a:Cross_:1489174755537064046> Not Found", description="Primary QR not set.", color=discord.Color.red()))
        g.pop("qr")
        await self._save_file()
        await ctx.send(embed=discord.Embed(title="<a:tick:1489157731393994854> Removed", description="Primary QR removed.", color=discord.Color.green()))

    @commands.hybrid_command(name="qr", description="Send the server primary QR (if set).")
    async def qr(self, ctx):
        g = self.data.get("guilds", {}).get(str(ctx.guild.id), {})
        url = g.get("qr")
        if not url:
            return await ctx.send(embed=discord.Embed(title="<a:Cross_:1489174755537064046> Not Set", description="Server primary QR not set. Admins can use `/setqr <url>`.", color=discord.Color.red()))
        embed = discord.Embed(title="📌 Server QR", color=discord.Color.blue())
        embed.set_image(url=url)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="qr2", description="Send the server secondary QR (if set).")
    async def qr2(self, ctx):
        g = self.data.get("guilds", {}).get(str(ctx.guild.id), {})
        url = g.get("qr2")
        if not url:
            return await ctx.send(embed=discord.Embed(title="<a:Cross_:1489174755537064046> Not Set", description="Server secondary QR not set. Admins can use `/setqr2 <url>`.", color=discord.Color.red()))
        embed = discord.Embed(title="📌 Server QR (secondary)", color=discord.Color.blue())
        embed.set_image(url=url)
        await ctx.send(embed=embed)

    # -------------------------
    # Misc
    # -------------------------
    @commands.hybrid_command(name="whoami_addy", description="Show your saved addresses quickly.")
    async def whoami_addy(self, ctx):
        uid = str(ctx.author.id)
        user = self.data.get("users", {}).get(uid, {})
        addy = user.get("addy", "Not set")
        addy2 = user.get("addy2", "Not set")
        embed = discord.Embed(title="🔎 Your saved addresses", color=discord.Color.blue())
        embed.add_field(name="Primary", value=f"```{addy}```", inline=False)
        embed.add_field(name="Secondary", value=f"```{addy2}```", inline=False)
        await ctx.send(embed=embed)

    # -------------------------
    # Setup
    # -------------------------
async def setup(bot: commands.Bot):
    await bot.add_cog(Config(bot))
