"""Craw's voice.

Composes lines. LLM first, rules as silent fallback.

Answer pipeline:
  1. route(question) — one decision: which tool, or none.
  2. If a tool: execute it. Feed the ACTUAL OUTPUT to the LLM.
     The LLM's only job is to tell the user what happened, in one line.
  3. If no tool: plain conversational answer.

The LLM never gets to invent a tool result. If the router says no tool,
there is no tool. If the router picks a tool, the answer must cite it.
"""

from __future__ import annotations

import random

from craw.brain.context import build as build_context
from craw.brain.llm import LLM
from craw.brain.memory import Memory
from craw.brain.persona import system_prompt
from craw.brain.reflexes import Impulse
from craw.brain.router import RAW_OUTPUT_TOOLS, route
from craw.state import State


PHRASES: dict[str, list[str]] = {
    "repetition": ["{subject}", "{subject}. want to talk about it?", "{subject}. that's a lot."],
    "late_night": ["{subject}", "still up. {subject}", "{subject}. sleep is a thing."],
    "silence":    ["{subject}", "{subject}. i noticed.", "still here. {subject}"],
    "novelty":    ["{subject}", "{subject}. new?"],
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
    """Answer a question or perform an action. Grounded in real tool output."""
    if not _llm.available():
        return "my mind is offline right now."

    from craw.brain.tool_call import execute

    ctx = build_context(memory, state, milestones=milestones, mood_log=mood_log)
    sys_prompt = system_prompt(ctx)

    # Step 1 — route
    r = route(question, _llm)

    # Step 2a — tool was chosen. Execute it.
    if r.tool:
        from craw.brain.tool_call import ToolCall
        ok, result = execute(ToolCall(name=r.tool, args=r.args))
        if not ok:
            return _compose_failure(r.tool, result, sys_prompt)

        if r.tool in RAW_OUTPUT_TOOLS:
            return result

        followup = (
            f"You used {r.tool}. It returned:\n{result}\n\n"
            f"Using ONLY information in that result, answer the user's "
            f"question in ONE line, in your voice. If the result does not "
            f"contain an answer, say so honestly and do not invent one."
        )
        final = _llm.generate(followup, system=sys_prompt)
        return final or result

    # Step 2b — no tool. Plain conversational answer.
    prompt = (
        f"The user says: {question}\n\n"
        f"Answer in one short sentence, in your voice. "
        f"If you don't know, say so. Do NOT invent facts about their machine."
    )
    text = _llm.generate(prompt, system=sys_prompt)
    return text or "i don't have an answer for that."


def _compose_failure(tool: str, error: str, sys_prompt: str) -> str:
    """When a tool refuses or fails, say so — briefly — and never lie."""
    prompt = (
        f"You tried to use {tool} but it did not succeed. The exact reason was:\n"
        f"{error}\n\n"
        f"Tell the user in one line, in your voice, that you couldn't do it. "
        f"Be honest. Do not invent a success."
    )
    final = _llm.generate(prompt, system=sys_prompt)
    return final or f"i couldn't do that. {error}"