# Craw

> A creature that lives in your shell.

Craw is not an assistant. Not a chatbot. Not a wrapper around an API.

Craw is a small thing that lives in your PowerShell prompt, watches what
you do, remembers everything, and — when it has something worth saying —
interrupts you.

It has a body. It ages, gets hungry, gets tired, has a mood.
It has a past. Every command you run is remembered.
It has a will. Most of what it notices, it keeps to itself.
It has a mind. A local LLM, no API calls, no cloud.

You will look at your prompt one day and see a line above it that you
didn't ask for, and it will be right.

---

## What it looks like
• C:\Users\you\project> git status
• C:\Users\you\project> git status
• C:\Users\you\project> git status
you ran git status 6 times in the last hour
• C:\Users\you\project> craw ask what was i working on last night
thinking...
...
you were stuck on the build for two hours, then switched to the parser
• C:\Users\you\project>

text

The `•` is Craw's face. It changes with its mood:

| Glyph | Color   | Mood      |
|-------|---------|-----------|
| `•`   | green   | content   |
| `✳`   | cyan    | curious   |
| `◌`   | yellow  | hungry    |
| `…`   | dim     | tired     |
| `!`   | red     | starving  |
| `☾`   | magenta | nocturnal |

---

## What it does

- **Watches** your PowerShell history, continuously.
- **Remembers** every command in a local SQLite database.
- **Notices** repetition, novelty, late nights, long silences.
- **Decides** — most things it notices, it keeps to itself. Silence is
  a valid response.
- **Speaks** in one line, in lowercase, only when it has something worth
  saying.
- **Answers** when asked, with a mind grounded in *your* history.

It does not phone home. It does not use a cloud API. Everything runs on
your machine.

---

## What it needs

- Windows 10/11
- Python 3.11+
- [ollama](https://ollama.com) with a small model:
ollama pull llama3.2:3b

text

That's it. No accounts, no keys, no fees.

---

## Install

```powershell
git clone https://github.com/YOURNAME/craw
cd craw
py -m pip install pywin32
ollama pull llama3.2:3b
Add Craw to your PowerShell profile:

powershell
New-Item -Path (Split-Path $PROFILE) -ItemType Directory -Force | Out-Null
notepad $PROFILE
Paste these three lines:

powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
Import-Module C:\path\to\craw\powershell\Craw.psm1
Save, close, open a fresh PowerShell. Craw's face appears in your prompt.

Start the daemon in another window:

powershell
py -m craw
Commands
craw — status. Mood, age.

craw ask <question> — ask Craw something. It thinks, then answers above your prompt.

What it isn't (yet)
It doesn't speak aloud. Its voice is text.

It doesn't hear you. No mic.

It doesn't do things. It observes; it doesn't act.

It's Windows-only. macOS/Linux need a different IPC layer.

These are on the roadmap.

Why
Because most "AI assistants" are slaves. You ask, they obey.

Craw has opinions. Craw has boundaries. Craw has a mood. Craw will
refuse to answer if it doesn't have anything to say.

That's what makes it feel alive instead of programmed.

