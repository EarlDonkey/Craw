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

    reason: str          # short tag: "repetition", "silence", "late_night", ...
    subject: str         # what it's about, human readable
    evidence: list[Entry]  # memory entries that triggered it
    urgency: float       # 0..1 — how much Craw wants to speak


class Reflexes:
    """Scans memory for things worth thinking about."""

    def __init__(self, memory: Memory, state: State) -> None:
        self.memory = memory
        self.state = state
        self._last_scan = 0.0
        self.scan_interval = 60.0  # seconds between scans

    # --- main -------------------------------------------------------------

    def scan(self) -> list[Impulse]:
        now = time.time()
        if now - self._last_scan < self.scan_interval:
            return []
        self._last_scan = now
        return self._all()

    # --- individual reflexes ---------------------------------------------

    def _all(self) -> list[Impulse]:
        out: list[Impulse] = []
        out.extend(self._repetition())
        out.extend(self._late_night())
        out.extend(self._silence())
        out.extend(self._novelty())
        return out

    def _repetition(self) -> list[Impulse]:
        """Same command many times in the last hour."""
        recent = self.memory.since("observation", 3600)
        counts: dict[str, list[Entry]] = {}
        for e in recent:
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
        """It's late and Craw has seen you recently."""
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
        """Long silence followed by activity, or just long silence."""
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
        """A command Craw has never seen before."""
        recent = self.memory.since("observation", 600)
        novel = [e for e in recent if e.meta.get("mode") == "live" or "tried something new" in e.text]
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