from __future__ import annotations

from typing import Any

from .. import i18n
from ..config import Config, VodStyle
from ..core import client_selection
from ..core import image_proxy
from ..core import media_mapper
from ..core.client_model import ClientItem
from ..models import MediaEpisode
from . import client_text
from . import tvbox_text
from .tvbox_models import Vod

CLIENT_DETAIL_DIRECTORY = "directory"
CLIENT_DETAIL_PLAYLIST = "playlist"
ICON_BASE_URL = ""
FALLBACK_ICONS = {
    "folder": "/assets/icons/folder.png",
    "playlist": "/assets/icons/playlist.png",
    "search": "/assets/icons/search.png",
    "video": "/assets/icons/video.png",
}
DEFAULT_VOD_STYLE = "list"
VOD_STYLE_SPECS = {
    "list": {"type": "list", "ratio": 1.0},
    "landscape": {"type": "rect", "ratio": 1.78, "land": 1},
    "portrait": {"type": "rect", "ratio": 0.56},
}


def set_icon_base_url(base_url: str) -> None:
    global ICON_BASE_URL
    ICON_BASE_URL = base_url.rstrip("/")


def icon_url(kind: str) -> str:
    path = FALLBACK_ICONS[kind]
    return f"{ICON_BASE_URL}{path}" if ICON_BASE_URL else path


def fallback_pic(kind: str, thumbnail: str = "") -> str:
    if thumbnail:
        return thumbnail
    if kind == "folder":
        return icon_url("folder")
    if kind == "playlist":
        return icon_url("playlist")
    if kind == "search":
        return icon_url("search")
    return icon_url("video")


def normalize_vod_style(value: str | VodStyle) -> str:
    return value if value in VOD_STYLE_SPECS else DEFAULT_VOD_STYLE


def vod_style_fields(value: str | VodStyle) -> dict[str, Any]:
    spec = VOD_STYLE_SPECS[normalize_vod_style(value)]
    style = {
        "type": spec["type"],
        "ratio": spec["ratio"],
    }
    fields: dict[str, Any] = {
        "style": style,
        "ratio": spec["ratio"],
    }
    if spec.get("land"):
        fields["land"] = spec["land"]
    return fields


def type_flag_for_vod_style(value: str | VodStyle) -> str:
    return "1" if normalize_vod_style(value) == VodStyle.LIST else "2"


def decorate_vod_style(vod: dict[str, Any], value: str | VodStyle) -> dict[str, Any]:
    return {**vod, **vod_style_fields(value)}


def decorate_page_style(page: dict[str, Any], value: str | VodStyle) -> dict[str, Any]:
    out = {**page, **vod_style_fields(value)}
    items = out.get("list")
    if isinstance(items, list):
        out["list"] = [decorate_vod_style(item, value) if isinstance(item, dict) else item for item in items]
    return out


def image_upstream_urls_from_page(page: Any, config: Config) -> list[str]:
    if not isinstance(page, dict):
        return []
    urls = []
    for item in page.get("list") or []:
        if not isinstance(item, dict):
            continue
        url = image_proxy.image_upstream_from_proxy_url(str(item.get("vod_pic") or ""), config)
        if url:
            urls.append(url)
    return urls


def vod_from_client_item(item: ClientItem) -> dict[str, Any]:
    icon_kind = "playlist" if item.kind == "playlist" else item.kind
    if item.kind == "error":
        icon_kind = "video"
    is_play_directory = item.selected_url == client_selection.SELECTION_DIRECTORY_SELECTED_URL
    remarks = client_text.subtitle(item)
    vod = Vod(
        vod_id=item.id,
        vod_name=clean_title(i18n.tvbox_play_directory() if is_play_directory and not item.title else item.title),
        vod_pic=fallback_pic(icon_kind, item.art.thumb),
        vod_remarks=remarks,
        vod_content=item.summary,
        type_flag="1" if item.is_folder else "",
        vod_tag="folder" if item.is_folder else "",
    ).to_dict()
    if item.playlist_title:
        vod["dashbox_playlist_item"] = "1"
        vod["dashbox_playlist_name"] = item.playlist_title
    if item.selected_url and item.selected_url != client_selection.SELECTION_DIRECTORY_SELECTED_URL:
        vod["dashbox_playlist_item"] = "1"
        vod["dashbox_playlist_url"] = item.selected_url
    if item.selected_url:
        vod["dashbox_client_detail"] = (
            CLIENT_DETAIL_DIRECTORY
            if item.selected_url == client_selection.SELECTION_DIRECTORY_SELECTED_URL
            else CLIENT_DETAIL_PLAYLIST
        )
    if item.selected_key:
        vod["dashbox_playlist_key"] = item.selected_key
    if item.index:
        vod["dashbox_index"] = item.index
    if item.play_url:
        vod["vod_play_from"] = "yt-dlp"
        vod["vod_play_url"] = f"{clean_title(item.title or i18n.play())}${tvbox_text.safe_play_value(item.play_url)}"
    if item.episodes:
        episode_lines = playlist_play_url_from_episodes(item.episodes)
        if not item.selected_url:
            vod["vod_play_from"] = "yt-dlp"
            vod["vod_play_url"] = episode_lines
        elif item.selected_url == client_selection.SELECTION_DIRECTORY_SELECTED_URL:
            vod["vod_play_from"] = i18n.tvbox_current_directory()
            vod["vod_play_url"] = episode_lines
        else:
            selected_title = clean_title(str(item.playlist_title or item.title or i18n.play()))
            selected_episode = f"{selected_title}${tvbox_text.safe_play_value(item.selected_url)}"
            vod["vod_play_from"] = i18n.tvbox_play_current_directory()
            vod["vod_play_url"] = selected_episode + "$$$" + episode_lines
    vod.update(dict(item.extras))
    return vod


def clean_title(value: str) -> str:
    return tvbox_text.safe_title(value)


def unavailable_vod(vod_id: str, title: str = "", remarks: str = "") -> dict[str, Any]:
    return Vod(vod_id, title or vod_id, vod_remarks=remarks or i18n.unavailable()).to_dict()


def rewrite_first_episode_title(play_url: str, title: str) -> str:
    first, separator, rest = play_url.partition("#")
    _name, marker, url = first.partition("$")
    if not marker:
        return play_url
    return f"{clean_title(title)}${url}{separator}{rest}"


def with_playlist_metadata_detail(vods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {**vod, "dashbox_use_playlist_metadata": "1"} if vod.get("dashbox_playlist_item") else vod
        for vod in vods
    ]


def playlist_episode(entry: dict[str, Any], index: int, fallback_url: str = "") -> str:
    episode = media_mapper.playlist_episode(entry, index, fallback_url)
    if not episode:
        return ""
    title = clean_title(str(episode.title or i18n.play()))
    url = str(episode.url or "")
    if not url:
        return ""
    return f"{title}${tvbox_text.safe_play_value(url)}"


def playlist_play_url_from_episodes(episodes: Any) -> str:
    if not isinstance(episodes, (list, tuple)):
        return ""
    return "#".join(
        episode
        for episode in (playlist_episode_from_mapping(item) for item in episodes)
        if episode
    )


def playlist_episode_from_mapping(item: Any) -> str:
    if isinstance(item, MediaEpisode):
        title = clean_title(str(item.title or i18n.play()))
        url = str(item.url or "")
        if not url:
            return ""
        return f"{title}${tvbox_text.safe_play_value(url)}"
    item_title = getattr(item, "title", None)
    item_url = getattr(item, "url", None)
    if item_title is not None or item_url is not None:
        title = clean_title(str(item_title or i18n.play()))
        url = str(item_url or "")
        if not url:
            return ""
        return f"{title}${tvbox_text.safe_play_value(url)}"
    if not isinstance(item, dict):
        return ""
    title = clean_title(str(item.get("title") or i18n.play()))
    url = str(item.get("url") or "")
    if not url:
        return ""
    return f"{title}${tvbox_text.safe_play_value(url)}"


def with_episode_index(url: str, index: int) -> str:
    return media_mapper.with_episode_index(url, index)
