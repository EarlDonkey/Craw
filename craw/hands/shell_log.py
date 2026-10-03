"""Craw's shell log.

Every command Craw runs is written here. Not for auditing — for *you*
being able to see what happened. Rotated at 1 MB.
"""

from __future__ import annotations

import time
from pathlib import Path

from craw.state import CRAW_HOME

LOG_PATH = CRAW_HOME / "shell.log"
ROTATE_AT_BYTES = 1024 * 1024   # 1 MB


def write(command: str, decision: str, exit_code: int, duration_ms: int, output: str) -> None:
    """Append one line to the log."""
    try:
        CRAW_HOME.mkdir(parents=True, exist_ok=True)
        _rotate_if_needed()
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        snippet = (output or "").strip().replace("\n", " ")[:120]
        line = (
            f"[{ts}] exit={exit_code:>3} {duration_ms:>5}ms "
            f"({decision}) {command[:200]}"
            f"{'  → ' + snippet if snippet else ''}\n"
        )
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def _rotate_if_needed() -> None:
    if not LOG_PATH.exists():
        return
    if LOG_PATH.stat().st_size < ROTATE_AT_BYTES:
        return
    backup = LOG_PATH.with_suffix(".log.1")
    try:
        if backup.exists():
            backup.unlink()
        LOG_PATH.rename(backup)
    except OSError:
        pass


def tail(n: int = 20) -> list[str]:
    """Return the last N lines from the log."""
    if not LOG_PATH.exists():
        return []
    try:
        lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-n:]