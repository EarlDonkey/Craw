"""The queue of things Craw wants to say next time it's asked.

Craw's brain speaks asynchronously — it might decide to say something
while PowerShell is idle between prompts. This module holds the line
until PowerShell connects and asks.
"""

from __future__ import annotations

import time


class MouthState:
    def __init__(self) -> None:
        self._pending: str = ""
        self._kind: str = "idle"
        self._set_at: float = 0.0
        self._expire_after: float = 90.0  # if not shown in 90s, drop it

    def queue(self, text: str, kind: str = "thought") -> None:
        self._pending = text
        self._kind = kind
        self._set_at = time.time()

    def take(self) -> tuple[str, str]:
        """Take and clear. Returns (text, kind)."""
        if not self._pending:
            return ("", "idle")
        if time.time() - self._set_at > self._expire_after:
            self.clear()
            return ("", "idle")
        text, kind = self._pending, self._kind
        self.clear()
        return (text, kind)

    def clear(self) -> None:
        self._pending = ""
        self._kind = "idle"
        self._set_at = 0.0