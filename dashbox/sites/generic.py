from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit

from ..config import Config
from ..models import MediaNode
from ..models import NodeKind
from .types import MetadataStrategy, SiteMetadataPlan, YtdlpMetadataOptions


def is_http_url(url: str) -> bool:
    return urlsplit(url).scheme.lower() in {"http", "https"}


def matches_url(_url: str) -> bool:
    return True


def headers_for_format_urls(_urls: list[str]) -> dict[str, str]:
    return {}


def supports_flat_playlist_info(_info: dict[str, Any]) -> bool:
    return False


def enrich_flat_playlist_info(
    _info: dict[str, Any],
    _webpage: str,
    _url: str,
    *,
    download_webpage: Callable[[str], str],
    limit: int = 0,
    concurrency: int = 1,
) -> bool:
    return False


def site_api_config_item_is_directory_entry(_url: str) -> bool:
    return False


def site_api_detail_is_aggregate_vod(_url: str, _info: dict[str, Any]) -> bool:
    return False


def site_api_concurrency(_url: str, configured: int) -> int:
    return configured


def image_url_is_proxyable(_url: str) -> bool:
    return False


def image_referer_for_url(_url: str) -> str:
    return ""


def ytdlp_impersonate_target(_url: str) -> str:
    return ""


async def display_metadata(
    raw_id: str,
    *,
    config: Config,
    html_metadata: Callable[[str], Awaitable[dict[str, Any]]],
    impersonated_html_metadata: Callable[[str], Awaitable[dict[str, Any]]],
    http_client_provider: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    return await html_metadata(raw_id)


def metadata_plan_for_config_url(url: str) -> SiteMetadataPlan:
    return SiteMetadataPlan(
        node_kind=config_node_kind(url),
        strategy=MetadataStrategy.DISPLAY if is_http_url(url) else MetadataStrategy.NONE,
        canonical_url=url,
    )


def metadata_plan_for_playlist_probe(url: str) -> SiteMetadataPlan:
    return SiteMetadataPlan(
        node_kind=NodeKind.LEAF_VOD,
        strategy=MetadataStrategy.PLAYLIST_YTDLP if is_http_url(url) else MetadataStrategy.NONE,
        canonical_url=url,
        ytdlp=YtdlpMetadataOptions(
            extract_url=url,
            noplaylist=False,
            extract_flat="in_playlist",
            playlist_items="1",
        ) if is_http_url(url) else None,
    )


def config_node_kind(_url: str) -> NodeKind:
    return NodeKind.LEAF_VOD


def config_url_supports_playlist_probe(
    url: str,
    *,
    config_kind: NodeKind,
    known_leaf: bool = False,
) -> bool:
    return config_kind == NodeKind.LEAF_VOD and not known_leaf and is_http_url(url)


def node_kind_from_metadata(
    config_kind: NodeKind,
    info: dict[str, Any] | None = None,
    *,
    known_leaf: bool = False,
) -> NodeKind:
    if config_kind == NodeKind.PLAYLIST_DIRECTORY:
        return NodeKind.PLAYLIST_DIRECTORY
    if known_leaf:
        return NodeKind.LEAF_VOD
    if info and playlist_metadata_is_folder(info):
        return NodeKind.PLAYLIST_DIRECTORY
    return NodeKind.LEAF_VOD


def node_kind_from_playlist_info(info: dict[str, Any], _url: str = "") -> NodeKind | None:
    return NodeKind.PLAYLIST_DIRECTORY if playlist_metadata_is_folder(info) else NodeKind.LEAF_VOD


def playlist_collection_synthetic_urls(_url: str, _existing_urls: list[str], _info: dict[str, Any]) -> list[str]:
    return []


def light_collection_child_urls(_url: str, _meta: dict[str, Any] | None = None) -> list[str]:
    return []


def light_collection_uses_static_metadata(_url: str) -> bool:
    return False


def category_extract_url(url: str) -> str:
    return url


def category_flat_playlist_items(_url: str) -> str:
    return ""


def category_supports_collection_probe(_url: str) -> bool:
    return False


def category_fallback_child_urls(_url: str) -> list[str]:
    return []


def url_is_search_directory(_url: str) -> bool:
    return False


def config_node_from_url_item(
    _url: str,
    _node_id: str,
    _title: str = "",
    _thumbnail: str = "",
    _remarks: str = "",
) -> MediaNode | None:
    return None


def search_node_from_url_item(
    _url: str,
    _node_id: str,
    _title: str = "",
    _remarks: str = "",
) -> MediaNode | None:
    return None


def collection_title(info: dict[str, Any], fallback_url: str) -> str:
    return str(info.get("title") or info.get("playlist_title") or fallback_url)


def playlist_item_supports_full_detail(_url: str) -> bool:
    return False


def playlist_items_allow_full_selected_detail(_url: str) -> bool:
    return True


def single_video_uses_full_detail(_url: str) -> bool:
    return False


def single_video_uses_light_detail(_url: str) -> bool:
    return False


def single_video_detail_url(url: str) -> str:
    return url


def single_video_prewarm_args(url: str) -> tuple[str, str] | None:
    return (url, "") if is_http_url(url) else None


def single_video_extract_url(url: str) -> str:
    return url


def playlist_metadata_is_folder(info: dict[str, Any]) -> bool:
    count = info.get("playlist_count")
    if isinstance(count, int) and count > 0:
        return True
    entries = info.get("entries")
    return isinstance(entries, list) and any(isinstance(entry, dict) for entry in entries)


def metadata_needs_html_supplement(info: dict[str, Any]) -> bool:
    return not (info.get("title") and info.get("thumbnail"))


def metadata_has_display_value(info: dict[str, Any]) -> bool:
    return bool(
        info.get("title")
        or info.get("thumbnail")
        or info.get("duration")
        or info.get("duration_string")
        or info.get("uploader")
    )


def metadata_from_ytdlp_info(info: dict[str, Any], raw_id: str) -> dict[str, Any]:
    return {
        "webpage_url": str(info.get("webpage_url") or info.get("original_url") or raw_id),
        "id": info.get("id"),
        "title": info.get("title") or info.get("playlist_title"),
        "thumbnail": thumbnail_from_info(info),
        "playlist_count": info.get("playlist_count"),
        "duration": info.get("duration"),
        "duration_string": info.get("duration_string"),
        "uploader": info.get("uploader") or info.get("channel"),
        "entries": info.get("entries"),
    }


def normalize_playable_url(value: str) -> str:
    return value.strip()


def playable_url_from_info(info: dict[str, Any], fallback_url: str = "") -> str:
    return normalize_playable_url(str(
        info.get("webpage_url")
        or info.get("url")
        or info.get("original_url")
        or fallback_url
        or ""
    ))


def search_entry_kind(_entry: dict[str, Any]) -> str:
    return ""


def collection_child_title(url: str, _source_info: dict[str, Any]) -> str:
    return url


def playlist_entry_is_rejected_collection(_info: dict[str, Any]) -> bool:
    return False


def playlist_entry_is_collection(_info: dict[str, Any]) -> bool:
    return False


def aggregate_playlist_episode(
    _entry: dict[str, Any],
    _index: int,
    _fallback_url: str,
    _current_url: str = "",
) -> dict[str, str]:
    return {}


def extraction_error_reason(_url: str, _error: Exception) -> str:
    return ""


def thumbnail_from_info(info: dict[str, Any]) -> str:
    thumbnail = str(info.get("thumbnail") or "")
    if thumbnail:
        return thumbnail
    thumbnails = [item for item in info.get("thumbnails") or [] if isinstance(item, dict) and item.get("url")]
    if not thumbnails:
        return ""
    best = max(thumbnails, key=lambda item: int(item.get("width") or 0) * int(item.get("height") or 0))
    return str(best["url"])


def merge_metadata(primary: dict[str, Any], supplement: dict[str, Any]) -> dict[str, Any]:
    if not primary:
        return dict(supplement)
    if not supplement:
        return dict(primary)
    out = dict(primary)
    for key, value in supplement.items():
        if value not in (None, "", [], {}) and out.get(key) in (None, "", [], {}):
            out[key] = value
    return out


def fallback_config_node(
    node_id: str,
    url: str,
    *,
    title: str = "",
    thumbnail: str = "",
    remarks: str = "",
    kind: NodeKind = NodeKind.LEAF_VOD,
) -> MediaNode:
    if kind == NodeKind.PLAYLIST_DIRECTORY:
        return MediaNode(
            node_id,
            title or url,
            kind="folder",
            thumbnail=thumbnail,
            remarks=remarks,
            remarks_key="" if remarks else "enter",
        )
    return MediaNode(
        node_id,
        title or url,
        thumbnail=thumbnail,
        remarks=remarks,
        remarks_key="" if remarks else "enter_detail",
    )
