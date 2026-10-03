"""Craw's milestones.

The firsts of a life: the first time you met, the first word spoken, the
first late night, the first hunger spike. These are written once and
never overwritten. They are the archaeology of the creature.

Stored in memory with meta tag `milestone=True` so they can be queried
out from everything else.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable

from craw.brain.memory import Entry, Memory


# Canonical firsts. Once each exists in memory, it is never written again.
FIRSTS = [
    "first_met",
    "first_spoke",
    "first_late_night",
    "first_hunger_spike",
    "first_loud_command",
    "first_multi_day_streak",
]


@dataclass
class Milestone:
    name: str
    at: float
    text: str


class Milestones:
    def __init__(self, memory: Memory) -> None:
        self.memory = memory
        self._seen: set[str] = set()

    def load(self) -> None:
        """Read existing milestones from memory so we don't duplicate."""
        rows = self.memory.recent("observation", limit=2000)
        for e in rows:
            name = e.meta.get("milestone")
            if name:
                self._seen.add(name)

    def has(self, name: str) -> bool:
        return name in self._seen

    def record(self, name: str, text: str) -> Milestone | None:
        """Write a milestone exactly once. Returns None if already recorded."""
        if name in self._seen:
            return None
        self.memory.observe(text, milestone=name, immutable=True)
        self._seen.add(name)
        return Milestone(name=name, at=time.time(), text=text)

    def all(self) -> list[Entry]:
        """Every milestone, oldest first."""
        rows = self.memory.recent("observation", limit=5000)
        milestones = [e for e in rows if e.meta.get("milestone")]
        milestones.sort(key=lambda e: e.at)
        return milestones

    def summary(self, limit: int = 8) -> str:
        """A short block for the LLM context."""
        ms = self.all()[-limit:]
        if not ms:
            return ""
        lines = ["Things you remember from your life so far:"]
        for e in ms:
            ago = _ago(e.at)
            lines.append(f"  - {ago}: {e.text}")
        return "\n".join(lines)


def _ago(t: float) -> str:
    secs = time.time() - t
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs / 60)}m ago"
    if secs < 86400:
        return f"{int(secs / 3600)}h ago"
    days = int(secs / 86400)
    return f"{days}d ago" if days > 1 else "yesterday"