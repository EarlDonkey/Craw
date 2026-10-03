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
import threading
from dataclasses import dataclass, field

from craw import log
from craw.brain.memory import Memory
from craw.brain.mouth_state import MouthState
from craw.brain.reflexes import Reflexes
from craw.brain.voice import answer, compose
from craw.brain.will import Will
from craw.brain.voice_out import Speaker
from craw.mouth.ipc import Mouth
from craw.mouth.protocol import Message, Response, face_for_mood
from craw.senses.base import Sense
from craw.senses.shell import ShellSense
from craw.senses.audio import Ears
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
    mouth_state: MouthState = field(default_factory=MouthState)

    def __post_init__(self) -> None:
        self._running = False
        self._last_sense = 0.0
        self._last_reflex = 0.0
        self._last_breathe = 0.0
        self._just_ingested_history = False
        self.will = Will.load()
        self.mouth = Mouth(self._handle_request)
        self.speaker = Speaker()
        self.ears = Ears(self._on_utterance)


    # --- lifecycle --------------------------------------------------------

    def run(self) -> None:
        self._install_signals()
        self.mouth.start()
        self.ears.start()
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
    
    
    def _on_utterance(self, text: str) -> None:
        """Craw heard you say something. Route it like `craw ask`."""
        log.body(f"heard: {text[:80]}")
        threading.Thread(
            target=self._answer_later,
            args=(text,),
            daemon=True,
        ).start()
    
    
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
            except Exception as exc:
                log.sense(f"{s.name} errored: {exc!r}")
                continue
            if not obs:
                continue
            if any(o.meta.get("mode") == "history" for o in obs):
                self._just_ingested_history = True
            for o in obs:
                try:
                    self.memory.observe(o.text, **o.meta)
                except Exception as exc:
                    log.sense(f"observe errored: {exc!r}")
            log.sense(f"{s.name}: {len(obs)} observations")

    def _run_reflexes(self) -> None:
        # Don't react to retrospective history. First run is for learning,
        # not for talking. Live mode only.
        if self._just_ingested_history:
            self._just_ingested_history = False
            return
        impulses = self.reflexes.scan()
        if not impulses:
            return
        for imp in impulses:
            log.reflex(f"[{imp.reason}] {imp.subject}  (urgency {imp.urgency:.2f})")
            # Every impulse becomes a *thought*.
            self.memory.think(
                imp.subject,
                reason=imp.reason,
                urgency=imp.urgency,
                evidence=[e.id for e in imp.evidence],
            )
            # A few become *spoken*.
            if self.will.should_speak(imp):
                line = compose(imp, self.memory, self.state)
                if not line:
                    continue
                self.will.spoke()
                self.state.speak()
                log.speak(line)
                self.mouth_state.queue(line, kind="thought")
                self.speaker.say(line)
    def _breathe(self) -> None:
        self.state.save()
        log.body(
            f"age {self.state.age_seconds / 60:.0f}m  "
            f"hunger {self.state.hunger:.2f}  "
            f"energy {self.state.energy:.2f}  "
            f"mood {self.state.mood}  "
            f"mem {self.memory.count()}"
        )

    # --- the mouth --------------------------------------------------------

    def _handle_request(self, request: dict) -> Response:
        ask = request.get("ask", "face")
        self.state.tick()
        face = face_for_mood(self.state.mood, int(self.state.age_seconds / 60))

        if ask == "say":
            question = request.get("text", "").strip()
            if question:
                # Hand off to a background thread so the pipe replies instantly.
                threading.Thread(
                    target=self._answer_later,
                    args=(question,),
                    daemon=True,
                ).start()
                return Response(
                    face=face,
                    message=Message(text="thinking...", kind="reply"),
                )
                
        if ask == "mute":
            self.speaker.mute()
            log.body("voice muted")
            self.memory.say("craw muted", who="user")
            self.memory.say("voice muted.", who="craw")
            return Response(face=face, message=Message(text="voice muted.", kind="reply"))

        if ask == "unmute":
            self.speaker.unmute()
            log.body("voice unmuted")
            self.memory.say("craw unmuted", who="user")
            self.memory.say("voice back.", who="craw")
            return Response(face=face, message=Message(text="voice back.", kind="reply"))
        
        if ask == "mute_mic":
            self.ears.mute()
            log.body("mic muted")
            return Response(face=face, message=Message(text="i can't hear you.", kind="reply"))

        if ask == "unmute_mic":
            self.ears.unmute()
            log.body("mic unmuted")
            return Response(face=face, message=Message(text="i'm listening.", kind="reply"))

        text, kind = self.mouth_state.take()
        return Response(face=face, message=Message(text=text, kind=kind))

    def _answer_later(self, question: str) -> None:
        try:
            log.body(f"asked: {question[:60]}")
            reply = answer(question, self.memory, self.state)
            log.body(f"replied: {(reply or '')[:60]}")
            self.memory.say(question, who="user")
            self.memory.say(reply, who="craw")
            self.mouth_state.queue(reply, kind="reply")
            self.speaker.say(reply)
        except Exception as exc:
            log.body(f"answer errored: {exc!r}")


    # --- bookends ---------------------------------------------------------

    def _greet(self) -> None:
        self.state.see()
        age_min = self.state.age_seconds / 60
        if self.memory.count() == 0:
            log.body("first breath.")
        else:
            log.body(f"woke. age {age_min:.0f}m. {self.memory.count()} memories.")

    def _farewell(self) -> None:
        self.mouth.stop()
        self.ears.stop()
        self.state.save()
        log.body("going quiet.")