from __future__ import annotations

import concurrent.futures
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from ..models import NodeKind
from ..models import MediaNode
from .html_extract import HtmlNode, first_descendant, parse_html
from .hosts import host_matches, url_path_segments_for_host
from .pagination import limit_page_urls, with_page_query_param
from .spankbang import clean_html_text, unique_entries
from .types import MetadataStrategy, SiteMetadataPlan


logger = logging.getLogger("dashbox.sites.xvideos")


def matches_url(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return (
        host_matches(host, "xvideos.com")
        or host_matches(host, "xvideos2.com")
        or host_matches(host, "xvideos.es")
    )


def is_single_video_url(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    path = parts.path.lower()
    fragment = parts.fragment.lower()
    if (host_matches(host, "xvideos.com") or host_matches(host, "xvideos2.com")) and (
        path.startswith("/video.") or path.startswith("/video")
    ):
        return True
    if host_matches(host, "xvideos.es") and (path.startswith("/video.") or path.startswith("/video")):
        return True
    if host in ("www.xvideos.com", "flashservice.xvideos.com") and path.startswith("/embedframe/"):
        return True
    if host == "static-hw.xvideos.com" and path == "/swf/xv-player.swf":
        return True
    return (host_matches(host, "xvideos.com") or host_matches(host, "xvideos2.com")) and fragment.startswith("quickies/a/")


def is_favorite_url(url: str) -> bool:
    segments = url_path_segments_for_host(url, "xvideos.com")
    return bool(len(segments) >= 2 and segments[0].lower() == "favorite" and segments[1].isdigit())


def favorite_title_from_url(url: str) -> str:
    segments = url_path_segments_for_host(url, "xvideos.com")
    if len(segments) < 2 or segments[0].lower() != "favorite":
        return ""
    return "/".join(segments[1:])


def config_node_kind(url: str) -> NodeKind | None:
    if is_favorite_url(url):
        return NodeKind.PLAYLIST_DIRECTORY
    return None


def metadata_plan_for_config_url(url: str) -> SiteMetadataPlan:
    kind = config_node_kind(url)
    return SiteMetadataPlan(
        node_kind=kind or NodeKind.LEAF_VOD,
        strategy=MetadataStrategy.SITE_API if kind == NodeKind.PLAYLIST_DIRECTORY else MetadataStrategy.DISPLAY,
        canonical_url=url,
    )


def site_api_config_item_is_directory_entry(url: str) -> bool:
    return is_favorite_url(url)


def site_api_detail_is_aggregate_vod(url: str, _info: dict[str, Any]) -> bool:
    return is_favorite_url(url)


def config_favorite_node(url: str, node_id: str, title: str = "", thumbnail: str = "", remarks: str = "") -> MediaNode | None:
    if not is_favorite_url(url):
        return None
    return MediaNode(
        node_id,
        title or favorite_title_from_url(url) or url,
        kind="playlist",
        thumbnail=thumbnail,
        remarks=remarks,
        remarks_key="" if remarks else "playlist",
    )


def config_node_from_url_item(url: str, node_id: str, title: str = "", thumbnail: str = "", remarks: str = "") -> MediaNode | None:
    return config_favorite_node(url, node_id, title, thumbnail, remarks)


def favorite_category_info(
    url: str,
    *,
    download_webpage: Callable[[str], str],
    limit: int = 0,
    concurrency: int = 1,
) -> dict[str, Any]:
    return favorite_playlist_info(
        url,
        download_webpage=download_webpage,
        limit=limit,
        concurrency=concurrency,
    )


def site_api_category_info(
    url: str,
    *,
    download_webpage: Callable[[str], str],
    limit: int = 0,
    concurrency: int = 1,
) -> dict[str, Any]:
    return favorite_category_info(
        url,
        download_webpage=download_webpage,
        limit=limit,
        concurrency=concurrency,
    )


def site_api_detail_info(
    url: str,
    *,
    download_webpage: Callable[[str], str],
    limit: int = 0,
    concurrency: int = 1,
) -> dict[str, Any]:
    return site_api_category_info(
        url,
        download_webpage=download_webpage,
        limit=limit,
        concurrency=concurrency,
    )


def favorite_playlist_info(
    url: str,
    *,
    download_webpage: Callable[[str], str],
    limit: int = 0,
    concurrency: int = 1,
) -> dict[str, Any]:
    if not is_favorite_url(url):
        return {}
    webpage = download_webpage(url)
    return playlist_info_from_webpage(
        webpage,
        url,
        download_webpage=download_webpage,
        limit=limit,
        concurrency=concurrency,
    )


def playlist_info_from_webpage(
    webpage: str,
    url: str,
    *,
    download_webpage: Callable[[str], str] | None = None,
    limit: int = 0,
    concurrency: int = 1,
) -> dict[str, Any]:
    title = document_title(webpage)
    entries = list(playlist_entries_from_webpage(webpage, url).values())
    if download_webpage:
        entries = enrich_playlist_pages(
            entries,
            webpage,
            url,
            download_webpage=download_webpage,
            limit=limit,
            concurrency=concurrency,
        )
    entries = unique_entries(entries)
    if limit > 0:
        entries = entries[:limit]
    return {
        "id": urlsplit(url).path.strip("/"),
        "title": title or url,
        "webpage_url": url,
        "original_url": url,
        "extractor": "XVideosFavorite",
        "extractor_key": "XVideosFavorite",
        "entries": [public_item(entry) for entry in entries],
    }


def playlist_entries_from_webpage(webpage: str, base_url: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for item in ordered_playlist_entries_from_webpage(webpage, base_url):
        for key in item_keys(item):
            if key:
                out[key] = public_item(item)
    return out


def ordered_playlist_entries_from_webpage(webpage: str, base_url: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    root = parse_html(webpage)
    for block in thumb_blocks(root):
        link = first_video_link(block)
        href = link.attr("href") if link else ""
        if not href:
            continue
        webpage_url = urljoin(base_url, href)
        image = first_descendant(block, "img")
        thumbnail = (image.attr("data-src") or image.attr("src")) if image else ""
        title = title_from_block(block)
        duration = clean_html_text(duration_from_block(block))
        item = {
            "ie_key": "XVideos",
            "_type": "url",
            "id": block.attr("data-eid"),
            "url": webpage_url,
            "webpage_url": webpage_url,
            "title": title,
            "thumbnail": thumbnail,
            "duration_string": duration,
        }
        if video_id := block.attr("data-id"):
            item["_dashbox_video_id"] = video_id
        if href:
            item["_dashbox_href"] = href
        out.append(item)
    return out


def document_title(webpage: str) -> str:
    node = first_descendant(parse_html(webpage), "title")
    return clean_html_text(node.text() if node else "")


def thumb_blocks(root: HtmlNode) -> list[HtmlNode]:
    return [
        node
        for node in root.descendants("div")
        if node.has_class("thumb-block")
    ]


def first_video_link(node: HtmlNode) -> HtmlNode | None:
    fallback: HtmlNode | None = None
    for link in node.descendants("a"):
        href = link.attr("href")
        if not href.startswith(("/video.", "/video")):
            continue
        if first_descendant(link, "img"):
            return link
        if fallback is None:
            fallback = link
    return fallback


def title_from_block(node: HtmlNode) -> str:
    title_block = first_descendant(node, "p", class_name="title")
    if not title_block:
        return ""
    for link in title_block.descendants("a"):
        title = link.attr("title")
        if title:
            return clean_html_text(title)
    return ""


def duration_from_block(node: HtmlNode) -> str:
    duration = first_descendant(node, "span", class_name="duration")
    return duration.text() if duration else ""


def item_keys(item: dict[str, str]) -> set[str]:
    return {
        item.get("webpage_url", ""),
        item.get("url", ""),
        item.get("id", ""),
        item.get("_dashbox_video_id", ""),
        item.get("_dashbox_href", ""),
    }


def public_item(item: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in item.items()
        if not key.startswith("_dashbox_")
    }


def enrich_playlist_pages(
    entries: list[dict[str, str]],
    first_webpage: str,
    base_url: str,
    *,
    download_webpage: Callable[[str], str],
    limit: int = 0,
    concurrency: int = 1,
) -> list[dict[str, str]]:
    out = unique_entries(entries)
    page_urls = numbered_playlist_page_urls(first_webpage, base_url)
    if not page_urls:
        next_url = next_playlist_page_url(first_webpage, base_url, 1)
        if next_url:
            page_urls = [next_url]
    page_urls = limit_page_urls(page_urls, current_count=len(out), limit=limit, items_per_page=len(out))

    for page_url, webpage in fetch_pages(page_urls, download_webpage=download_webpage, concurrency=concurrency):
        before = len(out)
        out.extend(ordered_playlist_entries_from_webpage(webpage, page_url))
        out = unique_entries(out)
        if limit > 0 and len(out) >= limit:
            return out[:limit]
        if len(out) == before and page_url == page_urls[-1]:
            return out
    return out


def fetch_pages(
    page_urls: list[str],
    *,
    download_webpage: Callable[[str], str],
    concurrency: int = 1,
) -> list[tuple[str, str]]:
    if not page_urls:
        return []

    def fetch(url: str) -> tuple[str, str] | None:
        try:
            return url, download_webpage(url)
        except Exception as exc:
            logger.debug("xvideos favorite pagination failed url=%s error=%s", url, exc)
            return None

    workers = max(1, min(len(page_urls), concurrency))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        return [page for page in executor.map(fetch, page_urls) if page]


def next_playlist_page_url(webpage: str, base_url: str, current_page: int) -> str:
    explicit = explicit_next_page_url(webpage, base_url)
    if explicit:
        return explicit
    numbered = numbered_playlist_page_url(webpage, base_url, current_page + 1)
    if numbered:
        return numbered
    return playlist_page_url(base_url, current_page + 1)


def explicit_next_page_url(webpage: str, base_url: str) -> str:
    for link in parse_html(webpage).descendants("a"):
        href = link.attr("href")
        if href and is_next_link(link):
            return urljoin(base_url, href)
    return ""


def numbered_playlist_page_url(webpage: str, base_url: str, page: int) -> str:
    pages = numbered_playlist_page_urls(webpage, base_url)
    for url in pages:
        if page_number_from_url(url) in (page, page - 1):
            return url
    return ""


def numbered_playlist_page_urls(webpage: str, base_url: str) -> list[str]:
    favorite_id = favorite_id_from_url(base_url)
    if not favorite_id:
        return []
    pages: dict[int, str] = {}
    page_url_template = ""
    for link in parse_html(webpage).descendants("a"):
        href = link.attr("href")
        if not href:
            continue
        url = urljoin(base_url, href)
        segments = urlsplit(url).path.strip("/").split("/")
        if len(segments) < 4 or segments[0].lower() != "favorite" or segments[1] != favorite_id:
            continue
        page_text = segments[3]
        if not page_text.isdigit():
            continue
        page = int(page_text)
        if page < 1:
            continue
        pages.setdefault(page, url)
        if not page_url_template:
            page_url_template = page_url_with_placeholder(url)
    if page_url_template and pages:
        max_page = max(pages)
        for page in range(1, max_page + 1):
            pages.setdefault(page, page_url_template.format(page=page))
    return [pages[page] for page in sorted(pages)]


def favorite_id_from_url(url: str) -> str:
    parts = url_path_segments_for_host(url, "xvideos.com")
    if len(parts) < 2 or parts[0].lower() != "favorite":
        return ""
    return parts[1]


def is_next_link(link: HtmlNode) -> bool:
    if "next" in link.attr("rel").lower().split():
        return True
    if link.has_class("next-page"):
        return True
    label = (link.attr("aria-label") or link.attr("title")).strip().lower()
    return label in {"next", "下一页"}


def page_url_with_placeholder(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    head, tail = path.rsplit("/", 1) if "/" in path else ("", path)
    placeholder_path = f"{head}/{{page}}" if tail.isdigit() else path
    return urlunsplit((parts.scheme, parts.netloc, placeholder_path, parts.query, parts.fragment))


def page_number_from_url(url: str) -> int:
    value = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    try:
        return int(value)
    except ValueError:
        return 0


def playlist_page_url(base_url: str, page: int) -> str:
    return with_page_query_param(base_url, page)
