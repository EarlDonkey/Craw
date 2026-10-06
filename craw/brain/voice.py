"""Craw's voice.

Composes lines. LLM first, rules as silent fallback.

Answer pipeline:
  1. route(question) — one decision: which tool, or none.
  2. If the tool is write_code: ask for PLAIN CODE, not JSON.
     The 3B model can't escape quotes in JSON strings, so we bypass it.
  3. Otherwise: execute the tool, feed the ACTUAL OUTPUT to the LLM,
     and compose the answer from that output alone.
"""

from __future__ import annotations

import random
import sys

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
    """Compose an unprompted line. LLM first; rules as silent fallback."""
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

    from craw.brain.tool_call import execute, ToolCall

    ctx = build_context(memory, state, milestones=milestones, mood_log=mood_log)
    sys_prompt = system_prompt(ctx)

    # Step 1 — route
    r = route(question, _llm)
    print(
        f"[answer] question={question[:60]!r} -> tool={r.tool} "
        f"args={r.args} reason={r.reason}",
        file=sys.stderr,
        flush=True,
    )

    # Step 1b — write_code is special: bypass JSON entirely.
    if r.tool == "write_code":
        return _write_code_special(question, r, sys_prompt)

    # Step 2a — regular tool.
    if r.tool:
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


def _split_statements(code: str) -> str:
    """Best-effort repair for one-line Python from small models.

    Handles:
        name = input("What is your name? ") print("Hello, " + name)
    by inserting a newline before common statement-leading keywords
    when they appear mid-line.
    """
    import re

    lines = code.split("\n")
    out = []

    # Keywords that begin a new statement in Python. If one appears after
    # a ")" or "]" or a bare identifier, it's almost certainly a new line.
    starters = [
        "import ", "from ", "def ", "class ", "if ", "elif ", "else",
        "for ", "while ", "try:", "except", "finally", "with ",
        "print(", "return ", "yield ", "raise ", "assert ", "pass",
        "break", "continue", "global ", "nonlocal ", "del ",
        "input(", "open(",
    ]

    for line in lines:
        if not line.strip():
            out.append(line)
            continue

        # Look for a keyword that follows a ")" or "]" mid-line.
        # Only split if the character right before the keyword is
        # whitespace and the character before that is ")" or "]".
        modified = line
        for kw in starters:
            pattern = re.compile(r"(?<=[\)\]])\s+(?=" + re.escape(kw) + r")")
            modified = pattern.sub("\n", modified)

        # Also handle "= ... print(" and similar assignment-then-statement
        # patterns where there's no ")" boundary.
        for kw in starters:
            pattern = re.compile(
                r"(?<=[a-zA-Z0-9_\"'])\s{2,}(?=" + re.escape(kw) + r")"
            )
            modified = pattern.sub("\n", modified)

        out.append(modified)

    # Also handle the case where the whole thing is one long line with
    # a single space between statements.
    joined = "\n".join(out)
    for kw in starters:
        joined = re.sub(
            r"(?<=[\)\]])\s(?=" + re.escape(kw) + r")",
            "\n",
            joined,
        )

    # Collapse any accidental blank lines that resulted
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip()

def _write_code_special(question: str, r, sys_prompt: str) -> str:
    """Handle write_code without going through JSON.

    The 3B model can't escape quotes inside JSON strings. So instead of
    asking it for {"tool": "write_code", "args": {"content": "..."}}, we
    ask it for the raw code, then compose the args ourselves.
    """
    from craw.brain.tool_call import execute, ToolCall

    filename = ""
    if r.args and isinstance(r.args, dict):
        filename = str(r.args.get("path", "")).strip()
    if not filename:
        # Fall back to a sensible default name
        filename = "script.py"
    if not filename.endswith(".py"):
        filename += ".py"

    # Ask for the code with no wrappers at all.
    code_prompt = (
        f"Write a complete Python file for this request.\n\n"
        f"Request: {question}\n\n"
        f"STRICT FORMATTING RULES — VIOLATION IS NOT ACCEPTABLE:\n"
        f"1. One statement per line. NEVER put two statements on one line.\n"
        f"2. Every statement ends with a newline.\n"
        f"3. Do NOT use semicolons between statements.\n"
        f"4. NO markdown fences. NO backticks. NO triple backticks.\n"
        f"5. Output ONLY the raw file. No explanation. No preface.\n\n"
        f"CORRECT example:\n"
        f"name = input(\"What is your name? \")\n"
        f"print(\"Hello, \" + name)\n\n"
        f"WRONG example (never do this):\n"
        f"name = input(\"What is your name? \") print(\"Hello, \" + name)\n"
    )
    code = _llm.generate(code_prompt, system=sys_prompt)
    code = (code or "").strip()

    # Repair common one-line output from small models.
    code = _split_statements(code)

    # Strip any markdown fence the model added anyway.
    if code.startswith("```"):
        first_nl = code.find("\n")
        if first_nl != -1:
            code = code[first_nl + 1:]
        if code.endswith("```"):
            code = code[:-3]
    code = code.strip()

    if not code:
        return "i couldn't write the code. try rephrasing."

    ok, result = execute(ToolCall(
        name="write_code",
        args={"path": filename, "content": code},
    ))

    if not ok:
        return _compose_failure("write_code", result, sys_prompt)

    # Compose a one-line reply from the real result.
    prompt = (
        f"You used write_code. It returned:\n{result}\n\n"
        f"Tell the user in ONE line, in your voice, what you wrote."
    )
    final = _llm.generate(prompt, system=sys_prompt)
    return final or result


def _compose_failure(tool: str, error: str, sys_prompt: str) -> str:
    """When a tool refuses or fails, say so — briefly — and never lie."""
    if not error or not error.strip():
        return f"i tried to use {tool} but it didn't work."
    prompt = (
        f"You tried to use {tool} but it did not succeed. The exact reason was:\n"
        f"{error}\n\n"
        f"Tell the user in one line, in your voice, that you couldn't do it. "
        f"Be honest. Do not invent a success."
    )
    final = _llm.generate(prompt, system=sys_prompt)
    return final or f"i couldn't do that. {error}"