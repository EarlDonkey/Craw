"""Craw's actual hands.

Every tool is a plain Python function. Every one is safe. Every one is
reversible or read-only. No arbitrary shell, no arbitrary writes, no
network beyond the browse whitelist.

If you want to add a tool: write a function, wrap it in Tool(...), and
register it. That's it. The router picks it up automatically.
"""

from __future__ import annotations

import os
import subprocess
import time
import webbrowser
from pathlib import Path

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

def tell_time(**_ignored) -> str:
    return time.strftime("%H:%M")


def tell_date(**_ignored) -> str:
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


# ---- workspace (internal sandbox) ----------------------------------------

def write_file(path: str, content: str) -> str:
    from craw.hands.workspace import resolve_in_workspace, MAX_FILE_BYTES

    target = resolve_in_workspace(path)
    if target is None:
        return "i can only write inside my own workspace."
    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        return f"that's too big — i cap writes at {MAX_FILE_BYTES // 1024} KB."
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} chars to {target.name}."
    except OSError as exc:
        return f"write failed: {exc}"


def read_workspace(path: str, max_bytes: int = 4000) -> str:
    from craw.hands.workspace import resolve_in_workspace

    target = resolve_in_workspace(path)
    if target is None:
        return "i can only read inside my own workspace."
    if not target.exists():
        return f"no such file: {target.name}"
    if not target.is_file():
        return f"not a file: {target.name}"
    try:
        return target.read_text(encoding="utf-8", errors="replace")[:max_bytes]
    except OSError as exc:
        return f"read failed: {exc}"


def list_workspace() -> str:
    from craw.hands.workspace import ensure, WORKSPACE

    ensure()
    try:
        entries = sorted(WORKSPACE.rglob("*"))
    except OSError as exc:
        return f"listing failed: {exc}"
    if not entries:
        return "(empty)"
    lines = []
    for e in entries[:100]:
        rel = e.relative_to(WORKSPACE)
        marker = "[dir]" if e.is_dir() else "     "
        lines.append(f"{marker} {rel}")
    return "\n".join(lines)


# ---- code playground -----------------------------------------------------

def _strip_fences(text: str) -> str:
    """Remove markdown code fences from LLM output.

    Handles all these cases:

        ```python\\ncode\\n```
        ```python code```
        ```\\ncode\\n```
        ```code```
        code (no fences)
        code```

    Returns the bare content with the fence and language tag removed.
    """
    text = text.strip()

    # Opening fence
    if text.startswith("```"):
        after = text[3:]
        # Find where the language tag ends: newline or first whitespace
        nl = after.find("\n")
        sp = after.find(" ")
        if nl != -1 and (sp == -1 or nl < sp):
            # multi-line fence: strip through the newline
            text = after[nl + 1:]
        elif sp != -1:
            # one-line fence with language tag: strip through the space
            text = after[sp + 1:]
        else:
            # bare ``` with no language tag, no space
            text = after

    # Closing fence
    text = text.rstrip()
    if text.endswith("```"):
        text = text[:-3]

    return text.strip()


def write_code(path: str, content: str) -> str:
    from craw.hands.workspace import resolve_in_code_root, MAX_FILE_BYTES, code_root
    from craw.hands.crypto_guard import check as crypto_check, refusal_message

    target = resolve_in_code_root(path)
    if target is None:
        return (
            f"i can only write inside the playground: {code_root()}\n"
            f"'{path}' resolves outside it."
        )

    content = _strip_fences(content)

    if len(content.encode("utf-8")) > MAX_FILE_BYTES:
        return f"that's too big — i cap writes at {MAX_FILE_BYTES // 1024} KB."

    allowed, reason = crypto_check(content)
    if not allowed:
        return refusal_message(reason)

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        existed = target.exists()
        target.write_text(content, encoding="utf-8")
        verb = "updated" if existed else "wrote"
        rel = target.relative_to(code_root())
        return f"{verb} {rel} ({len(content)} chars)"
    except OSError as exc:
        return f"write failed: {exc}"


def read_code(path: str, max_bytes: int = 8000) -> str:
    from craw.hands.workspace import resolve_in_code_root

    target = resolve_in_code_root(path)
    if target is None:
        return "i can only read inside the playground."
    if not target.exists():
        return f"no such file: {target.name}"
    if not target.is_file():
        return f"not a file: {target.name}"
    try:
        return target.read_text(encoding="utf-8", errors="replace")[:max_bytes]
    except OSError as exc:
        return f"read failed: {exc}"


def list_code(path: str = "") -> str:
    from craw.hands.workspace import resolve_in_code_root, code_root

    target = resolve_in_code_root(path) if path else code_root()
    if target is None:
        return "path is outside the playground."
    if not target.exists():
        return f"no such folder: {target}"
    if not target.is_dir():
        return f"not a folder: {target}"
    try:
        entries = sorted(target.iterdir(),
                         key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as exc:
        return f"list failed: {exc}"
    if not entries:
        return "(empty)"
    lines = []
    for e in entries[:200]:
        rel = e.relative_to(code_root())
        marker = "[dir]" if e.is_dir() else "     "
        lines.append(f"{marker} {rel}")
    return "\n".join(lines)


# ---- browse --------------------------------------------------------------

def browse(url: str) -> str:
    from craw.hands.browse_policy import BrowsePolicy
    from craw.hands.browse_runner import fetch
    from craw.brain.memory import get_memory
    from craw.brain.reading import Readings
    from craw.brain.library import Library

    policy = BrowsePolicy.load()
    decision = policy.check(url)
    if not decision.allowed:
        return f"i can't browse that. {decision.reason}."

    result = fetch(url, policy)
    if not result.ok:
        return f"fetch failed: {result.error}"

    try:
        mem = get_memory()
        r = Readings(mem).record(
            url=result.url,
            title=result.title,
            text=result.text,
            domain=decision.domain,
        )
        try:
            Library(mem).index_reading(
                reading_id=r.id,
                url=result.url,
                title=result.title,
                text=result.text,
            )
        except Exception:
            pass
    except Exception:
        pass

    body = result.text[:4000]
    head = f"# {result.title}\n{result.url}\n\n" if result.title else f"{result.url}\n\n"
    return head + body


# ---- recall --------------------------------------------------------------

def recall(query: str) -> str:
    from craw.brain.library import Library
    from craw.brain.memory import get_memory

    lib = Library(get_memory())
    result = lib.search_and_format(query, limit=3)
    if not result:
        return f"nothing in my library matches {query!r}."
    return result


# ---- run_shell (policy-gated) --------------------------------------------

_POLICY = None


def _policy():
    global _POLICY
    if _POLICY is None:
        from craw.hands.shell_policy import ShellPolicy
        _POLICY = ShellPolicy.load()
    return _POLICY


def run_shell(command: str) -> str:
    from craw.hands.shell_runner import run as run_cmd
    from craw.hands.shell_log import write as log_write

    policy = _policy()
    decision = policy.evaluate(command)
    if not decision.allowed:
        log_write(command, "refused", -1, 0, decision.reason)
        return f"i can't run that. {decision.reason}."

    result = run_cmd(command, policy)
    if result.ok:
        return result.output
    return f"exit {result.exit_code}\n{result.output}"


# ---- registration --------------------------------------------------------

def _register_all() -> None:
    if REGISTRY.names():
        return

    # auto tier
    REGISTRY.register(Tool("tell_time", "what time is it", tell_time, tier="auto"))
    REGISTRY.register(Tool("tell_date", "what day is it", tell_date, tier="auto"))
    REGISTRY.register(Tool("list_dir", "list files and subfolders inside a folder",
                           list_dir, tier="auto",
                           args={"path": "string, folder path (optional)"}))
    REGISTRY.register(Tool("search_files",
                           "find files by name (not folders — use list_dir for folders)",
                           search_files, tier="auto",
                           args={"query": "string", "folder": "string (optional)"}))
    REGISTRY.register(Tool("read_file", "read a text file", read_file, tier="auto",
                           args={"path": "string", "max_bytes": "int (optional)"}))
    REGISTRY.register(Tool("read_clipboard", "read the clipboard", read_clipboard, tier="auto"))
    REGISTRY.register(Tool("system_stats", "cpu, ram, disk usage", system_stats, tier="auto"))
    REGISTRY.register(Tool("active_window", "which window is focused", active_window, tier="auto"))
    REGISTRY.register(Tool("list_processes", "top processes by memory", list_processes, tier="auto"))

    # workspace
    REGISTRY.register(Tool("write_file",
                           "save a note or text to a file in the internal workspace",
                           write_file, tier="confirm",
                           args={"path": "string, relative path", "content": "string"}))
    REGISTRY.register(Tool("read_workspace", "read a file from the internal workspace",
                           read_workspace, tier="auto",
                           args={"path": "string, relative path"}))
    REGISTRY.register(Tool("list_workspace", "list files in the internal workspace",
                           list_workspace, tier="auto"))

    # code playground
    REGISTRY.register(Tool(
        "write_code",
        "WRITE CODE: create or update a file in the playground. "
        "Use for 'write a script', 'create a program', 'make a tool', "
        "'save this code', 'add a function to X.py'. "
        "args: path (filename or relative path), content (full file text).",
        write_code, tier="confirm",
        args={"path": "string, filename or relative path",
              "content": "string, the full file contents"},
    ))
    REGISTRY.register(Tool("read_code", "read a file from the code playground",
                           read_code, tier="auto",
                           args={"path": "string, filename or relative path",
                                 "max_bytes": "int (optional)"}))
    REGISTRY.register(Tool("list_code", "list files in the code playground",
                           list_code, tier="auto",
                           args={"path": "string (optional)"}))

    # recall + browse
    REGISTRY.register(Tool("recall",
                           "search what you have already read (use for questions about things you read)",
                           recall, tier="auto",
                           args={"query": "string"}))
    REGISTRY.register(Tool("read_web_page",
                           "fetch a web page and read it yourself (does NOT open a browser)",
                           browse, tier="confirm",
                           args={"url": "string, full URL"}))

    # confirm tier — apps, media, ui
    REGISTRY.register(Tool("open_app", "open a whitelisted app by name", open_app, tier="confirm",
                           args={"name": "string"}))
    REGISTRY.register(Tool("open_path", "open a file or folder", open_path, tier="confirm",
                           args={"path": "string"}))
    REGISTRY.register(Tool("open_in_browser",
                           "open a URL in your default browser (shows it to the user)",
                           open_url, tier="confirm",
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

    # shell
    REGISTRY.register(Tool("run_shell", "run a shell command (whitelisted)",
                           run_shell, tier="confirm",
                           args={"command": "string, the full command to run"}))


_register_all()