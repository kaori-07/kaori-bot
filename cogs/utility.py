import ast
import asyncio
import operator
import discord
from discord.ext import commands
from discord import app_commands
import psutil
import datetime
import platform
import humanize
import aiohttp
from cogs.utils.emoji_manager import EMOJI
from cogs.utils.json_store import get_store

# --- safe math evaluator (no eval(), no attribute/name access) ---
_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval(expression: str):
    """Evaluate a basic arithmetic expression safely (no names, no calls, no attribute access)."""
    node = ast.parse(expression, mode="eval").body

    def _eval(n):
        if isinstance(n, ast.Constant):
            if isinstance(n.value, (int, float)):
                return n.value
            raise ValueError("Only numbers are allowed.")
        if isinstance(n, ast.BinOp) and type(n.op) in _ALLOWED_OPS:
            left = _eval(n.left)
            right = _eval(n.right)
            if isinstance(n.op, (ast.Pow,)) and (abs(left) > 10_000 or abs(right) > 1000):
                raise ValueError("Expression too large.")
            return _ALLOWED_OPS[type(n.op)](left, right)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _ALLOWED_OPS:
            return _ALLOWED_OPS[type(n.op)](_eval(n.operand))
        raise ValueError("Unsupported expression.")

    return _eval(node)


class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = datetime.datetime.utcnow()
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        if self.session and not self.session.closed:
            self.bot.loop.create_task(self.session.close())

    def get_uptime(self):
        """Calculate bot uptime."""
        now = datetime.datetime.utcnow()
        delta = now - self.start_time
        return humanize.naturaldelta(delta)

    # Ping command
    @commands.hybrid_command(name="ping", description="Check the bot's latency.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def ping(self, ctx: commands.Context):
        latency = round(self.bot.latency * 1000)
        embed = discord.Embed(title=f"{EMOJI['ping']} Pong!", description=f"Latency: **{latency}ms**", color=discord.Color.green())
        await ctx.send(embed=embed)

    # Uptime command
    @commands.command(name="uptime", description="Check how long the bot has been online.")
    async def uptime(self, ctx: commands.Context):
        embed = discord.Embed(title=f"{EMOJI['clock']} Bot Uptime", description=f"Bot has been online for **{self.get_uptime()}**.", color=discord.Color.blue())
        await ctx.send(embed=embed)

    # Server info command
    @commands.hybrid_command(name="serverinfo", description="Get details about the current server.")
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def serverinfo(self, ctx: commands.Context):
        guild = ctx.guild
        embed = discord.Embed(title=f"{EMOJI['stats']} Server Info", color=discord.Color.blue())
        embed.add_field(name="Server Name", value=guild.name, inline=True)
        embed.add_field(name="Server ID", value=guild.id, inline=True)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Created On", value=guild.created_at.strftime("%b %d, %Y"), inline=True)
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        await ctx.send(embed=embed)

    # User info command
    @commands.hybrid_command(name="userinfo", description="Get information about a user.")
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def userinfo(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        embed = discord.Embed(title=f"{EMOJI['user']} {member.name}'s Info", color=discord.Color.blue())
        embed.add_field(name="Username", value=member.name, inline=True)
        embed.add_field(name="User ID", value=member.id, inline=True)
        embed.add_field(name="Joined Server", value=member.joined_at.strftime("%b %d, %Y") if member.joined_at else "N/A", inline=True)
        embed.add_field(name="Account Created", value=member.created_at.strftime("%b %d, %Y"), inline=True)
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    # Bot info command
    @commands.command(name="botinfo", description="Get information about the bot.")
    async def botinfo(self, ctx: commands.Context):
        embed = discord.Embed(title=f"{EMOJI['robot']} Bot Info", description="Here is some information about the bot.", color=discord.Color.green())
        embed.add_field(name="Bot Name", value=self.bot.user.name, inline=True)
        embed.add_field(name="Bot ID", value=self.bot.user.id, inline=True)
        embed.add_field(name="Python Version", value=platform.python_version(), inline=True)
        embed.add_field(name="Discord.py Version", value=discord.__version__, inline=True)
        embed.add_field(name="Uptime", value=self.get_uptime(), inline=True)
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await ctx.send(embed=embed)

    # Calculator command
    @commands.hybrid_command(name="calc", description="Evaluate a mathematical expression.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def calc(self, ctx: commands.Context, *, expression: str):
        """Evaluates a math expression."""
        try:
            result = safe_eval(expression)
            embed = discord.Embed(title=f"{EMOJI['abacus']} Calculator", color=discord.Color.green())
            embed.add_field(name=f"{EMOJI['inbox']} Expression", value=f"`{expression}`", inline=False)
            embed.add_field(name=f"{EMOJI['outbox']} Result", value=f"`{result}`", inline=False)
            embed.set_footer(text="Safe arithmetic evaluator — no code execution")
            await ctx.send(embed=embed)
        except ZeroDivisionError:
            await ctx.send(f"{EMOJI['error']} Cannot divide by zero.")
        except Exception:
            await ctx.send(f"{EMOJI['error']} Invalid mathematical expression. Only numbers and `+ - * / // % **` are allowed.")

    # System stats command
    @commands.command(name="sysinfo", description="Get system resource usage.")
    async def sysinfo(self, ctx: commands.Context):
        cpu_usage = psutil.cpu_percent(interval=1)
        ram_usage = psutil.virtual_memory().percent
        embed = discord.Embed(title=f"{EMOJI['computer']} System Info", color=discord.Color.purple())
        embed.add_field(name="CPU Usage", value=f"{cpu_usage}%", inline=True)
        embed.add_field(name="RAM Usage", value=f"{ram_usage}%", inline=True)
        await ctx.send(embed=embed)

    # Avatar command
    @commands.command(name="avatar", description="Get a user's avatar.")
    async def avatar(self, ctx: commands.Context, user: discord.User = None):
        user = user or ctx.author
        embed = discord.Embed(title=f"{EMOJI['image']} {user.name}'s Avatar", color=discord.Color.blue())
        embed.set_image(url=user.display_avatar.url)
        await ctx.send(embed=embed)

    # Invite command
    @commands.command(name="invite", description="Get the bot's invite link.")
    async def invite(self, ctx: commands.Context):
        embed = discord.Embed(title=f"{EMOJI['link']} Bot Invite", description="Click the link below to invite the bot.", color=discord.Color.green())
        embed.add_field(name="Invite Link", value=f"[Click Here](https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&permissions=8&scope=bot+applications.commands)", inline=False)
        await ctx.send(embed=embed)

    # ---------------- timezone ----------------
    @commands.hybrid_command(name="settimezone", description="Set your timezone (IANA name, e.g. America/New_York).")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def settimezone(self, ctx: commands.Context, tz_name: str):
        import zoneinfo
        try:
            zoneinfo.ZoneInfo(tz_name)
        except Exception:
            return await ctx.send(f"{EMOJI['error']} Unknown timezone. Use an IANA name like `America/New_York`, `Europe/London`, or `Asia/Kolkata`.")

        store = get_store("timezones.json", dict)

        def _mut(data):
            data[str(ctx.author.id)] = tz_name
            return data
        store.mutate(_mut)
        await ctx.send(f"{EMOJI['success']} Timezone set to **{tz_name}**.")

    @commands.command(name="time", description="See what time it is for a user.")
    async def time_cmd(self, ctx: commands.Context, user: discord.User = None):
        import zoneinfo
        user = user or ctx.author
        store = get_store("timezones.json", dict)
        tz_name = store.read().get(str(user.id))
        if not tz_name:
            return await ctx.send(f"{EMOJI['error']} {user.mention} hasn't set a timezone. Use `/settimezone` first.")

        now = datetime.datetime.now(zoneinfo.ZoneInfo(tz_name))
        embed = discord.Embed(title=f"{EMOJI['clock']} {user.name}'s Local Time", description=f"**{now.strftime('%A, %B %d — %I:%M %p')}**\n{tz_name}", color=discord.Color.blue())
        await ctx.send(embed=embed)

    # ---------------- QR code / URL shortener ----------------
    @commands.command(name="qrcode", description="Generate a QR code for any text or URL.")
    async def qrcode(self, ctx: commands.Context, *, content: str):
        import urllib.parse
        encoded = urllib.parse.quote(content)
        url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={encoded}"
        embed = discord.Embed(title=f"{EMOJI['image']} QR Code", color=discord.Color.dark_grey())
        embed.set_image(url=url)
        embed.set_footer(text=content[:100])
        await ctx.send(embed=embed)

    @commands.command(name="shorten", description="Shorten a long URL.")
    async def shorten(self, ctx: commands.Context, url: str):
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            async with self.session.get("https://is.gd/create.php", params={"format": "simple", "url": url}) as resp:
                short = (await resp.text()).strip()
        except aiohttp.ClientError:
            return await ctx.send(f"{EMOJI['error']} The URL shortener service is unavailable right now.")

        if not short.startswith("http"):
            return await ctx.send(f"{EMOJI['error']} Couldn't shorten that URL: {short}")
        await ctx.send(f"{EMOJI['link']} {short}")

    # ---------------- unit conversion ----------------
    UNIT_CONVERSIONS = {
        ("km", "mi"): 0.621371, ("mi", "km"): 1.60934,
        ("kg", "lb"): 2.20462, ("lb", "kg"): 0.453592,
        ("c", "f"): None, ("f", "c"): None,  # handled specially
        ("m", "ft"): 3.28084, ("ft", "m"): 0.3048,
    }

    @commands.command(name="convert", description="Convert between units — e.g. /convert 10 km mi")
    async def convert(self, ctx: commands.Context, amount: float, from_unit: str, to_unit: str):
        from_unit, to_unit = from_unit.lower(), to_unit.lower()

        if {from_unit, to_unit} == {"c", "f"}:
            result = (amount * 9 / 5) + 32 if from_unit == "c" else (amount - 32) * 5 / 9
        else:
            factor = self.UNIT_CONVERSIONS.get((from_unit, to_unit))
            if factor is None:
                supported = ", ".join(f"{a}→{b}" for a, b in self.UNIT_CONVERSIONS if self.UNIT_CONVERSIONS[(a, b)] is not None) + ", c↔f"
                return await ctx.send(f"{EMOJI['error']} Unsupported conversion. Supported: {supported}")
            result = amount * factor

        embed = discord.Embed(title=f"{EMOJI['abacus']} Unit Conversion", description=f"**{amount} {from_unit}** = **{result:.4f} {to_unit}**", color=discord.Color.teal())
        await ctx.send(embed=embed)

    # ---------------- sticky messages ----------------
    @commands.command(name="sticky_set", description="Pin a message that reposts itself after new activity.")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def sticky_set(self, ctx: commands.Context, *, content: str):
        store = get_store("stickies.json", dict)

        def _mut(data):
            data[str(ctx.channel.id)] = {"content": content, "last_message_id": None}
            return data
        store.mutate(_mut)

        msg = await ctx.send(content)

        def _set_msg_id(data):
            data[str(ctx.channel.id)]["last_message_id"] = msg.id
            return data
        store.mutate(_set_msg_id)
        await ctx.send(f"{EMOJI['success']} Sticky message set in this channel.", delete_after=4)

    @commands.command(name="sticky_remove", description="Remove the sticky message from this channel.")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def sticky_remove(self, ctx: commands.Context):
        store = get_store("stickies.json", dict)

        def _mut(data):
            data.pop(str(ctx.channel.id), None)
            return data
        store.mutate(_mut)
        await ctx.send(f"{EMOJI['success']} Sticky message removed.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        store = get_store("stickies.json", dict)
        data = store.read()
        entry = data.get(str(message.channel.id))
        if not entry:
            return

        if entry.get("last_message_id"):
            try:
                old = await message.channel.fetch_message(entry["last_message_id"])
                await old.delete()
            except discord.HTTPException:
                pass

        try:
            new_msg = await message.channel.send(entry["content"])

            def _set_msg_id(data):
                data.setdefault(str(message.channel.id), entry)["last_message_id"] = new_msg.id
                return data
            store.mutate(_set_msg_id)
        except discord.HTTPException:
            pass

    # ---------------- message export ----------------
    @commands.command(name="export_history", description="Export recent channel messages to a text file.")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def export_history(self, ctx: commands.Context, limit: int = 100):
        limit = max(1, min(limit, 1000))
        import io
        lines = []
        async for msg in ctx.channel.history(limit=limit, oldest_first=False):
            ts = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
            lines.append(f"[{ts}] {msg.author}: {msg.content}")
        lines.reverse()

        buf = io.BytesIO("\n".join(lines).encode("utf-8"))
        await ctx.send(
            content=f"{EMOJI['scroll']} Exported **{len(lines)}** message(s) from {ctx.channel.mention}.",
            file=discord.File(buf, filename=f"{ctx.channel.name}_history.txt"),
        )

    # ---------------- web search / currency (free, keyless APIs) ----------------
    @commands.command(name="search", aliases=['websearch'])
    async def search_cmd(self, ctx: commands.Context, *, query: str):
        """Quick web search using DuckDuckGo's free instant-answer API."""
        try:
            async with self.session.get("https://api.duckduckgo.com/", params={"q": query, "format": "json", "no_html": 1}) as resp:
                if resp.status != 200:
                    return await ctx.send(f"{EMOJI['error']} Search failed.")
                data = await resp.json()
        except aiohttp.ClientError:
            return await ctx.send(f"{EMOJI['error']} Search service unavailable right now.")

        abstract = data.get("AbstractText") or ""
        related = data.get("RelatedTopics") or []
        if not abstract and not related:
            return await ctx.send(f"{EMOJI['info']} No instant answer found for `{query}` — try rephrasing.")

        embed = discord.Embed(title=f"{EMOJI['search']} {query}", color=discord.Color.blurple())
        if abstract:
            embed.description = abstract[:2000]
            if data.get("AbstractURL"):
                embed.url = data["AbstractURL"]
        if not abstract and related:
            lines = [t.get("Text", "") for t in related[:5] if isinstance(t, dict) and t.get("Text")]
            embed.description = "\n".join(f"• {l}" for l in lines)[:2000]
        await ctx.send(embed=embed)

    @commands.command(name="fx", aliases=['currency'])
    async def fx_cmd(self, ctx: commands.Context, amount: float, from_currency: str, to_currency: str):
        """Convert between fiat currencies (free, keyless exchange rate API)."""
        from_currency, to_currency = from_currency.upper(), to_currency.upper()
        try:
            async with self.session.get(f"https://open.er-api.com/v6/latest/{from_currency}") as resp:
                if resp.status != 200:
                    return await ctx.send(f"{EMOJI['error']} Couldn't fetch exchange rates.")
                data = await resp.json()
        except aiohttp.ClientError:
            return await ctx.send(f"{EMOJI['error']} Exchange rate service unavailable right now.")

        rates = data.get("rates", {})
        if to_currency not in rates:
            return await ctx.send(f"{EMOJI['error']} Unknown currency code `{to_currency}`.")
        result = amount * rates[to_currency]
        embed = discord.Embed(title=f"{EMOJI['currency']} Currency Conversion", description=f"**{amount:,.2f} {from_currency}** = **{result:,.2f} {to_currency}**", color=discord.Color.teal())
        await ctx.send(embed=embed)

    # ---------------- dev tools ----------------
    @commands.command(name="genpassword", aliases=['genpass'])
    async def genpassword(self, ctx: commands.Context, length: int = 16):
        """Generate a random secure password."""
        import secrets as _secrets
        import string as _string
        length = max(8, min(length, 64))
        alphabet = _string.ascii_letters + _string.digits + "!@#$%^&*()-_=+"
        pw = "".join(_secrets.choice(alphabet) for _ in range(length))
        try:
            await ctx.author.send(f"{EMOJI['locked']} Your generated password (**{length}** chars):\n`{pw}`")
            await ctx.send(f"{EMOJI['success']} Sent your password via DM.")
        except discord.Forbidden:
            await ctx.send(f"{EMOJI['error']} I couldn't DM you — enable DMs from server members and try again.")

    @commands.command(name="hash")
    async def hash_cmd(self, ctx: commands.Context, algorithm: str, *, text: str):
        """Hash text using md5, sha1, or sha256."""
        import hashlib
        algorithm = algorithm.lower()
        if algorithm not in ("md5", "sha1", "sha256"):
            return await ctx.send(f"{EMOJI['error']} Supported algorithms: `md5`, `sha1`, `sha256`.")
        digest = hashlib.new(algorithm, text.encode("utf-8")).hexdigest()
        await ctx.send(f"{EMOJI['success']} `{algorithm}`: `{digest}`")

    @commands.command(name="base64")
    async def base64_cmd(self, ctx: commands.Context, mode: str, *, text: str):
        """Encode or decode base64 text — mode is 'encode' or 'decode'."""
        import base64 as _b64
        mode = mode.lower()
        try:
            if mode == "encode":
                result = _b64.b64encode(text.encode("utf-8")).decode("utf-8")
            elif mode == "decode":
                result = _b64.b64decode(text.encode("utf-8")).decode("utf-8", errors="replace")
            else:
                return await ctx.send(f"{EMOJI['error']} Mode must be `encode` or `decode`.")
        except Exception:
            return await ctx.send(f"{EMOJI['error']} Couldn't process that — check your input.")
        await ctx.send(f"```{result[:1900]}```")

    @commands.command(name="jsonformat", aliases=['jsonfmt'])
    async def jsonformat(self, ctx: commands.Context, *, raw: str):
        """Pretty-print and validate JSON."""
        import json as _json
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1])
        try:
            parsed = _json.loads(raw)
        except _json.JSONDecodeError as e:
            return await ctx.send(f"{EMOJI['error']} Invalid JSON:\n```\n{e}\n```")
        pretty = _json.dumps(parsed, indent=2)
        if len(pretty) > 1900:
            buf = io.BytesIO(pretty.encode("utf-8"))
            return await ctx.send(f"{EMOJI['success']} Valid JSON (too long to display inline):", file=discord.File(buf, filename="formatted.json"))
        await ctx.send(f"{EMOJI['success']} Valid JSON:\n```json\n{pretty}\n```")

    @commands.command(name="regextest")
    async def regextest(self, ctx: commands.Context, pattern: str, *, text: str):
        """Test a regex pattern against text and show all matches."""
        import re as _re
        try:
            matches = _re.findall(pattern, text)
        except _re.error as e:
            return await ctx.send(f"{EMOJI['error']} Invalid regex: {e}")
        if not matches:
            return await ctx.send(f"{EMOJI['info']} No matches found.")
        preview = "\n".join(f"• `{m}`" for m in matches[:20])
        await ctx.send(f"{EMOJI['success']} **{len(matches)}** match(es):\n{preview}")

    @commands.command(name="colorpreview", aliases=['color'])
    async def colorpreview(self, ctx: commands.Context, hex_color: str):
        """Preview a hex color as a solid embed swatch."""
        hex_color = hex_color.lstrip("#")
        try:
            color_val = int(hex_color, 16)
        except ValueError:
            return await ctx.send(f"{EMOJI['error']} Invalid hex color — use format like `FF5733`.")
        r, g, b = (color_val >> 16) & 255, (color_val >> 8) & 255, color_val & 255
        embed = discord.Embed(title=f"#{hex_color.upper()}", description=f"RGB: `{r}, {g}, {b}`", color=color_val)
        embed.set_thumbnail(url=f"https://singlecolorimage.com/get/{hex_color}/200x200")
        await ctx.send(embed=embed)

    @commands.command(name="asciiart", aliases=['ascii'])
    async def asciiart(self, ctx: commands.Context, *, text: str):
        """Convert short text into large ASCII-style block letters using a free API."""
        text = text[:20]
        try:
            async with self.session.get("https://artii.herokuapp.com/make", params={"text": text}) as resp:
                if resp.status != 200:
                    return await ctx.send(f"{EMOJI['error']} ASCII art service unavailable right now.")
                art = await resp.text()
        except aiohttp.ClientError:
            return await ctx.send(f"{EMOJI['error']} ASCII art service unavailable right now.")
        await ctx.send(f"```\n{art[:1900]}\n```")

    @commands.command(name="mocktext", aliases=['spongebob'])
    async def mocktext(self, ctx: commands.Context, *, text: str):
        """Convert text to sPoNgEbOb MoCk CaSe."""
        result = "".join(c.upper() if i % 2 == 0 else c.lower() for i, c in enumerate(text))
        await ctx.send(result)

    @commands.command(name="countdown")
    async def countdown(self, ctx: commands.Context, seconds: int, *, label: str = "Countdown"):
        """Post a live-updating countdown timer."""
        seconds = max(1, min(seconds, 600))
        embed = discord.Embed(title=f"{EMOJI['clock']} {label}", description=f"**{seconds}s** remaining...", color=discord.Color.orange())
        msg = await ctx.send(embed=embed)
        for remaining in range(seconds - 1, -1, -1):
            await asyncio.sleep(1)
            if remaining % 5 == 0 or remaining < 5:
                embed.description = f"**{remaining}s** remaining..." if remaining > 0 else f"{EMOJI['success']} Time's up!"
                try:
                    await msg.edit(embed=embed)
                except discord.HTTPException:
                    return


async def setup(bot):
    await bot.add_cog(Utility(bot))
