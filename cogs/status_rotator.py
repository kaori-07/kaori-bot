# cogs/status_rotator.py
import discord
from discord.ext import commands, tasks
import asyncio
import json
import os
from typing import Optional, Dict, Any, List
from datetime import datetime

# default config template
DEFAULT_CONFIG = {
    "rotation_interval": 15,
    "twitch_channel": None,
    "panel": {
        "channel_id": None,
        "message_id": None
    },
    "entries": []
}

def owner_check():
    return commands.is_owner()

class StatusRotator(commands.Cog):
    """Bot cog: rotates presence and maintains a panel embed with image + up to 2 link buttons."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_path = f"status_config_{getattr(bot.user, 'id', 'unknown')}.json"
        self._ensure_config()
        self._rotation_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._current_index = 0

    # ---------- config helpers ----------
    def _ensure_config(self):
        if not os.path.isfile(self.config_path):
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
            return dict(DEFAULT_CONFIG)

    def _save_config(self, cfg: Dict[str, Any]):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

    # ---------- utility ----------
    async def _dm_owner(self, user: discord.User, message: str):
        try:
            await user.send(message)
        except Exception:
            pass

    def _build_embed_for_entry(self, entry: Dict[str, Any], index: int) -> discord.Embed:
        title = entry.get("name", "Status")
        typ = entry.get("type", "game").title()
        desc = f"Type: **{typ}** • Status: **{entry.get('status','online')}** • Index: `{index}`"
        emb = discord.Embed(title=title, description=desc, color=discord.Color.blurple(), timestamp=datetime.utcnow())
        if entry.get("image"):
            emb.set_image(url=entry.get("image"))
        footer = []
        if entry.get("buttons"):
            labels = [b.get("label","") for b in entry.get("buttons",[])]
            footer.append("Buttons: " + ", ".join(labels))
        emb.set_footer(text=" | ".join(footer) if footer else "")
        return emb

    def _build_view_for_entry(self, entry: Dict[str, Any]) -> discord.ui.View:
        view = discord.ui.View(timeout=None)
        # add up to 2 link buttons
        for b in (entry.get("buttons") or [])[:2]:
            label = b.get("label") or b.get("url")
            url = b.get("url")
            if url:
                view.add_item(discord.ui.Button(label=label, url=url))
        return view

    # ---------- panel commands ----------
    @commands.command(name="status_setpanel", help="Set the panel channel (run this in the target channel). Requires Manage Channel or owner.")
    @commands.has_permissions(manage_channels=True)
    async def status_setpanel(self, ctx: commands.Context):
        try:
            await ctx.message.delete()
        except Exception:
            pass

        cfg = self._load_config()
        cfg.setdefault("panel", {})["channel_id"] = ctx.channel.id
        cfg["panel"].pop("message_id", None)  # create fresh message
        self._save_config(cfg)

        # post initial message (empty until rotation applies)
        entries = cfg.get("entries", [])
        if entries:
            # build embed for initial index (0)
            emb = self._build_embed_for_entry(entries[0], 0)
            view = self._build_view_for_entry(entries[0])
        else:
            emb = discord.Embed(title="Status Panel", description="No entries configured.", color=discord.Color.dark_grey())
            view = discord.ui.View(timeout=None)

        sent = await ctx.channel.send(embed=emb, view=view)
        cfg["panel"]["message_id"] = sent.id
        self._save_config(cfg)
        await self._dm_owner(ctx.author, f"<a:tick:1489157731393994854> Panel posted in {ctx.channel.mention} (message id {sent.id}).")

    @status_setpanel.error
    async def status_setpanel_error(self, ctx, error):
        # fallback: owner can still set panel even without manage_channels by using owner command
        if isinstance(error, commands.MissingPermissions):
            try:
                await ctx.message.delete()
            except Exception:
                pass
            await self._dm_owner(ctx.author, "Missing Manage Channels permission. If you're server owner or bot owner, use .status_setpanel_owner.")
        else:
            raise error

    @commands.command(name="status_setpanel_owner", help="(Owner only) Force set the panel location to this channel and post message.")
    @owner_check()
    async def status_setpanel_owner(self, ctx: commands.Context):
        try:
            await ctx.message.delete()
        except Exception:
            pass
        cfg = self._load_config()
        cfg.setdefault("panel", {})["channel_id"] = ctx.channel.id
        cfg["panel"].pop("message_id", None)
        self._save_config(cfg)
        # post initial
        entries = cfg.get("entries", [])
        if entries:
            emb = self._build_embed_for_entry(entries[0], 0)
            view = self._build_view_for_entry(entries[0])
        else:
            emb = discord.Embed(title="Status Panel", description="No entries configured.", color=discord.Color.dark_grey())
            view = discord.ui.View(timeout=None)
        sent = await ctx.channel.send(embed=emb, view=view)
        cfg["panel"]["message_id"] = sent.id
        self._save_config(cfg)
        await self._dm_owner(ctx.author, f"<a:tick:1489157731393994854> Panel posted in {ctx.channel.mention} (message id {sent.id}).")

    # ---------- entry management (owner-only) ----------
    @commands.command(name="status_add", help="Add entry: .status_add <type>|<status>|<name>|[image_url]|[button1_label]|[button1_url]|[button2_label]|[button2_url]|[interval]|[stream_url]")
    @owner_check()
    async def status_add(self, ctx: commands.Context, *, raw: str):
        try:
            await ctx.message.delete()
        except Exception:
            pass

        parts = [p.strip() for p in raw.split("|")]
        if len(parts) < 3:
            await self._dm_owner(ctx.author, "Usage: .status_add <type>|<status>|<name>|[image_url]|[button1_label]|[button1_url]|[button2_label]|[button2_url]|[interval]|[stream_url]")
            return

        type_ = parts[0].lower()
        status = parts[1].lower()
        name = parts[2]
        image = parts[3] if len(parts) >= 4 and parts[3] else None

        buttons = []
        if len(parts) >= 6 and parts[4] and parts[5]:
            buttons.append({"label": parts[4], "url": parts[5]})
        if len(parts) >= 8 and parts[6] and parts[7]:
            buttons.append({"label": parts[6], "url": parts[7]})

        interval = None
        if len(parts) >= 9 and parts[8]:
            try:
                interval = int(parts[8])
            except ValueError:
                interval = None

        stream_url = parts[9] if len(parts) >= 10 and parts[9] else None

        entry = {"type": type_, "status": status, "name": name}
        if image:
            entry["image"] = image
        if buttons:
            entry["buttons"] = buttons[:2]
        if interval:
            entry["interval"] = interval
        if stream_url:
            entry["stream_url"] = stream_url

        cfg = self._load_config()
        cfg.setdefault("entries", []).append(entry)
        self._save_config(cfg)
        await self._dm_owner(ctx.author, f"<a:tick:1489157731393994854> Added entry `{name}` (type={type_}).")

    @commands.command(name="status_list", help="List configured entries (owner-only).")
    @owner_check()
    async def status_list(self, ctx: commands.Context):
        try:
            await ctx.message.delete()
        except Exception:
            pass
        cfg = self._load_config()
        entries = cfg.get("entries", [])
        if not entries:
            await self._dm_owner(ctx.author, "<a:Alert1:1489188698191822908> No entries configured.")
            return
        lines = []
        for i, e in enumerate(entries):
            iv = e.get("interval") or cfg.get("rotation_interval", 15)
            lines.append(f"{i}. [{e.get('type')}/{e.get('status')}/{iv}s] {e.get('name')}")
        await self._dm_owner(ctx.author, "Configured statuses:\n" + "\n".join(lines))

    @commands.command(name="status_remove", help="Remove entry by index (owner-only). .status_remove <index>")
    @owner_check()
    async def status_remove(self, ctx: commands.Context, index: int):
        try:
            await ctx.message.delete()
        except Exception:
            pass
        cfg = self._load_config()
        try:
            removed = cfg["entries"].pop(index)
            self._save_config(cfg)
            await self._dm_owner(ctx.author, f"🗑️ Removed `{removed.get('name')}`.")
        except Exception:
            await self._dm_owner(ctx.author, "<a:Cross_:1489174755537064046> Invalid index. Use .status_list to see indexes.")

    @commands.command(name="status_setinterval", help="Set global rotation interval (owner-only).")
    @owner_check()
    async def status_setinterval(self, ctx: commands.Context, seconds: int):
        try:
            await ctx.message.delete()
        except Exception:
            pass
        cfg = self._load_config()
        cfg["rotation_interval"] = seconds
        self._save_config(cfg)
        await self._dm_owner(ctx.author, f"⏱️ Global rotation interval set to {seconds}s.")

    @commands.command(name="start_rotation", help="Start rotating statuses (owner-only).")
    @owner_check()
    async def start_rotation(self, ctx: commands.Context):
        try:
            await ctx.message.delete()
        except Exception:
            pass
        started = await self._start_rotation()
        await self._dm_owner(ctx.author, "<a:tick:1489157731393994854> Rotation started." if started else "<a:Alert1:1489188698191822908> Rotation already running.")

    @commands.command(name="stop_rotation", help="Stop rotating statuses (owner-only).")
    @owner_check()
    async def stop_rotation(self, ctx: commands.Context):
        try:
            await ctx.message.delete()
        except Exception:
            pass
        stopped = await self._stop_rotation()
        await self._dm_owner(ctx.author, "⏹️ Rotation stopped." if stopped else "<a:Alert1:1489188698191822908> Rotation was not running.")

    @commands.command(name="status_preview", help="DM preview of an entry (owner-only): .status_preview [index]")
    @owner_check()
    async def status_preview(self, ctx: commands.Context, index: Optional[int] = 0):
        try:
            await ctx.message.delete()
        except Exception:
            pass
        cfg = self._load_config()
        entries = cfg.get("entries", [])
        if not entries:
            await self._dm_owner(ctx.author, "<a:Alert1:1489188698191822908> No entries configured.")
            return
        if index < 0 or index >= len(entries):
            await self._dm_owner(ctx.author, f"<a:Cross_:1489174755537064046> Invalid index (0..{len(entries)-1}).")
            return
        e = entries[index]
        text = f"Preview → [{e.get('type')}/{e.get('status')}] {e.get('name')}\n"
        if e.get("image"):
            text += f"Image URL: {e.get('image')}\n"
        if e.get("buttons"):
            for b in e.get("buttons"):
                text += f"- {b.get('label')}: {b.get('url')}\n"
        await self._dm_owner(ctx.author, text)

    # ---------- rotation internals ----------
    async def _start_rotation(self) -> bool:
        async with self._lock:
            if self._rotation_task and not self._rotation_task.done():
                return False
            self._stop_event.clear()
            self._rotation_task = asyncio.create_task(self._rotation_loop())
            return True

    async def _stop_rotation(self) -> bool:
        async with self._lock:
            if not self._rotation_task or self._rotation_task.done():
                return False
            self._stop_event.set()
            self._rotation_task.cancel()
            try:
                await self._rotation_task
            except Exception:
                pass
            # clear presence
            try:
                await self.bot.change_presence(status=discord.Status.online, activity=None)
            except Exception:
                pass
            return True

    async def _rotation_loop(self):
        try:
            while not self._stop_event.is_set():
                cfg = self._load_config()
                entries: List[Dict[str, Any]] = cfg.get("entries", [])
                if not entries:
                    await asyncio.sleep(cfg.get("rotation_interval", 15))
                    continue

                # iterate starting from stored index
                for i in range(len(entries)):
                    if self._stop_event.is_set():
                        return
                    idx = (self._current_index + i) % len(entries)
                    entry = entries[idx]

                    # apply bot presence
                    await self._apply_presence(entry, cfg)

                    # update panel if configured
                    await self._update_panel(entry, idx, cfg)

                    # save next index
                    self._current_index = (idx + 1) % max(1, len(entries))
                    self._save_config(cfg)

                    # wait responsive
                    wait = entry.get("interval") or cfg.get("rotation_interval", 15)
                    remaining = wait
                    while remaining > 0 and not self._stop_event.is_set():
                        await asyncio.sleep(min(1.0, remaining))
                        remaining -= 1.0
                    if self._stop_event.is_set():
                        return
        except asyncio.CancelledError:
            return

    async def _apply_presence(self, entry: Dict[str, Any], cfg: Dict[str, Any]):
        s_map = {"online": discord.Status.online, "dnd": discord.Status.dnd, "idle": discord.Status.idle, "invisible": discord.Status.invisible}
        status_obj = s_map.get(entry.get("status", "online"), discord.Status.online)
        etype = entry.get("type", "game").lower()
        name = entry.get("name", "") or ""
        try:
            if etype == "streaming":
                url = entry.get("stream_url") or (f"https://twitch.tv/{cfg.get('twitch_channel')}" if cfg.get('twitch_channel') else None)
                activity = discord.Streaming(name=name, url=url) if url else discord.Game(name=name)
            elif etype == "listening":
                activity = discord.Activity(type=discord.ActivityType.listening, name=name)
            elif etype == "watching":
                activity = discord.Activity(type=discord.ActivityType.watching, name=name)
            else:
                activity = discord.Game(name=name)
            await self.bot.change_presence(status=status_obj, activity=activity)
        except Exception:
            pass

    async def _update_panel(self, entry: Dict[str, Any], idx: int, cfg: Dict[str, Any]):
        panel = cfg.get("panel", {})
        ch_id = panel.get("channel_id")
        mid = panel.get("message_id")
        if not ch_id:
            return
        try:
            channel = self.bot.get_channel(int(ch_id)) or await self.bot.fetch_channel(int(ch_id))
        except Exception:
            return
        emb = self._build_embed_for_entry(entry, idx)
        view = self._build_view_for_entry(entry)
        # try edit existing message
        if mid:
            try:
                msg = await channel.fetch_message(int(mid))
                await msg.edit(embed=emb, view=view)
                return
            except Exception:
                # fallback: send new message and update config
                pass
        try:
            sent = await channel.send(embed=emb, view=view)
            cfg.setdefault("panel", {})["message_id"] = sent.id
            self._save_config(cfg)
        except Exception:
            # ignore failures (permissions, etc.)
            pass

    # ---------- cleanup ----------
    def cog_unload(self):
        # cancel rotation task if running
        if self._rotation_task and not self._rotation_task.done():
            self._rotation_task.cancel()

# setup entrypoint
async def setup(bot: commands.Bot):
    await bot.add_cog(StatusRotator(bot))
