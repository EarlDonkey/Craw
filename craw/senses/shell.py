"""Craw's eyes on your shell.

Reads PowerShell's PSReadLine history file and turns it into observations.
Retrospective for now — once Craw lives in the prompt, this same sense
will also receive live events with timestamps and exit codes.

Everything is observed. Filtering is the brain's job, not the sense's.
"""

from __future__ import annotations

import os
import time
import json
from craw.state import CRAW_HOME
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from craw.senses.base import Observation

CHECKPOINT_PATH = CRAW_HOME / "shell_checkpoint.json"


# Where PSReadLine keeps history. Same on Windows PowerShell and PowerShell 7.
def _history_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt"


# Commands that are noise. Not filtered from memory — filtered from *pattern*
# detection, because "he ran ls" is not interesting, but "he ran ls 40 times
# in a row" is. We keep the raw commands; we just don't count these as events.
_NOISE = {"", "ls", "dir", "cd", "pwd", "clear", "cls", "exit"}


@dataclass
class Command:
    """One command from history. No timestamp — PSReadLine doesn't give us one."""

    text: str
    index: int  # position in history, 0 = oldest


class ShellSense:
    """Reads PowerShell history. Produces observations about what it sees."""

    name = "shell"
    interval_seconds = 30.0  # check every 30s

    def __init__(self) -> None:
        self.path = _history_path()
        self._last_count = self._load_checkpoint()  # how many lines we've already ingested
        self._seen_repeat: dict[str, float] = {}  # cmd -> last time we flagged it

    
    def _load_checkpoint(self) -> int:
        if not CHECKPOINT_PATH.exists():
            return 0
        try:
            return int(json.loads(CHECKPOINT_PATH.read_text())["count"])
        except (OSError, ValueError, KeyError):
            return 0

    def _save_checkpoint(self) -> None:
        CRAW_HOME.mkdir(parents=True, exist_ok=True)
        CHECKPOINT_PATH.write_text(json.dumps({"count": self._last_count}))
    
    # --- main -------------------------------------------------------------

    def sense(self) -> list[Observation]:
        commands = self._read_all()
        if not commands:
            return []

        new = commands[self._last_count :]
        self._last_count = len(commands)

        # First run: ingest everything at once (retrospective).
        # Later runs: only look at what's new.
        if self._last_count == len(new) and new:
            return self._observe_batch(commands, retrospective=True)
        return self._observe_batch(new, retrospective=False)

    # --- reading ----------------------------------------------------------

    def _read_all(self) -> list[Command]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        return [Command(text=line.strip(), index=i) for i, line in enumerate(lines) if line.strip()]

    # --- observing --------------------------------------------------------
    

    def _observe_batch(self, commands: list[Command], *, retrospective: bool) -> list[Observation]:
        """Turn a batch of commands into observations.

        Always emits: the raw sequence, so memory has it.
        Additionally emits: patterns — repetition, streaks, rarities.
        """
        out: list[Observation] = []
        now = time.time()
        prefix = "history" if retrospective else "live"

        # 1. Raw. Every command. Always.
        for c in commands:
            out.append(
                Observation(
                    text=f"ran: {c.text}",
                    meta={
                        "source": "shell",
                        "command": c.text,
                        "index": c.index,
                        "mode": prefix,
                        "at": now,
                    },
                    source="shell",
                )
            )
        
        if retrospective:
            return out  # don't do pattern detection on retrospective history
        
        # 2. Repetition — same command 3+ times within the batch.
        counts = Counter(c.text for c in commands if c.text not in _NOISE)
        for cmd, n in counts.most_common():
            if n >= 3:
                out.append(
                    Observation(
                        text=f"repeated: {cmd} ({n}x)",
                        meta={
                            "source": "shell",
                            "command": cmd,
                            "count": n,
                            "mode": prefix,
                            "at": now,
                        },
                        source="shell",
                    )
                )

        # 3. Rarity — a command that appears exactly once in a large batch.
        #    These are often the interesting ones: new tools, experiments.
        if len(commands) >= 20:
            for cmd, n in counts.items():
                if n == 1 and len(cmd) > 3:
                    out.append(
                        Observation(
                            text=f"tried something new: {cmd}",
                            meta={
                                "source": "shell",
                                "command": cmd,
                                "mode": prefix,
                                "at": now,
                            },
                            source="shell",
                        )
                    )

        # 4. Sequence — two commands that always appear together.
        #    This is the beginning of Craw noticing your workflows.
        bigrams = Counter(
            (commands[i].text, commands[i + 1].text)
            for i in range(len(commands) - 1)
            if commands[i].text not in _NOISE and commands[i + 1].text not in _NOISE
        )
        for (a, b), n in bigrams.most_common(5):
            if n >= 2:
                out.append(
                    Observation(
                        text=f"pattern: {a} -> {b} ({n}x)",
                        meta={
                            "source": "shell",
                            "before": a,
                            "after": b,
                            "count": n,
                            "mode": prefix,
                            "at": now,
                        },
                        source="shell",
                    )
                )

        return out