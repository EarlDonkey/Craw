"""Entry point. `python -m craw` starts the daemon.

If launched without a visible console (startup shortcut, hidden window),
stdout/stderr are redirected to .craw/daemon.log so the daemon is
inspectable later.

Refuses to start if another live daemon already holds the PID lock.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _redirect_logs_if_headless() -> None:
    try:
        is_tty = sys.stderr is not None and sys.stderr.isatty()
    except (AttributeError, ValueError):
        is_tty = False
    if is_tty:
        return
    log_path = Path(__file__).resolve().parent.parent / ".craw" / "daemon.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        f = open(log_path, "a", encoding="utf-8", buffering=1)
        sys.stdout = f
        sys.stderr = f
    except OSError:
        pass


def main() -> int:
    _redirect_logs_if_headless()

    from craw.brain.pidlock import acquire, release
    from craw import eventlog

    ok, owner = acquire()
    if not ok:
        print(f"[craw] another daemon is already running (pid {owner}). exiting.")
        return 1

    try:
        from craw.brain.memory import get_memory
        from craw.brain.reflexes import Reflexes
        from craw.daemon import Daemon
        from craw.senses.shell import ShellSense
        from craw.state import State

        state = State.load()
        eventlog.start(pid=os.getpid(), host=state.host_name or "")

        memory = get_memory()
        senses = [ShellSense()]
        reflexes = Reflexes(memory, state)
        daemon = Daemon(state=state, memory=memory, senses=senses, reflexes=reflexes)
        try:
            daemon.run()
        finally:
            memory.close()
            eventlog.stop("clean shutdown")
    except BaseException as exc:
        try:
            eventlog.crashed(exc)
        finally:
            raise
    finally:
        release()

    return 0


if __name__ == "__main__":
    sys.exit(main())