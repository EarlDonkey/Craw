"""Craw's voice.

Composes lines. LLM first, rules as silent fallback. A creature should
be able to say something small without thinking hard.

Rules of the voice:
  - one line
  - no exclamation marks
  - no emoji
  - lowercase is fine
  - silence is better than filler
"""

from __future__ import annotations

import random

from craw.brain.context import build as build_context
from craw.brain.llm import LLM
from craw.brain.memory import Memory
from craw.brain.persona import system_prompt
from craw.brain.reflexes import Impulse
from craw.state import State


PHRASES: dict[str, list[str]] = {
    "repetition": [
        "{subject}",
        "{subject}. want to talk about it?",
        "{subject}. that's a lot.",
    ],
    "late_night": [
        "{subject}",
        "still up. {subject}",
        "{subject}. sleep is a thing.",
    ],
    "silence": [
        "{subject}",
        "{subject}. i noticed.",
        "still here. {subject}",
    ],
    "novelty": [
        "{subject}",
        "{subject}. new?",
    ],
}

FALLBACK = ["{subject}"]

_llm = LLM()


def _tidy(line: str) -> str:
    line = " ".join(line.split())
    while line.endswith(("..", "!!", "??")):
        line = line[:-1]
    return line


def compose(
    impulse: Impulse,
    memory: Memory,
    state: State,
    milestones=None,
    mood_log=None,
) -> str:
    """Compose a line. LLM first; rules as silent fallback."""
    if _llm.available():
        ctx = build_context(memory, state, milestones=milestones, mood_log=mood_log)
        prompt = (
            f"You just decided to speak because: {impulse.subject}\n"
            f"(reason: {impulse.reason}, urgency: {impulse.urgency:.2f})\n\n"
            f"Write one line, in your voice. Or write 'silence'."
        )
        text = _llm.generate(prompt, system=system_prompt(ctx))
        if text and text.lower().strip(" .") != "silence":
            return text
        if text.lower().strip(" .") == "silence":
            return ""
    pool = PHRASES.get(impulse.reason, FALLBACK)
    template = random.choice(pool)
    return _tidy(template.format(subject=impulse.subject))


def answer(
    question: str,
    memory: Memory,
    state: State,
    milestones=None,
    mood_log=None,
) -> str:
    """Answer a direct question. May call a tool once."""
    if not _llm.available():
        return "my mind is offline right now."

    from craw.brain.tool_call import parse_tool_call, execute
    from craw.hands import REGISTRY

    ctx = build_context(memory, state, milestones=milestones, mood_log=mood_log)
    tools_block = REGISTRY.prompt_block()

    prompt = (
        f"The user says: {question}\n\n"
        f"Respond in one of two ways:\n"
        f"  1. If a tool matches the request, output ONLY a JSON object:\n"
        f'     {{"tool": "<name>", "args": {{...}}}}\n'
        f"  2. Otherwise, answer in one short sentence, in your voice.\n\n"
        f"Do not describe what you would do. Either call the tool or answer."
    )
    text = _llm.generate_with_tools(prompt, system=system_prompt(ctx), tools_block=tools_block)

    call = parse_tool_call(text)
    if call is None:
        return text or "i don't have an answer for that."

    ok, result = execute(call)
    if ok:
        followup = (
            f"You used {call.name}. It returned:\n{result}\n\n"
            f"Tell the user, in one line, in your voice."
        )
    else:
        followup = (
            f"You tried {call.name} but it failed: {result}\n\n"
            f"Tell the user, in one line."
        )
    final = _llm.generate(followup, system=system_prompt(ctx))
    return final or result