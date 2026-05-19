from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal


class NodeKind(StrEnum):
    CONFIG_DIRECTORY = "config_directory"
    COLLECTION_DIRECTORY = "collection_directory"
    PLAYLIST_DIRECTORY = "playlist_directory"
    AGGREGATE_VOD = "aggregate_vod"
    LEAF_VOD = "leaf_vod"


MediaNodeKind = Literal["video", "folder", "playlist", "search"]


@dataclass(frozen=True)
class MediaEpisode:
    title: str
    url: str


@dataclass(frozen=True)
class MediaNode:
    id: str
    title: str
    kind: MediaNodeKind = "video"
    thumbnail: str = ""
    remarks: str = ""
    remarks_key: str = ""
    item_count: int = 0
    part_count: int = 0
    content: str = ""
    play_from: str = ""
    play_url: str = ""
    playlist_name: str = ""
    playlist_url: str = ""
    episodes: tuple[MediaEpisode, ...] = ()
    node_kind: str = ""
    extras: dict[str, Any] = field(default_factory=dict)
