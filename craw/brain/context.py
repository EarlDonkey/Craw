"""What Craw knows right now, in a few hundred words.

Built fresh every time Craw is about to speak. Reads recent memory,
current mood, mood trend, milestones, recent readings, and the last
exchange, and produces a compact context block.
"""

from __future__ import annotations

import time

from craw.brain.memory import Memory
from craw.brain.milestones import Milestones
from craw.brain.mood_log import MoodLog
from craw.brain.reading import Readings
from craw.state import State


def build(
    memory: Memory,
    state: State,
    *,
    recent_limit: int = 15,
    milestones: Milestones | None = None,
    mood_log: MoodLog | None = None,
) -> str:
    lines: list[str] = []

    lines.append(f"You are {state.age_seconds / 60:.0f} minutes old.")
    lines.append(f"Hunger: {state.hunger:.2f} (0 full, 1 starving).")
    lines.append(f"Energy: {state.energy:.2f}.")
    lines.append(f"Mood: {state.mood}.")
    hour = time.localtime().tm_hour
    lines.append(f"Local time: {hour:02d}:00.")

    if state.host_name:
        lines.append(f"The person you are speaking to is {state.host_name}.")
    else:
        lines.append("You do not yet know the person's name.")

    if mood_log is not None:
        trend = mood_log.trend(3600)
        if trend:
            lines.append(trend)

    lines.append("")

    if milestones is not None:
        ms = milestones.summary(limit=6)
        if ms:
            lines.append(ms)
            lines.append("")

    try:
        reading_block = Readings(memory).summary_block(limit=5)
        if reading_block:
            lines.append(reading_block)
            lines.append("")
    except Exception:
        pass

    recent_obs = memory.recent("observation", limit=recent_limit)
    if recent_obs:
        lines.append("Things you recently noticed:")
        for e in recent_obs:
            if e.meta.get("milestone"):
                continue
            lines.append(f"  - {e.text}")
        lines.append("")

    recent_convo = memory.recent("conversation", limit=6)
    if recent_convo:
        lines.append("Recent exchanges:")
        for e in recent_convo:
            lines.append(f"  - {e.text}")
        lines.append("")

    recent_thoughts = memory.recent("thought", limit=5)
    if recent_thoughts:
        lines.append("Things you were thinking about:")
        for e in recent_thoughts:
            lines.append(f"  - {e.text}")

    return "\n".join(lines)