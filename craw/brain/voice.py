"""Craw's voice.

Composes lines. LLM first, rules as silent fallback.

Answer pipeline:
  1. route(question) — one decision: which tool, or none.
  2. If the tool is write_code: generate code with a strict prompt,
     validate it with py_compile, retry up to 3 times if invalid.
  3. Otherwise: execute the tool, feed the ACTUAL OUTPUT to the LLM,
     and compose the answer from that output alone.
"""

from __future__ import annotations

import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

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

    # Step 1b — write_code is special: bypass JSON, validate, retry.
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
        i = 1 while i <= 10: print(i) i += 1
        while i <= 10: print(i) i += 1
        for i in range(1, 6): print(i * i)
    """
    # semicolons always mean a newline in Python
    code = code.replace("; ", "\n").replace(";", "\n")

    starters = [
        "import ", "from ", "def ", "class ", "if ", "elif ", "else:",
        "for ", "while ", "try:", "except", "finally", "with ",
        "print(", "return ", "yield ", "raise ", "assert ",
        "input(", "open(",
    ]

    lines = code.split("\n")
    out = []
    for line in lines:
        if not line.strip():
            out.append(line)
            continue
        modified = line
        for kw in starters:
            escaped = re.escape(kw)
            # split after ) or ]
            modified = re.sub(
                r"(?<=[\)\]])\s+(?=" + escaped + r")",
                "\n", modified,
            )
            # split after a double-space before a keyword
            modified = re.sub(
                r"(?<=[a-zA-Z0-9_\"'])\s{2,}(?=" + escaped + r")",
                "\n", modified,
            )
            # split after a digit before a keyword
            modified = re.sub(
                r"(?<=[0-9])\s+(?=" + escaped + r")",
                "\n", modified,
            )
        # split after ": " when followed by a keyword
        for kw in starters:
            escaped = re.escape(kw)
            modified = re.sub(
                r"(?<=: )\s*(?=" + escaped + r")",
                "\n", modified,
            )
        # split after ") " when followed by ident= (assignment)
        modified = re.sub(
            r"(?<=\))\s+(?=[a-zA-Z_][a-zA-Z0-9_]*\s*[=+\-*/%])",
            "\n", modified,
        )
        # split after ") " when followed by ident. (method chain)
        modified = re.sub(
            r"(?<=\))\s+(?=[a-zA-Z_][a-zA-Z0-9_]*\s*\.)",
            "\n", modified,
        )
        out.append(modified)

    joined = "\n".join(out)
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined.strip()


def _auto_indent(code: str) -> str:
    """Indent the body of loops/conditionals when the model forgot.

    Works on flat code that has NO leading whitespace. If the input
    already has meaningful indentation, this is a no-op.

    Logic:
      - A line ending in ":" that starts with while/for/if/elif/else/
        try/except/finally/with/def/class pushes a new indent level.
      - A line that begins with a top-level keyword (def, class,
        import, from, or a comment) at the current level pops back
        to the nearest top level.
      - Empty lines keep their state.
      - Everything else stays at the current level.
    """
    # If the source already has indentation, don't touch it.
    for line in code.split("\n"):
        if line and line != line.lstrip() and line.strip():
            return code

    lines = code.split("\n")
    out: list[str] = []
    indent = 0

    top_level = ("def ", "class ", "import ", "from ",
                 "if __name__", "#", "@")

    for i, raw in enumerate(lines):
        stripped = raw.strip()

        if not stripped:
            out.append("")
            continue

        # Top-level markers: pop indent to 0
        if indent > 0 and any(stripped.startswith(k) for k in top_level):
            indent = 0

        out.append("    " * indent + stripped)

        # If this line opens a block, indent the next line.
        if stripped.endswith(":"):
            indent += 1

        # If the next line looks like a top-level sibling, pop back.
        if i + 1 < len(lines):
            nxt = lines[i + 1].strip()
            if nxt and indent > 0:
                if any(nxt.startswith(k) for k in top_level):
                    indent = 0

    return "\n".join(out)


def _try_compile(code: str) -> tuple[bool, str]:
    """Compile the code with py_compile. Returns (ok, error_text)."""
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(code)
            tmp_path = f.name
        result = subprocess.run(
            [sys.executable, "-m", "py_compile", tmp_path],
            capture_output=True, text=True, timeout=10,
        )
        Path(tmp_path).unlink(missing_ok=True)
        if result.returncode == 0:
            return True, ""
        return False, (result.stderr or "").strip()[:300]
    except Exception as exc:
        return False, str(exc)


def _write_code_special(question: str, r, sys_prompt: str) -> str:
    """Handle write_code.

    Flow:
      1. If the router already produced valid Python, use it directly.
      2. Otherwise, ask the LLM with a strict prompt, validate with
         py_compile, retry up to 3 times.
      3. If all attempts fail, report honestly.
    """
    from craw.brain.tool_call import execute, ToolCall
    from craw.hands.tools import _strip_fences

    filename = ""
    if r.args and isinstance(r.args, dict):
        filename = str(r.args.get("path", "")).strip()
    if not filename:
        filename = "script.py"
    if not filename.endswith(".py"):
        filename += ".py"

    # ── Try the router's content first ──
    router_content = ""
    if r.args and isinstance(r.args, dict):
        router_content = str(r.args.get("content", "")).strip()
    if router_content:
        router_content = _strip_fences(router_content)
        router_content = _split_statements(router_content)
        router_content = _auto_indent(router_content)
        ok, _err = _try_compile(router_content)
        if ok:
            ok2, msg = execute(ToolCall(
                name="write_code",
                args={"path": filename, "content": router_content},
            ))
            if ok2:
                return msg
            return _compose_failure("write_code", msg, sys_prompt)

    # ── Fallback: ask the LLM with a strict prompt, validate, retry ──
    base_prompt = (
        f"Write a complete Python file for this request.\n\n"
        f"Request: {question}\n\n"
        f"CRITICAL: Python uses 4-space indentation for blocks. "
        f"Every line inside a loop or if-statement MUST be indented. "
        f"If you do not indent, the file will not run.\n\n"
        f"Output ONLY the raw file contents. No explanation. "
        f"No backticks. No 'python' prefix.\n\n"
        f"CORRECT EXAMPLE — this is what you must produce:\n"
        f"i = 1\n"
        f"while i <= 10:\n"
        f"    print(i)\n"
        f"    i += 1\n\n"
        f"WRONG — never do this:\n"
        f"i = 1 while i <= 10: print(i) i += 1\n"
        f"while i <= 10: print(i) i += 1\n"
        f"while i <= 10:\n"
        f"print(i)\n"
        f"i += 1\n"
    )

    best_code = ""
    last_error = ""

    for attempt in range(3):
        if attempt == 0:
            prompt = base_prompt
        else:
            prompt = (
                base_prompt
                + "\n\nYOUR PREVIOUS ATTEMPT FAILED. The exact error was:\n"
                + last_error
                + "\n\nYour broken code was:\n"
                + best_code
                + "\n\nREWRITE IT. Pay attention to indentation. "
                  "Every line inside a while/for/if block must start "
                  "with 4 spaces. Output ONLY the corrected code."
            )

        code = _llm.generate(prompt, system=sys_prompt)
        code = (code or "").strip()

        # Strip fences and language tags
        code = _strip_fences(code)

        # Repair common one-liner patterns
        code = _split_statements(code)

        # Add indentation for blocks the model left flat
        code = _auto_indent(code)

        if not code:
            last_error = "empty response"
            continue

        best_code = code

        ok, err = _try_compile(code)
        if ok:
            ok2, msg = execute(ToolCall(
                name="write_code",
                args={"path": filename, "content": code},
            ))
            if not ok2:
                return _compose_failure("write_code", msg, sys_prompt)
            return msg

        last_error = err

    return (
        f"i tried to write {filename} 3 times but couldn't get valid python. "
        f"last error: {last_error[:120]}"
    )


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