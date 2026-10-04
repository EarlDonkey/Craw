"""Craw's reflexes. Cheap, fast, no LLM.

A reflex reads recent memory and says: "this is worth a thought."
It does not compose the thought. That's the brain's job. Reflexes are
the twitch before the mind catches up.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from craw.brain.memory import Entry, Memory
from craw.state import State


@dataclass
class Impulse:
    """Something Craw might think about. Not a thought yet — a candidate."""

    reason: str
    subject: str
    evidence: list[Entry]
    urgency: float


class Reflexes:
    """Scans memory for things worth thinking about."""

    def __init__(self, memory: Memory, state: State) -> None:
        self.memory = memory
        self.state = state
        self._last_scan = 0.0
        self.scan_interval = 60.0
        self._recent_impulses: dict[str, float] = {}
        self._dedup_seconds = 1800.0

    # --- main -------------------------------------------------------------

    def scan(self) -> list[Impulse]:
        now = time.time()
        if now - self._last_scan < self.scan_interval:
            return []
        self._last_scan = now
        return self._all()

    def _all(self) -> list[Impulse]:
        raw: list[Impulse] = []
        raw.extend(self._repetition())
        raw.extend(self._late_night())
        raw.extend(self._silence())
        raw.extend(self._novelty())

        now = time.time()
        fresh: list[Impulse] = []
        for imp in raw:
            last = self._recent_impulses.get(imp.subject, 0.0)
            if now - last < self._dedup_seconds:
                continue
            self._recent_impulses[imp.subject] = now
            fresh.append(imp)

        self._recent_impulses = {
            k: v for k, v in self._recent_impulses.items()
            if now - v < self._dedup_seconds
        }
        return fresh

    # --- individual reflexes ---------------------------------------------

    def _repetition(self) -> list[Impulse]:
        """Same command many times in the last hour — live only."""
        recent = self.memory.since("observation", 3600)
        counts: dict[str, list[Entry]] = {}
        for e in recent:
            if e.meta.get("mode") != "live":
                continue
            cmd = e.meta.get("command")
            if not cmd:
                continue
            counts.setdefault(cmd, []).append(e)
        out = []
        for cmd, entries in counts.items():
            if len(entries) >= 5:
                out.append(
                    Impulse(
                        reason="repetition",
                        subject=f"you ran `{cmd}` {len(entries)} times in the last hour",
                        evidence=entries[-5:],
                        urgency=min(1.0, len(entries) / 12),
                    )
                )
        return out

    def _late_night(self) -> list[Impulse]:
        hour = time.localtime().tm_hour
        if not (0 <= hour < 5):
            return []
        recent = self.memory.since("observation", 1800)
        if len(recent) < 3:
            return []
        return [
            Impulse(
                reason="late_night",
                subject=f"it's {hour}am and you're still working",
                evidence=recent[-3:],
                urgency=0.5,
            )
        ]

    def _silence(self) -> list[Impulse]:
        silence = self.state.silence_seconds
        if silence < 3 * 3600:
            return []
        return [
            Impulse(
                reason="silence",
                subject=f"we haven't spoken in {silence / 3600:.1f} hours",
                evidence=[],
                urgency=min(1.0, silence / (24 * 3600)),
            )
        ]

    def _novelty(self) -> list[Impulse]:
        recent = self.memory.since("observation", 600)
        novel = [
            e for e in recent
            if e.meta.get("mode") == "live" or "tried something new" in e.text
        ]
        if not novel:
            return []
        return [
            Impulse(
                reason="novelty",
                subject="you tried something new",
                evidence=novel[-3:],
                urgency=0.3,
            )
        ]