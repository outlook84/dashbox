from __future__ import annotations

from ..config.validation import is_ytdlp_search_prefix
from ..sites import registry


def search_url_for_key(prefix: str, limit: int, key: str) -> str:
    return f"{prefix}{limit}:{key}"


def is_search_extract_url(url: str) -> bool:
    return registry.is_extract_search_url(url) or is_ytdlp_search_url(url)


def is_ytdlp_search_url(url: str) -> bool:
    return ":" in url and is_ytdlp_search_prefix(url.split(":", 1)[0])
