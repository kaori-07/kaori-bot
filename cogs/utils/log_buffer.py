# cogs/utils/log_buffer.py
"""A tiny in-memory logging handler that keeps the last N log records so the
web dashboard can show a live "console" without needing to tail a file."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Deque, Dict, List


class RingBufferHandler(logging.Handler):
    def __init__(self, capacity: int = 300):
        super().__init__()
        self._buf: Deque[Dict] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._seq = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:
            msg = record.getMessage()
        with self._lock:
            self._seq += 1
            self._buf.append({
                "id": self._seq,
                "ts": time.time(),
                "level": record.levelname,
                "message": msg,
            })

    def since(self, last_id: int = 0) -> List[Dict]:
        with self._lock:
            return [r for r in self._buf if r["id"] > last_id]

    def all(self) -> List[Dict]:
        with self._lock:
            return list(self._buf)


# process-wide singleton so main.py and dashboard/app.py share the same buffer
LOG_BUFFER = RingBufferHandler()
LOG_BUFFER.setFormatter(logging.Formatter("%(message)s"))
