from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..models import NodeKind


class MetadataStrategy(Enum):
    DISPLAY = "display"
    SINGLE_YTDLP = "single_ytdlp"
    PLAYLIST_YTDLP = "playlist_ytdlp"
    SITE_API = "site_api"
    NONE = "none"


@dataclass(frozen=True)
class YtdlpMetadataOptions:
    extract_url: str
    noplaylist: bool
    extract_flat: str | bool | None = None
    playlist_items: str | None = None
    process: bool = True


@dataclass(frozen=True)
class SiteMetadataPlan:
    node_kind: NodeKind
    strategy: MetadataStrategy
    canonical_url: str | None = None
    ytdlp: YtdlpMetadataOptions | None = None
    reason: str = ""
