from __future__ import annotations

from urllib.parse import SplitResult, parse_qs, parse_qsl, urlencode, urlsplit, urlunsplit


def url_host(value: str) -> str:
    return (urlsplit(value).hostname or "").lower()


def host_matches(host: str, domain: str) -> bool:
    host = host.lower().rstrip(".")
    domain = domain.lower().rstrip(".")
    return host == domain or host.endswith(f".{domain}")


def url_host_matches(value: str, domain: str) -> bool:
    return host_matches(url_host(value), domain)


def url_parts_for_host(value: str, domain: str) -> SplitResult | None:
    parts = urlsplit(value)
    if not host_matches(parts.hostname or "", domain):
        return None
    return parts


def url_parts_for_any_host(value: str, *domains: str) -> SplitResult | None:
    parts = urlsplit(value)
    host = parts.hostname or ""
    if not any(host_matches(host, domain) for domain in domains):
        return None
    return parts


def url_path_segments(value: str) -> list[str]:
    return [segment for segment in urlsplit(value).path.split("/") if segment]


def url_path_segments_for_host(value: str, domain: str) -> list[str]:
    parts = url_parts_for_host(value, domain)
    if parts is None:
        return []
    return url_path_segments(value)


def first_query_value(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return values[0] if values else ""


def url_query_value(value: str, key: str) -> str:
    return first_query_value(parse_qs(urlsplit(value).query), key)


def with_query_param(value: str, key: str, query_value: str) -> str:
    parts = urlsplit(value)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[key] = query_value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
