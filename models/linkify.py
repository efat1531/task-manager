"""Pure text helpers for turning task text into clickable links.

No Qt, DB, or network here so the detection logic stays unit-testable. The view
layer (``views.main_window``) uses these to decide when a title cell should be
rendered as a hyperlink that opens the default browser.
"""
from __future__ import annotations

import re
from typing import Optional

# A pragmatic http(s) URL matcher: scheme + host + any non-space, non-quote run.
# Trailing punctuation that commonly hugs a URL in prose is trimmed afterwards.
_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.IGNORECASE)

# A pull-request-style number token, e.g. "#123".
_PR_NUMBER_RE = re.compile(r"#(\d+)")

_TRAILING = ".,;:!?"


def first_url(*texts: str) -> Optional[str]:
    """Return the first http(s) URL found across ``texts`` (checked in order).

    Used to find a task's link: title is passed before description so a URL in
    the title wins. Returns ``None`` when no text contains a URL.
    """
    for text in texts:
        if not text:
            continue
        match = _URL_RE.search(text)
        if match:
            return match.group(0).rstrip(_TRAILING)
    return None


def pr_number(title: str) -> Optional[str]:
    """Return the ``#<digits>`` token from ``title`` (e.g. ``"#123"``), or None."""
    if not title:
        return None
    match = _PR_NUMBER_RE.search(title)
    return match.group(0) if match else None
