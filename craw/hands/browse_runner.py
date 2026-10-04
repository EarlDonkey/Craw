"""Craw's fetcher.

Fetches a whitelisted URL, strips HTML to readable text, and returns
a dict with title, markdown-ish body, and byte count. Does not follow
redirects to non-whitelisted domains.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

import httpx

from craw.hands.browse_log import write as log_write
from craw.hands.browse_policy import BrowsePolicy


USER_AGENT = "Craw/0.4 (+local)"
STRIP_TAGS = ("script", "style", "nav", "footer", "aside", "header", "noscript")


@dataclass
class FetchResult:
    ok: bool
    url: str
    title: str
    text: str
    bytes: int
    duration_ms: int
    error: str = ""


def fetch(url: str, policy: BrowsePolicy) -> FetchResult:
    start = time.time()
    try:
        with httpx.Client(
            follow_redirects=False,
            timeout=policy.timeout_seconds,
            headers={"User-Agent": USER_AGENT},
        ) as client:
            resp = client.get(url)
    except httpx.TimeoutException:
        dur = int((time.time() - start) * 1000)
        log_write(url, "timeout", 0, dur)
        return FetchResult(False, url, "", "", 0, dur, "timed out")
    except httpx.HTTPError as exc:
        dur = int((time.time() - start) * 1000)
        log_write(url, "error", 0, dur)
        return FetchResult(False, url, "", "", 0, dur, str(exc))

    # redirect — check target against policy before following
    if resp.is_redirect:
        location = resp.headers.get("location", "")
        if location.startswith("/"):
            from urllib.parse import urljoin
            location = urljoin(url, location)
        redirect_decision = policy.check(location)
        if not redirect_decision.allowed:
            dur = int((time.time() - start) * 1000)
            log_write(url, "redir-x", 0, dur)
            return FetchResult(False, url, "", "", 0, dur, "redirected off-list")
        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=policy.timeout_seconds,
                headers={"User-Agent": USER_AGENT},
            ) as client:
                resp = client.get(location)
        except httpx.HTTPError as exc:
            dur = int((time.time() - start) * 1000)
            log_write(url, "error", 0, dur)
            return FetchResult(False, url, "", "", 0, dur, str(exc))

    content = resp.content
    if len(content) > policy.max_bytes:
        content = content[: policy.max_bytes]

    html = content.decode(resp.encoding or "utf-8", errors="replace")
    title = _extract_title(html)
    text = _to_markdown(html)

    dur = int((time.time() - start) * 1000)
    log_write(url, "ok", len(content), dur)
    return FetchResult(True, url, title, text, len(content), dur)


def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return _clean(m.group(1)) if m else ""


def _to_markdown(html: str) -> str:
    """Very small HTML -> text converter. No external dep."""
    # strip dangerous/noisy blocks
    for tag in STRIP_TAGS:
        html = re.sub(
            rf"<{tag}\b[^>]*>.*?</{tag}>",
            "",
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
    # preserve code blocks
    html = re.sub(r"<pre[^>]*>(.*?)</pre>", r"\n```\n\1\n```\n",
                  html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<code[^>]*>(.*?)</code>", r"`\1`",
                  html, flags=re.IGNORECASE | re.DOTALL)
    # headings
    for i in range(1, 7):
        html = re.sub(rf"<h{i}[^>]*>(.*?)</h{i}>",
                      lambda m, n=i: "\n" + "#" * n + " " + m.group(1) + "\n",
                      html, flags=re.IGNORECASE | re.DOTALL)
    # paragraphs / br / li
    html = re.sub(r"</p\s*>", "\n\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<li[^>]*>", "\n- ", html, flags=re.IGNORECASE)
    # strip everything else
    html = re.sub(r"<[^>]+>", "", html)
    # collapse
    html = _clean(html)
    return html


def _clean(s: str) -> str:
    s = re.sub(r"&nbsp;", " ", s)
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&lt;", "<", s)
    s = re.sub(r"&gt;", ">", s)
    s = re.sub(r"&quot;", '"', s)
    s = re.sub(r"&#39;", "'", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    return s.strip()