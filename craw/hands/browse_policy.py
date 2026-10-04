"""Craw's browsing policy.

Which domains Craw is allowed to fetch, and which URLs are refused
regardless. Whitelist, not blacklist. If the hostname isn't on the
list (or a *.suffix match), it doesn't get fetched.

Also refuses:
  - non-http(s) schemes
  - URLs with user:pass in them
  - private IP ranges (localhost, 10.x, 192.168.x, 172.16-31.x, 169.254.x)
  - .local, .internal, .lan TLDs

Reads .craw/browse_policy.json at runtime so you can add domains
without touching Python.
"""

from __future__ import annotations

import ipaddress
import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from craw.state import CRAW_HOME

POLICY_PATH = CRAW_HOME / "browse_policy.json"


DEFAULT_ALLOWED = [
    "docs.python.org",
    "developer.mozilla.org",
    "github.com",
    "stackoverflow.com",
    "en.wikipedia.org",
    "*.wikipedia.org",
    "arxiv.org",
    "news.ycombinator.com",
    "khanacademy.org",
    "*.khanacademy.org",
    "youtube.com",
    "*.youtube.com",
    "pypi.org",
    "learn.microsoft.com",
    "apcentral.collegeboard.org",
    "docs.github.com",
    "raw.githubusercontent.com",
    "gist.github.com",
]


BLOCKED_ALWAYS = [
    "localhost",
    "127.",
    "0.",
    "169.254.",
    "10.",
    "192.168.",
    ".local",
    ".internal",
    ".lan",
]


@dataclass
class Decision:
    allowed: bool
    reason: str = ""
    url: str = ""
    domain: str = ""


@dataclass
class BrowsePolicy:
    allowed: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED))
    max_bytes: int = 1_048_576        # 1 MB
    timeout_seconds: int = 15

    @classmethod
    def load(cls, path: Path = POLICY_PATH) -> "BrowsePolicy":
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        return cls(
            allowed=list(data.get("allowed", DEFAULT_ALLOWED)),
            max_bytes=int(data.get("max_bytes", 1_048_576)),
            timeout_seconds=int(data.get("timeout_seconds", 15)),
        )

    def check(self, url: str) -> Decision:
        try:
            parsed = urlparse(url)
        except Exception:
            return Decision(False, "couldn't parse url", url)

        if parsed.scheme not in ("http", "https"):
            return Decision(False, "only http and https", url)

        if parsed.username or parsed.password:
            return Decision(False, "no user:pass in urls", url)

        host = (parsed.hostname or "").lower()
        if not host:
            return Decision(False, "no hostname", url)

        # private / internal — refused before whitelist even matters
        for bad in BLOCKED_ALWAYS:
            if bad in host:
                return Decision(False, f"blocked: {bad}", url, host)

        # if host is an IP literal, only allow public IPs
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                return Decision(False, "private ip", url, host)
        except ValueError:
            pass  # not an IP, fine

        # whitelist match: exact or *.suffix
        for pattern in self.allowed:
            if pattern.startswith("*."):
                suffix = pattern[2:]
                if host == suffix or host.endswith("." + suffix):
                    return Decision(True, "whitelisted", url, host)
            elif host == pattern.lower():
                return Decision(True, "whitelisted", url, host)

        return Decision(False, f"{host} isn't on my list", url, host)