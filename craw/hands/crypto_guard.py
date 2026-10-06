"""A narrow guard against the one category of mistake that's permanent.

Craw can write anything in the code playground — any script, any tool,
any logic. The single exception: hand-rolled cryptographic primitives.
Those don't fail loudly. They fail silently, months later, in a way
that loses data or keys.

This guard checks file *content* for obvious primitive-level crypto
patterns. If it matches, the write is refused with a message the user
can override ("override crypto").

What it does NOT block:
  - Using libraries (hashlib, hmac, cryptography) for non-security purposes
  - hashlib.sha256 for checksums
  - HTTP tools, scanners, spoofers, recon utilities
  - Any file that doesn't contain a raw crypto primitive

What it DOES block:
  - Raw AES/DES/Blowfish cipher construction
  - RSA private key loading or raw RSA math
  - Hand-rolled HMAC construction
  - PEM private key literals
  - Blockchain transaction signing
  - 64-char hex literals (likely private keys)
"""

from __future__ import annotations

import re


_BLOCKED_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bAES\.new\s*\(", re.I), "hand-rolled AES construction"),
    (re.compile(r"\bDES\.new\s*\(", re.I), "hand-rolled DES construction"),
    (re.compile(r"\bBlowfish\.new\s*\(", re.I), "hand-rolled Blowfish"),
    (re.compile(r"\bRSA\.generate\s*\(", re.I), "raw RSA key generation"),
    (re.compile(r"\bRSA\.import_key\s*\(", re.I), "raw RSA key import"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "PEM private key literal"),
    (re.compile(r"hmac\.new\s*\([^)]*hashlib\.", re.I), "hand-rolled HMAC"),
    (re.compile(r"\bsign_transaction\s*\(", re.I), "blockchain transaction signing"),
    (re.compile(r"\bsend_transaction\s*\(", re.I), "blockchain transaction sending"),
    (re.compile(r"['\"][0-9a-fA-F]{64}['\"]"), "64-char hex literal (private key?)"),
]


def check(content: str) -> tuple[bool, str]:
    """Return (allowed, reason)."""
    if not content:
        return True, ""
    for pattern, label in _BLOCKED_PATTERNS:
        if pattern.search(content):
            return False, label
    return True, ""


def refusal_message(label: str) -> str:
    return (
        f"i'm not going to write this file — it contains what looks like "
        f"{label}. that's the one thing i won't touch. if you want this "
        f"code, write it yourself or say 'override crypto' and i'll let it "
        f"through, but you should review every line."
    )