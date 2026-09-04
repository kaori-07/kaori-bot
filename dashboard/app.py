# dashboard/app.py
from __future__ import annotations

import asyncio
import datetime
import glob
import io
import os
import re
import secrets
import sqlite3
import time
import zipfile
from pathlib import Path

import bcrypt
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user,
)
from flask_wtf import CSRFProtect

from cogs.utils.emoji_manager import EMOJI, EmojiStore
from cogs.utils.json_store import get_store
from cogs.utils import cog_control
from cogs.utils.log_buffer import LOG_BUFFER

# Mirrors cogs/status_rotator.py's DEFAULT_CONFIG shape. Duplicated (rather than
# imported) so the dashboard doesn't need discord.py installed just to preview
# the UI standalone (`python dashboard/app.py`).
PRESENCE_DEFAULT_CONFIG = {
    "rotation_interval": 15,
    "twitch_channel": None,
    "running": False,
    "panel": {"channel_id": None, "message_id": None},
    "entries": [],
}

ROOT = Path(__file__).resolve().parents[1]
SECRET_KEY_FILE = ROOT / ".dashboard_secret"

# Mirrors cogs/antinuke.py's db paths. Duplicated (not imported) for the same
# reason as PRESENCE_DEFAULT_CONFIG above - keeps the dashboard importable
# without discord.py installed.
_DB_DIR = ROOT / "data" / "db"
_ANTI_DB = _DB_DIR / "anti.db"

_CUSTOM_EMOJI_RE = re.compile(r"^<(a?):([A-Za-z0-9_]+):(\d+)>$")


def render_emoji_html(value: str) -> str:
    """Custom Discord emoji tags (<a:name:id>) are meaningless as raw text in
    a browser - render them as the actual CDN image instead. Unicode emoji
    are already renderable as-is."""
    from markupsafe import Markup, escape
    if not value:
        return Markup("")
    m = _CUSTOM_EMOJI_RE.match(value.strip())
    if not m:
        return Markup(escape(value))
    animated, name, emoji_id = m.groups()
    ext = "gif" if animated else "png"
    return Markup(
        f'<img class="emoji-cdn-icon" src="https://cdn.discordapp.com/emojis/{emoji_id}.{ext}" '
        f'alt="{escape(name)}" title=":{escape(name)}:">'
    )

# --- simple in-memory brute-force guard (per-process; fine for a single owner login) ---
_failed_attempts: dict[str, list[float]] = {}
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60


def _get_secret_key() -> str:
    env_key = os.getenv("DASHBOARD_SECRET_KEY")
    if env_key:
        return env_key
    if SECRET_KEY_FILE.exists():
        return SECRET_KEY_FILE.read_text().strip()
    key = secrets.token_hex(32)
    SECRET_KEY_FILE.write_text(key)
    return key


class OwnerUser(UserMixin):
    id = "owner"


def _check_credentials(username: str, password: str) -> bool:
    expected_user = os.getenv("DASHBOARD_USERNAME")
    expected_hash = os.getenv("DASHBOARD_PASSWORD_HASH")
    if not expected_user or not expected_hash:
        return False
    if username != expected_user:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), expected_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _rate_limited(ip: str) -> bool:
    now = time.time()
    attempts = [t for t in _failed_attempts.get(ip, []) if now - t < LOCKOUT_SECONDS]
    _failed_attempts[ip] = attempts
    return len(attempts) >= MAX_ATTEMPTS


def _record_failure(ip: str) -> None:
    _failed_attempts.setdefault(ip, []).append(time.time())


def create_app(bot=None) -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = _get_secret_key()
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Only force secure cookies if explicitly running behind HTTPS/a reverse proxy
    app.config["SESSION_COOKIE_SECURE"] = os.getenv("DASHBOARD_FORCE_HTTPS", "false").lower() == "true"

    csrf = CSRFProtect(app)
    app.jinja_env.filters["render_emoji"] = render_emoji_html

    login_manager = LoginManager(app)
    login_manager.login_view = "login"
    login_manager.session_protection = "strong"

    @login_manager.user_loader
    def load_user(user_id):
        return OwnerUser() if user_id == "owner" else None

    def run_coro(coro):
        """Run a coroutine on the bot's event loop from this Flask thread and
        block until it completes. No-op / returns None if the bot isn't running."""
        if bot is None or bot.loop is None or not bot.loop.is_running():
            return None
        fut = asyncio.run_coroutine_threadsafe(coro, bot.loop)
        try:
            return fut.result(timeout=10)
        except Exception:
            return None

    # ---------------------------------------------------------------
    # Auth
    # ---------------------------------------------------------------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("index"))

        if request.method == "POST":
            ip = request.remote_addr or "unknown"
            if _rate_limited(ip):
                flash("Too many failed attempts. Try again in a minute.", "error")
                return render_template("login.html")

            username = request.form.get("username", "")
            password = request.form.get("password", "")

            if not os.getenv("DASHBOARD_USERNAME") or not os.getenv("DASHBOARD_PASSWORD_HASH"):
                flash(
                    "No dashboard credentials configured yet. Run "
                    "'python set_dashboard_password.py' on the server first.",
                    "error",
                )
                return render_template("login.html")

            if _check_credentials(username, password):
                login_user(OwnerUser(), remember=False)
                return redirect(url_for("index"))

            _record_failure(ip)
            flash("Invalid username or password.", "error")

        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    # ---------------------------------------------------------------
    # Dashboard home
    # ---------------------------------------------------------------
    @app.route("/")
    @login_required
    def index():
        bot_online = bool(bot and bot.is_ready())
        guild_count = len(bot.guilds) if bot_online else 0
        user_count = sum(g.member_count or 0 for g in bot.guilds) if bot_online else 0
        latency_ms = round(bot.latency * 1000) if bot_online and bot.latency else None
        bot_name = str(bot.user) if bot_online else "Offline"
        avatar_url = bot.user.display_avatar.url if bot_online else None

        cog_files = sorted(
            Path(f).stem for f in glob.glob(str(ROOT / "cogs" / "*.py"))
            if not Path(f).stem.startswith("_")
        )
        states = cog_control.all_states(cog_files)
        loaded_exts = set(bot.extensions.keys()) if bot_online else set()

        cogs_info = []
        for name in cog_files:
            cogs_info.append({
                "name": name,
                "enabled": states.get(name, True),
                "loaded": f"cogs.{name}" in loaded_exts,
            })

        return render_template(
            "dashboard.html",
            bot_online=bot_online,
            bot_name=bot_name,
            avatar_url=avatar_url,
            guild_count=guild_count,
            user_count=user_count,
            latency_ms=latency_ms,
            cogs_info=cogs_info,
            active="overview",
        )

    # ---------------------------------------------------------------
    # Cog management
    # ---------------------------------------------------------------
    @app.route("/cogs/toggle/<cog_name>", methods=["POST"])
    @login_required
    def toggle_cog(cog_name):
        safe_name = Path(cog_name).stem
        currently = cog_control.is_enabled(safe_name)
        cog_control.set_enabled(safe_name, not currently)
        flash(
            f"'{safe_name}' will be {'enabled' if not currently else 'disabled'} "
            f"on next reload/restart.",
            "success",
        )
        return redirect(url_for("index"))

    @app.route("/cogs/reload-all", methods=["POST"])
    @login_required
    def reload_all():
        if bot is None:
            flash("Bot process is not attached to this dashboard instance.", "error")
            return redirect(url_for("index"))

        async def _reload():
            for ext in list(bot.extensions.keys()):
                try:
                    await bot.unload_extension(ext)
                except Exception:
                    pass
            cogs_dir = ROOT / "cogs"
            for f in sorted(cogs_dir.glob("*.py")):
                stem = f.stem
                if stem.startswith("_"):
                    continue
                if not cog_control.is_enabled(stem):
                    continue
                try:
                    await bot.load_extension(f"cogs.{stem}")
                except Exception:
                    pass
            try:
                await bot.tree.sync()
            except Exception:
                pass

        run_coro(_reload())
        flash("Cogs reloaded.", "success")
        return redirect(url_for("index"))

    # ---------------------------------------------------------------
    # Emoji manager
    # ---------------------------------------------------------------
    @app.route("/emojis", methods=["GET"])
    @login_required
    def emojis():
        current = EMOJI.all()
        defaults = EMOJI.all_defaults()
        rows = sorted(current.items())
        return render_template("emojis.html", emojis=rows, defaults=defaults, active="emojis")

    @app.route("/emojis/save", methods=["POST"])
    @login_required
    def save_emoji():
        slug = request.form.get("slug", "").strip()
        value = request.form.get("value", "").strip()
        if not slug:
            flash("Slug cannot be empty.", "error")
        elif not value:
            flash("Value cannot be empty.", "error")
        else:
            EMOJI.set(slug, value)
            flash(f"Saved '{slug}'.", "success")
        return redirect(url_for("emojis"))

    @app.route("/emojis/reset/<slug>", methods=["POST"])
    @login_required
    def reset_emoji(slug):
        if EMOJI.reset_to_default(slug):
            flash(f"'{slug}' reset to its default emoji.", "success")
        else:
            flash(f"'{slug}' has no shipped default to reset to.", "error")
        return redirect(url_for("emojis"))

    @app.route("/emojis/delete/<slug>", methods=["POST"])
    @login_required
    def delete_emoji(slug):
        EMOJI.delete(slug)
        flash(f"Deleted '{slug}'.", "success")
        return redirect(url_for("emojis"))

    # ---------------------------------------------------------------
    # Rich presence / status rotator
    # ---------------------------------------------------------------
    @app.route("/presence", methods=["GET"])
    @login_required
    def presence():
        store = get_store("status_config.json", lambda: dict(PRESENCE_DEFAULT_CONFIG))
        cfg = store.read()
        return render_template("presence.html", cfg=cfg, active="presence")

    @app.route("/presence/add", methods=["POST"])
    @login_required
    def presence_add():
        store = get_store("status_config.json", lambda: dict(PRESENCE_DEFAULT_CONFIG))
        entry = {
            "type": request.form.get("type", "game"),
            "status": request.form.get("status", "online"),
            "name": request.form.get("name", "").strip(),
        }
        if not entry["name"]:
            flash("Name / state text is required.", "error")
            return redirect(url_for("presence"))

        image = request.form.get("image", "").strip()
        if image:
            entry["image"] = image

        stream_url = request.form.get("stream_url", "").strip()
        if entry["type"] == "streaming" and stream_url:
            entry["stream_url"] = stream_url

        emoji = request.form.get("emoji", "").strip()
        if entry["type"] == "custom" and emoji:
            entry["emoji"] = emoji

        interval_raw = request.form.get("interval", "").strip()
        if interval_raw:
            try:
                interval = int(interval_raw)
                if interval > 0:
                    entry["interval"] = interval
            except ValueError:
                flash("Interval override must be a whole number of seconds — ignored.", "error")

        buttons = []
        b1_label = request.form.get("button1_label", "").strip()
        b1_url = request.form.get("button1_url", "").strip()
        if b1_label and b1_url:
            buttons.append({"label": b1_label, "url": b1_url})
        b2_label = request.form.get("button2_label", "").strip()
        b2_url = request.form.get("button2_url", "").strip()
        if b2_label and b2_url:
            buttons.append({"label": b2_label, "url": b2_url})
        if buttons:
            entry["buttons"] = buttons[:2]

        def _mut(data):
            data.setdefault("entries", []).append(entry)
            return data
        store.mutate(_mut)
        flash("Presence entry added.", "success")
        return redirect(url_for("presence"))

    @app.route("/presence/remove/<int:index>", methods=["POST"])
    @login_required
    def presence_remove(index):
        store = get_store("status_config.json", lambda: dict(PRESENCE_DEFAULT_CONFIG))

        def _mut(data):
            entries = data.get("entries", [])
            if 0 <= index < len(entries):
                entries.pop(index)
            return data
        store.mutate(_mut)
        flash("Presence entry removed.", "success")
        return redirect(url_for("presence"))

    @app.route("/presence/toggle", methods=["POST"])
    @login_required
    def presence_toggle():
        cog = bot.get_cog("StatusRotator") if bot else None
        store = get_store("status_config.json", lambda: dict(PRESENCE_DEFAULT_CONFIG))
        cfg = store.read()
        currently_running = cfg.get("running", False)

        if cog is not None:
            if currently_running:
                run_coro(cog._stop_rotation())
            else:
                run_coro(cog._start_rotation())
        else:
            # bot/cog not attached - just flip the persisted flag; it will
            # auto-resume next time the bot starts.
            store.mutate(lambda d: {**d, "running": not currently_running})

        flash("Rotation toggled.", "success")
        return redirect(url_for("presence"))

    @app.route("/presence/interval", methods=["POST"])
    @login_required
    def presence_interval():
        try:
            seconds = int(request.form.get("interval", "15"))
            seconds = max(5, seconds)
        except ValueError:
            flash("Interval must be a number.", "error")
            return redirect(url_for("presence"))

        store = get_store("status_config.json", lambda: dict(PRESENCE_DEFAULT_CONFIG))
        store.mutate(lambda d: {**d, "rotation_interval": seconds})
        flash(f"Rotation interval set to {seconds}s.", "success")
        return redirect(url_for("presence"))

    # ---------------------------------------------------------------
    # Guild management
    # ---------------------------------------------------------------
    @app.route("/guilds")
    @login_required
    def guilds():
        bot_online = bool(bot and bot.is_ready())
        guild_list = []
        if bot_online:
            for g in sorted(bot.guilds, key=lambda x: (x.member_count or 0), reverse=True):
                guild_list.append({
                    "id": g.id,
                    "name": g.name,
                    "member_count": g.member_count or 0,
                    "icon_url": g.icon.url if g.icon else None,
                    "owner": str(g.owner) if g.owner else "Unknown",
                })
        return render_template("guilds.html", guild_list=guild_list, bot_online=bot_online, active="guilds")

    @app.route("/guilds/leave/<int:guild_id>", methods=["POST"])
    @login_required
    def leave_guild(guild_id):
        if bot is None:
            flash("Bot process is not attached to this dashboard instance.", "error")
            return redirect(url_for("guilds"))

        guild = bot.get_guild(guild_id)
        if guild is None:
            flash("Server not found (maybe already left).", "error")
            return redirect(url_for("guilds"))

        name = guild.name
        result = run_coro(guild.leave())
        flash(f"Left '{name}'.", "success")
        return redirect(url_for("guilds"))

    @app.route("/guilds/<int:guild_id>/members")
    @login_required
    def guild_members(guild_id):
        if bot is None or not bot.is_ready():
            flash("Bot process is not attached to this dashboard instance.", "error")
            return redirect(url_for("guilds"))
        guild = bot.get_guild(guild_id)
        if guild is None:
            flash("Server not found.", "error")
            return redirect(url_for("guilds"))

        query = request.args.get("q", "").strip().lower()
        members = [m for m in guild.members if not query or query in m.display_name.lower() or query in str(m).lower()]
        members = sorted(members, key=lambda m: m.display_name.lower())[:200]
        member_rows = [{
            "id": m.id, "name": str(m), "display_name": m.display_name,
            "avatar_url": m.display_avatar.url, "bot": m.bot,
            "top_role": m.top_role.name if m.top_role else None,
            "joined_at": m.joined_at.strftime("%Y-%m-%d") if m.joined_at else "—",
        } for m in members]

        voice_rows = []
        for vc_channel in guild.voice_channels:
            if vc_channel.members:
                voice_rows.append({"channel": vc_channel.name, "members": [m.display_name for m in vc_channel.members]})

        return render_template(
            "guild_members.html", guild=guild, member_rows=member_rows, voice_rows=voice_rows,
            query=query, total_members=guild.member_count, active="guilds",
        )

    # ---------------------------------------------------------------
    # Broadcast / announce tool
    # ---------------------------------------------------------------
    @app.route("/broadcast")
    @login_required
    def broadcast():
        bot_online = bool(bot and bot.is_ready())
        guild_list = []
        if bot_online:
            for g in bot.guilds:
                channels = [
                    {"id": c.id, "name": c.name}
                    for c in getattr(g, "text_channels", [])
                    if c.permissions_for(g.me).send_messages
                ] if g.me else []
                guild_list.append({"id": g.id, "name": g.name, "channels": channels})
        return render_template("broadcast.html", guild_list=guild_list, bot_online=bot_online, active="broadcast")

    @app.route("/broadcast/send", methods=["POST"])
    @login_required
    def broadcast_send():
        if bot is None:
            flash("Bot process is not attached to this dashboard instance.", "error")
            return redirect(url_for("broadcast"))

        try:
            channel_id = int(request.form.get("channel_id", "0"))
        except ValueError:
            channel_id = 0
        title = request.form.get("title", "").strip()
        message = request.form.get("message", "").strip()

        if not channel_id or not message:
            flash("Channel and message are required.", "error")
            return redirect(url_for("broadcast"))

        async def _send():
            channel = bot.get_channel(channel_id)
            if channel is None:
                return False
            import discord
            if title:
                embed = discord.Embed(title=title, description=message, color=discord.Color.blurple())
                await channel.send(embed=embed)
            else:
                await channel.send(message)
            return True

        ok = run_coro(_send())
        if ok:
            flash("Message sent.", "success")
        else:
            flash("Failed to send — channel not found or bot lacks permission.", "error")
        return redirect(url_for("broadcast"))

    # ---------------------------------------------------------------
    # Live log console
    # ---------------------------------------------------------------
    @app.route("/logs")
    @login_required
    def logs():
        return render_template("logs.html", initial_logs=LOG_BUFFER.all(), active="logs")

    @app.route("/api/logs")
    @login_required
    def api_logs():
        try:
            since = int(request.args.get("since", "0"))
        except ValueError:
            since = 0
        return jsonify({"logs": LOG_BUFFER.since(since)})

    # ---------------------------------------------------------------
    # Live status/polling endpoint (used by every page's header + overview)
    # ---------------------------------------------------------------
    @app.route("/api/live")
    @login_required
    def api_live():
        bot_online = bool(bot and bot.is_ready())
        presence_store = get_store("status_config.json", lambda: dict(PRESENCE_DEFAULT_CONFIG))
        presence_cfg = presence_store.read()

        cog_files = sorted(
            Path(f).stem for f in glob.glob(str(ROOT / "cogs" / "*.py"))
            if not Path(f).stem.startswith("_")
        )
        states = cog_control.all_states(cog_files)
        loaded_exts = set(bot.extensions.keys()) if bot_online else set()

        system = {}
        try:
            import psutil
            proc = psutil.Process(os.getpid())
            with proc.oneshot():
                system["cpu_percent"] = proc.cpu_percent(interval=None)
                system["memory_mb"] = round(proc.memory_info().rss / 1024 / 1024, 1)
                system["threads"] = proc.num_threads()
        except Exception:
            pass

        uptime_seconds = None
        start_time = getattr(bot, "_started_at", None) if bot else None
        if start_time:
            uptime_seconds = round((datetime.datetime.utcnow() - start_time).total_seconds())

        command_count = len(set(c.qualified_name for c in bot.commands)) if bot_online else 0
        shard_count = getattr(bot, "shard_count", None) if bot_online else None

        return jsonify({
            "online": bot_online,
            "bot_name": str(bot.user) if bot_online else "Offline",
            "guild_count": len(bot.guilds) if bot_online else 0,
            "user_count": sum(g.member_count or 0 for g in bot.guilds) if bot_online else 0,
            "latency_ms": round(bot.latency * 1000) if bot_online and bot.latency else None,
            "presence_running": presence_cfg.get("running", False),
            "command_count": command_count,
            "cog_loaded_count": len(loaded_exts),
            "shard_count": shard_count,
            "uptime_seconds": uptime_seconds,
            "system": system,
            "cogs": [
                {"name": n, "enabled": states.get(n, True), "loaded": f"cogs.{n}" in loaded_exts}
                for n in cog_files
            ],
        })

    @app.route("/cogs/sync", methods=["POST"])
    @login_required
    def sync_commands():
        if bot is None:
            flash("Bot process is not attached to this dashboard instance.", "error")
            return redirect(url_for("index"))

        async def _sync():
            return await bot.tree.sync()

        result = run_coro(_sync())
        if result is not None:
            flash(f"Synced {len(result)} slash command(s).", "success")
        else:
            flash("Sync failed or timed out — check the live logs.", "error")
        return redirect(url_for("index"))

    # ---------------------------------------------------------------
    # Music control
    # ---------------------------------------------------------------
    @app.route("/music")
    @login_required
    def music():
        bot_online = bool(bot and bot.is_ready())
        players_info = []
        if bot_online:
            music_cog = bot.get_cog("MusicCog")
            if music_cog:
                for guild_id, player in list(music_cog.players.items()):
                    guild = bot.get_guild(guild_id)
                    if not guild:
                        continue
                    vc = player.get("voice_client")
                    now = player.get("now")
                    players_info.append({
                        "guild_id": guild_id,
                        "guild_name": guild.name,
                        "connected": bool(vc and vc.is_connected()),
                        "playing": bool(vc and vc.is_playing()),
                        "paused": bool(vc and vc.is_paused()),
                        "now_title": now.get("title") if now else None,
                        "now_url": now.get("webpage_url") if now else None,
                        "queue_len": len(player.get("queue") or []),
                        "volume": round((player.get("volume") or 0.15) * 100),
                        "repeat": player.get("repeat", "off"),
                    })
        return render_template("music.html", players=players_info, bot_online=bot_online, active="music")

    @app.route("/music/<int:guild_id>/<action>", methods=["POST"])
    @login_required
    def music_action(guild_id, action):
        if bot is None:
            flash("Bot process is not attached to this dashboard instance.", "error")
            return redirect(url_for("music"))
        if action not in ("pause", "resume", "skip", "stop"):
            flash("Unknown action.", "error")
            return redirect(url_for("music"))

        async def _do():
            music_cog = bot.get_cog("MusicCog")
            if not music_cog:
                return False
            player = music_cog.get_player(guild_id)
            vc = player.get("voice_client")
            if not vc:
                return False
            if action == "pause" and vc.is_playing():
                vc.pause()
            elif action == "resume" and vc.is_paused():
                vc.resume()
            elif action == "skip":
                vc.stop()
            elif action == "stop":
                vc.stop()
                player["queue"].clear()
            else:
                return False
            return True

        ok = run_coro(_do())
        flash(f"{action.capitalize()} sent." if ok else "Nothing to do — player not active.", "success" if ok else "error")
        return redirect(url_for("music"))

    @app.route("/music/<int:guild_id>/volume", methods=["POST"])
    @login_required
    def music_volume(guild_id):
        if bot is None:
            flash("Bot process is not attached to this dashboard instance.", "error")
            return redirect(url_for("music"))
        try:
            vol_pct = max(0, min(100, int(request.form.get("volume", "15"))))
        except ValueError:
            flash("Invalid volume.", "error")
            return redirect(url_for("music"))
        vol = vol_pct / 100

        async def _set_vol():
            music_cog = bot.get_cog("MusicCog")
            if not music_cog:
                return False
            player = music_cog.get_player(guild_id)
            player["volume"] = vol
            vc = player.get("voice_client")
            if vc and getattr(vc, "source", None):
                try:
                    vc.source.volume = vol
                except Exception:
                    pass
            return True

        run_coro(_set_vol())
        flash(f"Volume set to {vol_pct}%.", "success")
        return redirect(url_for("music"))

    # ---------------------------------------------------------------
    # Antinuke control
    # ---------------------------------------------------------------
    WHITELIST_COLS = ["chcr", "chdl", "chup", "mngstemo", "meneve", "memup", "ban",
                       "kick", "prune", "botadd", "rlcr", "rldl", "rlup", "serverup", "mngweb"]

    def _anti_conn():
        _DB_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_ANTI_DB))
        conn.execute("CREATE TABLE IF NOT EXISTS antinuke (guild_id TEXT PRIMARY KEY, status INTEGER)")
        conn.execute("CREATE TABLE IF NOT EXISTS extraowners (guild_id TEXT, owner_id TEXT)")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS whitelisted_users (guild_id TEXT, user_id TEXT, "
            + ", ".join(f"{c} INTEGER" for c in WHITELIST_COLS) + ")"
        )
        return conn

    def _resolve_name(uid_str):
        if bot and bot.is_ready():
            try:
                u = bot.get_user(int(uid_str))
                if u:
                    return str(u)
            except (ValueError, TypeError):
                pass
        return uid_str

    @app.route("/antinuke")
    @login_required
    def antinuke():
        bot_online = bool(bot and bot.is_ready())
        conn = _anti_conn()
        try:
            status_rows = {gid: bool(status) for gid, status in conn.execute("SELECT guild_id, status FROM antinuke")}
            wl_counts = {}
            for row in conn.execute("SELECT guild_id, COUNT(*) FROM whitelisted_users GROUP BY guild_id"):
                wl_counts[row[0]] = row[1]
            owner_counts = {}
            for row in conn.execute("SELECT guild_id, COUNT(*) FROM extraowners GROUP BY guild_id"):
                owner_counts[row[0]] = row[1]
        finally:
            conn.close()

        guild_cards = []
        if bot_online:
            for g in bot.guilds:
                gid = str(g.id)
                guild_cards.append({
                    "id": g.id,
                    "name": g.name,
                    "icon_url": g.icon.url if g.icon else None,
                    "enabled": status_rows.get(gid, False),
                    "whitelisted": wl_counts.get(gid, 0),
                    "extra_owners": owner_counts.get(gid, 0),
                })
        else:
            # bot offline - still show DB-known guilds by ID so the panel isn't empty
            for gid in status_rows:
                guild_cards.append({
                    "id": gid, "name": f"Guild {gid}", "icon_url": None,
                    "enabled": status_rows.get(gid, False),
                    "whitelisted": wl_counts.get(gid, 0),
                    "extra_owners": owner_counts.get(gid, 0),
                })

        return render_template("antinuke.html", guild_cards=guild_cards, bot_online=bot_online, active="antinuke")

    @app.route("/antinuke/toggle/<guild_id>", methods=["POST"])
    @login_required
    def antinuke_toggle(guild_id):
        conn = _anti_conn()
        try:
            row = conn.execute("SELECT status FROM antinuke WHERE guild_id = ?", (str(guild_id),)).fetchone()
            new_status = 0 if (row and row[0]) else 1
            if row:
                conn.execute("UPDATE antinuke SET status = ? WHERE guild_id = ?", (new_status, str(guild_id)))
            else:
                conn.execute("INSERT INTO antinuke (guild_id, status) VALUES (?, ?)", (str(guild_id), new_status))
            conn.commit()
        finally:
            conn.close()
        flash(f"Anti-Nuke {'enabled' if new_status else 'disabled'} for that server.", "success")
        return redirect(url_for("antinuke"))

    @app.route("/antinuke/whitelist/<guild_id>")
    @login_required
    def antinuke_whitelist(guild_id):
        conn = _anti_conn()
        try:
            rows = conn.execute("SELECT user_id FROM whitelisted_users WHERE guild_id = ?", (str(guild_id),)).fetchall()
            owner_rows = conn.execute("SELECT owner_id FROM extraowners WHERE guild_id = ?", (str(guild_id),)).fetchall()
        finally:
            conn.close()

        whitelist = [{"id": r[0], "name": _resolve_name(r[0])} for r in rows]
        extra_owners = [{"id": r[0], "name": _resolve_name(r[0])} for r in owner_rows]

        guild = bot.get_guild(int(guild_id)) if (bot and bot.is_ready()) else None
        guild_name = guild.name if guild else f"Guild {guild_id}"

        return render_template(
            "antinuke_whitelist.html",
            guild_id=guild_id, guild_name=guild_name,
            whitelist=whitelist, extra_owners=extra_owners, active="antinuke",
        )

    @app.route("/antinuke/whitelist/<guild_id>/remove/<user_id>", methods=["POST"])
    @login_required
    def antinuke_whitelist_remove(guild_id, user_id):
        conn = _anti_conn()
        try:
            conn.execute("DELETE FROM whitelisted_users WHERE guild_id = ? AND user_id = ?", (str(guild_id), str(user_id)))
            conn.commit()
        finally:
            conn.close()
        flash("Removed from whitelist.", "success")
        return redirect(url_for("antinuke_whitelist", guild_id=guild_id))

    @app.route("/antinuke/owner/<guild_id>/remove/<user_id>", methods=["POST"])
    @login_required
    def antinuke_owner_remove(guild_id, user_id):
        conn = _anti_conn()
        try:
            conn.execute("DELETE FROM extraowners WHERE guild_id = ? AND owner_id = ?", (str(guild_id), str(user_id)))
            conn.commit()
        finally:
            conn.close()
        flash("Removed trusted admin.", "success")
        return redirect(url_for("antinuke_whitelist", guild_id=guild_id))

    # ---------------------------------------------------------------
    # Analytics
    # ---------------------------------------------------------------
    @app.route("/analytics")
    @login_required
    def analytics():
        usage = get_store("command_usage.json", dict).read()
        by_command = sorted(usage.get("by_command", {}).items(), key=lambda x: x[1], reverse=True)[:15]
        by_guild_raw = usage.get("by_guild", {})

        by_guild = []
        for gid, count in sorted(by_guild_raw.items(), key=lambda x: x[1], reverse=True)[:10]:
            name = gid
            if bot and bot.is_ready() and gid != "dm":
                g = bot.get_guild(int(gid)) if gid.isdigit() else None
                if g:
                    name = g.name
            by_guild.append({"name": name, "count": count})

        return render_template(
            "analytics.html",
            total=usage.get("total", 0),
            by_command=by_command,
            by_guild=by_guild,
            active="analytics",
        )

    # ---------------------------------------------------------------
    # Server logging config
    # ---------------------------------------------------------------
    LOG_EVENTS = ["message_delete", "message_edit", "member_join", "member_leave",
                  "role_change", "nickname_change", "voice_activity"]

    @app.route("/serverlogs")
    @login_required
    def serverlogs():
        bot_online = bool(bot and bot.is_ready())
        store = get_store("serverlogs.json", dict)
        cfg = store.read()

        guilds_info = []
        if bot_online:
            for g in bot.guilds:
                entry = cfg.get(str(g.id), {})
                channel = g.get_channel(entry.get("channel_id")) if entry.get("channel_id") else None
                events = {**{e: True for e in LOG_EVENTS}, **entry.get("events", {})}
                guilds_info.append({
                    "id": g.id, "name": g.name,
                    "channel_name": channel.name if channel else None,
                    "events": events,
                })
        return render_template("serverlogs.html", guilds_info=guilds_info, bot_online=bot_online,
                                log_events=LOG_EVENTS, active="serverlogs")

    @app.route("/serverlogs/<guild_id>/toggle/<event>", methods=["POST"])
    @login_required
    def serverlogs_toggle(guild_id, event):
        if event not in LOG_EVENTS:
            flash("Unknown event.", "error")
            return redirect(url_for("serverlogs"))

        store = get_store("serverlogs.json", dict)

        def _mut(data):
            entry = data.setdefault(str(guild_id), {"channel_id": None, "events": {e: True for e in LOG_EVENTS}})
            entry.setdefault("events", {e: True for e in LOG_EVENTS})
            entry["events"][event] = not entry["events"].get(event, True)
            return data
        store.mutate(_mut)
        flash(f"Toggled {event}.", "success")
        return redirect(url_for("serverlogs"))

    # ---------------------------------------------------------------
    # Data backup / export
    # ---------------------------------------------------------------
    @app.route("/backup/export")
    @login_required
    def backup_export():
        data_dir = ROOT / "data"
        cookies_dir = data_dir / "cookies"
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            if data_dir.exists():
                for path in data_dir.rglob("*"):
                    if not path.is_file():
                        continue
                    # cookie files are login session credentials, not bot state -
                    # never let them leave the server via a backup download
                    if cookies_dir in path.parents:
                        continue
                    zf.write(path, arcname=str(path.relative_to(ROOT)))
            emoji_file = ROOT / "emoji.json"
            if emoji_file.exists():
                zf.write(emoji_file, arcname="emoji.json")
        buf.seek(0)
        return send_file(buf, mimetype="application/zip", as_attachment=True, download_name="bot_data_backup.zip")

    @app.route("/api/status")
    @login_required
    def api_status():
        bot_online = bool(bot and bot.is_ready())
        return jsonify({
            "online": bot_online,
            "guilds": len(bot.guilds) if bot_online else 0,
            "latency_ms": round(bot.latency * 1000) if bot_online and bot.latency else None,
        })

    return app


if __name__ == "__main__":
    # Standalone mode (no live bot attached) - useful for previewing/testing
    # the dashboard UI without running the Discord bot.
    from dotenv import load_dotenv
    load_dotenv()
    app = create_app(bot=None)
    app.run(host=os.getenv("DASHBOARD_HOST", "127.0.0.1"), port=int(os.getenv("DASHBOARD_PORT", "5000")), debug=True)
