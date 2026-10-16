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
    hunger: float = 0.0
    energy: float = 1.0
    mood: str = "curious"

    # identity
    host_name: str = ""
    first_met_at: float = field(default_factory=time.time)

    # --- derived ---------------------------------------------------------

    @property
    def age_seconds(self) -> float:
        return time.time() - self.born_at

    @property
    def silence_seconds(self) -> float:
        return time.time() - self.last_seen_at

    # --- life processes --------------------------------------------------

    def tick(self) -> None:
        """Advance one beat. Called by the daemon every few seconds."""
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

    def set_host_name(self, name: str) -> None:
        """Remember what to call you. Does nothing if name is empty."""
        cleaned = name.strip()
        if not cleaned:
            return
        self.host_name = cleaned
        if self.first_met_at == 0.0:
            self.first_met_at = time.time()

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
        try:
            raw = STATE_PATH.read_text(encoding="utf-8").strip()
            if not raw:
                s = cls()
                s.save()
                return s
            data = json.loads(raw)
        except (OSError, json.JSONDecodeError):
            # Corrupt or unreadable. Back it up and start fresh.
            try:
                backup = STATE_PATH.with_suffix(".json.corrupt")
                STATE_PATH.rename(backup)
            except OSError:
                pass
            s = cls()
            s.save()
            return s
        # Tolerate schema drift: drop keys we no longer have.
        valid = {f.name for f in cls.__dataclass_fields__.values()}
        data = {k: v for k, v in data.items() if k in valid}
        return cls(**data)