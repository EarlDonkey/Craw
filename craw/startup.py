"""Install Craw as a startup shortcut.

Drops a .lnk in the Windows Startup folder that runs `pythonw -m craw`
hidden, with logs redirected to .craw/daemon.log.

This is not a Windows service — it runs in your user session, so the
voice, ears, and desktop tools all work. It starts when you log in,
which is the practical "always on" that a creature needs.

Uses the absolute path to pythonw.exe, never the `py` launcher stub.
The Store version of `py.exe` chains through a parent process that
survives child kills, causing zombie daemons.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


STARTUP_DIR_NAME = "Microsoft\\Windows\\Start Menu\\Programs\\Startup"


def _startup_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("APPDATA not set — not a Windows environment?")
    return Path(appdata) / STARTUP_DIR_NAME


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _python_launcher() -> str:
    """Absolute path to pythonw.exe (windowless Python).

    Never returns `py` or a relative name. Absolute only.
    """
    exe_dir = Path(sys.executable).parent
    pyw = exe_dir / "pythonw.exe"
    if pyw.exists():
        return str(pyw)
    # Fallback: python.exe (still absolute, just shows a window)
    py = exe_dir / "python.exe"
    if py.exists():
        return str(py)
    raise RuntimeError(f"no pythonw.exe or python.exe next to {sys.executable}")


def install() -> tuple[bool, str]:
    """Create the startup shortcut. Returns (ok, message)."""
    startup = _startup_dir()
    if not startup.exists():
        return False, f"startup folder not found: {startup}"

    link_path = startup / "Craw.lnk"
    root = _repo_root()
    python = _python_launcher()

    ps = f"""
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut('{link_path}')
$sc.TargetPath = '{python}'
$sc.Arguments = '-m craw'
$sc.WorkingDirectory = '{root}'
$sc.WindowStyle = 7
$sc.Description = 'Craw — a creature that lives in your shell'
$sc.Save()
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"failed to create shortcut: {exc}"

    if result.returncode != 0:
        return False, f"powershell error: {result.stderr.strip()}"

    if not link_path.exists():
        return False, "shortcut not created (unknown reason)"

    return True, f"installed: {link_path}  (target: {python})"


def uninstall() -> tuple[bool, str]:
    startup = _startup_dir()
    link_path = startup / "Craw.lnk"
    if not link_path.exists():
        return False, "no shortcut to remove"
    try:
        link_path.unlink()
        return True, f"removed: {link_path}"
    except OSError as exc:
        return False, f"failed to remove: {exc}"


def status() -> tuple[bool, str]:
    startup = _startup_dir()
    link_path = startup / "Craw.lnk"
    if link_path.exists():
        return True, f"installed at {link_path}"
    return False, "not installed"