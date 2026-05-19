from __future__ import annotations

import concurrent.futures
import html
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urljoin, urlsplit

from ..config import Config
from ..models import NodeKind
from .html_extract import HtmlNode, first_descendant, parse_html
from .hosts import host_matches, url_parts_for_host, url_path_segments_for_host
from .pagination import limit_page_urls, with_page_query_param
from .types import MetadataStrategy, SiteMetadataPlan


PLAYLIST_EXTRACTORS = {"spankbangplaylist"}
logger = logging.getLogger("dashbox.sites.spankbang")


def matches_url(url: str) -> bool:
    return url_parts_for_host(url, "spankbang.com") is not None


async def display_metadata(
    raw_id: str,
    *,
    config: Config,
    html_metadata: Callable[[str], Awaitable[dict[str, Any]]],
    impersonated_html_metadata: Callable[[str], Awaitable[dict[str, Any]]],
    http_client_provider: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    return await impersonated_html_metadata(raw_id)


def is_playlist_info(info: dict[str, Any]) -> bool:
    extractor = str(info.get("extractor_key") or info.get("extractor") or "").lower()
    return extractor in PLAYLIST_EXTRACTORS


def supports_flat_playlist_info(info: dict[str, Any]) -> bool:
    return is_playlist_info(info)


def enrich_flat_playlist_info(
    info: dict[str, Any],
    webpage: str,
    url: str,
    *,
    download_webpage: Callable[[str], str],
    limit: int = 0,
    concurrency: int = 1,
) -> bool:
    if not is_playlist_info(info):
        return False
    enrich_flat_playlist(info, webpage)
    enrich_flat_playlist_pages(
        info,
        webpage,
        url,
        download_webpage=download_webpage,
        limit=limit,
        concurrency=concurrency,
    )
    return True


def is_playlist_url(url: str) -> bool:
    segments = url_path_segments_for_host(url, "spankbang.com")
    return bool(
        len(segments) >= 2
        and is_ascii_alnum(segments[0])
        and segments[1].lower() == "playlist"
    )


def is_playlist_video_url(url: str) -> bool:
    segments = url_path_segments_for_host(url, "spankbang.com")
    if len(segments) < 3 or segments[1].lower() != "playlist":
        return False
    parts = segments[0].split("-")
    return len(parts) >= 2 and is_ascii_alnum(parts[0]) and is_ascii_alnum(parts[-1])


def config_node_kind(url: str) -> NodeKind | None:
    if is_playlist_url(url):
        return NodeKind.PLAYLIST_DIRECTORY
    return None


def metadata_plan_for_config_url(url: str) -> SiteMetadataPlan:
    kind = config_node_kind(url)
    return SiteMetadataPlan(
        node_kind=kind or NodeKind.LEAF_VOD,
        strategy=MetadataStrategy.SITE_API if kind == NodeKind.PLAYLIST_DIRECTORY else MetadataStrategy.DISPLAY,
        canonical_url=url,
    )


def site_api_concurrency(_url: str, configured: int) -> int:
    return max(1, min(configured, 2))


def image_url_is_proxyable(url: str) -> bool:
    parts = urlsplit(url)
    host = parts.hostname or ""
    return parts.scheme == "https" and host_matches(host, "sb-cd.com")


def image_referer_for_url(url: str) -> str:
    return "https://spankbang.com/" if image_url_is_proxyable(url) else ""


def playlist_info(
    url: str,
    *,
    download_webpage: Callable[[str], str],
    limit: int = 0,
    concurrency: int = 1,
) -> dict[str, Any]:
    if not is_playlist_url(url):
        return {}
    webpage = download_webpage(url)
    return playlist_info_from_webpage(
        webpage,
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
    return playlist_info(
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


def playlist_info_from_webpage(
    webpage: str,
    url: str,
    *,
    download_webpage: Callable[[str], str] | None = None,
    limit: int = 0,
    concurrency: int = 1,
) -> dict[str, Any]:
    info = {
        "id": playlist_id_from_url(url),
        "title": document_title(webpage) or playlist_title_from_url(url) or url,
        "webpage_url": url,
        "original_url": url,
        "extractor": "SpankBangPlaylist",
        "extractor_key": "SpankBangPlaylist",
        "entries": [],
    }
    if download_webpage:
        enrich_flat_playlist_pages(
            info,
            webpage,
            url,
            download_webpage=download_webpage,
            limit=limit,
            concurrency=concurrency,
        )
    else:
        append_flat_playlist_entries(info, webpage, url, limit=limit)
    return info


def enrich_flat_playlist(info: dict[str, Any], webpage: str) -> None:
    url = str(info.get("webpage_url") or info.get("original_url") or "")
    entries = [entry for entry in info.get("entries") or [] if isinstance(entry, dict)]
    if not url or not entries:
        return
    metadata = playlist_entries_from_webpage(webpage, url)
    if not metadata:
        return
    for entry in entries:
        key = str(entry.get("url") or entry.get("webpage_url") or entry.get("id") or "")
        if not key:
            continue
        item = metadata.get(key) or metadata.get(urljoin(url, key)) or metadata.get(str(entry.get("id") or ""))
        if not item:
            continue
        for field in ("title", "thumbnail", "duration_string"):
            if item.get(field) and not entry.get(field):
                entry[field] = item[field]
        if item.get("webpage_url") and not entry.get("webpage_url"):
            entry["webpage_url"] = item["webpage_url"]
    info["entries"] = unique_entries(entries)


def append_flat_playlist_entries(info: dict[str, Any], webpage: str, base_url: str, *, limit: int = 0) -> int:
    entries = [entry for entry in info.get("entries") or [] if isinstance(entry, dict)]
    count_before = len(unique_entries(entries))
    metadata = playlist_entries_from_webpage(webpage, base_url)
    if not metadata:
        info["entries"] = unique_entries(entries)
        return 0
    by_url = {
        str(entry.get("webpage_url") or entry.get("url") or ""): entry
        for entry in entries
        if entry.get("webpage_url") or entry.get("url")
    }
    by_id = {str(entry.get("id") or ""): entry for entry in entries if entry.get("id")}
    for item in ordered_playlist_entries_from_webpage(webpage, base_url):
        url = item.get("webpage_url") or ""
        video_id = display_id_from_playlist_url(url)
        entry = by_url.get(url) or by_id.get(video_id)
        if entry is None:
            entry = {
                "_type": "url",
                "ie_key": "SpankBang",
                "id": video_id,
                "url": url,
                "webpage_url": url,
            }
            entries.append(entry)
            if url:
                by_url[url] = entry
            if video_id:
                by_id[video_id] = entry
        for field in ("title", "thumbnail", "duration_string"):
            if item.get(field) and not entry.get(field):
                entry[field] = item[field]
        if limit > 0 and len(unique_entries(entries)) >= limit:
            break
    info["entries"] = unique_entries(entries)
    if limit > 0:
        info["entries"] = info["entries"][:limit]
    return max(0, len(info["entries"]) - count_before)


def enrich_flat_playlist_pages(
    info: dict[str, Any],
    first_webpage: str,
    base_url: str,
    *,
    download_webpage: Callable[[str], str],
    limit: int = 0,
    concurrency: int = 1,
) -> None:
    append_flat_playlist_entries(info, first_webpage, base_url, limit=limit)
    if limit > 0 and len(info.get("entries") or []) >= limit:
        return
    page_urls = numbered_playlist_page_urls(first_webpage, base_url)
    if page_urls:
        enrich_numbered_playlist_pages(
            info,
            page_urls,
            download_webpage=download_webpage,
            limit=limit,
            concurrency=concurrency,
        )
        return
    enrich_probe_playlist_pages(
        info,
        first_webpage,
        base_url,
        download_webpage=download_webpage,
        limit=limit,
    )


def enrich_numbered_playlist_pages(
    info: dict[str, Any],
    page_urls: list[str],
    *,
    download_webpage: Callable[[str], str],
    limit: int = 0,
    concurrency: int = 1,
) -> None:
    current_count = len(unique_entries([entry for entry in info.get("entries") or [] if isinstance(entry, dict)]))
    page_urls = limit_page_urls(
        page_urls,
        current_count=current_count,
        limit=limit,
        items_per_page=max(1, current_count),
    )
    if not page_urls:
        return

    def fetch(url: str) -> tuple[str, str] | None:
        try:
            return url, download_webpage(url)
        except Exception as exc:
            logger.debug("spankbang playlist pagination failed url=%s error=%s", url, exc)
            return None

    workers = max(1, min(len(page_urls), concurrency))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        pages = [page for page in executor.map(fetch, page_urls) if page]
    for page_url, webpage in pages:
        append_flat_playlist_entries(info, webpage, page_url, limit=limit)
        if limit > 0 and len(info.get("entries") or []) >= limit:
            return


def enrich_probe_playlist_pages(
    info: dict[str, Any],
    first_webpage: str,
    base_url: str,
    *,
    download_webpage: Callable[[str], str],
    limit: int = 0,
) -> None:
    current_page = 1
    current_webpage = first_webpage
    seen_urls = {base_url}
    while True:
        next_url = next_playlist_page_url(current_webpage, base_url, current_page)
        if not next_url or next_url in seen_urls:
            return
        seen_urls.add(next_url)
        try:
            current_webpage = download_webpage(next_url)
        except Exception as exc:
            logger.debug("spankbang playlist pagination failed url=%s error=%s", next_url, exc)
            return
        added = append_flat_playlist_entries(info, current_webpage, next_url, limit=limit)
        if added <= 0:
            return
        if limit > 0 and len(info.get("entries") or []) >= limit:
            return
        current_page += 1


def unique_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for entry in entries:
        key = str(entry.get("webpage_url") or entry.get("url") or entry.get("id") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(entry)
    return out


def playlist_entries_from_webpage(webpage: str, base_url: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for item in ordered_playlist_entries_from_webpage(webpage, base_url):
        webpage_url = item["webpage_url"]
        href_path = urlsplit(webpage_url).path
        video_id = item.pop("_dashbox_video_id", "")
        display_id = display_id_from_playlist_url(webpage_url)
        for key in {webpage_url, href_path, video_id, display_id}:
            if key:
                out[key] = item
    return out


def ordered_playlist_entries_from_webpage(webpage: str, base_url: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    root = parse_html(webpage)
    for block in video_item_blocks(root):
        link = first_playlist_link(block)
        if link is None:
            continue
        href = link.attr("href")
        webpage_url = urljoin(base_url, href)
        image = first_descendant(block, "img")
        thumbnail = (image.attr("src") or image.attr("data-src")) if image else ""
        title = image.attr("alt") if image else ""
        duration_node = first_data_testid_node(block, "video-item-length")
        duration = clean_html_text(duration_node.text() if duration_node else "")
        item = {
            "webpage_url": webpage_url,
            "title": clean_html_text(title),
            "thumbnail": thumbnail,
            "duration_string": duration,
            "_dashbox_video_id": block.attr("data-id"),
        }
        out.append(item)
    return out


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
    for item_page, url in numbered_page_items(webpage, base_url).items():
        if item_page == page:
            return url
    return ""


def numbered_playlist_page_urls(webpage: str, base_url: str) -> list[str]:
    pages = numbered_page_items(webpage, base_url)
    return [pages[page] for page in sorted(pages)]


def playlist_page_url(base_url: str, page: int) -> str:
    return with_page_query_param(base_url, page)


def display_id_from_playlist_url(value: str) -> str:
    segments = urlsplit(value).path.strip("/").split("/")
    if len(segments) < 2 or segments[1].lower() != "playlist":
        return ""
    parts = segments[0].split("-")
    if len(parts) < 2:
        return ""
    display_id = parts[-1]
    return display_id if is_ascii_alnum(display_id) else ""


def video_item_blocks(root: HtmlNode) -> list[HtmlNode]:
    return [
        node
        for node in root.descendants("div")
        if node.attr("data-testid") == "video-item"
    ]


def first_playlist_link(node: HtmlNode) -> HtmlNode | None:
    for link in node.descendants("a"):
        if is_playlist_video_href(link.attr("href")):
            return link
    return None


def first_data_testid_node(node: HtmlNode, value: str) -> HtmlNode | None:
    for item in node.descendants():
        if item.attr("data-testid") == value:
            return item
    return None


def is_playlist_video_href(value: str) -> bool:
    segments = urlsplit(value).path.strip("/").split("/")
    if len(segments) < 3 or segments[1].lower() != "playlist":
        return False
    parts = segments[0].split("-")
    return len(parts) >= 2 and is_ascii_alnum(parts[0]) and is_ascii_alnum(parts[-1])


def is_ascii_alnum(value: str) -> bool:
    return bool(value and value.isascii() and value.isalnum())


def is_next_link(link: HtmlNode) -> bool:
    if "next" in link.attr("rel").lower().split():
        return True
    label = (link.attr("aria-label") or link.attr("title")).strip().lower()
    return label in {"next", "下一页"}


def numbered_page_items(webpage: str, base_url: str) -> dict[int, str]:
    base_path = playlist_base_path(base_url)
    pages: dict[int, str] = {}
    for link in parse_html(webpage).descendants("a"):
        href = link.attr("href")
        if not href:
            continue
        url = urljoin(base_url, href)
        path = urlsplit(url).path.rstrip("/")
        if not path.startswith(f"{base_path}/"):
            continue
        page_text = path.rsplit("/", 1)[-1]
        if not page_text.isdigit():
            continue
        page = int(page_text)
        if page > 1:
            pages.setdefault(page, url)
    return pages


def playlist_base_path(url: str) -> str:
    path = urlsplit(url).path.rstrip("/")
    head, tail = path.rsplit("/", 1) if "/" in path else ("", path)
    return head if tail.isdigit() else path


def playlist_id_from_url(url: str) -> str:
    return "/".join(urlsplit(url).path.strip("/").split("/")[:3])


def playlist_title_from_url(url: str) -> str:
    segments = urlsplit(url).path.strip("/").split("/")
    if len(segments) >= 3 and segments[1].lower() == "playlist":
        return clean_html_text(segments[2].replace("+", " "))
    return ""


def document_title(webpage: str) -> str:
    node = first_descendant(parse_html(webpage), "title")
    return clean_html_text(node.text() if node else "")


def clean_html_text(value: str) -> str:
    return " ".join(html.unescape(value).split())
