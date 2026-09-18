"""HTML -> plain text and small string helpers."""
from __future__ import annotations

import hashlib
import html as htmllib
import re

_BLOCK_TAGS = re.compile(r"</?(p|div|br|li|ul|ol|h[1-6]|tr|td|th|table|section|article|dd|dt)[^>]*>", re.I)
_TAG = re.compile(r"<[^>]+>")
_SCRIPT = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_WS = re.compile(r"[ \t\r\f\v]+")
_NL = re.compile(r"\n\s*\n+")


def html_to_text(raw: str | None) -> str:
    if not raw:
        return ""
    s = _SCRIPT.sub(" ", raw)
    s = _BLOCK_TAGS.sub("\n", s)
    s = _TAG.sub(" ", s)
    s = htmllib.unescape(s)
    s = s.replace("\xa0", " ")
    s = _WS.sub(" ", s)
    s = "\n".join(line.strip() for line in s.split("\n"))
    s = _NL.sub("\n\n", s)
    return s.strip()


def squash(s: str | None) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def stable_id(*parts: str) -> str:
    return hashlib.sha1("|".join(p or "" for p in parts).encode()).hexdigest()[:16]


def norm_key(s: str | None) -> str:
    """Lowercase, alnum-only key used for cross-source de-duplication."""
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())
