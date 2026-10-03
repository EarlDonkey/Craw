"""Craw's voice.

Takes an impulse and composes a line. Rules for now; the LLM version
arrives later and will use this as a fallback and a floor. A creature
should be able to say something small without thinking hard.

Rules of the voice:
  - one line
  - no exclamation marks
  - no emoji
  - lowercase is fine
  - silence is better than filler
"""

from __future__ import annotations

import random

from craw.brain.reflexes import Impulse

# Per-reason phrase pools. Kept small on purpose.
PHRASES: dict[str, list[str]] = {
    "repetition": [
        "{subject}",
        "{subject}. want to talk about it?",
        "{subject}. that's a lot.",
    ],
    "late_night": [
        "{subject}",
        "still up. {subject}",
        "{subject}. sleep is a thing.",
    ],
    "silence": [
        "{subject}",
        "{subject}. i noticed.",
        "still here. {subject}",
    ],
    "novelty": [
        "{subject}",
        "{subject}. new?",
    ],
}

FALLBACK = ["{subject}"]


def compose(impulse: Impulse) -> str:
    """Turn an impulse into a single spoken line."""
    pool = PHRASES.get(impulse.reason, FALLBACK)
    template = random.choice(pool)
    line = template.format(subject=impulse.subject)
    return _tidy(line)


def _tidy(line: str) -> str:
    line = " ".join(line.split())
    while line.endswith(("..", "!!", "??")):
        line = line[:-1]
    return line