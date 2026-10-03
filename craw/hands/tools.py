"""Craw's actual hands.

Every tool is a plain Python function. Every one is safe. Every one is
reversible or read-only. No filesystem mutation, no shell, no network.

If you want to add a tool: write a function, wrap it in Tool(...), and
register it. That's it. The router picks it up automatically.
"""

from __future__ import annotations

import os
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Any

from craw.hands.registry import REGISTRY, Tool


HOME = Path(os.environ.get("USERPROFILE", Path.home()))
SCREENSHOT_DIR = HOME / "Downloads" / "Craw" / ".craw" / "screenshots"

ALLOWED_APPS: dict[str, str] = {
    "notepad":      "notepad.exe",
    "calculator":   "calc.exe",
    "calc":         "calc.exe",
    "explorer":     "explorer.exe",
    "task manager": "taskmgr.exe",
    "taskmgr":      "taskmgr.exe",
    "cmd":          "cmd.exe",
    "powershell":   "powershell.exe",
    "chrome":       r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "edge":         r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "vscode":       "code",
    "code":         "code",
    "spotify":      r"C:\Users\user\AppData\Roaming\Spotify\Spotify.exe",
}


# ---- auto tier -----------------------------------------------------------

def tell_time() -> str:
    return time.strftime("%H:%M")


def tell_date() -> str:
    return time.strftime("%A, %B %d, %Y")


def list_dir(path: str = "") -> str:
    target = Path(path).expanduser() if path else HOME
    if not target.exists():
        return f"no such folder: {target}"
    if not target.is_dir():
        return f"not a folder: {target}"
    try:
        entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        return f"permission denied: {target}"
    lines = [f"{'[dir]' if e.is_dir() else '     '} {e.name}" for e in entries[:100]]
    return "\n".join(lines) if lines else "(empty)"


def search_files(query: str, folder: str = "") -> str:
    root = Path(folder).expanduser() if folder else HOME
    if not root.exists():
        return f"no such folder: {root}"
    q = query.lower()
    matches: list[Path] = []
    for p in root.rglob("*"):
        if q in p.name.lower():
            matches.append(p)
            if len(matches) >= 30:
                break
    if not matches:
        return f"nothing matching '{query}'"
    return "\n".join(str(p.relative_to(root)) for p in matches)


def read_file(path: str, max_bytes: int = 2000) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"no such file: {p}"
    if not p.is_file():
        return f"not a file: {p}"
    if p.stat().st_size > 2 * 1024 * 1024:
        return "file too large (over 2MB)"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"read failed: {exc}"
    return text[:max_bytes]


def read_clipboard() -> str:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        text = root.clipboard_get()
        root.destroy()
        return text[:1000] if text else "(empty)"
    except Exception as exc:
        return f"clipboard read failed: {exc}"


def system_stats() -> str:
    try:
        import psutil
    except ImportError:
        return "psutil not installed"
    cpu = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(str(HOME))
    return (
        f"cpu {cpu:.0f}%  "
        f"ram {mem.percent:.0f}%  "
        f"disk {disk.percent:.0f}%"
    )


def active_window() -> str:
    try:
        import win32gui
    except ImportError:
        return "win32gui not installed"
    try:
        hwnd = win32gui.GetForegroundWindow()
        return win32gui.GetWindowText(hwnd) or "(unknown)"
    except Exception as exc:
        return f"failed: {exc}"


def list_processes() -> str:
    try:
        import psutil
    except ImportError:
        return "psutil not installed"
    procs = []
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            procs.append((p.info["name"], p.info["memory_info"].rss))
        except Exception:
            continue
    procs.sort(key=lambda x: x[1], reverse=True)
    top = procs[:20]
    return "\n".join(f"{n}  {m // (1024*1024)}MB" for n, m in top)


# ---- confirm tier --------------------------------------------------------

def open_app(name: str) -> str:
    key = name.lower().strip()
    target = ALLOWED_APPS.get(key)
    if not target:
        return f"i can't open '{name}'. not on my list."
    try:
        subprocess.Popen([target], shell=False)
        return f"opened {name}."
    except FileNotFoundError:
        return f"{name} isn't installed here."
    except Exception as exc:
        return f"failed to open {name}: {exc}"


def open_path(path: str) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return f"no such path: {p}"
    try:
        os.startfile(str(p))   # noqa: S606
        return f"opened {p.name}"
    except Exception as exc:
        return f"failed: {exc}"


def open_url(url: str) -> str:
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url
    try:
        webbrowser.open(url)
        return f"opened {url}"
    except Exception as exc:
        return f"failed: {exc}"


def play_pause() -> str:
    try:
        import ctypes
        ctypes.windll.user32.keybd_event(0xB3, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0xB3, 0, 2, 0)
        return "toggled playback."
    except Exception as exc:
        return f"failed: {exc}"


def volume_up() -> str:
    return _volume_key(0xAF, "volume up.")


def volume_down() -> str:
    return _volume_key(0xAE, "volume down.")


def mute() -> str:
    return _volume_key(0xAD, "muted.")


def _volume_key(vk: int, msg: str) -> str:
    try:
        import ctypes
        for _ in range(5):
            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
        return msg
    except Exception as exc:
        return f"failed: {exc}"


def take_screenshot() -> str:
    try:
        from PIL import ImageGrab
    except ImportError:
        return "Pillow not installed"
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    fname = SCREENSHOT_DIR / f"shot_{int(time.time())}.png"
    try:
        img = ImageGrab.grab()
        img.save(fname)
        return f"saved to {fname.name}"
    except Exception as exc:
        return f"failed: {exc}"


def notify(title: str, body: str = "") -> str:
    try:
        from win10toast import ToastNotifier
    except ImportError:
        try:
            ps = (
                f'[reflection.assembly]::loadwithpartialname("System.Windows.Forms") | Out-Null;'
                f'[System.Windows.Forms.MessageBox]::Show("{body}", "{title}")'
            )
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps])
            return "notified."
        except Exception as exc:
            return f"failed: {exc}"
    try:
        ToastNotifier().show_toast(title, body, duration=5, threaded=True)
        return "notified."
    except Exception as exc:
        return f"failed: {exc}"


def remember(text: str) -> str:
    return f"remembered: {text}"


# ---- registration --------------------------------------------------------

def _register_all() -> None:
    REGISTRY.register(Tool("tell_time", "what time is it", tell_time, tier="auto"))
    REGISTRY.register(Tool("tell_date", "what day is it", tell_date, tier="auto"))
    REGISTRY.register(Tool("list_dir", "list files in a folder", list_dir, tier="auto",
                           args={"path": "string, folder path (optional)"}))
    REGISTRY.register(Tool("search_files", "find files by name", search_files, tier="auto",
                           args={"query": "string", "folder": "string (optional)"}))
    REGISTRY.register(Tool("read_file", "read a text file", read_file, tier="auto",
                           args={"path": "string", "max_bytes": "int (optional)"}))
    REGISTRY.register(Tool("read_clipboard", "read the clipboard", read_clipboard, tier="auto"))
    REGISTRY.register(Tool("system_stats", "cpu, ram, disk usage", system_stats, tier="auto"))
    REGISTRY.register(Tool("active_window", "which window is focused", active_window, tier="auto"))
    REGISTRY.register(Tool("list_processes", "top processes by memory", list_processes, tier="auto"))

    REGISTRY.register(Tool("open_app", "open a whitelisted app by name", open_app, tier="confirm",
                           args={"name": "string"}))
    REGISTRY.register(Tool("open_path", "open a file or folder", open_path, tier="confirm",
                           args={"path": "string"}))
    REGISTRY.register(Tool("open_url", "open a URL in the browser", open_url, tier="confirm",
                           args={"url": "string"}))
    REGISTRY.register(Tool("play_pause", "toggle media playback", play_pause, tier="confirm"))
    REGISTRY.register(Tool("volume_up", "raise volume", volume_up, tier="confirm"))
    REGISTRY.register(Tool("volume_down", "lower volume", volume_down, tier="confirm"))
    REGISTRY.register(Tool("mute", "mute the system", mute, tier="confirm"))
    REGISTRY.register(Tool("take_screenshot", "screenshot to Craw's home", take_screenshot, tier="confirm"))
    REGISTRY.register(Tool("notify", "show a notification", notify, tier="confirm",
                           args={"title": "string", "body": "string"}))
    REGISTRY.register(Tool("remember", "save a note into memory", remember, tier="confirm",
                           args={"text": "string"}))


_register_all()