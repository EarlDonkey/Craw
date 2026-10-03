"""The wire between Craw's brain and whatever is wearing its face.

Right now the face is PowerShell. Later it'll be voice, a web page, a
window. The protocol stays the same: newline-delimited JSON, one
request, one response.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class Face:
    """What the prompt should show."""

    glyph: str        # the mood character
    color: str        # "green", "yellow", "red", "cyan", "dim"
    mood: str         # "content", "curious", "hungry", ...
    age_min: int      # how old Craw is, in minutes


@dataclass
class Message:
    """A thing Craw wants to say. Empty text = silence."""

    text: str = ""
    kind: str = "idle"  # "idle" | "thought" | "reply"


@dataclass
class Response:
    """What PowerShell gets back when it asks the daemon."""

    face: Face
    message: Message

    def to_json(self) -> str:
        return json.dumps(
            {
                "face": asdict(self.face),
                "message": asdict(self.message),
            }
        )


def face_for_mood(mood: str, age_min: int) -> Face:
    """Map a mood to a glyph and a color. This is Craw's face."""
    table: dict[str, tuple[str, str]] = {
        "content":   ("•", "green"),
        "curious":   ("✳", "cyan"),
        "hungry":    ("◌", "yellow"),
        "tired":     ("…", "dim"),
        "starving":  ("!", "red"),
        "nocturnal": ("☾", "magenta"),
    }
    glyph, color = table.get(mood, ("•", "green"))
    return Face(glyph=glyph, color=color, mood=mood, age_min=age_min)


def parse_request(line: str) -> dict[str, Any]:
    """PowerShell sends one JSON object per line."""
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return {}