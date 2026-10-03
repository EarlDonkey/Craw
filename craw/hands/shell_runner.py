"""Craw's shell runner.

Runs a command that passed the policy. Hard 30-second timeout. Capped
output. Everything logged.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass

from craw.hands.shell_log import write as log_write
from craw.hands.shell_policy import ShellPolicy


@dataclass
class Result:
    ok: bool
    output: str
    exit_code: int
    duration_ms: int


def run(command: str, policy: ShellPolicy) -> Result:
    """Execute a command. The policy is assumed to have already allowed it."""
    start = time.time()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            timeout=policy.timeout_seconds,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        duration = int((time.time() - start) * 1000)
        output = (proc.stdout or "") + (proc.stderr or "")
        if len(output) > policy.output_cap_bytes:
            output = output[: policy.output_cap_bytes] + "\n... (truncated)"
        log_write(command, "ran", proc.returncode, duration, output)
        return Result(
            ok=proc.returncode == 0,
            output=output.strip() or "(no output)",
            exit_code=proc.returncode,
            duration_ms=duration,
        )
    except subprocess.TimeoutExpired:
        duration = int((time.time() - start) * 1000)
        log_write(command, "timeout", -1, duration, "")
        return Result(
            ok=False,
            output=f"timed out after {policy.timeout_seconds}s",
            exit_code=-1,
            duration_ms=duration,
        )
    except Exception as exc:
        duration = int((time.time() - start) * 1000)
        log_write(command, "error", -1, duration, str(exc))
        return Result(ok=False, output=f"failed: {exc}", exit_code=-1, duration_ms=duration)