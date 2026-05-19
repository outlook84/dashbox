from __future__ import annotations

import re
from typing import Any


_DURATION_TEXT_RE = re.compile(r"\d{1,2}:\d{2}(?::\d{2})?")


def duration_text(value: Any) -> str:
    if isinstance(value, bool):
        return ""
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return ""
    if seconds <= 0:
        return ""
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minute:02d}:{sec:02d}"
    return f"{minute}:{sec:02d}"


def existing_duration_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    duration = value.strip()
    if _DURATION_TEXT_RE.fullmatch(duration):
        return duration
    return ""
