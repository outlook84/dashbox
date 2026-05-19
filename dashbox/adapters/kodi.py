from __future__ import annotations

from dataclasses import asdict, is_dataclass, replace
from typing import Any

from ..config import Config, ImageProxyMode
from . import client_text
from .. import i18n
from ..core import image_policy
from ..core import image_proxy
from ..core.client_model import ClientArt, ClientItem, ClientPage, ClientPlay

API_VERSION = 2
FALLBACK_ICONS = {
    "folder": "/assets/icons/folder.png",
    "playlist": "/assets/icons/playlist.png",
    "refresh": "/assets/icons/refresh.png",
    "search": "/assets/icons/search.png",
    "video": "/assets/icons/video.png",
}


def page_to_dict(page: ClientPage, config: Config, base_url: str = "") -> dict[str, Any]:
    return {
        "version": API_VERSION,
        "id": page.id,
        "title": page.title,
        "content_type": page.content_type,
        "items": [item_to_dict(item, config, base_url) for item in page.items],
        "total_items": page.total_items,
        "cache_to_disc": page.cache_to_disc,
        "update_listing": page.update_listing,
        "refreshable": page.refreshable,
        "refresh": value_to_dict(page.refresh) if page.refresh is not None else None,
        "icons": {"refresh": fallback_icon_url("refresh", base_url)},
        "labels": kodi_labels(),
    }


def play_to_dict(play: ClientPlay) -> dict[str, Any]:
    return {"version": API_VERSION, **value_to_dict(play)}


def item_to_dict(item: ClientItem, config: Config, base_url: str = "") -> dict[str, Any]:
    art = item_art(item, config, base_url)
    display_item = replace(
        item,
        subtitle=client_text.subtitle(item),
        art=art,
    )
    return value_to_dict(display_item)


def kodi_labels() -> dict[str, str]:
    return {
        "play_directory": i18n.tvbox_play_directory(),
        "refresh_directory": i18n.text("tvbox.refresh_directory"),
        "current_directory": i18n.tvbox_current_directory(),
        "refresh_rejected": i18n.text("tvbox.refresh_rejected"),
    }


def item_art(item: ClientItem, config: Config, base_url: str = "") -> ClientArt:
    art = proxied_art(item.art, config, base_url)
    if art.thumb:
        return replace(art, icon=art.icon or art.thumb)

    icon = fallback_icon_url(item.kind, base_url)
    return replace(art, thumb=icon, poster=icon, icon=icon)


def fallback_icon_url(kind: str, base_url: str = "") -> str:
    icon_kind = "playlist" if kind == "playlist" else kind
    if icon_kind not in FALLBACK_ICONS:
        icon_kind = "video"
    path = FALLBACK_ICONS[icon_kind]
    return f"{base_url.rstrip('/')}{path}" if base_url else path


def proxied_art(art: ClientArt, config: Config, base_url: str = "") -> ClientArt:
    if not art.thumb or config.image_proxy_mode == ImageProxyMode.OFF:
        return art
    thumb = image_policy.proxied_thumbnail_url(art.thumb, base_url, config.image_proxy_mode)
    return replace(
        art,
        thumb=thumb,
        poster=thumb if art.poster == art.thumb else art.poster,
        icon=thumb if art.icon == art.thumb else art.icon,
        fanart=thumb if art.fanart == art.thumb else art.fanart,
        landscape=thumb if art.landscape == art.thumb else art.landscape,
    )


def image_upstream_urls_from_page(page: Any, config: Config) -> list[str]:
    if not isinstance(page, dict):
        return []
    urls: list[str] = []
    for item in page.get("items") or []:
        if not isinstance(item, dict):
            continue
        art = item.get("art")
        if not isinstance(art, dict):
            continue
        for value in art.values():
            url = image_proxy.image_upstream_from_proxy_url(str(value or ""), config)
            if url:
                urls.append(url)
    return urls


def value_to_dict(value: Any) -> Any:
    if is_dataclass(value):
        return value_to_dict(asdict(value))
    if isinstance(value, dict):
        return {str(key): value_to_dict(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [value_to_dict(item) for item in value]
    return value
