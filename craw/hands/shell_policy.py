"""Craw's shell policy.

The whitelist. Every command Craw runs has to match a prefix here. No
prefix match, no execution. Bare `python <script>` is allowed; bare
`pip install <anything>` is allowed; everything in DENY is refused.

This is a policy layer, not a sandbox. A whitelisted command can do
anything the command itself can do. The policy stops Craw from *slipping*
into a denied command; it does not stop a whitelisted command from being
a bad idea.

Read .craw/shell_policy.json to override any of this at runtime.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from craw.state import CRAW_HOME

POLICY_PATH = CRAW_HOME / "shell_policy.json"


# --- defaults -------------------------------------------------------------

AUTO_PREFIXES = [
    "git status", "git log", "git diff", "git branch",
    "git show", "git remote -v", "git remote show",
    "python --version", "python -V", "py --version",
    "pip list", "pip show", "pip freeze",
    "dir", "ls", "pwd", "whoami", "hostname",
    "where ", "which ", "type ",
    "ipconfig", "ping ", "nslookup ", "tracert ",
    "systeminfo", "tasklist", "tasklist /",
]

CONFIRM_PREFIXES = [
    "git add ", "git commit ", "git checkout ", "git switch ",
    "pip install ", "pip uninstall ",
    "python ", "py ",
    "mkdir ",
]

DENY_ALWAYS = [
    "rm", "del ", "rmdir ", "rd ", "format ",
    "shutdown", "restart-computer",
    "taskkill /f", "taskkill /F",
    "reg ", "regedit", "sc ", "net ", "schtasks",
    "git push", "git reset --hard", "git clean -fd",
    "curl", "wget", "ssh ", "scp ", "sftp ", "nc ",
    "powershell -command", "pwsh -command",
    "cmd /c", "cmd.exe /c",
    "invoke-expression", "iex ",
]

# Dangerous characters in the *arguments* portion of a command.
# If the command contains these beyond the first token, refuse.
SHELL_METACHARACTERS = [
    " && ", " || ", " ; ", " | ", "`", "$(", "${",
    "\n", "\r", " > ", " >> ", " < ",
]


@dataclass
class Decision:
    allowed: bool
    tier: str          # "auto" | "confirm" | "deny"
    reason: str = ""
    command: str = ""


@dataclass
class ShellPolicy:
    auto_prefixes: list[str] = field(default_factory=lambda: list(AUTO_PREFIXES))
    confirm_prefixes: list[str] = field(default_factory=lambda: list(CONFIRM_PREFIXES))
    deny_always: list[str] = field(default_factory=lambda: list(DENY_ALWAYS))
    timeout_seconds: int = 30
    output_cap_bytes: int = 102_400

    # --- load/save --------------------------------------------------------

    @classmethod
    def load(cls, path: Path = POLICY_PATH) -> "ShellPolicy":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        return cls(
            auto_prefixes=list(data.get("auto_prefixes", AUTO_PREFIXES)),
            confirm_prefixes=list(data.get("confirm_prefixes", CONFIRM_PREFIXES)),
            deny_always=list(data.get("deny_always", DENY_ALWAYS)),
            timeout_seconds=int(data.get("timeout_seconds", 30)),
            output_cap_bytes=int(data.get("output_cap_bytes", 102_400)),
        )

    # --- evaluation -------------------------------------------------------

    def evaluate(self, command: str) -> Decision:
        cmd = command.strip()
        if not cmd:
            return Decision(False, "deny", "empty command", command)

        lower = cmd.lower()

        # 1. Deny always — check first. Deny beats allow.
        for bad in self.deny_always:
            if lower.startswith(bad.lower()) or f" {bad.lower()}" in lower:
                return Decision(False, "deny", f"command matches deny list: {bad}", command)

        # 2. Shell metacharacters in the argument portion.
        #    The first token is allowed to be anything; the rest is checked.
        parts = cmd.split(maxsplit=1)
        rest = parts[1] if len(parts) > 1 else ""
        for meta in SHELL_METACHARACTERS:
            if meta in rest:
                return Decision(
                    False, "deny",
                    f"shell metacharacter not allowed: {meta!r}",
                    command,
                )

        # 3. Confirm-tier prefixes.
        for prefix in self.confirm_prefixes:
            if lower.startswith(prefix.lower()):
                return Decision(True, "confirm", f"matches confirm prefix: {prefix}", command)

        # 4. Auto-tier prefixes.
        for prefix in self.auto_prefixes:
            if lower.startswith(prefix.lower()):
                return Decision(True, "auto", f"matches auto prefix: {prefix}", command)

        return Decision(False, "deny", "no matching prefix", command)