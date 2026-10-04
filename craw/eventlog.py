"""Craw's Event Log integration.

Writes lifecycle events (start, stop, crash) to the Windows Application
Event Log under the source name "Craw". If the source isn't registered
(needs admin once), we silently skip — the file log still works.

Reading: Event Viewer → Windows Logs → Application → source "Craw"
"""

from __future__ import annotations

import sys


_SOURCE = "Craw"


def _try_log(message: str, event_type: str = "Information") -> None:
    try:
        import win32evtlogutil
        import win32evtlog
    except ImportError:
        return

    type_map = {
        "Information": win32evtlog.EVENTLOG_INFORMATION_TYPE,
        "Warning":     win32evtlog.EVENTLOG_WARNING_TYPE,
        "Error":       win32evtlog.EVENTLOG_ERROR_TYPE,
    }
    etype = type_map.get(event_type, win32evtlog.EVENTLOG_INFORMATION_TYPE)

    try:
        win32evtlogutil.ReportEvent(
            _SOURCE,
            eventID=1,
            eventCategory=0,
            eventType=etype,
            strings=[message],
        )
    except Exception:
        # Source not registered, or not admin. Silent — file log will catch it.
        pass


def start(pid: int, host: str = "") -> None:
    who = f" as {host}" if host else ""
    _try_log(f"Craw started (pid {pid}){who}.", "Information")


def stop(reason: str = "clean shutdown") -> None:
    _try_log(f"Craw stopping: {reason}.", "Information")


def crashed(exc: BaseException) -> None:
    _try_log(f"Craw crashed: {exc!r}", "Error")


def register_source() -> bool:
    """Register the 'Craw' source in the Event Log. Needs admin once."""
    try:
        import win32evtlogutil
        win32evtlogutil.AddSourceToRegistry(
            appName=_SOURCE,
            msgDLL=None,
            eventLogType="Application",
        )
        return True
    except Exception:
        return False