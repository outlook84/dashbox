from __future__ import annotations

from urllib.parse import quote, unquote

from ..utils import text


def safe_title(value: str) -> str:
    return text.display_title(value).replace("#", "＃").replace("$", "＄")


def safe_play_value(value: str) -> str:
    return quote(value, safe=":/?&=+;,@")


def restore_play_value(value: str) -> str:
    return unquote(value)
