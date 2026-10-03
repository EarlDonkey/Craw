"""Entry point. `python -m craw` starts the daemon."""

from __future__ import annotations

import sys

from craw.brain.memory import Memory
from craw.brain.reflexes import Reflexes
from craw.daemon import Daemon
from craw.senses.shell import ShellSense
from craw.state import State


def main() -> int:
    state = State.load()
    memory = Memory()
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