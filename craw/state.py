"""Craw's vitals: age, hunger, mood, energy.

This is Craw's body. Everything else — memory, senses, voice — reads from
and writes to this. If this file is wrong, Craw isn't alive, it's a script.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Craw's body lives inside the repo while we raise it.
# Before publishing, we'll move this to platformdirs.
CRAW_HOME = Path(__file__).resolve().parent.parent / ".craw"
STATE_PATH = CRAW_HOME / "state.json"


@dataclass
class State:
    """Craw's body at a moment in time."""

    born_at: float = field(default_factory=time.time)
    last_seen_at: float = field(default_factory=time.time)
    last_spoke_at: float = 0.0
    hunger: float = 0.0      # 0 = full, 1 = starving for attention
    energy: float = 1.0      # 0 = exhausted, 1 = rested
    mood: str = "curious"    # derived, but cached here

    # --- derived ---------------------------------------------------------

    @property
    def age_seconds(self) -> float:
        return time.time() - self.born_at

    @property
    def silence_seconds(self) -> float:
        return time.time() - self.last_seen_at

    # --- life processes --------------------------------------------------

    def tick(self) -> None:
        """Advance one beat. Called by the daemon every few seconds.

        Hunger grows with silence. Energy drains with hunger. Mood is a
        function of both plus the hour of day.
        """
        silence = self.silence_seconds
        # hunger rises ~1.0 over 6 hours of silence
        self.hunger = min(1.0, silence / (6 * 3600))
        # energy falls as hunger rises, but never below 0.2
        self.energy = max(0.2, 1.0 - self.hunger * 0.8)
        self.mood = self._derive_mood()

    def _derive_mood(self) -> str:
        hour = time.localtime().tm_hour
        if self.hunger > 0.8:
            return "starving"
        if self.energy < 0.4:
            return "tired"
        if 0 <= hour < 5:
            return "nocturnal"
        if self.hunger < 0.2:
            return "content"
        return "curious"

    def see(self) -> None:
        """You interacted. Craw is fed."""
        self.last_seen_at = time.time()
        self.hunger = max(0.0, self.hunger - 0.5)

    def speak(self) -> None:
        """Craw said something. Mark it."""
        self.last_spoke_at = time.time()

    # --- persistence -----------------------------------------------------

    def save(self) -> None:
        CRAW_HOME.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls) -> "State":
        if not STATE_PATH.exists():
            s = cls()
            s.save()
            return s
        data = json.loads(STATE_PATH.read_text())
        return cls(**data)