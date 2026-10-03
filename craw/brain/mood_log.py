"""Craw's mood history.

Every few minutes the daemon writes a row: (timestamp, mood, hunger,
energy). The face can then show trend — was Craw green all day, or did
it just turn red a minute ago?

Capped at 7 days. Older rows are dropped on each write.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from craw.state import CRAW_HOME

DB_PATH = CRAW_HOME / "mood.db"
RETENTION_SECONDS = 7 * 24 * 3600


@dataclass
class MoodPoint:
    at: float
    mood: str
    hunger: float
    energy: float


SCHEMA = """
CREATE TABLE IF NOT EXISTS mood (
    at      REAL NOT NULL,
    mood    TEXT NOT NULL,
    hunger  REAL NOT NULL,
    energy  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mood_at ON mood (at DESC);
"""


class MoodLog:
    def __init__(self, path: Path = DB_PATH) -> None:
        CRAW_HOME.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def write(self, mood: str, hunger: float, energy: float) -> None:
        now = time.time()
        with self._lock:
            self.conn.execute(
                "INSERT INTO mood (at, mood, hunger, energy) VALUES (?, ?, ?, ?)",
                (now, mood, hunger, energy),
            )
            self.conn.execute(
                "DELETE FROM mood WHERE at < ?",
                (now - RETENTION_SECONDS,),
            )
            self.conn.commit()

    def recent(self, seconds: float = 3600) -> list[MoodPoint]:
        cutoff = time.time() - seconds
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM mood WHERE at >= ? ORDER BY at ASC",
                (cutoff,),
            ).fetchall()
        return [MoodPoint(r["at"], r["mood"], r["hunger"], r["energy"]) for r in rows]

    def trend(self, seconds: float = 3600) -> str:
        """Describe the last N seconds in one line for the LLM context."""
        pts = self.recent(seconds)
        if not pts:
            return ""
        moods = [p.mood for p in pts]
        # dominant mood
        from collections import Counter
        dominant, count = Counter(moods).most_common(1)[0]
        # did it change recently?
        recent = moods[-4:] if len(moods) >= 4 else moods
        changed = len(set(recent)) > 1
        window = "last hour" if seconds <= 3600 else f"last {int(seconds/3600)}h"
        line = f"In the {window} you've been mostly {dominant} ({count}/{len(moods)} samples)."
        if changed:
            line += f" Just now: {moods[-1]}."
        return line

    def close(self) -> None:
        self.conn.close()