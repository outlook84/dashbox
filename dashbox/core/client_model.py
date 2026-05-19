from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal, Mapping

from ..models import MediaNode

ClientItemKind = Literal["video", "folder", "playlist", "search", "error"]
ClientContentType = Literal["videos", "files"]
ClientActionKind = Literal["open", "detail", "play", "refresh", "search"]


@dataclass(frozen=True)
class ClientArt:
    thumb: str = ""
    poster: str = ""
    fanart: str = ""
    icon: str = ""
    banner: str = ""
    landscape: str = ""


@dataclass(frozen=True)
class ClientMediaInfo:
    title: str = ""
    plot: str = ""
    plot_outline: str = ""
    duration: int = 0
    year: int = 0
    media_type: str = "video"


@dataclass(frozen=True)
class ClientAction:
    kind: ClientActionKind
    id: str = ""
    endpoint: str = ""
    refresh: bool = False


@dataclass(frozen=True)
class ClientEpisode:
    title: str
    url: str


@dataclass(frozen=True)
class ClientItem:
    id: str
    title: str
    kind: ClientItemKind = "video"
    subtitle: str = ""
    summary: str = ""
    art: ClientArt = ClientArt()
    info: ClientMediaInfo = ClientMediaInfo()
    is_folder: bool = False
    is_playable: bool = False
    playlist_url: str = ""
    playlist_title: str = ""
    selected_url: str = ""
    selected_key: str = ""
    play_url: str = ""
    episodes: tuple[ClientEpisode, ...] = ()
    index: int = 0
    actions: tuple[ClientAction, ...] = ()
    node_kind: str = ""
    subtitle_key: str = ""
    item_count: int = 0
    part_count: int = 0
    extras: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ClientPage:
    id: str = ""
    title: str = ""
    content_type: ClientContentType = "videos"
    items: tuple[ClientItem, ...] = ()
    total_items: int = 0
    cache_to_disc: bool = False
    update_listing: bool = False
    refreshable: bool = False
    refresh: Any | None = None


@dataclass(frozen=True)
class ClientSubtitle:
    url: str
    name: str = ""
    language: str = ""
    format: str = ""


@dataclass(frozen=True)
class ClientInputStream:
    addon: str = ""
    manifest_type: str = ""
    manifest_headers: Mapping[str, str] = field(default_factory=dict)
    stream_headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ClientPlay:
    url: str
    title: str = ""
    mime_type: str = ""
    headers: Mapping[str, str] = field(default_factory=dict)
    subtitles: tuple[ClientSubtitle, ...] = ()
    art: ClientArt = ClientArt()
    info: ClientMediaInfo = ClientMediaInfo()
    inputstream: ClientInputStream | None = None
    content_lookup: bool | None = None
    danmaku_url: str = ""


def art_from_thumbnail(thumbnail: str) -> ClientArt:
    if not thumbnail:
        return ClientArt()
    return ClientArt(thumb=thumbnail, poster=thumbnail, icon=thumbnail)


def item_from_media_node(node: MediaNode, *, is_folder: bool | None = None, is_playable: bool | None = None) -> ClientItem:
    folder = node.kind in {"folder", "search"} if is_folder is None else is_folder
    playable = False if is_playable is None else is_playable
    actions: list[ClientAction] = []
    if folder:
        actions.append(ClientAction("open", id=node.id, endpoint="items"))
    if playable:
        actions.append(ClientAction("play", id=node.id, endpoint="play"))
    if node.kind == "search":
        actions.append(ClientAction("search", id=node.id, endpoint="search"))
    return ClientItem(
        id=node.id,
        title=node.title,
        kind=node.kind,
        node_kind=node.node_kind,
        subtitle=node.remarks,
        subtitle_key=node.remarks_key,
        item_count=node.item_count,
        part_count=node.part_count,
        summary=node.content,
        art=art_from_thumbnail(node.thumbnail),
        info=ClientMediaInfo(title=node.title, plot=node.content),
        is_folder=folder,
        is_playable=playable,
        selected_url=node.playlist_url,
        playlist_title=node.playlist_name,
        play_url=node.play_url,
        episodes=tuple(ClientEpisode(episode.title, episode.url) for episode in node.episodes),
        actions=tuple(actions),
        extras=dict(node.extras),
    )


def with_item_overrides(
    item: ClientItem,
    *,
    item_id: str = "",
    title: str = "",
    thumbnail: str = "",
    subtitle: str = "",
) -> ClientItem:
    return replace(
        item,
        id=item_id or item.id,
        title=title or item.title,
        subtitle=subtitle or item.subtitle,
        art=art_from_thumbnail(thumbnail) if thumbnail else item.art,
        info=replace(item.info, title=title or item.info.title),
    )


def page_from_media_nodes(
    nodes: list[MediaNode] | tuple[MediaNode, ...],
    *,
    page_id: str = "",
    title: str = "",
    directory_node_ids: tuple[str, ...] = (),
    refresh: Any | None = None,
    refreshable: bool = False,
) -> ClientPage:
    directory_ids = set(directory_node_ids)
    items = tuple(
        item_from_media_node(node, is_folder=True if node.id in directory_ids else None)
        for node in nodes
    )
    return ClientPage(
        id=page_id,
        title=title,
        items=items,
        total_items=len(items),
        refreshable=refreshable,
        refresh=refresh,
    )
