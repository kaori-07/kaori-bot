import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import asyncio
from datetime import datetime, timezone
from cogs.utils.emoji_manager import EMOJI

def _fmt_count(n: int) -> str:
    try:
        n = int(n)
    except Exception:
        return str(n)
    # human readable
    for unit in ['', 'K', 'M', 'B', 'T']:
        if abs(n) < 1000.0:
            return f"{n}{unit}"
        n = int(n/1000)
    return str(n)

def _truncate(text: str, limit: int = 1024) -> str:
    if not text:
        return ""
    text = str(text)
    return text if len(text) <= limit else text[:limit-3] + "..."

class Instagram(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Keep the app id user agent; can be changed if needed
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "x-ig-app-id": "936619743392459",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Accept-Language": "en-US,en;q=0.9"
        }
        self.base_url = "https://www.instagram.com/{username}/"
        self.json_url = "https://www.instagram.com/api/v1/users/web_profile_info/?username={username}"
        self.ban_image = "https://cdn.discordapp.com/attachments/1364845821954359358/1377526511921397842/IMG_5923.jpg?ex=68452689&is=6843d509&hm=e9917cbc9d53d96a84a79ba8930617d647dd68829c977e13047356366964edf9&"

    async def send_ban_embed(self, ctx, username: str):
        embed = discord.Embed(
            title=f"{EMOJI['forbidden']} Banned or Not Found",
            description=f"The ID `{username}` is banned or does not exist on Instagram.",
            color=discord.Color.red()
        )
        embed.set_image(url=self.ban_image)
        embed.set_footer(text="Instagram Check • Bot by Kaori")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="check", description="Look up an Instagram profile by username.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def check(self, ctx, username: str):
        """
        /check <username>
        - If the username isn't found or is banned, reports that.
        - Otherwise fetches and shows as many profile details as possible.
        Note: Instagram actively rate-limits/blocks scraping; if this starts
        failing consistently it likely means Instagram changed or blocked the
        endpoint on their end, not a bug in the bot.
        """
        async with ctx.typing():
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 1) Quick 404 check on the public profile page
                try:
                    base_resp = await session.get(
                        self.base_url.format(username=username),
                        headers=self.headers,
                        allow_redirects=True
                    )
                except asyncio.TimeoutError:
                    return await ctx.send(f"{EMOJI['warning']} Request timed out trying to reach Instagram.")
                except Exception as e:
                    return await ctx.send(f"{EMOJI['warning']} Network error: {e}")

                if base_resp.status == 404:
                    return await self.send_ban_embed(ctx, username)
                if base_resp.status != 200:
                    return await ctx.send(f"{EMOJI['warning']} Could not reach Instagram (HTTP {base_resp.status}).")

                # 2) Fetch the JSON profile info
                try:
                    json_resp = await session.get(
                        self.json_url.format(username=username),
                        headers=self.headers
                    )
                except asyncio.TimeoutError:
                    return await ctx.send(f"{EMOJI['warning']} JSON request timed out.")
                except Exception as e:
                    return await ctx.send(f"{EMOJI['warning']} JSON network error: {e}")

                if json_resp.status == 404:
                    return await self.send_ban_embed(ctx, username)
                if json_resp.status != 200:
                    # Some profiles may block this endpoint or require cookies
                    return await ctx.send(f"{EMOJI['warning']} JSON endpoint returned HTTP {json_resp.status}.")

                try:
                    payload = await json_resp.json()
                except aiohttp.ContentTypeError:
                    return await self.send_ban_embed(ctx, username)
                except Exception as e:
                    return await ctx.send(f"{EMOJI['warning']} Failed parsing JSON: {e}")

                # common places where user object might live
                user = None
                user = payload.get("data", {}).get("user") or payload.get("graphql", {}).get("user") or payload.get("user")
                if not user:
                    # Some responses put user directly under 'data' as a dict
                    if isinstance(payload.get("data"), dict) and "username" in payload.get("data"):
                        user = payload.get("data")
                if not user:
                    return await self.send_ban_embed(ctx, username)

                # safe getters
                def g(k, default=None):
                    return user.get(k, default)

                uid = g("id", "N/A")
                uname = g("username", username)
                fullname = g("full_name") or "N/A"
                bio = g("biography") or ""
                ext_url = g("external_url") or None
                verified = g("is_verified", False)
                private = g("is_private", False)
                is_business = g("is_business_account", False)
                is_prof = g("is_professional_account", False)
                category = g("category_name") or g("business_category_name") or g("category_enum") or None
                connected_fb = g("connected_fb_page") or None
                profile_pic = g("profile_pic_url_hd") or g("profile_pic_url")

                # follower/following/posts counts: handle nested shapes
                def safe_count(obj, *path):
                    curr = obj
                    try:
                        for p in path:
                            curr = curr[p]
                        return curr
                    except Exception:
                        return None

                followers = safe_count(user, "edge_followed_by", "count") or safe_count(user, "edge_followed_by", "count") or safe_count(user, "edge_followed_by", "count") or g("follower_count")
                following = safe_count(user, "edge_follow", "count") or g("following_count")
                posts_count = safe_count(user, "edge_owner_to_timeline_media", "count") or g("media_count") or 0

                # Build the main embed
                embed = discord.Embed(
                    title=f"{EMOJI['camera']} {uname} ({fullname})",
                    url=self.base_url.format(username=uname),
                    description=_truncate(bio, 400) or "No bio.",
                    color=discord.Color.green()
                )
                embed.set_author(name="Instagram Profile", icon_url="https://i.imgur.com/UVzT4eF.png")
                if profile_pic:
                    embed.set_thumbnail(url=profile_pic)

                # Basic fields
                embed.add_field(name=f"{EMOJI['numbers']} ID", value=str(uid), inline=True)
                embed.add_field(name=f"{EMOJI['users']} Followers", value=_fmt_count(followers) if followers is not None else "N/A", inline=True)
                embed.add_field(name=f"{EMOJI['repeat']} Following", value=_fmt_count(following) if following is not None else "N/A", inline=True)
                embed.add_field(name=f"{EMOJI['image']} Posts", value=str(posts_count), inline=True)
                embed.add_field(name=f"{EMOJI['locked']} Private?", value="Yes" if private else "No", inline=True)
                embed.add_field(name=f"{EMOJI['check']} Verified?", value="Yes" if verified else "No", inline=True)
                embed.add_field(name=f"{EMOJI['tag']} Business?", value="Yes" if is_business else ("Yes" if is_prof else "No"), inline=True)
                if category:
                    embed.add_field(name=f"{EMOJI['books']} Category", value=_truncate(str(category), 100), inline=True)

                # External / contact info if present
                if ext_url:
                    embed.add_field(name=f"{EMOJI['link']} External URL", value=_truncate(ext_url, 100), inline=False)

                # Try to show some contact info if available in JSON
                pub_email = g("public_email") or g("public_email_address")
                pub_phone = g("public_phone_number")
                if pub_email:
                    embed.add_field(name=f"{EMOJI['envelope']} Public Email", value=_truncate(pub_email, 100), inline=True)
                if pub_phone:
                    embed.add_field(name=f"{EMOJI['phone']} Public Phone", value=_truncate(pub_phone, 100), inline=True)

                if connected_fb:
                    embed.add_field(name=f"{EMOJI['link']} Connected Facebook", value=_truncate(str(connected_fb), 100), inline=False)

                # Try to include recent posts (up to 4)
                recent = safe_count(user, "edge_owner_to_timeline_media", "edges")
                posts_added = 0
                if recent and isinstance(recent, list):
                    # build a concise list
                    post_lines = []
                    for edge in recent[:4]:
                        node = edge.get("node", {})
                        shortcode = node.get("shortcode")
                        post_url = f"https://www.instagram.com/p/{shortcode}/" if shortcode else None
                        caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
                        caption = caption_edges[0].get("node", {}).get("text", "") if caption_edges else ""
                        caption = _truncate(caption.replace('\n', ' '), 120)
                        likes = node.get("edge_liked_by", {}).get("count") or node.get("edge_media_preview_like", {}).get("count") or node.get("like_count")
                        is_video = node.get("is_video", False)
                        views = node.get("video_view_count")
                        taken_ts = node.get("taken_at_timestamp")
                        date = ""
                        if taken_ts:
                            try:
                                dt = datetime.fromtimestamp(int(taken_ts), tz=timezone.utc)
                                date = dt.strftime("%Y-%m-%d")
                            except Exception:
                                date = ""
                        stats = []
                        if likes is not None:
                            stats.append(f"{EMOJI['heart']} {_fmt_count(likes)}")
                        if is_video and views is not None:
                            stats.append(f"{EMOJI['play_icon']} {_fmt_count(views)} views")
                        info = " • ".join(stats) if stats else ""
                        line = f"{date} • {caption}" if caption else f"{date}"
                        if post_url:
                            line = f"[Post]({post_url}) — {line}"
                        if info:
                            line += f" — {info}"
                        post_lines.append(line)
                        posts_added += 1
                    if post_lines:
                        embed.add_field(name=f"{EMOJI['receipt']} Recent posts ({posts_added})", value="\n".join(post_lines), inline=False)

                # Footer and send
                embed.set_footer(text="Instagram Check • Bot by Kaori")
                await ctx.send(embed=embed)

    @check.error
    async def check_error(self, ctx, error):
        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(f"{EMOJI['clock']} Slow down — try again in {error.retry_after:.0f}s.")
        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send(f"{EMOJI['warning']} Usage: `/check <username>`")
        raise error


async def setup(bot):
    await bot.add_cog(Instagram(bot))
