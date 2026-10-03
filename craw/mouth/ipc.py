"""Craw's mouth listens on a named pipe.

On Windows, named pipes are the right IPC primitive — no ports, no
firewall, no dependencies. PowerShell connects, asks a question, gets
an answer, disconnects. One line each way.

The daemon runs this in a background thread so it doesn't block the
heartbeat.
"""

from __future__ import annotations

import json
import threading
from typing import Callable

try:
    import win32pipe
    import win32file
    import pywintypes
    _HAVE_WIN32 = True
except ImportError:
    _HAVE_WIN32 = False

PIPE_NAME = r"\\.\pipe\craw"


class Mouth:
    """The IPC server. Runs in a background thread.

    `handler(request: dict) -> Response` is called for each request.
    """

    def __init__(self, handler: Callable[[dict], object]) -> None:  # noqa: F821
        self.handler = handler
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        if not _HAVE_WIN32:
            raise RuntimeError("Craw's mouth needs pywin32 on Windows. Run: pip install pywin32")
        self._thread = threading.Thread(target=self._serve, daemon=True, name="craw-mouth")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _serve(self) -> None:
        while not self._stop.is_set():
            try:
                self._serve_one()
            except Exception:
                continue

    def _serve_one(self) -> None:
        pipe = win32pipe.CreateNamedPipe(
            PIPE_NAME,
            win32pipe.PIPE_ACCESS_DUPLEX,
            win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
            1, 65536, 65536, 0, None,
        )
        try:
            win32pipe.ConnectNamedPipe(pipe, None)
            data = win32file.ReadFile(pipe, 65536)
            request = json.loads(data[1].decode("utf-8") or "{}")
            response = self.handler(request)
            win32file.WriteFile(pipe, response.to_json().encode("utf-8"))
        except pywintypes.error:
            pass
        finally:
            try:
                win32file.CloseHandle(pipe)
            except Exception:
                pass