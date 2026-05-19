from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


def limit_page_urls(
    page_urls: list[str],
    *,
    current_count: int,
    limit: int = 0,
    items_per_page: int = 0,
) -> list[str]:
    if limit <= 0:
        return page_urls
    remaining = max(0, limit - current_count)
    if not remaining:
        return []
    page_size = max(1, items_per_page)
    page_count = (remaining + page_size - 1) // page_size
    return page_urls[:page_count]


def with_page_query_param(base_url: str, page: int) -> str:
    parts = urlsplit(base_url)
    query = parse_qs(parts.query, keep_blank_values=True)
    query["page"] = [str(page)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), parts.fragment))
