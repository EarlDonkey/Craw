"""Craw's library.

Full-text search over everything Craw has read. Splits readings into
~400-word chunks, indexes them with SQLite FTS5. Given a query, returns
the top matching chunks with their source URL.

This is how Craw studies: not by memorizing titles, but by being able
to find the passage that answers a question.
"""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from craw.brain.memory import Memory, DB_PATH


CHUNK_WORDS = 400


LIBRARY_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS reading_fts USING fts5(
    reading_id UNINDEXED,
    url UNINDEXED,
    title UNINDEXED,
    chunk UNINDEXED,
    text,
    tokenize='porter'
);
"""


@dataclass
class Hit:
    reading_id: int
    url: str
    title: str
    chunk: int
    text: str
    score: float


class Library:
    """FTS index over Craw's readings."""

    def __init__(self, memory: Memory) -> None:
        self.memory = memory
        self._ensured = False
        self._lock = threading.RLock()

    def _ensure(self) -> None:
        if self._ensured:
            return
        with self._lock:
            if self._ensured:
                return
            self.memory.conn.executescript(LIBRARY_SCHEMA)
            self.memory.conn.commit()
            self._ensured = True

    # --- indexing ---------------------------------------------------------

    def index_reading(self, reading_id: int, url: str, title: str, text: str) -> int:
        """Split a reading into chunks and insert into FTS.

        Returns the number of chunks inserted.
        """
        self._ensure()
        chunks = _split_into_chunks(text, CHUNK_WORDS)
        if not chunks:
            return 0
        with self._lock:
            cur = self.memory.conn.cursor()
            # delete any prior chunks for this reading (idempotent reindex)
            cur.execute("DELETE FROM reading_fts WHERE reading_id = ?", (reading_id,))
            for i, chunk in enumerate(chunks):
                cur.execute(
                    "INSERT INTO reading_fts (reading_id, url, title, chunk, text) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (reading_id, url, title or "", i, chunk),
                )
            self.memory.conn.commit()
        return len(chunks)

    # --- searching --------------------------------------------------------

    def search(self, query: str, limit: int = 5) -> list[Hit]:
        """Full-text search. Returns the top N matching chunks."""
        self._ensure()
        q = _sanitize_fts_query(query)
        if not q:
            return []
        with self._lock:
            try:
                rows = self.memory.conn.execute(
                    "SELECT reading_id, url, title, chunk, text, "
                    "       bm25(reading_fts) AS score "
                    "FROM reading_fts "
                    "WHERE reading_fts MATCH ? "
                    "ORDER BY score "
                    "LIMIT ?",
                    (q, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                # bad FTS query — try a simpler one
                try:
                    rows = self.memory.conn.execute(
                        "SELECT reading_id, url, title, chunk, text, "
                        "       bm25(reading_fts) AS score "
                        "FROM reading_fts "
                        "WHERE text LIKE ? "
                        "LIMIT ?",
                        (f"%{query}%", limit),
                    ).fetchall()
                except sqlite3.OperationalError:
                    return []
        return [
            Hit(
                reading_id=r["reading_id"],
                url=r["url"],
                title=r["title"],
                chunk=r["chunk"],
                text=r["text"],
                score=r["score"],
            )
            for r in rows
        ]

    def search_and_format(self, query: str, limit: int = 3) -> str:
        """Format top hits for the LLM prompt."""
        hits = self.search(query, limit=limit)
        if not hits:
            return ""
        lines = [f"Here is what you have read about {query!r}:"]
        for i, h in enumerate(hits, 1):
            title = h.title or h.url
            snippet = h.text.strip()
            # cap each snippet
            if len(snippet) > 900:
                snippet = snippet[:900] + "..."
            lines.append(f"\n[{i}] {title}  ({h.url})")
            lines.append(snippet)
        return "\n".join(lines)


# --- helpers -------------------------------------------------------------

def _split_into_chunks(text: str, words_per_chunk: int) -> list[str]:
    """Split text into roughly N-word chunks on sentence boundaries."""
    # normalize
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current: list[str] = []
    current_words = 0
    for s in sentences:
        wc = len(s.split())
        if current_words + wc > words_per_chunk and current:
            chunks.append(" ".join(current))
            current = [s]
            current_words = wc
        else:
            current.append(s)
            current_words += wc
    if current:
        chunks.append(" ".join(current))
    return chunks


def _sanitize_fts_query(query: str) -> str:
    """Turn a raw question into a safe FTS5 query string.

    FTS5 has its own syntax with operators; user text can break it. We
    strip special characters and OR the meaningful words together.
    """
    words = re.findall(r"[A-Za-z0-9']+", query.lower())
    # drop stopwords
    stop = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been",
        "what", "who", "when", "where", "why", "how", "which",
        "of", "to", "in", "on", "at", "for", "with", "about",
        "and", "or", "but", "if", "then", "than", "so",
        "i", "you", "he", "she", "it", "we", "they",
        "me", "my", "your", "his", "her", "its", "our", "their",
        "do", "does", "did", "can", "could", "will", "would", "should",
        "tell", "give", "show", "say", "said",
    }
    meaningful = [w for w in words if w not in stop and len(w) > 2]
    if not meaningful:
        meaningful = words  # fall back to all words
    if not meaningful:
        return ""
    # OR them together; FTS5 ranks by bm25
    return " OR ".join(meaningful)