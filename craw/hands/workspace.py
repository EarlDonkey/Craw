"""Craw's workspace — internal sandbox AND user-provided code playground.

Two writable roots:

  1. WORKSPACE  — .craw/workspace/                     (internal notes)
  2. CODE_ROOT  — C:/Users/user/Desktop/Playground     (real code projects)

Everything else on the filesystem is read-only for Craw's write tools.

Path safety rules:
  - The resolved absolute path must be inside one of the writable roots.
  - Symlinks are resolved before the check.
  - ".." is allowed in the input but must resolve inside a writable root.
  - Writes are capped at MAX_FILE_BYTES.
  - CODE_ROOT is created if it doesn't exist.
"""

from __future__ import annotations

from pathlib import Path

from craw.state import CRAW_HOME

WORKSPACE = (CRAW_HOME / "workspace").resolve()
MAX_FILE_BYTES = 256 * 1024
DEFAULT_CODE_ROOT = Path(r"C:\Users\user\Desktop\Playground").resolve()


def _code_root() -> Path:
    """Code root. Overridable via .craw/code_root.txt (one line, a path)."""
    override = CRAW_HOME / "code_root.txt"
    if override.exists():
        try:
            raw = override.read_text(encoding="utf-8").strip()
            if raw:
                return Path(raw).expanduser().resolve()
        except OSError:
            pass
    return DEFAULT_CODE_ROOT


CODE_ROOT = _code_root()


def ensure() -> None:
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    try:
        CODE_ROOT.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_in_workspace(user_path: str) -> Path | None:
    """Resolve a path inside the internal sandbox. None if unsafe."""
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
    return resolved if _inside(resolved, WORKSPACE) else None


def resolve_in_code_root(user_path: str) -> Path | None:
    """Resolve a path inside the code playground. None if unsafe."""
    ensure()
    raw = (user_path or "").strip()
    if not raw:
        return None
    try:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = CODE_ROOT / candidate
        resolved = candidate.resolve()
    except (OSError, RuntimeError):
        return None
    return resolved if _inside(resolved, CODE_ROOT) else None


def resolve_safe(user_path: str) -> Path | None:
    """Legacy alias. Resolves inside WORKSPACE."""
    return resolve_in_workspace(user_path)


def code_root() -> Path:
    return CODE_ROOT