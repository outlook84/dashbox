from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .duration import duration_text
from ..models import MediaEpisode, MediaNode
from ..models import NodeKind
from .. import i18n
from ..config import ImageProxyMode
from ..sites import registry
from ..sites.types import MetadataStrategy
from ..utils import text
from . import image_policy


def node_from_info(info: dict[str, Any], base_url: str = "", image_proxy_mode: ImageProxyMode = ImageProxyMode.KNOWN) -> MediaNode:
    adapter = adapter_from_info(info)
    raw_node_id = str(info.get("webpage_url") or info.get("url") or info.get("id") or "")
    node_id = registry.call(adapter, "normalize_playable_url", raw_node_id)
    title = str(info.get("title") or node_id or i18n.unnamed())
    thumbnail = thumbnail_from_info(adapter, info, node_id)
    return MediaNode(
        id=node_id,
        title=title,
        thumbnail=image_policy.proxied_thumbnail_url(thumbnail, base_url, image_proxy_mode),
        remarks=display_remarks_from_info(info),
        content=content_from_info(info),
        node_kind=NodeKind.LEAF_VOD.value,
    )


def playlist_node_from_info(info: dict[str, Any], fallback_url: str) -> MediaNode:
    entries = [entry for entry in info.get("entries") or [] if isinstance(entry, dict)]
    count = len(entries)
    return MediaNode(
        id=playlist_node_id(info, fallback_url),
        title=str(info.get("title") or info.get("playlist_title") or fallback_url),
        kind="playlist",
        thumbnail=str(info.get("thumbnail") or ""),
        remarks_key="item_count" if count else "playlist",
        item_count=count,
        content=content_from_info(info),
        node_kind=NodeKind.PLAYLIST_DIRECTORY.value,
    )


def node_from_playlist_metadata(
    info: dict[str, Any],
    fallback_url: str,
    base_url: str = "",
    image_proxy_mode: ImageProxyMode = ImageProxyMode.KNOWN,
) -> MediaNode:
    count = info.get("playlist_count")
    has_count = isinstance(count, int) and count >= 0
    remarks = "" if has_count else str(info.get("uploader") or "")
    adapter = adapter_from_info(info, fallback_url)
    thumbnail = thumbnail_from_info(adapter, info, fallback_url)
    return MediaNode(
        id=playlist_node_id(info, fallback_url),
        title=str(info.get("title") or info.get("playlist_title") or fallback_url),
        kind="playlist",
        thumbnail=image_policy.proxied_thumbnail_url(thumbnail, base_url, image_proxy_mode),
        remarks=remarks,
        remarks_key="item_count" if has_count else ("" if remarks else "playlist"),
        item_count=count if has_count else 0,
        content=content_from_info(info),
        node_kind=NodeKind.PLAYLIST_DIRECTORY.value,
    )


def playlist_item_node_from_info(info: dict[str, Any], index: int, selected_url: str) -> MediaNode:
    node = node_from_info(info)
    return MediaNode(
        id=node.id,
        title=node.title,
        thumbnail=node.thumbnail,
        remarks=node.remarks,
        content=node.content,
        playlist_name=playlist_episode_title(info, index),
        playlist_url=selected_url,
        node_kind=NodeKind.LEAF_VOD.value,
    )


def search_node_from_entry(
    entry: dict[str, Any],
    base_url: str = "",
    image_proxy_mode: ImageProxyMode = ImageProxyMode.KNOWN,
) -> MediaNode | None:
    url = playable_url_from_info(entry, "")
    if not url:
        return None
    if url_is_known_leaf(url):
        return node_from_info(entry, base_url, image_proxy_mode)
    adapter = adapter_from_url(url)
    kind = registry.call(adapter, "search_entry_kind", entry)
    if kind == "search":
        node = node_from_playlist_metadata(entry, url, base_url, image_proxy_mode)
        return MediaNode(
            id=node.id,
            title=node.title,
            kind="search",
            thumbnail=node.thumbnail,
            remarks=node.remarks,
            remarks_key=node.remarks_key,
            item_count=node.item_count,
            part_count=node.part_count,
            content=node.content,
            extras=node.extras,
        )
    if kind == "folder":
        node = node_from_playlist_metadata(entry, url, base_url, image_proxy_mode)
        return MediaNode(
            id=node.id,
            title=node.title,
            kind="folder",
            thumbnail=node.thumbnail,
            remarks=node.remarks,
            remarks_key=node.remarks_key,
            item_count=node.item_count,
            part_count=node.part_count,
            content=node.content,
            extras=node.extras,
        )
    if kind == "playlist":
        node = node_from_playlist_metadata(entry, url, base_url, image_proxy_mode)
        return MediaNode(
            id=node.id,
            title=node.title,
            kind="folder",
            thumbnail=node.thumbnail,
            remarks=node.remarks,
            remarks_key=node.remarks_key,
            item_count=node.item_count,
            part_count=node.part_count,
            content=node.content,
            extras=node.extras,
        )
    return None


def search_nodes_from_info(
    info: dict[str, Any],
    base_url: str = "",
    image_proxy_mode: ImageProxyMode = ImageProxyMode.KNOWN,
) -> list[MediaNode]:
    entries = [entry for entry in info.get("entries") or [] if isinstance(entry, dict)]
    return [
        node
        for node in (search_node_from_entry(entry, base_url, image_proxy_mode) for entry in entries)
        if node
    ]


def collection_nodes_from_info(info: dict[str, Any]) -> list[MediaNode]:
    nodes = []
    entries = [entry for entry in info.get("entries") or [] if isinstance(entry, dict)]
    urls = [playable_url_from_info(entry, "") for entry in entries]
    for entry, url in zip(entries, urls):
        if url:
            nodes.append(node_from_playlist_metadata(entry, url))
    return nodes


def synthetic_collection_nodes(urls: list[str], source_info: dict[str, Any]) -> list[MediaNode]:
    nodes = []
    for url in urls:
        title = registry.call_for_url(url, "collection_child_title", url, source_info)
        nodes.append(MediaNode(
            url,
            title,
            kind="playlist",
            remarks_key="playlist",
            node_kind=NodeKind.PLAYLIST_DIRECTORY.value,
        ))
    return nodes


def playlist_item_nodes_from_info(info: dict[str, Any]) -> list[MediaNode]:
    entries = [entry for entry in info.get("entries") or [] if isinstance(entry, dict)]
    return [
        node
        for node in (
            playlist_item_node_from_entry(entry, index)
            for index, entry in enumerate(entries, 1)
        )
        if node
    ]


def playlist_item_node_from_entry(info: dict[str, Any], index: int) -> MediaNode | None:
    if playlist_entry_is_playlist_class(info):
        url = playable_url_from_info(info, "")
        return node_from_playlist_metadata(info, url) if url else None
    node = node_from_info(info)
    selected_url = with_episode_index(playable_url_from_info(info, node.id), index)
    if not selected_url:
        return None
    item = playlist_item_node_from_info(info, index, selected_url)
    return MediaNode(
        id=node.id,
        title=node.title,
        thumbnail=node.thumbnail,
        remarks=node.remarks,
        content=node.content,
        playlist_name=item.playlist_name,
        playlist_url=item.playlist_url,
        node_kind=NodeKind.LEAF_VOD.value,
    )


def aggregate_playlist_node_from_info(info: dict[str, Any], fallback_url: str) -> MediaNode:
    entries = [entry for entry in info.get("entries") or [] if isinstance(entry, dict)]
    episodes = [
        episode
        for episode in (playlist_episode(entry, index, fallback_url) for index, entry in enumerate(entries, 1))
        if episode
    ]
    node = playlist_node_from_info(info, fallback_url)
    return MediaNode(
        id=node.id,
        title=node.title,
        kind=node.kind,
        thumbnail=node.thumbnail,
        remarks=node.remarks,
        remarks_key=node.remarks_key,
        item_count=node.item_count,
        part_count=node.part_count,
        content=node.content,
        play_from="yt-dlp",
        playlist_name=node.playlist_name,
        playlist_url=node.playlist_url,
        episodes=tuple(episodes),
        node_kind=NodeKind.AGGREGATE_VOD.value,
        extras=dict(node.extras),
    )


def playlist_entry_is_playlist_class(info: dict[str, Any]) -> bool:
    adapter = adapter_from_info(info)
    if registry.call(adapter, "playlist_entry_is_rejected_collection", info):
        return False
    count = info.get("playlist_count")
    if isinstance(count, int) and count > 0:
        return True
    if info.get("_type") == "playlist":
        return True
    return registry.call(adapter, "playlist_entry_is_collection", info)


def playlist_episode(entry: dict[str, Any], index: int, fallback_url: str = "") -> MediaEpisode | None:
    url = playable_url_from_info(entry, "")
    adapter = adapter_from_url(fallback_url)
    adapter_episode = registry.call(adapter, "aggregate_playlist_episode", entry, index, fallback_url, url)
    if adapter_episode:
        return MediaEpisode(
            title=adapter_episode["title"],
            url=with_episode_index(adapter_episode["url"], index),
        )
    title = playlist_episode_title(entry, index, fallback_url)
    if not url and entry.get("id"):
        url = str(entry["id"])
    if not url:
        return None
    return MediaEpisode(title=title, url=with_episode_index(url, index))


def with_episode_index(url: str, index: int) -> str:
    if not url.startswith(("http://", "https://")):
        return url
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["dashbox_index"] = str(index)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def playlist_episode_title(entry: dict[str, Any], index: int, fallback_url: str = "") -> str:
    return clean_title(str(entry.get("title") or entry.get("id") or i18n.episode_title(index)))


def playlist_node_id(info: dict[str, Any], fallback_url: str) -> str:
    adapter = adapter_from_url(fallback_url)
    if registry.call(adapter, "node_kind_from_playlist_info", info, fallback_url) == NodeKind.AGGREGATE_VOD:
        return fallback_url
    return str(info.get("webpage_url") or info.get("original_url") or fallback_url)


def playable_url_from_info(info: dict[str, Any], fallback_url: str) -> str:
    adapter = adapter_from_info(info, fallback_url)
    return registry.call(adapter, "playable_url_from_info", info, fallback_url)


def adapter_from_info(info: dict[str, Any], fallback_url: str = ""):
    return registry.resolve_info(info, fallback_url)


def adapter_from_url(url: str):
    return registry.resolve(url)


def thumbnail_from_info(adapter: Any, info: dict[str, Any], playable_url: str = "") -> str:
    thumbnail = registry.default_callable(adapter, "thumbnail_from_info")
    try:
        return thumbnail(info, playable_url)
    except TypeError:
        return thumbnail(info)


def url_is_known_leaf(url: str) -> bool:
    adapter = registry.resolve(url)
    if registry.is_generic(adapter):
        return False
    plan = adapter.metadata_plan_for_config_url(url)
    return plan.node_kind == NodeKind.LEAF_VOD or plan.strategy == MetadataStrategy.SINGLE_YTDLP


def clean_title(value: str) -> str:
    return text.display_title(value)


def display_remarks_from_info(info: dict[str, Any]) -> str:
    return str(
        info.get("dashbox_unavailable_reason")
        or info.get("duration_string")
        or duration_text(info.get("duration"))
        or info.get("uploader")
        or ""
    )


def content_from_info(info: dict[str, Any]) -> str:
    value = str(
        info.get("description")
        or info.get("desc")
        or info.get("synopsis")
        or info.get("summary")
        or ""
    )
    return normalize_content(value)


def normalize_content(value: str) -> str:
    return "\u00a0".join(value.replace("\u00a0", " ").replace("\u3000", " ").split())
