# cogs/utils/emoji_manager.py
"""
Central emoji loader.

Every emoji used anywhere in the bot lives in emoji.json (project root).
To change an emoji, edit emoji.json (by hand or via the web dashboard) -
there is no need to touch any cog file or run a replace script.

Usage in a cog:

    from cogs.utils.emoji_manager import EMOJI

    await ctx.send(f"{EMOJI['success']} Done!")

The store re-checks the file's mtime on every access (cheap os.stat call)
and reloads automatically when the file changes, so edits apply live
without restarting the bot.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Dict

# project_root/cogs/utils/emoji_manager.py -> parents[2] == project_root
EMOJI_FILE = Path(__file__).resolve().parents[2] / "emoji.json"
DEFAULTS_FILE = Path(__file__).resolve().parents[2] / "emoji_defaults.json"

# Fallback defaults used only if emoji.json is missing/corrupt, so the bot
# never crashes just because someone left the file in a bad state.
DEFAULT_EMOJIS: Dict[str, str] = {
    "success": "\u2705",
    "error": "\u274c",
    "warning": "\u26a0\ufe0f",
    "loading": "\u23f3",
    "info": "\u2139\ufe0f",
}


class EmojiStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.RLock()
        self._cache: Dict[str, str] = {}
        self._mtime: float = -1.0
        self._load(force=True)

    # -------------------------------------------------------------
    def _load(self, force: bool = False) -> None:
        with self._lock:
            try:
                mtime = self._path.stat().st_mtime
            except FileNotFoundError:
                if force or not self._cache:
                    self._cache = dict(DEFAULT_EMOJIS)
                    self._save_unlocked()
                return

            if not force and mtime == self._mtime:
                return  # unchanged since last read

            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    self._cache = {str(k): str(v) for k, v in data.items()}
                    self._mtime = mtime
            except Exception:
                # keep the last good cache instead of crashing the bot
                if not self._cache:
                    self._cache = dict(DEFAULT_EMOJIS)

    def _save_unlocked(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fh:
            json.dump(self._cache, fh, indent=2, ensure_ascii=False, sort_keys=True)
        try:
            self._mtime = self._path.stat().st_mtime
        except FileNotFoundError:
            pass

    # -------------------------------------------------------------
    # Public API
    def get(self, key: str, default: str = "") -> str:
        self._load()
        return self._cache.get(key, default)

    def __getitem__(self, key: str) -> str:
        self._load()
        # missing key -> show a visible placeholder instead of raising,
        # so a typo'd slug doesn't crash a command
        return self._cache.get(key, f":{key}:")

    def __contains__(self, key: str) -> bool:
        self._load()
        return key in self._cache

    def all(self) -> Dict[str, str]:
        self._load()
        return dict(self._cache)

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._load()
            self._cache[key] = value
            self._save_unlocked()

    def delete(self, key: str) -> bool:
        with self._lock:
            self._load()
            if key in self._cache:
                del self._cache[key]
                self._save_unlocked()
                return True
            return False

    def update_many(self, mapping: Dict[str, str]) -> None:
        with self._lock:
            self._load()
            self._cache.update(mapping)
            self._save_unlocked()

    def reload(self) -> None:
        self._load(force=True)

    # -------------------------------------------------------------
    # Defaults (shipped reference values, never edited by the dashboard)
    def get_default(self, key: str) -> str | None:
        try:
            with open(DEFAULTS_FILE, "r", encoding="utf-8") as fh:
                defaults = json.load(fh)
            return defaults.get(key)
        except Exception:
            return None

    def all_defaults(self) -> Dict[str, str]:
        try:
            with open(DEFAULTS_FILE, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def reset_to_default(self, key: str) -> bool:
        default = self.get_default(key)
        if default is None:
            return False
        self.set(key, default)
        return True


EMOJI = EmojiStore(EMOJI_FILE)
