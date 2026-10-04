"""Rotating log of URLs Craw fetched."""

from __future__ import annotations

import time
from pathlib import Path

from craw.state import CRAW_HOME

LOG_PATH = CRAW_HOME / "browse.log"
ROTATE_AT_BYTES = 512 * 1024


def write(url: str, decision: str, bytes_: int, duration_ms: int) -> None:
    try:
        CRAW_HOME.mkdir(parents=True, exist_ok=True)
        _rotate_if_needed()
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {decision:8} {duration_ms:>5}ms {bytes_:>8}b {url}\n"
        LOG_PATH.open("a", encoding="utf-8").write(line)
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
    if not LOG_PATH.exists():
        return []
    try:
        lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-n:]