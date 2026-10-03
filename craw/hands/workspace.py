"""Craw's workspace.

The one folder where Craw can write. Everything else is read-only for
the creature. If write_file can't guarantee a path is inside this
folder, it refuses.

Path safety rules:
  - The resolved absolute path must start with WORKSPACE.
  - Symlinks are resolved before the check.
  - ".." is allowed in the input but must resolve inside WORKSPACE.
  - Writes are capped at MAX_FILE_BYTES.
"""

from __future__ import annotations

from pathlib import Path

from craw.state import CRAW_HOME

WORKSPACE = (CRAW_HOME / "workspace").resolve()
MAX_FILE_BYTES = 256 * 1024   # 256 KB


def ensure() -> None:
    WORKSPACE.mkdir(parents=True, exist_ok=True)


def resolve_safe(user_path: str) -> Path | None:
    """Return an absolute path inside WORKSPACE, or None if unsafe.

    Accepts relative paths (joined to WORKSPACE) and absolute paths
    (checked against WORKSPACE). Returns None on any escape attempt.
    """
    ensure()
    raw = (user_path or "").strip()
    if not raw:
        return None
    try:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = WORKSPACE / candidate
        resolved = candidate.resolve()
    except (OSError, RuntimeError):
        return None

    try:
        resolved.relative_to(WORKSPACE)
    except ValueError:
        return None
    return resolved