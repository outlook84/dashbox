from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qs, urlsplit

from ..config import Config
from ..models import NodeKind
from .hosts import first_query_value, host_matches, url_path_segments
from .types import MetadataStrategy, SiteMetadataPlan, YtdlpMetadataOptions


TWITCH_RESERVED_ROOTS = {
    "activate",
    "bits",
    "checkout",
    "collections",
    "directory",
    "downloads",
    "drops",
    "inventory",
    "jobs",
    "login",
    "logout",
    "moderator",
    "p",
    "popout",
    "prime",
    "products",
    "search",
    "settings",
    "store",
    "subscriptions",
    "team",
    "turbo",
    "videos",
    "wallet",
}

TWITCH_CHANNEL_VIDEO_TABS = {"videos", "profile", "clips"}


def is_url(url: str) -> bool:
    return _is_twitch_web_url(url) or _is_player_url(url) or _is_clips_url(url)


def matches_url(url: str) -> bool:
    return is_url(url)


async def display_metadata(
    raw_id: str,
    *,
    config: Config,
    html_metadata: Callable[[str], Awaitable[dict[str, Any]]],
    impersonated_html_metadata: Callable[[str], Awaitable[dict[str, Any]]],
    http_client_provider: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    if is_single_playable_url(raw_id):
        return {}
    return await html_metadata(raw_id)


def is_single_playable_url(url: str) -> bool:
    return is_vod_url(url) or is_clip_url(url) or is_stream_url(url)


def is_vod_url(url: str) -> bool:
    if _is_player_video_url(url):
        return True
    parts = urlsplit(url)
    if not _is_twitch_web_host(parts.hostname or ""):
        return False
    segments = [segment.lower() for segment in url_path_segments(url)]
    query = parse_qs(parts.query)
    if len(segments) >= 2 and segments[0] == "videos":
        return _is_numeric_id(segments[1])
    if len(segments) >= 3 and segments[1] in {"v", "video"}:
        return _is_numeric_id(segments[2])
    if len(segments) >= 2 and segments[1] == "schedule":
        return _is_numeric_id(first_query_value(query, "vodID"))
    return False


def is_clip_url(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    segments = url_path_segments(url)
    if host_matches(host, "clips.twitch.tv"):
        if first_query_value(parse_qs(parts.query), "clip"):
            return True
        return bool(segments)
    if not _is_twitch_web_host(host):
        return False
    lowered = [segment.lower() for segment in segments]
    return len(lowered) >= 2 and (lowered[0] == "clip" or lowered[1] == "clip") and bool(segments[-1])


def is_stream_url(url: str) -> bool:
    if _is_player_channel_url(url):
        return True
    parts = urlsplit(url)
    if not _is_twitch_web_host(parts.hostname or ""):
        return False
    segments = url_path_segments(url)
    if len(segments) != 1:
        return False
    channel = segments[0].lower()
    return bool(channel) and channel not in TWITCH_RESERVED_ROOTS


def is_collection_url(url: str) -> bool:
    parts = urlsplit(url)
    if not _is_twitch_web_host(parts.hostname or ""):
        return False
    segments = url_path_segments(url)
    return len(segments) >= 2 and segments[0].lower() == "collections" and bool(segments[1])


def is_channel_videos_url(url: str) -> bool:
    parts = urlsplit(url)
    if not _is_twitch_web_host(parts.hostname or ""):
        return False
    segments = [segment.lower() for segment in url_path_segments(url)]
    if len(segments) < 2 or segments[0] in TWITCH_RESERVED_ROOTS:
        return False
    if segments[1] not in TWITCH_CHANNEL_VIDEO_TABS:
        return False
    return True


def is_playlist_url(url: str) -> bool:
    return is_collection_url(url) or is_channel_videos_url(url)


def config_node_kind(url: str) -> NodeKind | None:
    if is_playlist_url(url):
        return NodeKind.PLAYLIST_DIRECTORY
    if is_single_playable_url(url):
        return NodeKind.LEAF_VOD
    return None


def metadata_plan_for_config_url(url: str) -> SiteMetadataPlan:
    if is_single_playable_url(url):
        return SiteMetadataPlan(
            node_kind=NodeKind.LEAF_VOD,
            strategy=MetadataStrategy.SINGLE_YTDLP,
            canonical_url=url,
            ytdlp=YtdlpMetadataOptions(
                extract_url=url,
                noplaylist=True,
            ),
        )
    if is_playlist_url(url):
        return SiteMetadataPlan(
            node_kind=NodeKind.PLAYLIST_DIRECTORY,
            strategy=MetadataStrategy.PLAYLIST_YTDLP,
            canonical_url=url,
            ytdlp=YtdlpMetadataOptions(
                extract_url=url,
                noplaylist=False,
                extract_flat="in_playlist",
                playlist_items="1",
            ),
        )
    return SiteMetadataPlan(
        node_kind=config_node_kind(url) or NodeKind.LEAF_VOD,
        strategy=MetadataStrategy.DISPLAY,
        canonical_url=url,
    )


def playlist_items_use_existing_metadata(url: str) -> bool:
    return is_playlist_url(url)


def playlist_items_allow_full_selected_detail(url: str) -> bool:
    return not playlist_items_use_existing_metadata(url)


def playlist_entry_is_collection(entry: dict[str, Any]) -> bool:
    url = str(entry.get("url") or entry.get("webpage_url") or "")
    return entry.get("ie_key") == "TwitchCollection" or is_collection_url(url)


def is_playlist_collection_info(info: dict[str, Any]) -> bool:
    entries = [entry for entry in info.get("entries") or [] if isinstance(entry, dict)]
    return bool(entries) and all(playlist_entry_is_collection(entry) for entry in entries)


def node_kind_from_playlist_info(info: dict[str, Any], _url: str = "") -> NodeKind | None:
    if is_playlist_collection_info(info):
        return NodeKind.COLLECTION_DIRECTORY
    return None


def _is_twitch_web_url(url: str) -> bool:
    return _is_twitch_web_host(urlsplit(url).hostname or "")


def _is_twitch_web_host(host: str) -> bool:
    host = host.lower()
    return host_matches(host, "twitch.tv") and not host_matches(host, "clips.twitch.tv")


def _is_player_url(url: str) -> bool:
    return host_matches(urlsplit(url).hostname or "", "player.twitch.tv")


def _is_clips_url(url: str) -> bool:
    return host_matches(urlsplit(url).hostname or "", "clips.twitch.tv")


def _is_player_video_url(url: str) -> bool:
    parts = urlsplit(url)
    if not host_matches(parts.hostname or "", "player.twitch.tv"):
        return False
    video_id = first_query_value(parse_qs(parts.query), "video").lstrip("v")
    return _is_numeric_id(video_id)


def _is_player_channel_url(url: str) -> bool:
    parts = urlsplit(url)
    if not host_matches(parts.hostname or "", "player.twitch.tv"):
        return False
    return bool(first_query_value(parse_qs(parts.query), "channel").strip())


def _is_numeric_id(value: str) -> bool:
    return bool(value and value.isascii() and value.isdigit())
