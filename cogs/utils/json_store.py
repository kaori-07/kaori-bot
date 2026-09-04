# cogs/utils/json_store.py
"""
Shared, hot-reloading JSON file store.

Several cogs read/write the same data files (e.g. wallet.py and config.py both
touch wallet.json). Previously each cog cached its own private copy in memory
at startup, so a change made through one cog was invisible to the other until
a full restart. get_store() returns a process-wide singleton per filename, so
every cog that asks for "wallet.json" shares the same in-memory dict and the
same on-disk file - writes from one are immediately visible to the other, and
the dashboard can safely read/write the same files too.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Union

_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _ROOT / "data"
_registry: Dict[str, "JSONStore"] = {}
_registry_lock = threading.Lock()


class JSONStore:
    def __init__(self, filename: str, default: Union[Callable[[], Any], Any] = dict):
        self.path = _DATA_DIR / filename
        self._lock = threading.RLock()
        self._default = default
        self._data: Any = self._make_default()
        self._mtime: float = -1.0
        self._load(force=True)

    def _make_default(self):
        return self._default() if callable(self._default) else self._default

    def _load(self, force: bool = False) -> None:
        with self._lock:
            try:
                mtime = self.path.stat().st_mtime
            except FileNotFoundError:
                if force:
                    self._save_unlocked()
                return
            if not force and mtime == self._mtime:
                return
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    self._data = json.load(fh)
                self._mtime = mtime
            except Exception:
                # keep last-good in-memory data rather than crash a command
                pass

    def _save_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=2, ensure_ascii=False)
        try:
            self._mtime = self.path.stat().st_mtime
        except FileNotFoundError:
            pass

    def read(self) -> Any:
        """Return the live (auto-refreshed) in-memory object. Mutate in place,
        then call save() to persist."""
        with self._lock:
            self._load()
            return self._data

    def save(self, data: Any = None) -> None:
        with self._lock:
            if data is not None:
                self._data = data
            self._save_unlocked()

    def mutate(self, fn: Callable[[Any], Any]) -> Any:
        """Run fn(data) -> new_data under the lock, then persist it."""
        with self._lock:
            self._load()
            self._data = fn(self._data)
            self._save_unlocked()
            return self._data


def get_store(filename: str, default: Union[Callable[[], Any], Any] = dict) -> JSONStore:
    """Return the process-wide singleton JSONStore for this filename."""
    with _registry_lock:
        if filename not in _registry:
            _registry[filename] = JSONStore(filename, default)
        return _registry[filename]
