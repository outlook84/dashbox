from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import SplitResult, parse_qs, unquote_plus, urlsplit

from .. import i18n
from ..config import Config
from ..models import NodeKind
from ..models import MediaNode
from .hosts import first_query_value, host_matches, url_path_segments
from .types import MetadataStrategy, SiteMetadataPlan, YtdlpMetadataOptions


ONION_HOST = "pornhubvybmsymdol4iibwgwtkpwmeyd6luq2gxajgjzfjvotyt5zhyd.onion"


def is_url(url: str) -> bool:
    return _url_parts(url) is not None


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
    return await impersonated_html_metadata(raw_id)


def _url_parts(url: str) -> SplitResult | None:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if (
        host_matches(host, "pornhub.com")
        or host_matches(host, "pornhub.net")
        or host_matches(host, "pornhub.org")
        or host_matches(host, "pornhubpremium.com")
        or host == ONION_HOST
    ):
        return parts
    return None


def is_single_video_url(url: str) -> bool:
    parts = _url_parts(url)
    if parts is None:
        return False
    path = parts.path.rstrip("/").lower()
    segments = [segment.lower() for segment in url_path_segments(url)]
    query = parse_qs(parts.query)
    viewkey = first_query_value(query, "viewkey")
    if path in ("/view_video.php", "/video/show"):
        return is_video_id(viewkey)
    if len(segments) == 2 and segments[0] == "embed":
        return is_video_id(segments[1])
    return False


def is_collection_url(url: str) -> bool:
    parts = _url_parts(url)
    if parts is None or is_single_video_url(url):
        return False
    return bool(url_path_segments(url))


def config_node_kind(url: str) -> NodeKind | None:
    if is_collection_url(url):
        return NodeKind.PLAYLIST_DIRECTORY
    return None


def metadata_plan_for_config_url(url: str) -> SiteMetadataPlan:
    kind = config_node_kind(url)
    if kind == NodeKind.PLAYLIST_DIRECTORY:
        return SiteMetadataPlan(
            node_kind=kind,
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
        node_kind=NodeKind.LEAF_VOD,
        strategy=MetadataStrategy.DISPLAY,
        canonical_url=url,
    )


def image_url_is_proxyable(url: str) -> bool:
    parts = urlsplit(url)
    host = parts.hostname or ""
    return parts.scheme == "https" and host_matches(host, "phncdn.com")


def image_referer_for_url(url: str) -> str:
    return "https://www.pornhub.com/" if image_url_is_proxyable(url) else ""


def ytdlp_impersonate_target(url: str) -> str:
    return "chrome" if is_url(url) else ""


def config_search_node(url: str, node_id: str, title: str = "", remarks: str = "") -> MediaNode | None:
    if not is_search_url(url):
        return None
    return MediaNode(
        node_id,
        title or title_from_url(url) or url,
        kind="search",
        remarks=remarks,
        remarks_key="" if remarks else "search",
    )


def search_node_from_url_item(url: str, node_id: str, title: str = "", remarks: str = "") -> MediaNode | None:
    return config_search_node(url, node_id, title, remarks)


def url_is_search_directory(url: str) -> bool:
    return is_search_url(url)


def collection_title(info: dict, fallback_url: str) -> str:
    return str(info.get("title") or info.get("playlist_title") or title_from_url(fallback_url) or fallback_url)


def is_search_url(url: str) -> bool:
    parts = _url_parts(url)
    if parts is None:
        return False
    segments = [segment.lower() for segment in url_path_segments(url)]
    return segments == ["video", "search"]


def title_from_url(url: str) -> str:
    if not is_collection_url(url):
        return ""
    parts = _url_parts(url)
    if parts is None:
        return ""
    query = parse_qs(parts.query)
    segments = [segment.lower() for segment in url_path_segments(url)]
    if not segments:
        return ""
    if segments == ["video"]:
        return "Pornhub Videos"
    if is_search_url(url):
        query_text = first_query_value(query, "search")
        return i18n.pornhub_search_title(clean_label(query_text))
    if segments[0] == "categories" and len(segments) >= 2:
        return f"Pornhub Category: {clean_label(segments[-1])}"
    if segments[0] in {"model", "pornstar"} and len(segments) >= 2:
        kind = "Model" if segments[0] == "model" else "Pornstar"
        return f"Pornhub {kind}: {clean_label(segments[1])}"
    if segments[0] in {"users", "channels"} and len(segments) >= 2:
        kind = "User" if segments[0] == "users" else "Channel"
        return f"Pornhub {kind}: {clean_label(segments[1])}"
    if segments[0] == "playlist" and len(segments) >= 2:
        return f"Pornhub Playlist {clean_label(segments[1])}"
    if segments[0] == "hd":
        return "Pornhub HD"
    if segments[0] == "described-video":
        return "Pornhub Described Videos"
    return f"Pornhub {clean_label(segments[-1])}"


def clean_label(value: str) -> str:
    value = unquote_plus(value)
    return " ".join(value.replace("-", " ").replace("_", " ").split())


def is_video_id(value: str) -> bool:
    return bool(value and value.isascii() and value.isalnum())
