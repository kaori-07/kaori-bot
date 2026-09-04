import discord
from discord.ext import commands, tasks
from discord import app_commands
import os
import aiohttp
import re
from cogs.utils.emoji_manager import EMOJI
from cogs.utils.json_store import get_store

STORE_FILE = "social_feeds.json"
YT_RSS = "https://www.youtube.com/feeds/videos.xml?channel_id={}"


class SocialFeeds(commands.Cog):
    """Polls YouTube's public RSS feed (no API key needed) for new uploads and
    posts a notification. Twitch live-notifications are supported too if
    TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET are set in .env; otherwise that
    half quietly no-ops instead of crashing."""

    def __init__(self, bot):
        self.bot = bot
        self.store = get_store(STORE_FILE, dict)
        self.session: aiohttp.ClientSession | None = None
        self._twitch_token: str | None = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession()
        self.poll_youtube.start()
        if os.getenv("TWITCH_CLIENT_ID") and os.getenv("TWITCH_CLIENT_SECRET"):
            self.poll_twitch.start()

    def cog_unload(self):
        self.poll_youtube.cancel()
        if self.poll_twitch.is_running():
            self.poll_twitch.cancel()
        if self.session and not self.session.closed:
            self.bot.loop.create_task(self.session.close())

    @commands.hybrid_command(name="feed_addyoutube", description="Get notified in this channel when a YouTube channel uploads.")
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def feed_addyoutube(self, ctx: commands.Context, youtube_channel_id: str, channel: discord.TextChannel = None):
        channel = channel or ctx.channel

        def _mut(data):
            entry = data.setdefault(str(ctx.guild.id), {"youtube": [], "twitch": []})
            entry["youtube"].append({"channel_id": youtube_channel_id, "post_channel_id": channel.id, "last_video_id": None})
            return data
        self.store.mutate(_mut)
        await ctx.send(f"{EMOJI['success']} Will post new uploads from that YouTube channel to {channel.mention}.")

    @commands.command(name="feed_addtwitch", description="Get notified in this channel when a Twitch streamer goes live.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def feed_addtwitch(self, ctx: commands.Context, twitch_username: str, channel: discord.TextChannel = None):
        if not (os.getenv("TWITCH_CLIENT_ID") and os.getenv("TWITCH_CLIENT_SECRET")):
            return await ctx.send(f"{EMOJI['error']} Twitch notifications need TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET set in .env first.")
        channel = channel or ctx.channel

        def _mut(data):
            entry = data.setdefault(str(ctx.guild.id), {"youtube": [], "twitch": []})
            entry["twitch"].append({"username": twitch_username.lower(), "post_channel_id": channel.id, "was_live": False})
            return data
        self.store.mutate(_mut)
        await ctx.send(f"{EMOJI['success']} Will post when **{twitch_username}** goes live in {channel.mention}.")

    # ---------------- YouTube polling (RSS, no API key) ----------------
    @tasks.loop(minutes=10)
    async def poll_youtube(self):
        data = self.store.read()
        changed = False
        for guild_id, entry in data.items():
            for feed in entry.get("youtube", []):
                try:
                    url = YT_RSS.format(feed["channel_id"])
                    async with self.session.get(url) as resp:
                        if resp.status != 200:
                            continue
                        xml = await resp.text()
                except aiohttp.ClientError:
                    continue

                m = re.search(r"<yt:videoId>([^<]+)</yt:videoId>", xml)
                title_m = re.search(r"<title>([^<]+)</title>", xml.split("<entry>", 1)[-1]) if "<entry>" in xml else None
                if not m:
                    continue
                video_id = m.group(1)
                if feed.get("last_video_id") == video_id:
                    continue

                is_first_check = feed.get("last_video_id") is None
                feed["last_video_id"] = video_id
                changed = True
                if is_first_check:
                    continue  # don't spam on first setup, just record the baseline

                guild = self.bot.get_guild(int(guild_id))
                post_channel = guild.get_channel(feed["post_channel_id"]) if guild else None
                if post_channel:
                    title = title_m.group(1) if title_m else "New video"
                    try:
                        await post_channel.send(f"{EMOJI['camera']} New upload: **{title}**\nhttps://youtu.be/{video_id}")
                    except discord.HTTPException:
                        pass
        if changed:
            self.store.save(data)

    @poll_youtube.before_loop
    async def before_yt(self):
        await self.bot.wait_until_ready()

    # ---------------- Twitch polling (optional) ----------------
    async def _twitch_headers(self) -> dict | None:
        client_id = os.getenv("TWITCH_CLIENT_ID")
        client_secret = os.getenv("TWITCH_CLIENT_SECRET")
        if not client_id or not client_secret:
            return None
        if not self._twitch_token:
            try:
                async with self.session.post(
                    "https://id.twitch.tv/oauth2/token",
                    params={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
                ) as resp:
                    if resp.status != 200:
                        return None
                    payload = await resp.json()
                    self._twitch_token = payload.get("access_token")
            except aiohttp.ClientError:
                return None
        if not self._twitch_token:
            return None
        return {"Client-ID": client_id, "Authorization": f"Bearer {self._twitch_token}"}

    @tasks.loop(minutes=5)
    async def poll_twitch(self):
        headers = await self._twitch_headers()
        if not headers:
            return

        data = self.store.read()
        changed = False
        for guild_id, entry in data.items():
            for feed in entry.get("twitch", []):
                try:
                    async with self.session.get(
                        "https://api.twitch.tv/helix/streams",
                        params={"user_login": feed["username"]},
                        headers=headers,
                    ) as resp:
                        if resp.status != 200:
                            continue
                        payload = await resp.json()
                except aiohttp.ClientError:
                    continue

                is_live = bool(payload.get("data"))
                if is_live and not feed.get("was_live"):
                    feed["was_live"] = True
                    changed = True
                    guild = self.bot.get_guild(int(guild_id))
                    post_channel = guild.get_channel(feed["post_channel_id"]) if guild else None
                    if post_channel:
                        stream = payload["data"][0]
                        try:
                            await post_channel.send(
                                f"{EMOJI['presence']} **{feed['username']}** is live: {stream.get('title', '')}\n"
                                f"https://twitch.tv/{feed['username']}"
                            )
                        except discord.HTTPException:
                            pass
                elif not is_live and feed.get("was_live"):
                    feed["was_live"] = False
                    changed = True
        if changed:
            self.store.save(data)

    @poll_twitch.before_loop
    async def before_twitch(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(SocialFeeds(bot))
