from __future__ import annotations

from .. import i18n
from ..core.client_model import ClientItem


def subtitle(item: ClientItem) -> str:
    if item.subtitle:
        return item.subtitle
    key = item.subtitle_key
    if key == "item_count":
        return i18n.item_count(item.item_count)
    if key == "part_count":
        return i18n.part_count(item.part_count) if item.part_count else ""
    if key == "playlist":
        return i18n.playlist()
    if key == "search":
        return i18n.search()
    if key == "enter":
        return i18n.enter()
    if key == "enter_detail":
        return i18n.enter_detail()
    if key == "unavailable":
        return i18n.unavailable()
    if key == "bilibili_bangumi":
        return i18n.bilibili_bangumi()
    if key == "bilibili_collection":
        return i18n.bilibili_collection()
    if key == "bilibili_course":
        return i18n.bilibili_course()
    if key == "bilibili_audio":
        return i18n.bilibili_audio()
    if key == "bilibili_favorites":
        return i18n.bilibili_favorites()
    if key == "bilibili_series":
        return i18n.bilibili_series()
    if key == "bilibili_songlist":
        return i18n.bilibili_songlist()
    if key == "bilibili_watch_later":
        return i18n.bilibili_watch_later()
    return ""
