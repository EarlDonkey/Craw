"""The shape every sense wears.

A sense has a name, a tick interval, and a `sense()` method that returns
zero or more observations. Observations are plain sentences — the brain
turns them into memory entries. Keeping senses dumb and the brain smart
means adding a new sense never requires touching the brain.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class Observation:
    """One thing a sense noticed. Plain text plus structured meta."""

    text: str
    meta: dict[str, Any]
    source: str  # e.g. "shell", "clock", "fs"

    def __post_init__(self) -> None:
        self.meta.setdefault("source", self.source)


class Sense(Protocol):
    """A sense is anything with a name and a `sense()` method."""

    name: str
    interval_seconds: float

    def sense(self) -> list[Observation]:
        ...