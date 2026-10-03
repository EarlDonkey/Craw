"""Craw's heartbeat.

This is the loop that makes Craw a creature instead of a script.
"""

from __future__ import annotations

import signal
import time
import threading
from dataclasses import dataclass, field

from craw import log
from craw.brain.memory import Memory
from craw.brain.milestones import Milestones
from craw.brain.mood_log import MoodLog
from craw.brain.mouth_state import MouthState
from craw.brain.reflexes import Reflexes
from craw.brain.voice import answer, compose
from craw.brain.will import Will
from craw.brain.voice_out import Speaker
from craw.mouth.ipc import Mouth
from craw.mouth.protocol import Message, Response, face_for_mood
from craw.senses.base import Sense
from craw.senses.audio import Ears
from craw.state import State


TICK_INTERVAL = 2.0
SENSE_INTERVAL = 30.0
REFLEX_INTERVAL = 60.0
BREATHE_INTERVAL = 300.0
MOOD_SAMPLE_INTERVAL = 300.0   # one row in mood.db every 5 minutes


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
        self._last_mood_sample = 0.0
        self._just_ingested_history = False
        self.will = Will.load()
        self.mouth = Mouth(self._handle_request)
        self.speaker = Speaker()
        self.ears = Ears(self._on_utterance)
        self.milestones = Milestones(self.memory)
        self.milestones.load()
        self.mood_log = MoodLog()

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
            pass

    # --- ears -------------------------------------------------------------

    _BLOCKED_WORDS = {"nigger", "faggot", "retard"}

    def _on_utterance(self, text: str) -> None:
        t = text.lower().strip()
        if len(t.split()) < 3:
            return
        if any(b in t for b in self._BLOCKED_WORDS):
            log.body(f"heard (blocked): {t[:60]}")
            return
        log.body(f"heard: {t[:80]}")
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

        if now - self._last_mood_sample >= MOOD_SAMPLE_INTERVAL:
            self._sample_mood()
            self._last_mood_sample = now

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
        if self._just_ingested_history:
            self._just_ingested_history = False
            return
        impulses = self.reflexes.scan()
        if not impulses:
            return
        for imp in impulses:
            log.reflex(f"[{imp.reason}] {imp.subject}  (urgency {imp.urgency:.2f})")
            self.memory.think(
                imp.subject,
                reason=imp.reason,
                urgency=imp.urgency,
                evidence=[e.id for e in imp.evidence],
            )
            self._maybe_milestone(imp)
            if self.will.should_speak(imp):
                line = compose(
                    imp, self.memory, self.state,
                    milestones=self.milestones, mood_log=self.mood_log,
                )
                if not line:
                    continue
                self.will.spoke()
                self.state.speak()
                log.speak(line)
                self.mouth_state.queue(line, kind="thought")
                self.speaker.say(line)

    def _maybe_milestone(self, imp) -> None:
        """Record a first, if this impulse is a first."""
        if imp.reason == "late_night":
            self.milestones.record(
                "first_late_night",
                f"the first time you were still working after midnight",
            )
        if imp.reason == "repetition" and imp.urgency >= 0.95:
            self.milestones.record(
                "first_loud_command",
                f"the first command you ran obsessively — {imp.subject}",
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

    def _sample_mood(self) -> None:
        self.mood_log.write(self.state.mood, self.state.hunger, self.state.energy)

    # --- the mouth --------------------------------------------------------

    def _handle_request(self, request: dict) -> Response:
        ask = request.get("ask", "face")
        self.state.tick()
        face = face_for_mood(self.state.mood, int(self.state.age_seconds / 60))

        if ask == "say":
            question = request.get("text", "").strip()
            if question:
                threading.Thread(
                    target=self._answer_later,
                    args=(question,),
                    daemon=True,
                ).start()
                return Response(
                    face=face,
                    message=Message(text="thinking...", kind="reply"),
                )

        if ask == "name":
            who = request.get("text", "").strip()
            if who:
                self.state.set_host_name(who)
                self.state.save()
                log.body(f"host name set: {who}")
                self.memory.say(f"my name is {who}", who="user")
                self.memory.say(f"noted. hello, {who}.", who="craw")
                self.milestones.record("first_met", f"the day you introduced yourself as {who}")
                return Response(
                    face=face,
                    message=Message(text=f"noted. hello, {who}.", kind="reply"),
                )

        if ask == "mute":
            self.speaker.mute()
            log.body("voice muted")
            return Response(face=face, message=Message(text="voice muted.", kind="reply"))

        if ask == "unmute":
            self.speaker.unmute()
            log.body("voice unmuted")
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
            reply = answer(
                question, self.memory, self.state,
                milestones=self.milestones, mood_log=self.mood_log,
            )
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
        self.milestones.record("first_spoke", "the first time we spoke") if self.memory.count() == 0 else None

        # First breath: no memories.
        if self.memory.count() == 0:
            log.body("first breath.")
            return

        # Generate a greeting with the LLM, informed by trend + milestones.
        self._greet_generated()

    def _greet_generated(self) -> None:
        """Ask the LLM to write the morning line."""
        from craw.brain.context import build as build_context
        from craw.brain.persona import system_prompt
        from craw.brain.llm import LLM

        llm = LLM()
        if not llm.available():
            # Fallback greeting if no LLM
            if self.state.host_name:
                log.body(f"woke. hello, {self.state.host_name}.")
            else:
                log.body("woke.")
            return

        ctx = build_context(
            self.memory, self.state,
            milestones=self.milestones, mood_log=self.mood_log,
        )
        prompt = (
            f"You just woke up. Write ONE line to greet the person — "
            f"a creature coming back into the room. Mention something you "
            f"noticed while you were quiet, or something from your milestones. "
            f"If there is nothing worth saying, return the single word: silence."
        )
        text = llm.generate(prompt, system=system_prompt(ctx))
        if text and text.lower().strip(" .") != "silence":
            log.body(f"woke. {text}")
            self.mouth_state.queue(text, kind="thought")
            self.speaker.say(text)
            self.state.speak()
        else:
            log.body("woke. quiet.")

    def _farewell(self) -> None:
        self.mouth.stop()
        self.ears.stop()
        self.state.save()
        self.mood_log.close()
        log.body("going quiet.")