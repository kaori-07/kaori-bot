import discord
from discord.ext import commands
from discord import app_commands
import os
import aiohttp
from cogs.utils.emoji_manager import EMOJI

DEFAULT_BASE_URL = "https://api.openai.com/v1"


class AIChat(commands.Cog):
    """General-purpose /ask command backed by any OpenAI-compatible chat completions
    API. Configure via .env: AI_API_KEY (required), AI_API_BASE (optional, defaults
    to OpenAI), AI_MODEL (optional, defaults to gpt-4o-mini). Works with OpenAI,
    Groq, OpenRouter, local llama.cpp servers, etc - anything speaking the same
    /chat/completions shape."""

    def __init__(self, bot):
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    def cog_unload(self):
        if self.session and not self.session.closed:
            self.bot.loop.create_task(self.session.close())

    def _configured(self) -> bool:
        return bool(os.getenv("AI_API_KEY"))

    @commands.hybrid_command(name="ask", description="Ask the AI assistant a question.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @commands.cooldown(1, 8, commands.BucketType.user)
    async def ask(self, ctx: commands.Context, *, question: str):
        if not self._configured():
            return await ctx.send(f"{EMOJI['error']} AI chat isn't configured — set `AI_API_KEY` in `.env` first.")

        try:
            await ctx.defer()
        except discord.HTTPException:
            pass
        api_key = os.getenv("AI_API_KEY")
        base_url = os.getenv("AI_API_BASE", DEFAULT_BASE_URL).rstrip("/")
        model = os.getenv("AI_MODEL", "gpt-4o-mini")

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful, concise Discord bot assistant. Keep answers under 1500 characters."},
                {"role": "user", "content": question},
            ],
            "max_tokens": 500,
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        try:
            async with self.session.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return await ctx.send(f"{EMOJI['error']} AI request failed (HTTP {resp.status}).")
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError):
            return await ctx.send(f"{EMOJI['error']} AI request timed out or failed.")

        try:
            answer = data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError):
            return await ctx.send(f"{EMOJI['error']} Got an unexpected response from the AI API.")

        embed = discord.Embed(title=f"{EMOJI['robot']} AI Answer", description=answer[:4000], color=discord.Color.blurple())
        embed.set_footer(text=f"Asked by {ctx.author.display_name} • {model}")
        await ctx.send(embed=embed)

    @ask.error
    async def ask_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(f"{EMOJI['clock']} Slow down — try again in {error.retry_after:.0f}s.")
        raise error


async def setup(bot):
    await bot.add_cog(AIChat(bot))
