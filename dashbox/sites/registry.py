from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import bilibili, generic, pornhub, spankbang, twitch, xvideos, youtube


SITE_ADAPTERS = (
    youtube,
    bilibili,
    xvideos,
    spankbang,
    pornhub,
    twitch,
)


def resolve(url: str) -> Any:
    for adapter in SITE_ADAPTERS:
        matches = getattr(adapter, "matches_url", None)
        if matches and matches(url):
            return adapter
    return generic


def resolve_info(info: dict[str, Any], fallback_url: str = "") -> Any:
    url = call_default("playable_url_from_info", info, fallback_url)
    adapter = resolve(url)
    if not is_generic(adapter):
        return adapter
    for candidate in SITE_ADAPTERS:
        matches = getattr(candidate, "matches_info", None)
        if matches and matches(info, fallback_url):
            return candidate
    return generic


def default_callable(adapter: Any, name: str) -> Any:
    return getattr(adapter, name, getattr(generic, name))


def call(adapter: Any, name: str, *args: Any, **kwargs: Any) -> Any:
    return default_callable(adapter, name)(*args, **kwargs)


def call_for_url(url: str, name: str, *args: Any, **kwargs: Any) -> Any:
    return call(resolve(url), name, *args, **kwargs)


def call_default(name: str, *args: Any, **kwargs: Any) -> Any:
    return getattr(generic, name)(*args, **kwargs)


def is_generic(adapter: Any) -> bool:
    return adapter is generic


def normalize_config_url(url: str) -> str:
    value = url.strip()
    for adapter in SITE_ADAPTERS:
        normalize = getattr(adapter, "normalize_config_url", None)
        if normalize is None:
            continue
        normalized = normalize(value)
        if normalized != value:
            return normalized
    return value


def headers_for_format_urls(urls: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for adapter in SITE_ADAPTERS:
        for key, value in call(adapter, "headers_for_format_urls", urls).items():
            headers.setdefault(key, value)
    return headers


def is_extract_search_url(url: str) -> bool:
    return any(call(adapter, "url_is_search_directory", url) for adapter in SITE_ADAPTERS)


def supports_flat_playlist_info(info: dict[str, Any]) -> bool:
    return any(call(adapter, "supports_flat_playlist_info", info) for adapter in SITE_ADAPTERS)


def enrich_flat_playlist_info(info: dict[str, Any], webpage: str, url: str, **kwargs: Any) -> bool:
    for adapter in SITE_ADAPTERS:
        if call(adapter, "enrich_flat_playlist_info", info, webpage, url, **kwargs):
            return True
    return False


def runtime_factories() -> tuple[Callable[..., Any], ...]:
    from .bilibili.runtime import BilibiliRuntime

    return (BilibiliRuntime,)


def image_url_is_proxyable(url: str) -> bool:
    return any(call(adapter, "image_url_is_proxyable", url) for adapter in SITE_ADAPTERS)


def image_referer_for_url(url: str) -> str:
    for adapter in SITE_ADAPTERS:
        referer = call(adapter, "image_referer_for_url", url)
        if referer:
            return referer
    return ""
