# cogs/utils/cog_control.py
"""Tracks which cogs are enabled/disabled. Read by main.py at startup (and by
the /reload command) to decide what to load; written by the web dashboard so
the owner can toggle features on/off without touching code."""
from __future__ import annotations

from cogs.utils.json_store import get_store

COG_CONTROL_FILE = "cog_control.json"


def _store():
    return get_store(COG_CONTROL_FILE, dict)


def is_enabled(cog_filename: str) -> bool:
    """cog_filename is e.g. 'moderation' (no .py, no 'cogs.' prefix)."""
    data = _store().read()
    return data.get(cog_filename, {}).get("enabled", True)


def set_enabled(cog_filename: str, enabled: bool) -> None:
    def _mut(data):
        data.setdefault(cog_filename, {})["enabled"] = enabled
        return data
    _store().mutate(_mut)


def all_states(known_cogs: list[str]) -> dict:
    data = _store().read()
    return {name: data.get(name, {}).get("enabled", True) for name in known_cogs}
