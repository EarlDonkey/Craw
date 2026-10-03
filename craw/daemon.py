"""Craw's heartbeat.

This is the loop that makes Craw a creature instead of a script. It runs
in the foreground so you can watch it think. Later it will detach and
wear a shell.

Cadence:
  - every 2s:   tick vitals (hunger grows, energy falls)
  - every 30s:  run each sense, write observations to memory
  - every 60s:  run reflexes, decide if anything is worth thinking about
  - every 5min: save state, prune, breathe
"""

from __future__ import annotations

import signal
import time
from dataclasses import dataclass

from craw import log
from craw.brain.memory import Memory
from craw.brain.reflexes import Reflexes
from craw.senses.base import Sense
from craw.senses.shell import ShellSense
from craw.state import State


TICK_INTERVAL = 2.0
SENSE_INTERVAL = 30.0
REFLEX_INTERVAL = 60.0
BREATHE_INTERVAL = 300.0


@dataclass
class Daemon:
    state: State
    memory: Memory
    senses: list[Sense]
    reflexes: Reflexes

    def __post_init__(self) -> None:
        self._running = False
        self._last_sense = 0.0
        self._last_reflex = 0.0
        self._last_breathe = 0.0

    # --- lifecycle --------------------------------------------------------

    def run(self) -> None:
        self._install_signals()
        self._running = True
        self._greet()
        while self._running:
            self._beat()
            time.sleep(TICK_INTERVAL)
        self._farewell()

    def stop(self, *_: object) -> None:
        self._running = False

    def _install_signals(self) -> None:
        signal.signal(signal.SIGINT, self.stop)
        try:
            signal.signal(signal.SIGTERM, self.stop)
        except (AttributeError, ValueError):
            pass  # Windows doesn't always support SIGTERM cleanly

    # --- the beat ---------------------------------------------------------

    def _beat(self) -> None:
        now = time.time()
        self.state.tick()

        if now - self._last_sense >= SENSE_INTERVAL:
            self._run_senses()
            self._last_sense = now

        if now - self._last_reflex >= REFLEX_INTERVAL:
            self._run_reflexes()
            self._last_reflex = now

        if now - self._last_breathe >= BREATHE_INTERVAL:
            self._breathe()
            self._last_breathe = now

    # --- organs -----------------------------------------------------------

    def _run_senses(self) -> None:
        for s in self.senses:
            try:
                obs = s.sense()
            except Exception as exc:  # a broken sense must not kill the daemon
                log.sense(f"{s.name} errored: {exc!r}")
                continue
            if not obs:
                continue
            for o in obs:
                self.memory.observe(o.text, **o.meta)
            log.sense(f"{s.name}: {len(obs)} observations")

    def _run_reflexes(self) -> None:
        impulses = self.reflexes.scan()
        if not impulses:
            return
        for imp in impulses:
            log.reflex(f"[{imp.reason}] {imp.subject}  (urgency {imp.urgency:.2f})")
            # For now, every impulse becomes a *thought*. The mouth arrives later.
            self.memory.think(
                imp.subject,
                reason=imp.reason,
                urgency=imp.urgency,
                evidence=[e.id for e in imp.evidence],
            )

    def _breathe(self) -> None:
        self.state.save()
        log.body(
            f"age {self.state.age_seconds / 60:.0f}m  "
            f"hunger {self.state.hunger:.2f}  "
            f"energy {self.state.energy:.2f}  "
            f"mood {self.state.mood}  "
            f"mem {self.memory.count()}"
        )

    # --- bookends ---------------------------------------------------------

    def _greet(self) -> None:
        self.state.see()
        age_min = self.state.age_seconds / 60
        if self.memory.count() == 0:
            log.body("first breath.")
        else:
            log.body(f"woke. age {age_min:.0f}m. {self.memory.count()} memories.")

    def _farewell(self) -> None:
        self.state.save()
        log.body("going quiet.")