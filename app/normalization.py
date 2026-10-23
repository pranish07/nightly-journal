from __future__ import annotations

import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_TRAILING_PUNCTUATION = re.compile(r"[.!?;:,]+$")


def normalize_goal_title(title: str) -> str:
    """Return a stable analytics key for a user-entered goal title.

    The displayed title is left untouched. This value is only for grouping,
    duplicate detection, and "reuse yesterday's goals".
    """

    normalized = unicodedata.normalize("NFKC", title).strip()
    normalized = _WHITESPACE.sub(" ", normalized).casefold()
    normalized = _TRAILING_PUNCTUATION.sub("", normalized).strip()
    return normalized
