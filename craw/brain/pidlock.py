"""Process-wide daemon lock.

One daemon at a time. Uses atomic file creation so two processes
starting at the same instant can't both win.
"""

from __future__ import annotations

import os
from pathlib import Path

from craw.state import CRAW_HOME

PID_PATH = CRAW_HOME / "daemon.pid"


def _is_alive(pid: int) -> bool:
    """Is a process with this PID currently running?

    Uses psutil on Windows, which is the only reliable cross-platform
    check. Falls back to tasklist if psutil isn't installed.
    """
    if pid <= 0:
        return False
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        pass
    try:
        import subprocess
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=3,
        )
        return str(pid) in out.stdout
    except Exception:
        return False


def read_pid() -> int | None:
    if not PID_PATH.exists():
        return None
    try:
        return int(PID_PATH.read_text().strip())
    except (OSError, ValueError):
        return None


def acquire() -> tuple[bool, int]:
    """Try to become the daemon. Returns (ok, pid).

    Uses atomic file creation so two processes starting at the same
    instant can't both win.
    """
    CRAW_HOME.mkdir(parents=True, exist_ok=True)

    for _attempt in range(2):
        try:
            fd = os.open(str(PID_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            # Someone already holds it. Are they alive?
            existing = read_pid()
            if existing is not None and _is_alive(existing) and existing != os.getpid():
                return False, existing
            # Dead or unreadable — reclaim.
            try:
                PID_PATH.unlink()
            except OSError:
                pass
            continue
        try:
            os.write(fd, str(os.getpid()).encode("ascii"))
        finally:
            os.close(fd)
        return True, os.getpid()

    return False, -1


def release() -> None:
    try:
        if read_pid() == os.getpid():
            PID_PATH.unlink(missing_ok=True)
    except OSError:
        pass