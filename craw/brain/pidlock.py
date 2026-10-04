"""Process-wide daemon lock."""

from __future__ import annotations

import os
from pathlib import Path

from craw.state import CRAW_HOME

PID_PATH = CRAW_HOME / "daemon.pid"


def _is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def read_pid() -> int | None:
    if not PID_PATH.exists():
        return None
    try:
        return int(PID_PATH.read_text().strip())
    except (OSError, ValueError):
        return None


def acquire() -> tuple[bool, int]:
    CRAW_HOME.mkdir(parents=True, exist_ok=True)
    existing = read_pid()
    if existing is not None and _is_alive(existing) and existing != os.getpid():
        return False, existing
    PID_PATH.write_text(str(os.getpid()))
    return True, os.getpid()


def release() -> None:
    try:
        if read_pid() == os.getpid():
            PID_PATH.unlink(missing_ok=True)
    except OSError:
        pass
