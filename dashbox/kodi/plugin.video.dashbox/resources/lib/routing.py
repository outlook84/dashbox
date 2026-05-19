from __future__ import annotations


DIRECTORY_SELECTED_URL = "__dashbox_directory__"


def display_items(
    page: dict,
    *,
    include_controls: bool = False,
    include_refresh: bool = False,
    labels: dict[str, str] | None = None,
) -> list[dict]:
    items = [item for item in page.get("items") or [] if isinstance(item, dict)]
    labels = labels or {}
    display = content_items(items, labels)
    display = [localized_item(item, labels) for item in display]
    if include_refresh and page.get("id") and page.get("refreshable") is True:
        display = [refresh_item(page, labels), *display]
    if include_controls:
        display = display + control_items(labels)
    return display


def content_items(items: list[dict], labels: dict[str, str]) -> list[dict]:
    if len(items) != 1:
        return items
    item = items[0]
    episodes = [episode for episode in item.get("episodes") or [] if isinstance(episode, dict)]
    if not episodes:
        return items
    return [
        play_directory_item(item, labels, len(episodes)),
        *[episode_item(item, episode, index) for index, episode in enumerate(episodes, 1)],
    ]


def refresh_item(page: dict, labels: dict[str, str]) -> dict:
    refresh = page.get("refresh") if isinstance(page.get("refresh"), dict) else {}
    icons = page.get("icons") if isinstance(page.get("icons"), dict) else {}
    icon = str(icons.get("refresh") or "")
    subtitle = labels.get("refresh_rejected") if refresh.get("rejected") is True else str(page.get("title") or "")
    if not subtitle:
        subtitle = labels.get("current_directory") or ""
    item = {
        "id": str(page.get("id") or ""),
        "title": labels.get("refresh_directory") or "",
        "kind": "refresh",
        "subtitle": subtitle,
        "is_folder": True,
        "is_playable": False,
    }
    if icon:
        item["art"] = {"thumb": icon, "icon": icon}
    return item


def localized_item(item: dict, labels: dict[str, str]) -> dict:
    if item.get("selected_url") != DIRECTORY_SELECTED_URL:
        return item
    title = labels.get("play_directory") or ""
    return {
        **item,
        "title": title,
        "info": {**(item.get("info") or {}), "title": title},
    }


def control_items(labels: dict[str, str]) -> list[dict]:
    return [
        {
            "id": "__dashbox_settings__",
            "title": labels.get("settings") or "",
            "kind": "settings",
            "is_folder": False,
            "is_playable": False,
            "plugin_action": "settings",
        },
    ]


def episode_item(parent: dict, episode: dict, index: int) -> dict:
    title = str(episode.get("title") or "Episode {}".format(index))
    url = str(episode.get("url") or "")
    return {
        "id": url,
        "title": title,
        "kind": "video",
        "subtitle": str(parent.get("title") or ""),
        "summary": str(parent.get("summary") or ""),
        "art": parent.get("art") or {},
        "info": {**(parent.get("info") or {}), "title": title},
        "is_folder": False,
        "is_playable": bool(url),
        "play_url": url,
    }


def play_directory_item(parent: dict, labels: dict[str, str], episode_count: int) -> dict:
    title = labels.get("play_directory") or ""
    return {
        "id": str(parent.get("id") or ""),
        "title": title,
        "kind": "playlist",
        "subtitle": str(parent.get("title") or ""),
        "summary": str(parent.get("summary") or ""),
        "art": parent.get("art") or {},
        "info": {**(parent.get("info") or {}), "title": title},
        "is_folder": False,
        "is_playable": True,
        "selected_url": DIRECTORY_SELECTED_URL,
        "play_url": "",
        "episodes": [],
        "episode_count": episode_count,
    }
