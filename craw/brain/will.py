"""Craw's willingness to speak.

Craw has many impulses. It should voice very few of them. This gate
enforces that: threshold, cooldown, hourly cap. Nothing here is clever.
It's discipline.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from craw.brain.reflexes import Impulse
from craw.state import CRAW_HOME

CONFIG_PATH = CRAW_HOME / "config.json"


@dataclass
class Will:
    threshold: float = 0.6
    cooldown_seconds: float = 900.0
    max_per_hour: int = 3

    _last_spoke_at: float = field(default_factory=lambda: 0.0, init=False)
    _recent_speaks: list[float] = field(default_factory=list, init=False)

    def should_speak(self, impulse: Impulse) -> bool:
        now = time.time()
        if impulse.urgency < self.threshold:
            return False
        if now - self._last_spoke_at < self.cooldown_seconds:
            return False
        self._recent_speaks = [t for t in self._recent_speaks if now - t < 3600]
        if len(self._recent_speaks) >= self.max_per_hour:
            return False
        return True

    def spoke(self) -> None:
        now = time.time()
        self._last_spoke_at = now
        self._recent_speaks.append(now)

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Will":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        return cls(
            threshold=float(data.get("speak_threshold", 0.6)),
            cooldown_seconds=float(data.get("speak_cooldown_seconds", 900)),
            max_per_hour=int(data.get("speak_max_per_hour", 3)),
        )