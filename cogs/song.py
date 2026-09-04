# cogs/song.py
from __future__ import annotations

import asyncio
import functools
import json
import logging
import os
import random
import re
import time
from typing import Dict, Optional, Union

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button, Modal, TextInput
from cogs.utils.emoji_manager import EMOJI

log = logging.getLogger("song_cog")
log.setLevel(logging.INFO)

# ---------- Configuration ----------
FFMPEG_PATH: Optional[str] = None  # set to full ffmpeg executable if not on PATH
FFMPEG_BEFORE = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
FFMPEG_OPTIONS = {"before_options": FFMPEG_BEFORE, "options": "-vn"}
SPOTIFY_PLAYLIST_LIMIT = 200  # max tracks to fetch from spotify playlist (0 = no cap)
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(_DATA_DIR, exist_ok=True)
PANEL_STORE = os.path.join(_DATA_DIR, "music_panels.json")
PANEL_PROGRESS_UPDATE_INTERVAL = 5.0  # seconds
PANEL_INACTIVITY_SECONDS = 300  # 5 minutes inactivity -> auto-delete panel

# Spotify credentials: prefer env vars; fallback to provided values
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID") or "b5f6a50f99df4fa28df0b57500915384"
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET") or "99c6696d6b7c4aae879f4424ba021e7b"

# ---------- Try imports ----------
try:
    import yt_dlp as youtube_dl  # preferred
except Exception:
    try:
        import youtube_dl
    except Exception:
        youtube_dl = None

try:
    from youtubesearchpython import VideosSearch
except Exception:
    VideosSearch = None

# spotipy optional
try:
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
except Exception:
    spotipy = None

# ---------- YTDL defaults ----------
YTDL_BASE_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "cachedir": False,
}


def _cookie_candidates() -> list:
    """Find cookie files for yt-dlp to authenticate as a logged-in browser
    session with. Many VPS/cloud IPs get aggressively rate-limited or
    outright blocked by YouTube when extracting anonymously, so a valid
    cookies.txt (exported from a real browser session, Netscape format)
    makes playback far more reliable. Supports cookie.txt, cookie1.txt,
    cookie2.txt, cookie3.txt... checked in that order, in either
    data/cookies/ (preferred) or the project root (for convenience)."""
    names = ["cookie.txt", "cookie1.txt", "cookie2.txt", "cookie3.txt", "cookie4.txt"]
    search_dirs = [
        os.path.join(_DATA_DIR, "cookies"),
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # project root
    ]
    found = []
    for d in search_dirs:
        for name in names:
            path = os.path.join(d, name)
            if os.path.isfile(path) and path not in found:
                found.append(path)
    return found


def _make_ytdl(extra: Optional[dict] = None):
    if youtube_dl is None:
        raise RuntimeError("yt-dlp / youtube_dl is not installed.")
    opts = dict(YTDL_BASE_OPTS)
    if extra:
        opts.update(extra)
    return youtube_dl.YoutubeDL(opts)


def _select_best_audio_url(info: dict) -> Optional[str]:
    if info.get("url") and not info.get("formats"):
        return info["url"]

    formats = info.get("formats") or []
    candidates = []
    for f in formats:
        url = f.get("url") or f.get("src")
        if not url:
            continue
        acodec = f.get("acodec")
        if acodec and acodec != "none":
            candidates.append(f)
        else:
            candidates.append(f)
    if not candidates:
        return None

    def score(fmt):
        abr = fmt.get("abr") or 0
        tbr = fmt.get("tbr") or 0
        return (abr, tbr)

    best = sorted(candidates, key=score, reverse=True)[0]
    return best.get("url") or best.get("src")


async def _extract_info_with_retry(loop, ytdl, target: str) -> Optional[dict]:
    """Tries the primary ytdl instance first, then a series of fallbacks:
    a plain web-client extractor, then each available cookie file (with and
    without the web-client override) - so if cookie.txt is expired/invalid,
    cookie1.txt gets tried next, then cookie2.txt, and so on, before giving up."""

    def has_playable(i):
        if not i:
            return False
        if "entries" in i:
            entries = i.get("entries") or []
            if not entries:
                return False
            i = entries[0]
        return _select_best_audio_url(i) is not None or bool(i.get("url"))

    # (label, lazy factory) - factories only run if we actually need that attempt
    attempts = [("primary", lambda: ytdl), ("web-client", lambda: _make_ytdl({"extractor_args": {"youtube": {"player_client": "web"}}}))]
    for path in _cookie_candidates():
        label = os.path.basename(path)
        attempts.append((f"cookie:{label}", lambda p=path: _make_ytdl({"cookiefile": p})))
        attempts.append((f"cookie:{label}+web-client", lambda p=path: _make_ytdl({"cookiefile": p, "extractor_args": {"youtube": {"player_client": "web"}}})))

    last_info = None
    for label, factory in attempts:
        try:
            attempt_ytdl = factory()
            extract = functools.partial(attempt_ytdl.extract_info, target, download=False)
            info = await loop.run_in_executor(None, extract)
        except Exception as e:
            log.debug("Extraction attempt '%s' failed: %s", label, e)
            info = None

        if has_playable(info):
            if label != "primary":
                log.info("Playback resolved via fallback: %s", label)
            return info
        last_info = info or last_info

    return last_info


# ---------- UI ----------
class PlayModal(Modal):
    def __init__(self, cog: "MusicCog"):
        super().__init__(title="Play a song")
        self.cog = cog
        self.query = TextInput(label="Search or URL", placeholder="YouTube link or search terms", required=True)
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await self.cog.add_and_play(interaction, self.query.value)


class MusicPanel(View):
    def __init__(self, cog: "MusicCog", guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    def _touch(self):
        try:
            self.cog.touch_panel(self.guild_id)
        except Exception:
            pass

    @discord.ui.button(label="Play", style=discord.ButtonStyle.primary, emoji="▶️")
    async def play_button(self, inter: discord.Interaction, btn: Button):
        self._touch()
        await inter.response.send_modal(PlayModal(self.cog))

    @discord.ui.button(label="⏯", style=discord.ButtonStyle.secondary)
    async def pause_resume(self, inter: discord.Interaction, btn: Button):
        self._touch()
        player = self.cog.players.get(self.guild_id)
        if not player or not player.get("voice_client"):
            return await inter.response.send_message("Not connected.", ephemeral=True)
        vc = player["voice_client"]
        if vc.is_paused():
            vc.resume()
            return await inter.response.send_message("Resumed.", ephemeral=True)
        if vc.is_playing():
            vc.pause()
            return await inter.response.send_message("Paused.", ephemeral=True)
        return await inter.response.send_message("Nothing is playing.", ephemeral=True)

    @discord.ui.button(label="⏭", style=discord.ButtonStyle.secondary)
    async def skip(self, inter: discord.Interaction, btn: Button):
        self._touch()
        player = self.cog.players.get(self.guild_id)
        if player and player.get("voice_client"):
            vc = player["voice_client"]
            if vc.is_playing() or vc.is_paused():
                vc.stop()
                return await inter.response.send_message("Skipped.", ephemeral=True)
        return await inter.response.send_message("Nothing to skip.", ephemeral=True)

    @discord.ui.button(label="⏹", style=discord.ButtonStyle.danger)
    async def stop(self, inter: discord.Interaction, btn: Button):
        self._touch()
        player = self.cog.players.get(self.guild_id)
        if player and player.get("voice_client"):
            vc = player["voice_client"]
            vc.stop()
            player["queue"].clear()
            return await inter.response.send_message("Stopped & cleared queue.", ephemeral=True)
        return await inter.response.send_message("Not connected.", ephemeral=True)

    @discord.ui.button(label="Shuffle", style=discord.ButtonStyle.secondary)
    async def shuffle_btn(self, inter: discord.Interaction, btn: Button):
        self._touch()
        player = self.cog.players.get(self.guild_id)
        if not player:
            return await inter.response.send_message("No player.", ephemeral=True)
        q = player.get("queue", [])
        random.shuffle(q)
        player["queue"] = q
        return await inter.response.send_message("Shuffled the queue.", ephemeral=True)

    @discord.ui.button(label="Repeat", style=discord.ButtonStyle.secondary)
    async def repeat_btn(self, inter: discord.Interaction, btn: Button):
        self._touch()
        player = self.cog.players.get(self.guild_id)
        if not player:
            return await inter.response.send_message("No player.", ephemeral=True)
        mode = player.get("repeat", "off")
        if mode == "off":
            mode = "all"
        elif mode == "all":
            mode = "single"
        else:
            mode = "off"
        player["repeat"] = mode
        return await inter.response.send_message(f"Repeat mode: {mode}", ephemeral=True)

    @discord.ui.button(label="Vol+", style=discord.ButtonStyle.secondary)
    async def vol_up(self, inter: discord.Interaction, btn: Button):
        self._touch()
        player = self.cog.players.get(self.guild_id)
        if not player:
            return await inter.response.send_message("No player.", ephemeral=True)
        player["volume"] = min(1.0, player.get("volume", 0.15) + 0.05)
        vc = player.get("voice_client")
        if vc and getattr(vc, "source", None) and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = player["volume"]
        return await inter.response.send_message(f"Volume: {player['volume']*100:.0f}%", ephemeral=True)

    @discord.ui.button(label="Vol-", style=discord.ButtonStyle.secondary)
    async def vol_down(self, inter: discord.Interaction, btn: Button):
        self._touch()
        player = self.cog.players.get(self.guild_id)
        if not player:
            return await inter.response.send_message("No player.", ephemeral=True)
        player["volume"] = max(0.0, player.get("volume", 0.15) - 0.05)
        vc = player.get("voice_client")
        if vc and getattr(vc, "source", None) and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = player["volume"]
        return await inter.response.send_message(f"Volume: {player['volume']*100:.0f}%", ephemeral=True)

    @discord.ui.button(label="Now", style=discord.ButtonStyle.secondary, emoji=f"{EMOJI['note']}")
    async def nowplaying(self, inter: discord.Interaction, btn: Button):
        self._touch()
        player = self.cog.players.get(self.guild_id)
        now = player.get("now") if player else None
        if not now:
            return await inter.response.send_message("Nothing is playing.", ephemeral=True)
        title = now.get("title")
        url = now.get("webpage_url")
        dur = now.get("duration")
        embed = discord.Embed(title="Now Playing", description=f"[{title}]({url})" if url else title)
        if dur:
            mins, secs = divmod(int(dur), 60)
            embed.add_field(name="Duration", value=f"{mins}:{secs:02d}", inline=True)
        return await inter.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Queue", style=discord.ButtonStyle.secondary, emoji=f"{EMOJI['scroll']}")
    async def show_queue(self, inter: discord.Interaction, btn: Button):
        self._touch()
        player = self.cog.players.get(self.guild_id)
        q = player.get("queue", []) if player else []
        if not q:
            return await inter.response.send_message(f"{EMOJI['info']} Queue is empty.", ephemeral=True)
        lines = [f"{i}. {it.get('title')}" for i, it in enumerate(q[:10], start=1)]
        if len(q) > 10:
            lines.append(f"...and {len(q)-10} more")
        return await inter.response.send_message("\n".join(lines), ephemeral=True)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.danger, emoji=f"{EMOJI['wave']}")
    async def leave(self, inter: discord.Interaction, btn: Button):
        self._touch()
        player = self.cog.players.get(self.guild_id)
        if not player or not player.get("voice_client"):
            return await inter.response.send_message("Not connected.", ephemeral=True)
        vc = player["voice_client"]
        await vc.disconnect()
        player["voice_client"] = None
        player["queue"].clear()
        player["now"] = None
        player["repeat"] = "off"
        player["is_playlist"] = False
        updater = player.get("panel_updater")
        if updater and not updater.done():
            updater.cancel()
        return await inter.response.send_message("Disconnected.", ephemeral=True)

    @discord.ui.button(label="Up Next", style=discord.ButtonStyle.secondary, emoji=f"{EMOJI['clipboard']}")
    async def up_next(self, inter: discord.Interaction, btn: Button):
        self._touch()
        player = self.cog.get_player(self.guild_id)
        q = player.get("queue", []) if player else []
        if not q:
            return await inter.response.send_message(f"{EMOJI['info']} Queue is empty.", ephemeral=True)
        lines = [f"{i}. {it.get('title')}" for i, it in enumerate(q[:8], start=1)]
        if len(q) > 8:
            lines.append(f"...and {len(q)-8} more")
        return await inter.response.send_message("\n".join(lines), ephemeral=True)

    @discord.ui.button(label="Save", style=discord.ButtonStyle.secondary, emoji=f"{EMOJI['floppy']}")
    async def save_track(self, inter: discord.Interaction, btn: Button):
        self._touch()
        player = self.cog.get_player(self.guild_id)
        now = player.get("now") if player else None
        if not now:
            return await inter.response.send_message("Nothing playing to save.", ephemeral=True)
        title = now.get("title")
        url = now.get("webpage_url") or now.get("stream_url") or "No-url"
        try:
            await inter.user.send(f"Saved track: **{title}**\n{url}")
            return await inter.response.send_message("Sent to your DMs.", ephemeral=True)
        except Exception:
            return await inter.response.send_message("Could not DM you. Check your privacy settings.", ephemeral=True)


# ---------- Cog ----------
class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: Dict[int, Dict] = {}
        try:
            _cookies = _cookie_candidates()
            self.ytdl = _make_ytdl({"cookiefile": _cookies[0]} if _cookies else None)
            if _cookies:
                log.info("Music: using cookie file '%s' (%d cookie file(s) found, others available as fallback)", os.path.basename(_cookies[0]), len(_cookies))
        except Exception:
            self.ytdl = None
        self.spotify_client = None
        self._init_spotify_client_if_possible()
        self._panels = self._load_panels()
        self._panel_inactivity_task = None
        try:
            self.bot.loop.create_task(self._register_views_on_ready())
        except Exception:
            pass
        # start panel inactivity watcher
        try:
            self._panel_inactivity_task = asyncio.create_task(self._panel_inactivity_watcher())
        except Exception:
            pass

    # ---------- persistence helpers ----------
    def _load_panels(self):
        try:
            if os.path.isfile(PANEL_STORE):
                with open(PANEL_STORE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            log.exception("Failed to load panel store")
        return {}

    def _save_panels(self):
        try:
            with open(PANEL_STORE, "w", encoding="utf-8") as f:
                json.dump(self._panels, f)
        except Exception:
            log.exception("Failed to save panel store")

    def _init_spotify_client_if_possible(self):
        if spotipy is None:
            return
        cid = os.getenv("SPOTIFY_CLIENT_ID") or SPOTIFY_CLIENT_ID
        secret = os.getenv("SPOTIFY_CLIENT_SECRET") or SPOTIFY_CLIENT_SECRET
        if not cid or not secret:
            return
        try:
            auth = SpotifyClientCredentials(client_id=cid, client_secret=secret)
            self.spotify_client = spotipy.Spotify(auth_manager=auth)
        except Exception:
            self.spotify_client = None

    def get_player(self, guild_id: int) -> Dict:
        if guild_id not in self.players:
            self.players[guild_id] = {
                "voice_client": None,
                "queue": [],
                "now": None,
                "volume": 0.15,
                "repeat": "off",
                "is_playlist": False,
                "panel_msg_id": None,
                "panel_channel_id": None,
                "panel_updater": None,
                "panel_last_active": None,
                "panel_inactivity_task": None,
                "start_time": None,
                "playlist_name": None,
            }
            s = self._panels.get(str(guild_id))
            if s:
                self.players[guild_id]["panel_msg_id"] = s.get("panel_msg_id")
                self.players[guild_id]["panel_channel_id"] = s.get("panel_channel_id")
        return self.players[guild_id]

    def touch_panel(self, guild_id: int):
        """Mark the panel as active now."""
        p = self.players.get(guild_id)
        if not p:
            return
        p["panel_last_active"] = time.time()

    async def ensure_voice(self, ctx: Union[commands.Context, discord.Interaction]) -> Optional[discord.VoiceClient]:
        author = ctx.user if isinstance(ctx, discord.Interaction) else ctx.author
        channel_attr = getattr(author, "voice", None)
        if not channel_attr or not channel_attr.channel:
            if isinstance(ctx, discord.Interaction):
                await ctx.followup.send(f"{EMOJI['error']} You must be connected to a voice channel.", ephemeral=True)
            else:
                await ctx.send(f"{EMOJI['error']} You must be connected to a voice channel.")
            return None
        channel = channel_attr.channel
        vc = discord.utils.get(self.bot.voice_clients, guild=channel.guild)
        if vc is None:
            try:
                vc = await channel.connect()
            except Exception as e:
                log.exception("Could not connect: %s", e)
                if isinstance(ctx, discord.Interaction):
                    await ctx.followup.send(f"{EMOJI['error']} Could not connect: {e}", ephemeral=True)
                else:
                    await ctx.send(f"{EMOJI['error']} Could not connect: {e}")
                return None
        else:
            if vc.channel.id != channel.id:
                try:
                    await vc.move_to(channel)
                except Exception:
                    pass
        player = self.get_player(channel.guild.id)
        player["voice_client"] = vc
        return vc

    async def add_and_play(self, ctx_or_inter: Union[commands.Context, discord.Interaction], query: str):
        is_inter = isinstance(ctx_or_inter, discord.Interaction)
        guild = ctx_or_inter.guild
        guild_id = guild.id
        player = self.get_player(guild_id)

        if not self.ytdl:
            msg = "yt-dlp / youtube_dl is not installed in the bot environment."
            if is_inter:
                await ctx_or_inter.followup.send(msg, ephemeral=True)
            else:
                await ctx_or_inter.send(msg)
            return

        vc = await self.ensure_voice(ctx_or_inter)
        if vc is None:
            return

        # resolve url or build search target
        target = None
        if "youtube.com" in query or "youtu.be" in query:
            target = query
        else:
            if VideosSearch is not None:
                try:
                    res = VideosSearch(query, limit=1).result().get("result", [])
                    if res:
                        target = res[0].get("link")
                except Exception:
                    target = None
            if not target:
                target = f"ytsearch1:{query}"

        loop = asyncio.get_event_loop()
        info = await _extract_info_with_retry(loop, self.ytdl, target)
        # If no info from ytdl, try Spotify search -> then search YouTube for best match (fallback)
        if not info:
            log.debug("ytdl failed to extract; trying Spotify search fallback (if available)...")
            if spotipy and self.spotify_client:
                try:
                    search = self.spotify_client.search(q=query, type="track", limit=1)
                    tracks = search.get("tracks", {}).get("items", []) if search else []
                    if tracks:
                        t = tracks[0]
                        title = t.get("name")
                        artists = ", ".join([a.get("name") for a in t.get("artists", []) if a.get("name")])
                        fallback_query = f"{title} {artists}"
                        # search YouTube for fallback_query
                        if VideosSearch is not None:
                            res = VideosSearch(fallback_query, limit=1).result().get("result", [])
                            if res:
                                target = res[0].get("link")
                            else:
                                target = f"ytsearch1:{fallback_query}"
                        else:
                            target = f"ytsearch1:{fallback_query}"
                        info = await _extract_info_with_retry(loop, self.ytdl, target)
                except Exception:
                    info = None

        if not info:
            text = f"{EMOJI['error']} Could not extract any information for that query."
            if is_inter:
                await ctx_or_inter.followup.send(text, ephemeral=True)
            else:
                await ctx_or_inter.send(text)
            return

        if "entries" in info:
            entries = info.get("entries") or []
            if not entries:
                txt = f"{EMOJI['error']} No entries found."
                if is_inter:
                    await ctx_or_inter.followup.send(txt, ephemeral=True)
                else:
                    await ctx_or_inter.send(txt)
                return
            info = entries[0]

        stream_url = _select_best_audio_url(info) or info.get("url")
        if not stream_url:
            txt = (f"{EMOJI['error']} No playable stream URL found. YouTube may be forcing SABR-only streaming. "
                   "Try updating yt-dlp or installing Node.js, or try another video.")
            if is_inter:
                await ctx_or_inter.followup.send(txt, ephemeral=True)
            else:
                await ctx_or_inter.send(txt)
            return

        track = {
            "title": info.get("title", "Unknown title"),
            "webpage_url": info.get("webpage_url") or info.get("url"),
            "stream_url": stream_url,
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "query": None,
        }

        player["queue"].append(track)
        pos = len(player["queue"])
        if is_inter:
            await ctx_or_inter.followup.send(f"{EMOJI['success']} Queued **{track['title']}** (position {pos}).", ephemeral=True)
        else:
            await ctx_or_inter.send(f"{EMOJI['success']} Queued **{track['title']}** (position {pos}).")

        # ensure panel exists or create a new one (force new panel per request)
        try:
            context_channel = ctx_or_inter.channel if not is_inter else ctx_or_inter.channel
            await self.ensure_panel_for_guild(context_channel, guild_id, force=True)
        except Exception:
            log.exception("Failed to ensure panel message; continuing.")

        # touch panel active
        self.touch_panel(guild_id)

        # start if idle
        if not vc.is_playing() and not vc.is_paused():
            await self._play_next(guild_id)

    async def spotify_playlist(self, ctx_or_inter: Union[commands.Context, discord.Interaction], playlist_id_or_url: str):
        """
        Robust Spotify playlist enqueue:
        - Accepts: full URL (https://open.spotify.com/playlist/{id}), spotify:playlist:{id}, or bare id.
        - Pages results in batches of 100 (Spotify max).
        - Respects SPOTIFY_PLAYLIST_LIMIT (0 = no cap).
        - Stores playlist name to show in panel.
        """
        is_inter = isinstance(ctx_or_inter, discord.Interaction)
        guild = ctx_or_inter.guild
        guild_id = guild.id
        player = self.get_player(guild_id)

        if spotipy is None:
            msg = "spotipy is not installed. Install spotipy and set SPOTIFY_CLIENT_ID & SPOTIFY_CLIENT_SECRET."
            if is_inter:
                await ctx_or_inter.followup.send(msg, ephemeral=True)
            else:
                await ctx_or_inter.send(msg)
            return

        if self.spotify_client is None:
            # try init again in case env set after cog load
            self._init_spotify_client_if_possible()
            if self.spotify_client is None:
                msg = "Spotify credentials not configured. Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET as env vars."
                if is_inter:
                    await ctx_or_inter.followup.send(msg, ephemeral=True)
                else:
                    await ctx_or_inter.send(msg)
                return

        # ---------- robust ID extraction ----------
        s = playlist_id_or_url.strip()
        pid = None

        # spotify:playlist:{id}
        if s.startswith("spotify:"):
            parts = s.split(":")
            if len(parts) >= 3 and parts[1] == "playlist":
                pid = parts[2]

        # https://open.spotify.com/playlist/{id}  (may include query params or trailing '/tracks')
        if pid is None and (s.startswith("http://") or s.startswith("https://")):
            try:
                path = s.split("?", 1)[0]
                parts = [p for p in path.split("/") if p]
                if "playlist" in parts:
                    idx = parts.index("playlist")
                    if idx + 1 < len(parts):
                        pid_candidate = parts[idx + 1]
                        if pid_candidate.lower() != "tracks":
                            pid = pid_candidate
                if pid is None and parts:
                    last = parts[-1]
                    if last.lower() != "tracks":
                        pid = last
            except Exception:
                pid = None

        # otherwise assume bare id
        if pid is None:
            pid = s

        # validate id and extract likely id substring
        pid = pid.strip() if pid else None
        if pid:
            m = re.search(r"([A-Za-z0-9_-]{10,50})", pid)
            if m:
                pid = m.group(1)
            else:
                pid = None

        if not pid:
            msg = (f"{EMOJI['error']} Could not parse a Spotify playlist id from your input. "
                   "Provide a URL like `https://open.spotify.com/playlist/<id>` or a playlist ID or `spotify:playlist:<id>`.")
            if is_inter:
                await ctx_or_inter.followup.send(msg, ephemeral=True)
            else:
                await ctx_or_inter.send(msg)
            return

        # ---------- paginate fetch (100 per request) ----------
        per_page = 100
        fetched = 0
        offset = 0
        added = 0
        total_expected = None

        try:
            # optional metadata to get playlist name & total
            try:
                pl_meta = self.spotify_client.playlist(pid, fields="tracks(total),name", market=None)
                total_expected = pl_meta.get("tracks", {}).get("total")
                if pl_meta.get("name"):
                    player["playlist_name"] = pl_meta.get("name")
            except Exception:
                total_expected = None

            while True:
                if SPOTIFY_PLAYLIST_LIMIT:
                    to_fetch = min(per_page, max(1, SPOTIFY_PLAYLIST_LIMIT - fetched))
                else:
                    to_fetch = per_page
                if to_fetch <= 0:
                    break

                results = self.spotify_client.playlist_items(pid, limit=to_fetch, offset=offset)
                items = results.get("items", []) or []
                if not items:
                    break

                for it in items:
                    track_obj = it.get("track")
                    if not track_obj:
                        continue
                    title = track_obj.get("name")
                    artists = ", ".join([a.get("name") for a in track_obj.get("artists", []) if a.get("name")])
                    spotify_url = track_obj.get("external_urls", {}).get("spotify")
                    search_query = f"{title} {artists}" if artists else title
                    track = {
                        "title": f"{title} - {artists}" if artists else title,
                        "webpage_url": spotify_url,
                        "stream_url": None,
                        "duration": track_obj.get("duration_ms") // 1000 if track_obj.get("duration_ms") else None,
                        "thumbnail": None,
                        "query": search_query,
                    }
                    player["queue"].append(track)
                    added += 1
                    fetched += 1
                    if SPOTIFY_PLAYLIST_LIMIT and fetched >= SPOTIFY_PLAYLIST_LIMIT:
                        break

                offset += len(items)

                if SPOTIFY_PLAYLIST_LIMIT and fetched >= SPOTIFY_PLAYLIST_LIMIT:
                    break
                if total_expected is not None and offset >= total_expected:
                    break
                if len(items) < to_fetch:
                    break

        except Exception as e:
            log.exception("Spotify playlist fetch failed: %s", e)
            txt = f"{EMOJI['error']} Could not fetch playlist: {e}"
            if is_inter:
                await ctx_or_inter.followup.send(txt, ephemeral=True)
            else:
                await ctx_or_inter.send(txt)
            return

        player["is_playlist"] = True

        # always drop new panel when queueing a spotify playlist
        try:
            context_channel = ctx_or_inter.channel if not is_inter else ctx_or_inter.channel
            await self.ensure_panel_for_guild(context_channel, guild_id, force=True)
        except Exception:
            log.exception("Failed to ensure panel message; continuing.")

        # mark active
        self.touch_panel(guild_id)

        if is_inter:
            await ctx_or_inter.followup.send(f"{EMOJI['success']} Added {added} tracks from Spotify playlist to the queue. ({player.get('playlist_name') or 'unknown name'})", ephemeral=False)
        else:
            await ctx_or_inter.send(f"{EMOJI['success']} Added {added} tracks from Spotify playlist to the queue. ({player.get('playlist_name') or 'unknown name'})")

        vc = await self.ensure_voice(ctx_or_inter)
        if vc is None:
            return
        if not vc.is_playing() and not vc.is_paused():
            await self._play_next(guild_id)

    async def _resolve_lazy_track(self, guild_id: int, track: dict) -> Optional[dict]:
        if track.get("stream_url"):
            return track
        query = track.get("query")
        if not query:
            return None
        loop = asyncio.get_event_loop()
        target = None
        if VideosSearch is not None:
            try:
                res = VideosSearch(query, limit=1).result().get("result", [])
                if res:
                    target = res[0].get("link")
            except Exception:
                target = None
        if not target:
            target = f"ytsearch1:{query}"
        info = await _extract_info_with_retry(loop, self.ytdl, target)
        if not info:
            return None
        if "entries" in info:
            entries = info.get("entries") or []
            if not entries:
                return None
            info = entries[0]
        stream_url = _select_best_audio_url(info) or info.get("url")
        if not stream_url:
            return None
        track["stream_url"] = stream_url
        if info.get("title"):
            track["title"] = info.get("title")
        if info.get("webpage_url"):
            track["webpage_url"] = info.get("webpage_url")
        thumb = info.get("thumbnail")
        if not thumb:
            thumbs = info.get("thumbnails") or []
            if thumbs:
                thumb = thumbs[-1].get("url")
        if thumb:
            track["thumbnail"] = thumb
        return track

    def create_panel_embed(self, guild_id: int) -> discord.Embed:
        player = self.get_player(guild_id)
        now = player.get("now")
        embed = discord.Embed(title="Music Panel", colour=discord.Colour.blurple())
        if player.get("playlist_name"):
            embed.set_author(name=f"Playlist: {player['playlist_name']}")
        if now:
            title = now.get("title", "Unknown")
            url = now.get("webpage_url") or now.get("stream_url") or None
            desc = f"[{title}]({url})" if url else title
            embed = discord.Embed(title="Now Playing", description=desc, colour=discord.Colour.blurple())
            thumb = now.get("thumbnail")
            if thumb:
                embed.set_thumbnail(url=thumb)
            dur = now.get("duration")
            if dur:
                mins, secs = divmod(int(dur), 60)
                embed.add_field(name="Duration", value=f"{mins}:{secs:02d}", inline=True)
            vol = int(self.get_player(guild_id).get("volume", 0.15) * 100)
            rep = self.get_player(guild_id).get("repeat", "off")
            qlen = len(self.get_player(guild_id).get("queue", []))
            embed.add_field(name="Volume", value=f"{vol}%", inline=True)
            embed.add_field(name="Repeat", value=rep, inline=True)
            embed.add_field(name="Queue", value=str(qlen), inline=True)
            if player.get("is_playlist"):
                embed.set_footer(text=f"Playlist mode — {player.get('playlist_name') or 'Spotify'}")
            start = player.get("start_time")
            if start and dur:
                elapsed = max(0, int(time.time() - start))
                elapsed = min(elapsed, int(dur))
                percent = int(elapsed / max(1, int(dur)) * 100)
                bar_len = 18
                filled = int(bar_len * percent / 100)
                bar = "▮" * filled + "▯" * (bar_len - filled)
                embed.add_field(name="Progress", value=f"{elapsed}s / {int(dur)}s ({percent}%)\n{bar}", inline=False)
        else:
            embed.description = "Idle — queue something with /play or the Play button."
        return embed

    async def ensure_panel_for_guild(self, channel: discord.TextChannel, guild_id: int, force: bool = False):
        """
        Ensure a panel exists in the supplied channel.
        If force=True, delete any existing panel and create a fresh one.
        """
        player = self.get_player(guild_id)
        panel_id = player.get("panel_msg_id")

        # force delete old panel if requested
        if force and panel_id:
            try:
                ch = self.bot.get_channel(player.get("panel_channel_id")) or channel
                if ch:
                    try:
                        old = await ch.fetch_message(panel_id)
                        await old.delete()
                    except Exception:
                        pass
            finally:
                player["panel_msg_id"] = None
                # remove from persisted store
                if str(guild_id) in self._panels:
                    del self._panels[str(guild_id)]
                    self._save_panels()

        # If a panel exists, update it
        if player.get("panel_msg_id"):
            try:
                msg = await channel.fetch_message(player["panel_msg_id"])
                await msg.edit(embed=self.create_panel_embed(guild_id))
                try:
                    self.bot.add_view(MusicPanel(self, guild_id), message_id=msg.id)
                except Exception:
                    pass
                player["panel_channel_id"] = channel.id
                self._panels[str(guild_id)] = {"panel_msg_id": msg.id, "panel_channel_id": channel.id}
                self._save_panels()
                player["panel_last_active"] = time.time()
                return msg
            except Exception:
                player["panel_msg_id"] = None

        # Otherwise create a new panel message
        view = MusicPanel(self, guild_id)
        try:
            msg = await channel.send(embed=self.create_panel_embed(guild_id), view=view)
            player["panel_msg_id"] = msg.id
            player["panel_channel_id"] = channel.id
            try:
                self.bot.add_view(view, message_id=msg.id)
            except Exception:
                pass
            self._panels[str(guild_id)] = {"panel_msg_id": msg.id, "panel_channel_id": channel.id}
            self._save_panels()
            player["panel_last_active"] = time.time()
            # ensure per-player inactivity task exists
            if player.get("panel_inactivity_task"):
                try:
                    if not player["panel_inactivity_task"].done():
                        player["panel_inactivity_task"].cancel()
                except Exception:
                    pass
            return msg
        except Exception:
            log.exception("Failed to create music panel message.")
            return None

    async def _register_views_on_ready(self):
        await self.bot.wait_until_ready()
        for gid_str, data in list(self._panels.items()):
            try:
                gid = int(gid_str)
            except Exception:
                continue
            panel_id = data.get("panel_msg_id")
            channel_id = data.get("panel_channel_id")
            if panel_id and channel_id:
                try:
                    try:
                        self.bot.add_view(MusicPanel(self, gid), message_id=panel_id)
                    except Exception:
                        pass
                    p = self.get_player(gid)
                    p["panel_msg_id"] = panel_id
                    p["panel_channel_id"] = channel_id
                    p["panel_last_active"] = time.time()
                except Exception:
                    log.exception("During view re-register")

    async def _play_next(self, guild_id: int):
        player = self.get_player(guild_id)
        if not player:
            return
        vc: discord.VoiceClient = player.get("voice_client")
        if vc is None:
            return
        if not player["queue"]:
            player["now"] = None
            return

        next_track = player["queue"].pop(0)
        if not next_track.get("stream_url") and next_track.get("query"):
            resolved = await self._resolve_lazy_track(guild_id, next_track)
            if not resolved:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    chan = next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
                    if chan:
                        await chan.send(f"{EMOJI['warning']} Skipped track (could not resolve): {next_track.get('title')}")
                await asyncio.sleep(0.2)
                return await self._play_next(guild_id)

        player["now"] = next_track
        history = player.setdefault("history", [])
        history.append(next_track.get("title", "Unknown track"))
        if len(history) > 50:
            del history[:-50]
        stream_url = next_track.get("stream_url")
        try:
            if FFMPEG_PATH:
                source = discord.FFmpegPCMAudio(stream_url, executable=FFMPEG_PATH, **FFMPEG_OPTIONS)
            else:
                source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
            pcm = discord.PCMVolumeTransformer(source, volume=player.get("volume", 0.15))
            player["start_time"] = time.time()
            vc.play(pcm, after=lambda e: asyncio.run_coroutine_threadsafe(self._after_play(guild_id, e), self.bot.loop))

            # update/ensure panel and mark active
            panel_id = player.get("panel_msg_id")
            if panel_id:
                guild_obj = self.bot.get_guild(guild_id)
                if guild_obj:
                    channel = None
                    ch_id = player.get("panel_channel_id")
                    if ch_id:
                        channel = self.bot.get_channel(ch_id)
                    if not channel:
                        channel = next((c for c in guild_obj.text_channels if c.permissions_for(guild_obj.me).send_messages), None)
                    if channel:
                        try:
                            msg = await channel.fetch_message(panel_id)
                            await msg.edit(embed=self.create_panel_embed(guild_id))
                        except Exception:
                            try:
                                await self.ensure_panel_for_guild(channel, guild_id, force=True)
                            except Exception:
                                pass

            player["panel_last_active"] = time.time()
            updater = player.get("panel_updater")
            if updater and not updater.done():
                updater.cancel()
            player["panel_updater"] = asyncio.create_task(self._panel_updater_task(guild_id))

        except Exception as e:
            log.exception("Failed to start playback: %s", e)
            guild = self.bot.get_guild(guild_id)
            if guild:
                chan = next((c for c in guild.text_channels if c.permissions_for(guild.me).send_messages), None)
                if chan:
                    await chan.send(f"{EMOJI['error']} Playback error: {e}")
            await self._after_play(guild_id, e)

    async def _panel_updater_task(self, guild_id: int):
        player = self.get_player(guild_id)
        try:
            while player and player.get("now"):
                panel_id = player.get("panel_msg_id")
                ch_id = player.get("panel_channel_id")
                if not panel_id or not ch_id:
                    return
                channel = self.bot.get_channel(ch_id)
                if not channel:
                    return
                try:
                    msg = await channel.fetch_message(panel_id)
                    await msg.edit(embed=self.create_panel_embed(guild_id))
                except Exception:
                    return
                await asyncio.sleep(PANEL_PROGRESS_UPDATE_INTERVAL)
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("panel updater error for guild %s", guild_id)

    async def _after_play(self, guild_id: int, error: Optional[Exception]):
        player = self.get_player(guild_id)
        now = player.get("now")
        rep = player.get("repeat", "off")
        if now:
            if rep == "single":
                player["queue"].insert(0, now)
            elif rep == "all":
                player["queue"].append(now)
        player["now"] = None
        player["start_time"] = None
        updater = player.get("panel_updater")
        if updater and not updater.done():
            try:
                updater.cancel()
            except Exception:
                pass
        if error:
            log.error("Playback error in guild %s: %s", guild_id, error)
        await asyncio.sleep(0.4)
        await self._play_next(guild_id)

    async def _panel_inactivity_watcher(self):
        """Background task that deletes panels inactive for PANEL_INACTIVITY_SECONDS."""
        try:
            while True:
                now_t = time.time()
                for gid, player in list(self.players.items()):
                    last = player.get("panel_last_active")
                    panel_id = player.get("panel_msg_id")
                    ch_id = player.get("panel_channel_id")
                    if panel_id and ch_id and last:
                        if now_t - last > PANEL_INACTIVITY_SECONDS:
                            try:
                                ch = self.bot.get_channel(ch_id)
                                if ch:
                                    try:
                                        msg = await ch.fetch_message(panel_id)
                                        await msg.delete()
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            # clear stored panel
                            player["panel_msg_id"] = None
                            player["panel_channel_id"] = None
                            if str(gid) in self._panels:
                                del self._panels[str(gid)]
                                self._save_panels()
                            player["panel_last_active"] = None
                await asyncio.sleep(30)
        except asyncio.CancelledError:
            return
        except Exception:
            log.exception("panel inactivity watcher crashed")
            return

    # ---------- commands (public) ----------
    @commands.hybrid_command(name="play", aliases=["p"])
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def play(self, ctx: commands.Context, *, query: str):
        await self.add_and_play(ctx, query)

    @commands.command(name="spotify_playlist", with_app_command=True)
    @commands.guild_only()
    async def spotify_playlist_cmd(self, ctx: commands.Context, playlist: str):
        await ctx.defer()
        await self.spotify_playlist(ctx, playlist)

    @commands.hybrid_command()
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def pause(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        vc = player.get("voice_client")
        if not vc or not vc.is_playing():
            return await ctx.send(f"{EMOJI['error']} Nothing is playing.")
        vc.pause()
        await ctx.send(f"{EMOJI['pause']} Paused.")
        self.touch_panel(ctx.guild.id)

    @commands.hybrid_command()
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def resume(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        vc = player.get("voice_client")
        if not vc or not vc.is_paused():
            return await ctx.send(f"{EMOJI['error']} Nothing is paused.")
        vc.resume()
        await ctx.send(f"{EMOJI['play_icon']} Resumed.")
        self.touch_panel(ctx.guild.id)

    @commands.hybrid_command()
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def stop(self, ctx: commands.Context):
        if not self._is_dj_or_alone(ctx):
            return await ctx.send(f"{EMOJI['locked']} Only the DJ role (or being alone in voice) can stop playback here.")
        player = self.get_player(ctx.guild.id)
        vc = player.get("voice_client")
        if not vc:
            return await ctx.send(f"{EMOJI['error']} I'm not connected.")
        vc.stop()
        player["queue"].clear()
        player["is_playlist"] = False
        updater = player.get("panel_updater")
        if updater and not updater.done():
            updater.cancel()
        await ctx.send(f"{EMOJI['stop_icon']} Stopped and cleared the queue.")
        self.touch_panel(ctx.guild.id)

    @commands.hybrid_command()
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def skip(self, ctx: commands.Context):
        if not self._is_dj_or_alone(ctx):
            return await ctx.send(f"{EMOJI['locked']} Only the DJ role (or being alone in voice) can skip here.")
        player = self.get_player(ctx.guild.id)
        vc = player.get("voice_client")
        if not vc or (not vc.is_playing() and not vc.is_paused()):
            return await ctx.send(f"{EMOJI['error']} Nothing to skip.")
        vc.stop()
        await ctx.send(f"{EMOJI['skip']} Skipped.")
        self.touch_panel(ctx.guild.id)

    @commands.hybrid_command()
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def leave(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        vc = player.get("voice_client")
        if not vc:
            return await ctx.send(f"{EMOJI['error']} I'm not connected.")
        await vc.disconnect()
        player["voice_client"] = None
        player["queue"].clear()
        player["now"] = None
        player["repeat"] = "off"
        player["is_playlist"] = False
        updater = player.get("panel_updater")
        if updater and not updater.done():
            updater.cancel()
        await ctx.send(f"{EMOJI['wave']} Disconnected and cleared queue.")
        self.touch_panel(ctx.guild.id)

    @commands.hybrid_command(name="nowplaying", aliases=["np"])
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def nowplaying(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        now = player.get("now")
        if not now:
            return await ctx.send(f"{EMOJI['error']} Nothing is playing.")
        embed = discord.Embed(title="Now Playing", description=f"[{now['title']}]({now.get('webpage_url')})" if now.get("webpage_url") else now.get("title"))
        if now.get("duration"):
            embed.add_field(name="Duration", value=str(now["duration"]), inline=True)
        await ctx.send(embed=embed)
        self.touch_panel(ctx.guild.id)

    @commands.hybrid_command(name="queue")
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def _queue(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        q = player.get("queue", [])
        if not q:
            return await ctx.send(f"{EMOJI['info']} Queue is empty.")
        lines = [f"{i}. {it.get('title')}" for i, it in enumerate(q[:20], start=1)]
        if len(q) > 20:
            lines.append(f"...and {len(q)-20} more.")
        await ctx.send("\n".join(lines))
        self.touch_panel(ctx.guild.id)

    # ---------------- lyrics ----------------
    @commands.command(name="lyrics", description="Look up lyrics for a song.")
    async def lyrics(self, ctx: commands.Context, *, query: str):
        await ctx.defer()
        if " - " in query:
            artist, title = [p.strip() for p in query.split(" - ", 1)]
        else:
            player = self.get_player(ctx.guild.id) if ctx.guild else None
            now = player.get("now") if player else None
            if now and now.get("title"):
                artist, title = "", now["title"]
            else:
                artist, title = "", query

        import aiohttp
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://api.lyrics.ovh/v1/{artist}/{title}" if artist else f"https://api.lyrics.ovh/v1/ /{title}") as resp:
                    if resp.status != 200:
                        return await ctx.send(f"{EMOJI['error']} No lyrics found for that.")
                    data = await resp.json()
        except Exception:
            return await ctx.send(f"{EMOJI['error']} Lyrics service is unavailable right now.")

        lyrics_text = data.get("lyrics", "").strip()
        if not lyrics_text:
            return await ctx.send(f"{EMOJI['error']} No lyrics found for that.")

        embed = discord.Embed(title=f"🎤 Lyrics: {title}", description=lyrics_text[:4000], color=discord.Color.blurple())
        await ctx.send(embed=embed)

    # ---------------- 24/7 mode ----------------
    @commands.command(name="247", description="Toggle 24/7 mode — bot stays in voice even when the queue is empty.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def toggle_247(self, ctx: commands.Context):
        player = self.get_player(ctx.guild.id)
        player["stay_connected"] = not player.get("stay_connected", False)
        await ctx.send(f"{EMOJI['success']} 24/7 mode is now **{'ON' if player['stay_connected'] else 'OFF'}**.")

    # ---------------- DJ role ----------------
    @commands.command(name="setdjrole", description="Restrict playback controls to a specific role.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def setdjrole(self, ctx: commands.Context, role: discord.Role = None):
        from cogs.utils.json_store import get_store
        store = get_store("music_dj.json", dict)

        def _mut(data):
            if role:
                data[str(ctx.guild.id)] = role.id
            else:
                data.pop(str(ctx.guild.id), None)
            return data
        store.mutate(_mut)
        await ctx.send(f"{EMOJI['success']} DJ role set to {role.mention}." if role else f"{EMOJI['success']} DJ restriction removed — anyone can control playback.")

    def _is_dj_or_alone(self, ctx: commands.Context) -> bool:
        from cogs.utils.json_store import get_store
        store = get_store("music_dj.json", dict)
        dj_role_id = store.read().get(str(ctx.guild.id))
        if not dj_role_id:
            return True
        if ctx.author.guild_permissions.administrator:
            return True
        role = ctx.guild.get_role(dj_role_id)
        if role and role in ctx.author.roles:
            return True
        vc = ctx.guild.voice_client
        if vc and vc.channel and len([m for m in vc.channel.members if not m.bot]) <= 1:
            return True
        return False

    # ---------------- playlists ----------------
    @commands.command(name="playlist_save", description="Save the current queue as a named playlist.")
    async def playlist_save(self, ctx: commands.Context, name: str):
        if not ctx.guild:
            return await ctx.send(f"{EMOJI['error']} This only works in a server with an active queue.")
        player = self.get_player(ctx.guild.id)
        queue = player.get("queue", [])
        if not queue:
            return await ctx.send(f"{EMOJI['error']} The queue is empty — nothing to save.")

        from cogs.utils.json_store import get_store
        store = get_store("playlists.json", dict)
        urls = [item.get("webpage_url") or item.get("url") for item in queue if item.get("webpage_url") or item.get("url")]

        def _mut(data):
            data.setdefault(str(ctx.author.id), {})[name] = urls
            return data
        store.mutate(_mut)
        await ctx.send(f"{EMOJI['success']} Saved **{len(urls)}** track(s) as playlist `{name}`.")

    @commands.command(name="playlist_load", description="Queue up a saved playlist.")
    @commands.guild_only()
    async def playlist_load(self, ctx: commands.Context, name: str):
        from cogs.utils.json_store import get_store
        store = get_store("playlists.json", dict)
        urls = store.read().get(str(ctx.author.id), {}).get(name)
        if not urls:
            return await ctx.send(f"{EMOJI['error']} No playlist named `{name}` found.")

        play_command = self.bot.get_command("play")
        if not play_command:
            return await ctx.send(f"{EMOJI['error']} Music playback isn't available right now.")

        await ctx.send(f"{EMOJI['success']} Queuing **{len(urls)}** track(s) from `{name}`...")
        for url in urls:
            try:
                await ctx.invoke(play_command, query=url)
            except Exception:
                continue

    @commands.command(name="playlists", description="List your saved playlists.")
    async def playlists_list(self, ctx: commands.Context):
        from cogs.utils.json_store import get_store
        store = get_store("playlists.json", dict)
        mine = store.read().get(str(ctx.author.id), {})
        if not mine:
            return await ctx.send(f"{EMOJI['info']} You haven't saved any playlists yet.")
        embed = discord.Embed(title=f"{EMOJI['music_note_beam']} Your Playlists", color=discord.Color.blurple())
        for name, urls in mine.items():
            embed.add_field(name=name, value=f"{len(urls)} track(s)", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="shuffle")
    @commands.guild_only()
    async def shuffle_queue(self, ctx: commands.Context):
        """Shuffle the current queue order."""
        if not self._is_dj_or_alone(ctx):
            return await ctx.send(f"{EMOJI['locked']} Only the DJ role (or being alone in voice) can shuffle here.")
        player = self.get_player(ctx.guild.id)
        queue = player.get("queue", [])
        if len(queue) < 2:
            return await ctx.send(f"{EMOJI['info']} Not enough tracks in the queue to shuffle.")
        random.shuffle(queue)
        await ctx.send(f"{EMOJI['success']} Shuffled **{len(queue)}** track(s) in the queue.")

    @commands.command(name="voteskip")
    @commands.guild_only()
    async def voteskip(self, ctx: commands.Context):
        """Vote to skip the current track — needs majority of listeners in voice."""
        vc = ctx.guild.voice_client
        if not vc or not vc.is_playing():
            return await ctx.send(f"{EMOJI['info']} Nothing is playing right now.")

        listeners = [m for m in vc.channel.members if not m.bot]
        if ctx.author not in listeners:
            return await ctx.send(f"{EMOJI['error']} You need to be in the voice channel to vote.")

        player = self.get_player(ctx.guild.id)
        votes = player.setdefault("skip_votes", set())
        votes.add(ctx.author.id)
        needed = max(1, (len(listeners) // 2) + 1)

        if len(votes) >= needed:
            vc.stop()
            player["skip_votes"] = set()
            await ctx.send(f"{EMOJI['skip']} Vote-skip passed ({len(votes)}/{needed}) — skipping!")
        else:
            await ctx.send(f"{EMOJI['success']} Vote registered ({len(votes)}/{needed} needed to skip).")

    @commands.command(name="history", aliases=['playhistory'])
    @commands.guild_only()
    async def play_history(self, ctx: commands.Context):
        """Show recently played tracks in this server."""
        player = self.get_player(ctx.guild.id)
        history = player.get("history", [])
        if not history:
            return await ctx.send(f"{EMOJI['info']} No play history yet this session.")
        embed = discord.Embed(title=f"{EMOJI['clock']} Recently Played", color=discord.Color.blurple())
        embed.description = "\n".join(f"{i+1}. {t}" for i, t in enumerate(history[-10:]))
        await ctx.send(embed=embed)

    @commands.hybrid_command()
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def audiodiag(self, ctx: commands.Context):
        embed = discord.Embed(title=f"{EMOJI['wrench']} Audio Diagnostics", color=discord.Color.blurple())

        embed.add_field(name="yt-dlp / youtube_dl", value=f"{EMOJI['success'] if self.ytdl else EMOJI['error']} {'available' if self.ytdl else 'missing'}", inline=True)

        import shutil as _sh
        ffexe = _sh.which("ffmpeg")
        embed.add_field(name="ffmpeg", value=f"{EMOJI['success'] if ffexe else EMOJI['error']} {'on PATH' if ffexe else 'not found'}", inline=True)

        cookies = _cookie_candidates()
        if cookies:
            cookie_list = "\n".join(f"• `{os.path.basename(p)}`" for p in cookies)
            embed.add_field(name=f"{EMOJI['shield']} Cookie files ({len(cookies)})", value=cookie_list, inline=False)
        else:
            embed.add_field(
                name=f"{EMOJI['warning']} Cookie files",
                value="None found. On a VPS, YouTube often rate-limits or blocks anonymous cloud IPs — "
                      "drop a `cookie.txt` (Netscape format, exported from a logged-in browser) into "
                      "`data/cookies/` or the project root to fix most playback failures. "
                      "`cookie1.txt`, `cookie2.txt`, etc. are tried automatically as fallbacks.",
                inline=False,
            )

        try:
            import davey
            embed.add_field(name="davey (E2EE voice)", value=f"{EMOJI['success']} installed", inline=True)
        except ImportError:
            embed.add_field(name="davey (E2EE voice)", value=f"{EMOJI['error']} missing — required for voice!", inline=True)

        try:
            import nacl
            embed.add_field(name="PyNaCl", value=f"{EMOJI['success']} installed", inline=True)
        except ImportError:
            embed.add_field(name="PyNaCl", value=f"{EMOJI['error']} missing — required for voice!", inline=True)

        if spotipy:
            embed.add_field(name="Spotify", value=f"{EMOJI['success']} spotipy available, client {'configured' if self.spotify_client else 'not configured'}", inline=True)
        else:
            embed.add_field(name="Spotify", value=f"{EMOJI['error']} spotipy missing", inline=True)

        embed.set_footer(text="If you see SABR/EJS errors, installing Node.js can help — the cog auto-retries with player_client=web and cookies when needed.")
        await ctx.send(embed=embed)
        self.touch_panel(ctx.guild.id)

    @commands.command(name="musicpanel")
    @commands.guild_only()
    async def musicpanel(self, ctx: commands.Context):
        """Send or recreate the music control panel."""
        player = self.get_player(ctx.guild.id)

        # always force creation of a fresh panel
        view = MusicPanel(self, ctx.guild.id)
        try:
            msg = await self.ensure_panel_for_guild(ctx.channel, ctx.guild.id, force=True)
            if msg:
                await ctx.send(f"{EMOJI['success']} Music panel created.")
            else:
                await ctx.send(f"{EMOJI['error']} Failed to create panel.")
        except Exception:
            log.exception("Failed to create panel")
            await ctx.send(f"{EMOJI['error']} Failed to create panel.")
        self.touch_panel(ctx.guild.id)

    # cleanup
    def cog_unload(self):
        # cancel background tasks
        try:
            if self._panel_inactivity_task and not self._panel_inactivity_task.done():
                self._panel_inactivity_task.cancel()
        except Exception:
            pass

        for gid, player in list(self.players.items()):
            vc = player.get("voice_client")
            try:
                if vc and vc.is_connected():
                    asyncio.create_task(vc.disconnect())
            except Exception:
                pass

        # Save panels before unload
        self._save_panels()


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicCog(bot))