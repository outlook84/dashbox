from __future__ import annotations

import html
import json
import logging
from collections.abc import Callable
from typing import Any, Literal
from urllib.parse import parse_qsl, urljoin

from ... import i18n
from ...models import NodeKind
from ..hosts import url_host_matches, url_parts_for_any_host, url_parts_for_host, url_path_segments_for_host, with_query_param
from ..types import MetadataStrategy, SiteMetadataPlan, YtdlpMetadataOptions
from .utils import clean_title, cid_text, dict_list, find_cid, find_cid_from_formats, positive_int_text

logger = logging.getLogger("dashbox.bilibili")

CollectionKind = Literal["medialist", "bangumi", "cheese", "audio"]
CollectionRoute = Literal[
    "watchlater",
    "favorites",
    "medialist",
    "space_collection",
    "space_series",
    "space_video",
    "bangumi_season",
    "bangumi_media",
    "cheese",
    "category",
    "channel",
    "space_audio",
    "audio",
]
COLLECTION_ROUTE_KINDS: dict[CollectionRoute, CollectionKind] = {
    "watchlater": "medialist",
    "favorites": "medialist",
    "medialist": "medialist",
    "space_collection": "medialist",
    "space_series": "medialist",
    "space_video": "medialist",
    "bangumi_season": "bangumi",
    "bangumi_media": "bangumi",
    "cheese": "cheese",
    "category": "medialist",
    "channel": "medialist",
    "space_audio": "audio",
    "audio": "audio",
}

def is_info(info: dict[str, Any]) -> bool:
    extractor = str(info.get("extractor_key") or info.get("extractor") or "").lower()
    if "bilibili" in extractor:
        return True
    urls = [
        str(info.get("webpage_url") or ""),
        str(info.get("original_url") or ""),
        str(info.get("url") or ""),
    ]
    return any(url_host_matches(url, "bilibili.com") or url_host_matches(url, "b23.tv") for url in urls)


def _collection_routes(url: str, *, include_watchlater: bool = True) -> tuple[CollectionRoute, ...]:
    if is_watchlater_url(url):
        return ("watchlater",) if include_watchlater else ()

    routes: list[CollectionRoute] = []
    for route, matches in COLLECTION_ROUTE_CHECKS:
        if matches(url):
            routes.append(route)
    return tuple(routes)


def is_video_playlist(info: dict[str, Any], fallback_url: str = "") -> bool:
    if not is_info(info):
        return False
    urls = [
        str(info.get("webpage_url") or ""),
        str(info.get("original_url") or ""),
        fallback_url,
    ]
    return any(is_video_url(url) for url in urls)


def playlist_info_node_kind(info: dict[str, Any], fallback_url: str = "") -> NodeKind | None:
    if is_video_playlist(info, fallback_url):
        return NodeKind.AGGREGATE_VOD
    return None


def node_kind_from_playlist_info(info: dict[str, Any], fallback_url: str = "") -> NodeKind | None:
    return playlist_info_node_kind(info, fallback_url)


def playlist_item_supports_full_detail(url: str) -> bool:
    return is_single_playable_url(url)


def single_video_uses_full_detail(url: str) -> bool:
    return is_single_playable_url(url)


def single_video_extract_url(url: str) -> str:
    return normalize_extract_url(url)


def config_node_kind(url: str) -> NodeKind | None:
    if is_search_url(url):
        return NodeKind.PLAYLIST_DIRECTORY
    if _collection_routes(url):
        return NodeKind.PLAYLIST_DIRECTORY
    if is_live_url(url):
        return NodeKind.LEAF_VOD
    if is_video_url(url):
        return NodeKind.AGGREGATE_VOD
    return None


def matches_url(url: str) -> bool:
    return url_parts_for_any_host(url, "bilibili.com", "b23.tv") is not None


def metadata_plan_for_config_url(url: str) -> SiteMetadataPlan:
    kind = config_node_kind(url)
    if is_single_playable_url(url):
        extract_url = ytdlp_light_metadata_url(url)
        return SiteMetadataPlan(
            node_kind=kind or NodeKind.LEAF_VOD,
            strategy=MetadataStrategy.SINGLE_YTDLP,
            canonical_url=url,
            ytdlp=YtdlpMetadataOptions(
                extract_url=extract_url,
                noplaylist=True,
                process=ytdlp_light_metadata_needs_processing(url),
            ),
        )
    if kind:
        return SiteMetadataPlan(
            node_kind=kind,
            strategy=MetadataStrategy.SITE_API,
            canonical_url=url,
        )
    return SiteMetadataPlan(
        node_kind=NodeKind.LEAF_VOD,
        strategy=MetadataStrategy.DISPLAY,
        canonical_url=url,
    )


def _video_playlist_episode_url(current_url: str, fallback_url: str, index: int) -> str:
    if current_url or not fallback_url or not is_video_url(fallback_url):
        return current_url
    return with_query_param(fallback_url, "p", str(index))


def aggregate_playlist_episode(
    entry: dict[str, Any],
    index: int,
    fallback_url: str,
    current_url: str = "",
) -> dict[str, str]:
    if not is_video_url(fallback_url):
        return {}
    url = _video_playlist_episode_url(current_url, fallback_url, index)
    if not url and entry.get("id"):
        url = str(entry["id"])
    if not url:
        return {}
    return {"title": _video_playlist_episode_title(entry, index), "url": url}


def _video_playlist_episode_title(entry: dict[str, Any], index: int) -> str:
    raw = str(entry.get("title") or "")
    title = clean_title(html.unescape(raw))
    marker = f"p{index:02d}"
    marker_pos = title.lower().find(marker)
    if marker_pos >= 0:
        title = title[marker_pos:]
    if len(title) > 40:
        title = marker.upper()
    return title or marker.upper()


def is_search_url(url: str) -> bool:
    return bool(search_keyword_from_url(url))


def search_keyword_from_url(url: str) -> str:
    parts = url_parts_for_host(url, "search.bilibili.com")
    if parts is None:
        return ""
    segments = [segment.lower() for segment in parts.path.split("/") if segment]
    if segments and segments[0] not in {"all", "video"}:
        return ""
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    return str(query.get("keyword") or query.get("search_query") or query.get("q") or "").strip()


def search_title_from_url(url: str) -> str:
    keyword = search_keyword_from_url(url)
    return i18n.bilibili_search_title(keyword)


def normalize_extract_url(url: str) -> str:
    aid = aid_from_url(url)
    if aid and url_host_matches(url, "player.bilibili.com"):
        normalized = f"https://www.bilibili.com/video/av{aid}"
        page = player_page_from_url(url)
        return with_query_param(normalized, "p", page) if page else normalized
    return url


def video_metadata_from_payload(payload: dict[str, Any], url: str) -> dict[str, Any]:
    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
        logger.warning("bilibili metadata invalid url=%s code=%s message=%s", url, payload.get("code"), payload.get("message"))
        return {}
    data = payload["data"]
    pages = dict_list(data.get("pages"))
    data["pages"] = pages
    logger.debug("bilibili metadata title=%s pages=%s", data.get("title"), len(pages))
    return data


def player_page_from_url(url: str) -> str:
    parts = url_parts_for_host(url, "player.bilibili.com")
    if parts is None or parts.path != "/player.html":
        return ""
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key in ("page", "p"):
        page = positive_int_text(query.get(key))
        if page:
            return page
    return ""


def player_cid_from_url(url: str) -> str:
    parts = url_parts_for_host(url, "player.bilibili.com")
    if parts is None or parts.path != "/player.html":
        return ""
    cid = dict(parse_qsl(parts.query, keep_blank_values=True)).get("cid")
    return cid_text(cid)


def page_number_from_cid(info: dict[str, Any], cid: str) -> str:
    if not cid or not isinstance(info, dict):
        return ""
    pages = dict_list(info.get("pages"))
    for index, page in enumerate(pages, start=1):
        if cid_text(page.get("cid")) == cid:
            return positive_int_text(page.get("page")) or str(index)
    return ""


def supports_video_api_metadata(url: str) -> bool:
    return bool(bvid_from_url(url) or aid_from_url(url))


def ytdlp_light_metadata_url(url: str) -> str:
    return normalize_extract_url(url)


def ytdlp_light_metadata_needs_processing(url: str) -> bool:
    if url_parts_for_host(url, "t.bilibili.com") is not None:
        return True
    segments = url_path_segments_for_host(url, "bilibili.com")
    return len(segments) == 2 and segments[0].lower() == "opus" and segments[1].isdigit()


def headers_for_format_urls(urls: list[str]) -> dict[str, str]:
    if not any(url_host_matches(url, "bilivideo.com") or url_host_matches(url, "bilibili.com") for url in urls):
        return {}
    return {
        "Referer": "https://www.bilibili.com/",
        "Origin": "https://www.bilibili.com",
    }


def danmaku_url_from_info(info: dict[str, Any], base_url: str) -> str:
    if not base_url or not is_info(info):
        return ""
    cid = find_cid(info) or find_cid_from_formats(info)
    if not cid:
        logger.debug("bilibili danmaku cid not found")
        return ""
    logger.debug("bilibili danmaku cid=%s", cid)
    return f"{base_url.rstrip('/')}/danmaku/bilibili/{cid}.xml"


def danmaku_xml_upstream_url(cid: str) -> str:
    return f"https://comment.bilibili.com/{cid}.xml"


def is_video_url(url: str) -> bool:
    parts = url_parts_for_any_host(url, "bilibili.com", "b23.tv")
    return bool(parts is not None and "/video/" in parts.path)


def is_live_url(url: str) -> bool:
    segments = url_path_segments_for_host(url, "live.bilibili.com")
    return (
        len(segments) == 1
        and segments[0].isdigit()
    ) or (
        len(segments) == 2
        and segments[0].lower() == "blanc"
        and segments[1].isdigit()
    )


def is_short_url(url: str) -> bool:
    return url_host_matches(url, "b23.tv")


def _is_single_playable_path(url: str) -> bool:
    segments = tuple(segment.lower() for segment in url_path_segments_for_host(url, "bilibili.com"))
    if len(segments) == 2 and segments[0] == "opus":
        return segments[1].isdigit()
    if len(segments) == 2 and segments[0] == "audio":
        return segments[1].startswith("au") and segments[1][2:].isdigit()
    if len(segments) == 3 and segments[:2] in {("bangumi", "play"), ("cheese", "play")}:
        return segments[2].startswith("ep") and segments[2][2:].isdigit()
    return False


def is_single_playable_url(url: str) -> bool:
    if is_live_url(url):
        return True
    parts = url_parts_for_host(url, "t.bilibili.com")
    if parts is not None:
        segments = url_path_segments_for_host(url, "t.bilibili.com")
        return len(segments) == 1 and segments[0].isdigit()
    parts = url_parts_for_host(url, "player.bilibili.com")
    if parts is not None and parts.path == "/player.html":
        return bool(aid_from_url(url))
    parts = url_parts_for_host(url, "bilibili.com")
    if parts is None:
        return False
    if is_video_url(url):
        return bool(bvid_from_url(url) or aid_from_url(url))
    if parts.path.startswith("/festival/") and bvid_from_url(url):
        return True
    return _is_single_playable_path(url)


def is_bangumi_season_url(url: str) -> bool:
    return bool(bangumi_season_id_from_url(url))


def is_bangumi_episode_url(url: str) -> bool:
    return bool(bangumi_episode_id_from_url(url))


def is_bangumi_media_url(url: str) -> bool:
    return bool(bangumi_media_id_from_url(url))


def is_cheese_season_url(url: str) -> bool:
    return bool(cheese_season_id_from_url(url))


def is_cheese_episode_url(url: str) -> bool:
    return bool(cheese_episode_id_from_url(url))


def is_watchlater_url(url: str) -> bool:
    segments = tuple(segment.lower() for segment in url_path_segments_for_host(url, "bilibili.com"))
    return segments in {
        ("watchlater",),
        ("list", "watchlater"),
        ("medialist", "play", "watchlater"),
    }


def is_category_url(url: str) -> bool:
    return bool(category_ids_from_url(url))


def is_channel_url(url: str) -> bool:
    return bool(channel_route_from_url(url))


def is_audio_album_url(url: str) -> bool:
    return bool(audio_album_id_from_url(url))


def is_medialist_url(url: str) -> bool:
    if is_watchlater_url(url):
        return False
    return bool(medialist_ids_from_url(url))


def is_favorites_url(url: str) -> bool:
    return bool(favorites_id_from_url(url))


def is_space_collection_url(url: str) -> bool:
    return bool(space_collection_ids_from_url(url))


def is_space_series_url(url: str) -> bool:
    return bool(space_series_ids_from_url(url))


def is_space_video_url(url: str) -> bool:
    return bool(space_video_mid_from_url(url))


def is_space_audio_url(url: str) -> bool:
    return bool(space_audio_mid_from_url(url))


def bvid_from_url(url: str) -> str:
    parts = url_parts_for_any_host(url, "bilibili.com", "b23.tv")
    if parts is not None:
        segments = [segment for segment in parts.path.split("/") if segment]
        if len(segments) == 2 and segments[0].lower() == "video" and _is_bvid(segments[1]):
            return segments[1]
    parts = url_parts_for_host(url, "bilibili.com")
    if parts is not None and parts.path.startswith("/festival/"):
        bvid = dict(parse_qsl(parts.query, keep_blank_values=True)).get("bvid") or ""
        return bvid if _is_bvid(bvid) else ""
    return ""


def _is_bvid(value: str) -> bool:
    return value.lower().startswith("bv") and _is_ascii_alnum(value[2:])


def aid_from_url(url: str) -> str:
    segments = url_path_segments_for_host(url, "bilibili.com")
    if len(segments) == 2 and segments[0].lower() == "video":
        raw_id = segments[1]
        if raw_id.lower().startswith("av") and raw_id[2:].isdigit():
            return raw_id[2:]
    parts = url_parts_for_host(url, "player.bilibili.com")
    if parts is not None and parts.path == "/player.html":
        aid = dict(parse_qsl(parts.query, keep_blank_values=True)).get("aid")
        return aid if aid and aid.isdigit() else ""
    return ""


def supported_short_url_target(fallback_url: str, target_url: str) -> str:
    if not target_url:
        return fallback_url
    target_url = urljoin(fallback_url, target_url)
    if is_supported_short_url_target(target_url):
        return target_url
    logger.debug("bilibili short url unsupported target url=%s target=%s", fallback_url, target_url)
    return fallback_url


def is_supported_short_url_target(url: str) -> bool:
    return is_single_playable_url(url) or bool(_collection_routes(url))


def extraction_error_reason(url: str, error: Exception) -> str:
    message = str(error)
    if is_live_url(url) and "Streamer is not live" in message:
        return i18n.bilibili_live_not_started()
    return ""


def bangumi_season_id_from_url(url: str) -> str:
    return prefixed_path_id(url, ("bangumi", "play"), "ss")


def bangumi_episode_id_from_url(url: str) -> str:
    return prefixed_path_id(url, ("bangumi", "play"), "ep")


def bangumi_media_id_from_url(url: str) -> str:
    return prefixed_path_id(url, ("bangumi", "media"), "md")


def cheese_season_id_from_url(url: str) -> str:
    return prefixed_path_id(url, ("cheese", "play"), "ss")


def cheese_episode_id_from_url(url: str) -> str:
    return prefixed_path_id(url, ("cheese", "play"), "ep")


def audio_album_id_from_url(url: str) -> str:
    return prefixed_path_id(url, ("audio",), "am")


def category_ids_from_url(url: str) -> dict[str, str]:
    segments = url_path_segments_for_host(url, "bilibili.com")
    if (
        len(segments) != 3
        or segments[0].lower() != "v"
        or not _is_ascii_alpha(segments[1])
        or not _is_ascii_alpha_or_underscore(segments[2])
    ):
        return {}
    return {"category": segments[1], "subcategory": segments[2]}


def channel_route_from_url(url: str) -> str:
    segments = url_path_segments_for_host(url, "bilibili.com")
    if (
        len(segments) != 2
        or segments[0].lower() not in {"c", "v"}
        or not _is_ascii_alnum_or_underscore(segments[1])
    ):
        return ""
    return segments[1]


def _is_ascii_alpha(value: str) -> bool:
    return bool(value and value.isascii() and value.isalpha())


def _is_ascii_alpha_or_underscore(value: str) -> bool:
    return bool(value and value.isascii() and all(char.isalpha() or char == "_" for char in value))


def _is_ascii_alnum(value: str) -> bool:
    return bool(value and value.isascii() and value.isalnum())


def _is_ascii_alnum_or_underscore(value: str) -> bool:
    return bool(value and value.isascii() and all(char.isalnum() or char == "_" for char in value))


def prefixed_path_id(url: str, prefix_segments: tuple[str, ...], id_prefix: str) -> str:
    segments = url_path_segments_for_host(url, "bilibili.com")
    if len(segments) != len(prefix_segments) + 1:
        return ""
    if tuple(segment.lower() for segment in segments[:-1]) != prefix_segments:
        return ""
    raw_id = segments[-1]
    if not raw_id.lower().startswith(id_prefix):
        return ""
    value = raw_id[len(id_prefix):]
    return value if value.isdigit() else ""


def channel_config_from_payload(payload: dict[str, Any], route: str) -> dict[str, Any]:
    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
        return {}
    data = payload["data"].get("data")
    if not isinstance(data, dict):
        return {}
    raw = data.get(f"channel_list.{route}")
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}
    return raw if isinstance(raw, dict) else {}


def medialist_ids_from_url(url: str) -> dict[str, Any]:
    parts = url_parts_for_host(url, "bilibili.com")
    if parts is None:
        return {}
    segments = url_path_segments_for_host(url, "bilibili.com")
    has_ml_prefix = False
    raw_id = ""
    if (
        len(segments) >= 3
        and segments[0].lower() == "medialist"
        and segments[1].lower() in {"play", "detail"}
    ):
        raw_id = segments[2]
        has_ml_prefix = raw_id.lower().startswith("ml")
    elif len(segments) == 2 and segments[0].lower() == "list":
        raw_id = segments[1]
        has_ml_prefix = raw_id.lower().startswith("ml")
    if not raw_id:
        return {}
    if has_ml_prefix:
        raw_id = raw_id[2:]
    if not _is_ascii_alnum_or_underscore(raw_id):
        return {}
    if raw_id == "watchlater":
        return {}
    if has_ml_prefix:
        return {"type": 3, "biz_id": raw_id}
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if query.get("sid"):
        return {"type": 5, "biz_id": query["sid"]}
    return {"type": 3, "biz_id": raw_id}


def favorites_id_from_url(url: str) -> str:
    space_segments = url_path_segments_for_host(url, "space.bilibili.com")
    if len(space_segments) == 2 and space_segments[0].isdigit() and space_segments[1].lower() == "favlist":
        space_parts = url_parts_for_host(url, "space.bilibili.com")
        if space_parts is None:
            return ""
        fid = dict(parse_qsl(space_parts.query, keep_blank_values=True)).get("fid")
        return fid if fid and fid.isdigit() else ""
    segments = url_path_segments_for_host(url, "bilibili.com")
    if (
        len(segments) != 3
        or segments[0].lower() != "medialist"
        or segments[1].lower() != "detail"
        or not segments[2].lower().startswith("ml")
    ):
        return ""
    fid = segments[2][2:]
    return fid if fid.isdigit() else ""


def space_collection_ids_from_url(url: str) -> dict[str, str]:
    parts = url_parts_for_host(url, "space.bilibili.com")
    if parts is None:
        return {}
    segments = url_path_segments_for_host(url, "space.bilibili.com")
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if (
        len(segments) == 3
        and segments[0].isdigit()
        and segments[1].lower() == "channel"
        and segments[2].lower() == "collectiondetail"
    ):
        sid = query.get("sid") or ""
        return {"mid": segments[0], "sid": sid} if sid.isdigit() else {}
    if (
        len(segments) == 3
        and segments[0].isdigit()
        and segments[1].lower() == "lists"
        and segments[2].isdigit()
        and query.get("type", "").lower() != "series"
    ):
        return {"mid": segments[0], "sid": segments[2]}
    return {}


def space_series_ids_from_url(url: str) -> dict[str, str]:
    parts = url_parts_for_host(url, "space.bilibili.com")
    if parts is None:
        return {}
    segments = url_path_segments_for_host(url, "space.bilibili.com")
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    if (
        len(segments) == 3
        and segments[0].isdigit()
        and segments[1].lower() == "channel"
        and segments[2].lower() == "seriesdetail"
    ):
        sid = query.get("sid") or ""
        return {"mid": segments[0], "sid": sid} if sid.isdigit() else {}
    if (
        len(segments) == 3
        and segments[0].isdigit()
        and segments[1].lower() == "lists"
        and segments[2].isdigit()
        and query.get("type", "").lower() == "series"
    ):
        return {"mid": segments[0], "sid": segments[2]}
    return {}


def space_audio_mid_from_url(url: str) -> str:
    segments = tuple(segment.lower() for segment in url_path_segments_for_host(url, "space.bilibili.com"))
    if len(segments) == 2 and segments[0].isdigit() and segments[1] == "audio":
        return segments[0]
    if len(segments) == 3 and segments[0].isdigit() and segments[1:] == ("upload", "audio"):
        return segments[0]
    return ""


def space_video_mid_from_url(url: str) -> str:
    segments = tuple(segment.lower() for segment in url_path_segments_for_host(url, "space.bilibili.com"))
    if len(segments) == 1 and segments[0].isdigit():
        return segments[0]
    if len(segments) == 2 and segments[0].isdigit() and segments[1] == "video":
        return segments[0]
    if len(segments) == 3 and segments[0].isdigit() and segments[1:] == ("upload", "video"):
        return segments[0]
    return ""


def space_audio_light_metadata(url: str) -> dict[str, Any]:
    mid = space_audio_mid_from_url(url)
    return {"title": i18n.bilibili_audio_title(mid)} if mid else {}

COLLECTION_ROUTE_CHECKS: tuple[tuple[CollectionRoute, Callable[[str], bool]], ...] = (
    ("favorites", is_favorites_url),
    ("medialist", is_medialist_url),
    ("space_collection", is_space_collection_url),
    ("space_series", is_space_series_url),
    ("space_video", is_space_video_url),
    ("bangumi_season", is_bangumi_season_url),
    ("bangumi_media", is_bangumi_media_url),
    ("cheese", is_cheese_season_url),
    ("category", is_category_url),
    ("channel", is_channel_url),
    ("space_audio", is_space_audio_url),
    ("audio", is_audio_album_url),
)
