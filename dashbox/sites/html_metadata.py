from __future__ import annotations

import html
import logging
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable
from urllib.parse import urljoin

from ..config import Config
from ..utils.dicts import compact_dict
from .html_extract import first_descendant, parse_html

logger = logging.getLogger("dashbox.metadata")


async def html_light_metadata(
    raw_id: str,
    config: Config,
    http_client_provider: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    if not raw_id.startswith(("http://", "https://")):
        return {}
    try:
        async with metadata_http_client(config, http_client_provider) as client:
            response = await client.get(
                raw_id,
                headers=request_headers(config, raw_id),
                timeout=min(config.upstream_timeout, 8),
            )
        response.raise_for_status()
    except Exception as exc:
        logger.debug("html metadata failed url=%s error=%s", raw_id, exc)
        return {}
    metadata = metadata_from_html(response.text, str(response.url))
    if metadata:
        logger.debug("html metadata title=%s url=%s", metadata.get("title"), raw_id)
    return metadata


@asynccontextmanager
async def metadata_http_client(config: Config, http_client_provider: Callable[[], Any] | None = None):
    if http_client_provider is not None:
        yield http_client_provider()
        return

    import httpx

    async with httpx.AsyncClient(timeout=min(config.upstream_timeout, 8), follow_redirects=True) as client:
        yield client


async def impersonated_html_light_metadata(raw_id: str, download_impersonated: Callable[[str], Awaitable[str]]) -> dict[str, Any]:
    if not raw_id.startswith(("http://", "https://")):
        return {}
    try:
        webpage = await download_impersonated(raw_id)
    except Exception as exc:
        logger.debug("impersonated html metadata failed url=%s error=%s", raw_id, exc)
        return {}
    metadata = metadata_from_html(webpage, raw_id)
    if metadata:
        logger.debug("impersonated html metadata title=%s url=%s", metadata.get("title"), raw_id)
    return metadata


def request_headers(config: Config, referer: str = "") -> dict[str, str]:
    headers = {"User-Agent": config.effective_user_agent}
    if referer:
        headers["Referer"] = referer
    return headers


def metadata_from_html(html_text: str, final_url: str) -> dict[str, Any]:
    values: dict[str, str] = {}
    root = parse_html(html_text)
    for node in root.descendants():
        if node.tag not in {"meta", "link"}:
            continue
        key = node.attr("property") or node.attr("name") or node.attr("rel")
        content = node.attr("content") or node.attr("href")
        if key and content:
            values.setdefault(key.lower(), content.strip())

    title = first_text(values, "og:title", "twitter:title")
    if not title:
        title_node = first_descendant(root, "title")
        if title_node:
            title = " ".join(html.unescape(title_node.text()).split())

    thumbnail = first_text(values, "og:image", "twitter:image", "image_src")
    if thumbnail:
        thumbnail = urljoin(final_url, thumbnail)
    duration = int_text(first_text(values, "video:duration", "duration"))
    description = first_text(values, "og:description", "twitter:description", "description")
    return compact_dict(webpage_url=final_url, title=title, thumbnail=thumbnail, duration=duration, description=description)


def first_text(values: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = values.get(key)
        if value:
            return value
    return ""


def int_text(value: str) -> int | None:
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None
