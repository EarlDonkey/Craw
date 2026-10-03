"""Craw's memory. Three kinds of remembering.

- observations: things Craw noticed about you
- conversations: things you said to each other
- thoughts: Craw's internal monologue, unspoken

Everything goes in one sqlite file inside Craw's home. No ORM, no magic.
The schema is the model.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal

from craw.state import CRAW_HOME

DB_PATH = CRAW_HOME / "craw.db"

Kind = Literal["observation", "conversation", "thought"]


@dataclass
class Entry:
    id: int
    kind: Kind
    at: float
    text: str
    meta: dict[str, Any]

    @property
    def age_seconds(self) -> float:
        return time.time() - self.at


SCHEMA = """
CREATE TABLE IF NOT EXISTS entries (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    kind    TEXT    NOT NULL,
    at      REAL    NOT NULL,
    text    TEXT    NOT NULL,
    meta    TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_entries_kind_at ON entries (kind, at DESC);
"""


class Memory:
    """Craw's past. Open once, use forever, close when the daemon dies."""

    def __init__(self, path: Path = DB_PATH) -> None:
        CRAW_HOME.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # --- writing ---------------------------------------------------------

    def remember(
        self,
        kind: Kind,
        text: str,
        meta: dict[str, Any] | None = None,
    ) -> Entry:
        at = time.time()
        cur = self.conn.execute(
            "INSERT INTO entries (kind, at, text, meta) VALUES (?, ?, ?, ?)",
            (kind, at, text, json.dumps(meta or {})),
        )
        self.conn.commit()
        return Entry(
            id=cur.lastrowid,
            kind=kind,
            at=at,
            text=text,
            meta=meta or {},
        )

    def observe(self, text: str, **meta: Any) -> Entry:
        return self.remember("observation", text, meta)

    def say(self, text: str, **meta: Any) -> Entry:
        return self.remember("conversation", text, meta)

    def think(self, text: str, **meta: Any) -> Entry:
        return self.remember("thought", text, meta)

    # --- reading ---------------------------------------------------------

    def recent(self, kind: Kind | None = None, limit: int = 20) -> list[Entry]:
        if kind is None:
            rows = self.conn.execute(
                "SELECT * FROM entries ORDER BY at DESC LIMIT ?", (limit,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM entries WHERE kind = ? ORDER BY at DESC LIMIT ?",
                (kind, limit),
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def since(self, kind: Kind, seconds: float) -> list[Entry]:
        cutoff = time.time() - seconds
        rows = self.conn.execute(
            "SELECT * FROM entries WHERE kind = ? AND at >= ? ORDER BY at ASC",
            (kind, cutoff),
        ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def count(self, kind: Kind | None = None) -> int:
        if kind is None:
            row = self.conn.execute("SELECT COUNT(*) AS n FROM entries").fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) AS n FROM entries WHERE kind = ?", (kind,)
            ).fetchone()
        return int(row["n"])

    # --- helpers ---------------------------------------------------------

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> Entry:
        return Entry(
            id=row["id"],
            kind=row["kind"],
            at=row["at"],
            text=row["text"],
            meta=json.loads(row["meta"]),
        )

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> "Memory":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()