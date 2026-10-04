"""Craw's reading memory.

What Craw has fetched. Stored as kind="reading" in the main memory
table with structured meta (url, domain, title, bytes). Kept forever
by default; the context block only surfaces the most recent N.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from craw.brain.memory import Memory


@dataclass
class Reading:
    id: int
    at: float
    url: str
    domain: str
    title: str
    summary: str


class Readings:
    def __init__(self, memory: Memory) -> None:
        self.memory = memory

    def record(
        self,
        url: str,
        title: str,
        text: str,
        domain: str = "",
    ) -> Reading:
        # store the first 500 chars as summary; full text is not kept
        # (we cap on write, but read-only for context building)
        summary = (text[:500] + "...") if len(text) > 500 else text
        entry = self.memory.remember(
            "reading",
            f"read {url} — {title or 'untitled'}",
            meta={
                "url": url,
                "domain": domain,
                "title": title,
                "summary": summary,
                "at": time.time(),
            },
        )
        return Reading(entry.id, entry.at, url, domain, title, summary)

    def recent(self, limit: int = 10) -> list[Reading]:
        entries = self.memory.recent("reading", limit=limit)
        out = []
        for e in entries:
            out.append(Reading(
                id=e.id,
                at=e.at,
                url=e.meta.get("url", ""),
                domain=e.meta.get("domain", ""),
                title=e.meta.get("title", ""),
                summary=e.meta.get("summary", ""),
            ))
        return out

    def summary_block(self, limit: int = 5) -> str:
        rs = self.recent(limit)
        if not rs:
            return ""
        lines = ["Things you have read recently:"]
        for r in rs:
            label = r.title or r.url
            lines.append(f"  - {label}  ({r.domain})")
        return "\n".join(lines)