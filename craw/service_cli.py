"""Craw CLI — install, uninstall, status, restart.

Usage:
  python -m craw.service_cli install
  python -m craw.service_cli uninstall
  python -m craw.service_cli status
  python -m craw.service_cli restart
  python -m craw.service_cli log
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def cmd_install() -> int:
    from craw.startup import install
    from craw.eventlog import register_source

    print("registering event log source (may need admin)...")
    if register_source():
        print("  event log source registered.")
    else:
        print("  event log source not registered — file log will still work.")

    print("installing startup shortcut...")
    ok, msg = install()
    print(f"  {msg}")
    return 0 if ok else 1


def cmd_uninstall() -> int:
    from craw.startup import uninstall
    ok, msg = uninstall()
    print(msg)
    return 0 if ok else 1


def cmd_status() -> int:
    from craw.startup import status

    ok, msg = status()
    print(f"startup: {msg}")

    pid_file = _root() / ".craw" / "daemon.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            print(f"daemon:  running (pid {pid})")
        except (OSError, ValueError):
            print("daemon:  unknown (pid file unreadable)")
    else:
        print("daemon:  not running")

    return 0


def cmd_restart() -> int:
    # Kill every python / pythonw first. Some may be zombies from
    # a previous session.
    subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe"], capture_output=True)
    subprocess.run(["taskkill", "/F", "/IM", "python.exe"], capture_output=True)
    time.sleep(2.0)

    # Clean stale state
    pid_file = _root() / ".craw" / "daemon.pid"
    try:
        pid_file.unlink(missing_ok=True)
    except OSError:
        pass

    # Start one fresh, using the absolute pythonw path
    from craw.startup import _python_launcher, _repo_root
    root = _repo_root()
    py = _python_launcher()
    subprocess.Popen([py, "-m", "craw"], cwd=str(root))
    time.sleep(3.0)
    return cmd_status()


def cmd_log() -> int:
    log = _root() / ".craw" / "daemon.log"
    if not log.exists():
        print("(no log file yet)")
        return 0
    print(f"tailing {log} (Ctrl+C to stop)")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Get-Content '{log}' -Wait -Tail 40"])
    except KeyboardInterrupt:
        pass
    return 0


COMMANDS = {
    "install":   cmd_install,
    "uninstall": cmd_uninstall,
    "status":    cmd_status,
    "restart":   cmd_restart,
    "log":       cmd_log,
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("usage: python -m craw.service_cli <command>")
        print("commands: " + ", ".join(COMMANDS.keys()))
        return 2
    return COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    sys.exit(main())