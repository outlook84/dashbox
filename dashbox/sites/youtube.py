from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .. import i18n
from ..config import Config
from ..models import NodeKind
from ..models import MediaNode
from ..utils.dicts import compact_dict
from . import html_metadata, youtube_subtitles
from .hosts import host_matches, url_parts_for_any_host, url_parts_for_host, url_path_segments, url_query_value
from .types import MetadataStrategy, SiteMetadataPlan, YtdlpMetadataOptions

logger = logging.getLogger("dashbox.sites.youtube")

YOUTUBE_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{11}$")
YOUTUBE_CLIP_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
YOUTUBE_PLAYLIST_ID_RE = re.compile(r"^(?:(?:PL|LL|EC|UU|FL|RD|UL|TL|PU|OLAK5uy_)[0-9A-Za-z-_]{10,}|RDMM|WL|LL|LM)$")
YOUTUBE_FEED_FOLDERS = {"recommended", "subscriptions", "history", "watch_later"}
YOUTUBE_CHANNEL_TABS = ("videos", "shorts", "streams", "playlists", "podcasts")
YOUTUBE_KIDS_CHANNEL_TABS = ("videos",)
YOUTUBE_MUSIC_CHANNEL_TABS = ("videos", "playlists")
YOUTUBE_DIRECTORY_KINDS = {"folder", "playlist", "search"}
YOUTUBE_COLLECTION_KINDS = {"folder", "playlist"}
YOUTUBE_EXTRACTOR_KEY_PREFIX = "Youtube"
YOUTUBE_YTDLP_PSEUDO_URLS = {
    ":ytrec": "https://www.youtube.com/feed/recommended",
    ":ytrecommended": "https://www.youtube.com/feed/recommended",
    ":ytsub": "https://www.youtube.com/feed/subscriptions",
    ":ytsubs": "https://www.youtube.com/feed/subscriptions",
    ":ytsubscription": "https://www.youtube.com/feed/subscriptions",
    ":ytsubscriptions": "https://www.youtube.com/feed/subscriptions",
    ":ythis": "https://www.youtube.com/feed/history",
    ":ythistory": "https://www.youtube.com/feed/history",
    ":ytfav": "https://www.youtube.com/playlist?list=LL",
    ":ytfavs": "https://www.youtube.com/playlist?list=LL",
    ":ytfavorite": "https://www.youtube.com/playlist?list=LL",
    ":ytfavorites": "https://www.youtube.com/playlist?list=LL",
    ":ytwatchlater": "https://www.youtube.com/playlist?list=WL",
}


@dataclass(frozen=True)
class YoutubeUrlFacts:
    value: str
    parts: Any
    path: str
    segments: tuple[str, ...]
    is_music: bool
    is_kids: bool
    is_tab_host: bool
    is_youtube_com: bool


@dataclass(frozen=True)
class YoutubeUrlRule:
    kind: str
    matches: Callable[[YoutubeUrlFacts], bool]


def _host(value: str) -> str:
    return (urlsplit(value).hostname or "").lower()


def _is_tab_or_music_host(host: str) -> bool:
    return is_youtube_tab_host(host) or is_youtube_music_host(host)


def _url_facts(value: str, *, normalize: bool = True) -> YoutubeUrlFacts:
    value = normalize_playlist_url(value) if normalize else value.strip()
    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    return YoutubeUrlFacts(
        value=value,
        parts=parts,
        path=parts.path.rstrip("/"),
        segments=tuple(url_path_segments(value)),
        is_music=is_youtube_music_host(host),
        is_kids=is_youtube_kids_host(host),
        is_tab_host=is_youtube_tab_host(host),
        is_youtube_com=is_youtube_com_host(host),
    )


def _first_matching_url_rule(facts: YoutubeUrlFacts, rules: tuple[YoutubeUrlRule, ...]) -> str:
    for rule in rules:
        if rule.matches(facts):
            return rule.kind
    return ""


def normalize_playable_url(value: str) -> str:
    value = value.strip()
    if YOUTUBE_ID_RE.fullmatch(value):
        return f"https://www.youtube.com/watch?v={value}"
    return value


def canonical_single_video_url(value: str) -> str:
    video_id = video_id_from_value(value)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return value.strip()


def normalize_playlist_url(value: str) -> str:
    pseudo_url = ytdlp_pseudo_url_target(value)
    if pseudo_url:
        return pseudo_url
    kids_channel_videos_url = youtube_kids_channel_videos_url(value)
    if kids_channel_videos_url:
        return kids_channel_videos_url
    playlist_id = playlist_id_from_value(value)
    value = value.strip()
    if playlist_id and value == playlist_id:
        return f"https://www.youtube.com/playlist?list={playlist_id}"
    return value


def normalize_config_url(value: str) -> str:
    return normalize_playlist_url(value)


def normalize_extract_url(value: str) -> str:
    return normalize_playlist_url(value)


def playlist_light_metadata_url(value: str) -> str:
    playlist_id = playlist_id_from_value(value)
    if not playlist_id:
        playlist_id = music_browse_playlist_id(value)
    if playlist_id:
        return f"https://www.youtube.com/playlist?list={playlist_id}"
    return ""


def music_browse_playlist_id(value: str) -> str:
    parts = url_parts_for_host(value.strip(), "music.youtube.com")
    if parts is None:
        return ""
    segments = url_path_segments(value.strip())
    if len(segments) != 2 or segments[0].lower() != "browse":
        return ""
    browse_id = segments[1]
    if browse_id.startswith("VL"):
        playlist_id = browse_id[2:]
    elif browse_id.startswith("MPSP"):
        playlist_id = browse_id[4:]
    elif browse_id.startswith("UC") and len(browse_id) > 2:
        playlist_id = f"UU{browse_id[2:]}"
    else:
        return ""
    return playlist_id if YOUTUBE_PLAYLIST_ID_RE.fullmatch(playlist_id) else ""


def thumbnail_from_info(info: dict[str, Any], playable_url: str = "") -> str:
    thumbnail = str(info.get("thumbnail") or "")
    if thumbnail:
        return thumbnail
    thumbnails = [item for item in info.get("thumbnails") or [] if isinstance(item, dict) and item.get("url")]
    if thumbnails:
        best = max(preferred_thumbnails(thumbnails), key=lambda item: int(item.get("width") or 0) * int(item.get("height") or 0))
        return str(best["url"])
    video_id = video_id_from_value(playable_url)
    if not video_id and not is_playlist_like_info(info):
        video_id = video_id_from_value(str(info.get("id") or ""))
    if video_id:
        return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
    return ""


def metadata_from_ytdlp_info(info: dict[str, Any], raw_id: str) -> dict[str, Any]:
    return {
        "webpage_url": str(info.get("webpage_url") or info.get("original_url") or raw_id),
        "id": info.get("id"),
        "title": info.get("title") or info.get("playlist_title"),
        "thumbnail": thumbnail_from_info(info, raw_id),
        "playlist_count": info.get("playlist_count"),
        "duration": info.get("duration"),
        "duration_string": info.get("duration_string"),
        "uploader": info.get("uploader") or info.get("channel"),
        "entries": info.get("entries"),
    }


def is_playlist_like_info(info: dict[str, Any]) -> bool:
    if info.get("_type") == "playlist":
        return True
    if isinstance(info.get("entries"), list):
        return True
    if "playlist_count" in info:
        return True
    extractor = str(info.get("extractor_key") or info.get("ie_key") or "")
    return extractor == "YoutubeTab"


def preferred_thumbnails(thumbnails: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stable = [
        item for item in thumbnails
        if not is_youtube_playlist_maxres_thumbnail(str(item.get("url") or ""))
    ]
    return stable or thumbnails


def is_youtube_playlist_maxres_thumbnail(url: str) -> bool:
    parts = url_parts_for_host(url, "ytimg.com")
    return bool(parts and parts.scheme == "https" and parts.path.startswith("/s_p/") and parts.path.endswith("/maxresdefault.jpg"))


def video_id_from_value(value: str) -> str:
    value = value.strip()
    if YOUTUBE_ID_RE.fullmatch(value):
        return value
    parts = urlsplit(value)
    host = parts.hostname or ""
    path = parts.path.rstrip("/")
    if is_youtube_video_host(host):
        segments = [segment for segment in path.split("/") if segment]
        if segments and segments[0].lower() in ("v", "embed", "e", "shorts", "live") and len(segments) >= 2:
            video_id = segments[1]
            return video_id if YOUTUBE_ID_RE.fullmatch(video_id) else ""
        if len(segments) == 3 and segments[0].lower() == "source" and segments[2].lower() == "shorts":
            video_id = segments[1]
            return video_id if YOUTUBE_ID_RE.fullmatch(video_id) else ""
        if path in ("", "/watch", "/watch_popup", "/movie", "/movie_popup", "/watch.php", "/movie.php"):
            video_id = url_query_value(value, "v")
            return video_id if YOUTUBE_ID_RE.fullmatch(video_id) else ""
    host = host.lower()
    if host_matches(host, "youtu.be"):
        video_id = parts.path.strip("/").split("/", 1)[0]
        return video_id if YOUTUBE_ID_RE.fullmatch(video_id) else ""
    return ""


def is_clip_url(value: str) -> bool:
    parts = url_parts_for_host(value.strip(), "youtube.com")
    if parts is None:
        return False
    segments = url_path_segments(value.strip())
    return len(segments) == 2 and segments[0].lower() == "clip" and bool(YOUTUBE_CLIP_ID_RE.fullmatch(segments[1]))


def is_livestream_embed_url(value: str) -> bool:
    parts = url_parts_for_host(value.strip(), "youtube.com")
    if parts is None:
        return False
    if parts.path.rstrip("/").lower() != "/embed/live_stream":
        return False
    channel_id = url_query_value(value.strip(), "channel")
    return bool(channel_id)


def is_direct_single_video_url(value: str) -> bool:
    return bool(video_id_from_value(value) or is_clip_url(value) or is_livestream_embed_url(value))


def is_url(value: str) -> bool:
    return bool(ytdlp_pseudo_url_target(value)) or is_youtube_host(_host(value))


def matches_url(url: str) -> bool:
    return is_url(url)


def matches_info(info: dict[str, Any], _fallback_url: str = "") -> bool:
    extractor = str(info.get("extractor_key") or info.get("ie_key") or info.get("extractor") or "")
    return extractor.startswith(YOUTUBE_EXTRACTOR_KEY_PREFIX)


async def display_metadata(
    raw_id: str,
    *,
    config: Config,
    html_metadata: Callable[[str], Awaitable[dict[str, Any]]],
    impersonated_html_metadata: Callable[[str], Awaitable[dict[str, Any]]],
    http_client_provider: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    youtube_id = video_id_from_value(raw_id)
    if not youtube_id:
        return await html_metadata(raw_id)
    html_meta = await html_metadata(raw_id)
    needs_oembed = not html_meta.get("title") or not html_meta.get("thumbnail")
    oembed_meta = {}
    if needs_oembed:
        oembed_meta = await youtube_oembed_metadata(raw_id, youtube_id, config, http_client_provider)
    base_meta = oembed_meta or {
        "webpage_url": normalize_playable_url(raw_id),
        "id": youtube_id,
        "thumbnail": thumbnail_from_info({"id": youtube_id}, raw_id),
    }
    if html_meta:
        return merged_html_metadata(base_meta, html_meta, raw_id, youtube_id, has_oembed=bool(oembed_meta))
    return base_meta


async def youtube_oembed_metadata(
    raw_id: str,
    youtube_id: str,
    config: Config,
    http_client_provider: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    try:
        async with html_metadata.metadata_http_client(config, http_client_provider) as client:
            response = await client.get(
                "https://www.youtube.com/oembed",
                params={"url": normalize_playable_url(raw_id), "format": "json"},
                headers=html_metadata.request_headers(config, raw_id),
                timeout=min(config.upstream_timeout, 8),
            )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logger.debug("youtube oembed metadata failed url=%s error=%s", raw_id, exc)
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        "webpage_url": normalize_playable_url(raw_id),
        "id": youtube_id,
        "title": payload.get("title"),
        "thumbnail": payload.get("thumbnail_url") or thumbnail_from_info({"id": youtube_id}, raw_id),
    }


def merged_html_metadata(
    base_meta: dict[str, Any],
    html_meta: dict[str, Any],
    raw_id: str,
    youtube_id: str,
    *,
    has_oembed: bool = False,
) -> dict[str, Any]:
    merged = {
        **base_meta,
        "webpage_url": normalize_playable_url(raw_id),
        "id": youtube_id,
    }
    for key in ("title", "thumbnail", "description", "duration"):
        value = html_meta.get(key)
        if value and (not has_oembed or not merged.get(key)):
            merged[key] = value
    return compact_dict(**merged)


def metadata_plan_for_config_url(url: str) -> SiteMetadataPlan:
    canonical_url = normalize_extract_url(url)
    extract_url = playlist_light_metadata_url(url) or canonical_url
    if config_url_supports_playlist_light_metadata(url):
        return SiteMetadataPlan(
            node_kind=NodeKind.PLAYLIST_DIRECTORY,
            strategy=MetadataStrategy.PLAYLIST_YTDLP,
            canonical_url=canonical_url,
            ytdlp=YtdlpMetadataOptions(
                extract_url=extract_url,
                noplaylist=False,
                extract_flat="in_playlist",
                playlist_items="1",
                process=True,
            ),
        )
    return SiteMetadataPlan(
        node_kind=NodeKind.LEAF_VOD,
        strategy=MetadataStrategy.DISPLAY,
        canonical_url=canonical_single_video_url(url),
    )


def ytdlp_pseudo_url_target(value: str) -> str:
    return YOUTUBE_YTDLP_PSEUDO_URLS.get(value.strip().lower(), "")


def is_youtube_host(host: str) -> bool:
    return is_youtube_tab_host(host) or is_youtube_music_host(host) or host_matches(host, "youtu.be")


def is_youtube_com_host(host: str) -> bool:
    return host_matches(host, "youtube.com")


def is_youtube_music_host(host: str) -> bool:
    return host_matches(host, "music.youtube.com")


def is_youtube_tab_host(host: str) -> bool:
    return is_youtube_com_host(host) or host_matches(host, "youtubekids.com")


def is_youtube_video_host(host: str) -> bool:
    return (
        host_matches(host, "youtube.com")
        or is_youtube_music_host(host)
        or host_matches(host, "youtube-nocookie.com")
        or host_matches(host, "youtubekids.com")
        or host_matches(host, "youtube.googleapis.com")
    )


def _matches_home_url(facts: YoutubeUrlFacts) -> bool:
    return facts.is_youtube_com and facts.path == "" and not facts.parts.query


def _matches_search_url(facts: YoutubeUrlFacts) -> bool:
    if not (facts.is_youtube_com or facts.is_music):
        return False
    path = facts.path.lower()
    if path not in ("/results", "/search"):
        return False
    return bool((url_query_value(facts.value, "search_query") or url_query_value(facts.value, "q")).strip())


def _matches_hashtag_url(facts: YoutubeUrlFacts) -> bool:
    segments = facts.segments
    return facts.is_youtube_com and len(segments) == 2 and segments[0].lower() == "hashtag" and bool(segments[1])


def _matches_feed_folder_url(facts: YoutubeUrlFacts) -> bool:
    segments = facts.segments
    return (
        facts.is_youtube_com
        and len(segments) == 2
        and segments[0].lower() == "feed"
        and segments[1].lower() in YOUTUBE_FEED_FOLDERS
    )


def _matches_playlist_folder_url(facts: YoutubeUrlFacts) -> bool:
    playlist_id = playlist_id_from_value(facts.value)
    return bool(playlist_id) and not playlist_id.startswith("RD")


def _matches_playlists_path(facts: YoutubeUrlFacts) -> bool:
    return not facts.is_kids and facts.path.lower().endswith("/playlists")


def _matches_music_browse_url(facts: YoutubeUrlFacts) -> bool:
    segments = facts.segments
    return facts.is_music and len(segments) == 2 and segments[0].lower() == "browse" and bool(segments[1])


def _matches_music_channel_url(facts: YoutubeUrlFacts) -> bool:
    segments = facts.segments
    return facts.is_music and len(segments) == 2 and segments[0].lower() == "channel" and bool(segments[1])


def _matches_music_channel_root_url(facts: YoutubeUrlFacts) -> bool:
    segments = facts.segments
    if not facts.is_music:
        return False
    if len(segments) == 1:
        return segments[0].startswith("@")
    if len(segments) == 2:
        return segments[0].lower() in ("c", "user")
    return False


def _channel_tabs_for_host(facts: YoutubeUrlFacts) -> tuple[str, ...]:
    if facts.is_music:
        return YOUTUBE_MUSIC_CHANNEL_TABS
    return YOUTUBE_KIDS_CHANNEL_TABS if facts.is_kids else YOUTUBE_CHANNEL_TABS


def _matches_channel_tab_url(facts: YoutubeUrlFacts) -> bool:
    if not (facts.is_tab_host or facts.is_music):
        return False
    tab = facts.segments[-1].lower() if len(facts.segments) >= 2 else ""
    return tab in _channel_tabs_for_host(facts)


def _matches_channel_root_url(facts: YoutubeUrlFacts) -> bool:
    if not (facts.is_tab_host or facts.is_music):
        return False
    segments = facts.segments
    if len(segments) == 1:
        return segments[0].startswith("@")
    if len(segments) == 2:
        return segments[0] in ("channel", "c", "user")
    return False


YOUTUBE_FOLDER_URL_RULES = (
    YoutubeUrlRule("folder", _matches_home_url),
    YoutubeUrlRule("search", _matches_search_url),
    YoutubeUrlRule("folder", _matches_hashtag_url),
    YoutubeUrlRule("folder", _matches_feed_folder_url),
    YoutubeUrlRule("playlist", _matches_playlist_folder_url),
    YoutubeUrlRule("folder", _matches_playlists_path),
    YoutubeUrlRule("folder", _matches_channel_tab_url),
    YoutubeUrlRule("folder", _matches_channel_root_url),
)

YOUTUBE_MUSIC_FOLDER_URL_RULES = (
    YoutubeUrlRule("search", _matches_search_url),
    YoutubeUrlRule("playlist", _matches_playlist_folder_url),
    YoutubeUrlRule("folder", _matches_music_browse_url),
    YoutubeUrlRule("folder", _matches_music_channel_url),
    YoutubeUrlRule("folder", _matches_music_channel_root_url),
    YoutubeUrlRule("folder", _matches_channel_tab_url),
)


def folder_url_kind(value: str) -> str:
    facts = _url_facts(value)
    if facts.is_music:
        return _music_folder_url_kind(facts)
    if not facts.is_tab_host:
        return ""
    return _first_matching_url_rule(facts, YOUTUBE_FOLDER_URL_RULES)


def is_search_url(value: str) -> bool:
    return bool(search_query_from_url(value))


def _music_folder_url_kind(facts: YoutubeUrlFacts) -> str:
    return _first_matching_url_rule(facts, YOUTUBE_MUSIC_FOLDER_URL_RULES)


def config_url_supports_playlist_light_metadata(value: str) -> bool:
    kind = folder_url_kind(value)
    return kind in YOUTUBE_DIRECTORY_KINDS or bool(playlist_id_from_value(value))


def config_node_kind(value: str) -> NodeKind | None:
    if folder_url_kind(value) in YOUTUBE_DIRECTORY_KINDS:
        return NodeKind.PLAYLIST_DIRECTORY
    return None


def config_search_node(value: str, node_id: str, title: str = "", remarks: str = "") -> MediaNode | None:
    if not is_search_url(value):
        return None
    return MediaNode(
        node_id,
        title or search_title_from_url(value),
        kind="search",
        remarks=remarks,
        remarks_key="" if remarks else "search",
    )


def search_node_from_url_item(value: str, node_id: str, title: str = "", remarks: str = "") -> MediaNode | None:
    return config_search_node(value, node_id, title, remarks)


def url_is_search_directory(value: str) -> bool:
    return is_search_url(value)


def search_entry_kind(entry: dict[str, Any]) -> str:
    url = playable_url_from_info(entry, "")
    if not url:
        return ""
    if is_unviewable_playlist_url(url):
        return ""
    kind = folder_url_kind(url)
    if kind == "search":
        return "search"
    if kind in YOUTUBE_COLLECTION_KINDS:
        return kind
    return ""


def collection_url_kind(value: str) -> str:
    if is_unviewable_playlist_url(value):
        return ""
    kind = folder_url_kind(value)
    if kind in YOUTUBE_COLLECTION_KINDS:
        return kind
    return ""


def playlist_entry_is_collection(info: dict[str, Any]) -> bool:
    url = playable_url_from_info(info, "")
    return collection_url_kind(url) == "playlist"


def playlist_entry_is_rejected_collection(info: dict[str, Any]) -> bool:
    return is_unviewable_playlist_url(playable_url_from_info(info, ""))


def search_query_from_url(value: str) -> str:
    parts = url_parts_for_any_host(value, "youtube.com", "music.youtube.com")
    if parts is None:
        return ""
    if parts.path.rstrip("/").lower() not in ("/results", "/search"):
        return ""
    return (url_query_value(value, "search_query") or url_query_value(value, "q")).strip()


def search_title_from_url(value: str) -> str:
    query = search_query_from_url(value)
    return i18n.youtube_search_title(query) if query else value


def playlist_id_from_value(value: str) -> str:
    value = value.strip()
    if YOUTUBE_PLAYLIST_ID_RE.fullmatch(value):
        return value
    parts = url_parts_for_any_host(value, "youtube.com", "music.youtube.com")
    if parts is None:
        return ""
    path = parts.path.rstrip("/").lower()
    if path not in ("/playlist", "/embed/videoseries"):
        return ""
    playlist_id = url_query_value(value, "list")
    return playlist_id if YOUTUBE_PLAYLIST_ID_RE.fullmatch(playlist_id) else ""


def is_unviewable_playlist_url(value: str) -> bool:
    playlist_id = playlist_id_from_value(value)
    return playlist_id.startswith("RD")


def light_collection_child_urls(value: str, meta: dict[str, Any] | None = None) -> list[str]:
    if not is_url(value):
        return []
    if not _is_channel_root_url(value):
        return []
    entry_urls = light_collection_entry_urls(value, meta or {})
    if entry_urls:
        return entry_urls
    parts = urlsplit(value)
    base_path = parts.path.rstrip("/")
    if is_youtube_music_host(parts.hostname or ""):
        playlist_url = music_channel_playlist_url(value, meta or {})
        if playlist_url:
            return [playlist_url]
        return [
            urlunsplit((parts.scheme, parts.netloc, f"{base_path}/videos", "", "")),
            urlunsplit((parts.scheme, parts.netloc, f"{base_path}/playlists", "", "")),
        ]
    is_kids = is_youtube_kids_host(parts.hostname or "")
    if not is_kids:
        return []
    tabs = ["videos"]
    return [
        urlunsplit((parts.scheme, parts.netloc, f"{base_path}/{tab}", "", ""))
        for tab in tabs
    ]


def light_collection_uses_static_metadata(value: str) -> bool:
    return channel_root_uses_static_light_metadata(value)


def category_extract_url(value: str) -> str:
    return normalize_extract_url(value)


def category_flat_playlist_items(value: str) -> str:
    return "1-4" if channel_root_supports_collection_probe(value) else ""


def category_supports_collection_probe(value: str) -> bool:
    return channel_root_supports_collection_probe(value)


def category_fallback_child_urls(value: str) -> list[str]:
    return channel_root_fallback_child_urls(value)


def channel_root_uses_static_light_metadata(value: str) -> bool:
    return _is_channel_root_url(value) and is_youtube_music_host(_host(value))


def channel_root_supports_collection_probe(value: str) -> bool:
    return _is_channel_root_url(value) and is_youtube_com_host(_host(value))


def channel_root_fallback_child_urls(value: str) -> list[str]:
    if not _is_channel_root_url(value):
        return []
    parts = url_parts_for_host(value, "youtube.com")
    if parts is None:
        return []
    base_path = parts.path.rstrip("/")
    return [urlunsplit((parts.scheme, parts.netloc, f"{base_path}/videos", "", ""))]


def channel_root_synthetic_collection_urls(value: str, child_urls: list[str]) -> list[str]:
    if not channel_root_supports_collection_probe(value):
        return []
    parts = urlsplit(value)
    base_path = parts.path.rstrip("/")
    playlists_url = urlunsplit((parts.scheme, parts.netloc, f"{base_path}/playlists", "", ""))
    return [] if playlists_url in child_urls else [playlists_url]


def music_channel_playlist_url(value: str, meta: dict[str, Any]) -> str:
    if not _matches_music_channel_url(_url_facts(value, normalize=False)):
        return ""
    url = str(meta.get("webpage_url") or "")
    return url if _matches_playlist_folder_url(_url_facts(url, normalize=False)) else ""


def light_collection_entry_urls(source_url: str, meta: dict[str, Any]) -> list[str]:
    source_is_kids = is_youtube_kids_host(_host(source_url))
    source_is_music = is_youtube_music_host(_host(source_url))
    out = []
    for entry in meta.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("webpage_url") or entry.get("url") or "")
        if source_is_kids and channel_tab_name(url) != "videos":
            continue
        if source_is_music and channel_tab_name(url) not in ("videos", "playlists"):
            continue
        if _is_channel_tab_url(url) and url not in out:
            out.append(url)
    return out


def is_playlist_collection_entry(entry: dict[str, Any]) -> bool:
    url = str(entry.get("url") or entry.get("webpage_url") or "")
    if is_unviewable_playlist_url(url):
        return False
    if entry.get("_type") == "url" and entry.get("ie_key") == "YoutubeTab":
        return collection_url_kind(url) in YOUTUBE_COLLECTION_KINDS
    if entry.get("_type") == "playlist":
        segments = url_path_segments(url)
        return bool(segments and segments[-1].lower() in YOUTUBE_CHANNEL_TABS)
    return False


def is_playlist_collection_info(info: dict[str, Any]) -> bool:
    entries = [entry for entry in info.get("entries") or [] if isinstance(entry, dict)]
    return bool(entries) and all(is_playlist_collection_entry(entry) for entry in entries)


def node_kind_from_playlist_info(info: dict[str, Any], _url: str = "") -> NodeKind | None:
    if is_playlist_collection_info(info):
        return NodeKind.COLLECTION_DIRECTORY
    return None


def playlist_collection_synthetic_urls(url: str, existing_urls: list[str], info: dict[str, Any]) -> list[str]:
    return channel_root_synthetic_collection_urls(url, existing_urls)


def playlist_item_supports_full_detail(url: str) -> bool:
    return is_direct_single_video_url(url)


def single_video_detail_url(url: str) -> str:
    return canonical_single_video_url(url)


def single_video_uses_light_detail(url: str) -> bool:
    return is_direct_single_video_url(url)


def single_video_prewarm_args(url: str) -> tuple[str, str] | None:
    canonical_url = canonical_single_video_url(url)
    if video_id_from_value(url):
        return canonical_url, normalize_extract_url(canonical_url)
    return None


def single_video_extract_url(url: str) -> str:
    return normalize_extract_url(url)


def _is_channel_root_url(value: str) -> bool:
    return _matches_channel_root_url(_url_facts(value, normalize=False))


def _is_channel_tab_url(value: str) -> bool:
    return _matches_channel_tab_url(_url_facts(value, normalize=False))


def channel_tab_name(value: str) -> str:
    segments = url_path_segments(value)
    return segments[-1].lower() if len(segments) >= 2 else ""


def collection_child_title(url: str, source_info: dict[str, Any]) -> str:
    channel_title = str(source_info.get("title") or source_info.get("channel") or "").strip()
    tab = channel_tab_name(url)
    return f"{channel_title} - Playlists" if channel_title and tab == "playlists" else tab or url


def is_youtube_kids_host(host: str) -> bool:
    return host_matches(host, "youtubekids.com")


def youtube_kids_channel_videos_url(value: str) -> str:
    parts = url_parts_for_host(value.strip(), "youtubekids.com")
    if parts is None:
        return ""
    segments = url_path_segments(value.strip())
    if len(segments) == 2 and segments[0].lower() == "channel" and segments[1]:
        return urlunsplit((parts.scheme, parts.netloc, f"/channel/{segments[1]}/videos", "", ""))
    return ""


def playable_url_from_info(info: dict[str, Any], fallback_url: str = "") -> str:
    return normalize_playable_url(str(
        info.get("webpage_url")
        or info.get("url")
        or info.get("original_url")
        or fallback_url
        or ""
    ))


def client_subtitles_from_info(
    info: dict[str, Any],
    *,
    subtitle_languages: tuple[str, ...] = (),
    subtitles_enabled: bool = False,
    all_manual: bool = False,
) -> tuple[dict[str, str], ...]:
    return youtube_subtitles.client_subtitles_from_info(
        info,
        subtitle_languages=subtitle_languages,
        subtitles_enabled=subtitles_enabled,
        all_manual=all_manual,
    )
