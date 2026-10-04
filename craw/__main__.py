"""Entry point. `python -m craw` starts the daemon.

If launched without a visible console (startup shortcut, hidden window),
stdout/stderr are redirected to .craw/daemon.log so the daemon is
inspectable later.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _redirect_logs_if_headless() -> None:
    """If stderr isn't a TTY, send it to a log file."""
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

    from craw.brain.memory import get_memory
    from craw.brain.reflexes import Reflexes
    from craw.daemon import Daemon
    from craw.senses.shell import ShellSense
    from craw.state import State

    state = State.load()
    memory = get_memory()
    senses = [ShellSense()]
    reflexes = Reflexes(memory, state)
    daemon = Daemon(state=state, memory=memory, senses=senses, reflexes=reflexes)
    try:
        daemon.run()
    finally:
        memory.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())