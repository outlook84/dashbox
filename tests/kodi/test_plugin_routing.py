import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ROUTING_PATH = ROOT / "dashbox" / "kodi" / "plugin.video.dashbox" / "resources" / "lib" / "routing.py"


spec = importlib.util.spec_from_file_location("dashbox_kodi_plugin_routing", ROUTING_PATH)
assert spec is not None and spec.loader is not None
routing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(routing)


def test_display_items_expands_single_playlist_item_episodes() -> None:
    page = {
        "items": [
            {
                "id": "https://media.example.test/bv1",
                "title": "样例合集",
                "kind": "playlist",
                "summary": "简介",
                "art": {"thumb": "https://example.test/thumb.jpg"},
                "info": {"title": "样例合集", "plot": "简介"},
                "episodes": [
                    {"title": "P01 上", "url": "https://media.example.test/bv1?p=1"},
                    {"title": "P02 下", "url": "https://media.example.test/bv1?p=2"},
                ],
            },
        ],
    }

    items = routing.display_items(page, labels={"play_directory": "Play all"})

    assert [item["title"] for item in items] == ["Play all", "P01 上", "P02 下"]
    assert items[0]["id"] == "https://media.example.test/bv1"
    assert items[0]["selected_url"] == "__dashbox_directory__"
    assert items[0]["is_playable"] is True
    assert [item["play_url"] for item in items[1:]] == [
        "https://media.example.test/bv1?p=1",
        "https://media.example.test/bv1?p=2",
    ]
    assert all(item["is_playable"] for item in items[1:])
    assert items[1]["subtitle"] == "样例合集"
    assert items[1]["art"]["thumb"] == "https://example.test/thumb.jpg"


def test_display_items_uses_localized_play_directory_label() -> None:
    page = {
        "items": [
            {
                "id": "https://media.example.test/bv1",
                "title": "样例合集",
                "episodes": [{"title": "P01 上", "url": "https://media.example.test/bv1?p=1"}],
            },
        ],
    }

    items = routing.display_items(page, labels={"play_directory": "播放此列表"})

    assert items[0]["title"] == "播放此列表"
    assert items[0]["info"]["title"] == "播放此列表"


def test_display_items_localizes_server_play_directory_item() -> None:
    page = {
        "items": [
            {
                "id": "selection-id",
                "title": "",
                "kind": "playlist",
                "selected_url": "__dashbox_directory__",
                "info": {"title": ""},
            },
            {"id": "video", "title": "Video"},
        ],
    }

    items = routing.display_items(page, labels={"play_directory": "播放此列表"})

    assert items[0]["title"] == "播放此列表"
    assert items[0]["info"]["title"] == "播放此列表"


def test_display_items_keeps_mixed_pages_collapsed() -> None:
    page = {
        "items": [
            {"id": "folder", "title": "Folder", "is_folder": True},
            {"id": "playlist", "title": "Playlist", "episodes": [{"title": "One", "url": "https://example.test/1"}]},
        ],
    }

    assert routing.display_items(page) == page["items"]


def test_display_items_can_append_plugin_controls() -> None:
    page = {"items": [{"id": "main", "title": "Main", "is_folder": True}]}

    items = routing.display_items(
        page,
        include_controls=True,
        labels={"settings": "设置"},
    )

    assert items[0]["id"] == "main"
    assert [item["plugin_action"] for item in items[1:]] == ["settings"]
    assert [item["title"] for item in items[1:]] == ["设置"]


def test_display_items_can_prepend_refresh_control() -> None:
    page = {
        "id": "folder",
        "refreshable": True,
        "icons": {"refresh": "http://testserver/assets/icons/refresh.png"},
        "items": [
            {
                "id": "https://media.example.test/bv1",
                "title": "样例合集",
                "episodes": [{"title": "P01 上", "url": "https://media.example.test/bv1?p=1"}],
            },
        ],
    }

    items = routing.display_items(
        page,
        include_refresh=True,
        labels={"play_directory": "播放此列表", "refresh_directory": "刷新此列表", "current_directory": "当前目录"},
    )

    assert items[0] == {
        "id": "folder",
        "title": "刷新此列表",
        "kind": "refresh",
        "subtitle": "当前目录",
        "is_folder": True,
        "is_playable": False,
        "art": {
            "thumb": "http://testserver/assets/icons/refresh.png",
            "icon": "http://testserver/assets/icons/refresh.png",
        },
    }
    assert [item["title"] for item in items[1:]] == ["播放此列表", "P01 上"]


def test_display_items_requires_server_play_directory_label() -> None:
    page = {
        "items": [
            {
                "id": "https://media.example.test/bv1",
                "title": "样例合集",
                "episodes": [{"title": "P01 上", "url": "https://media.example.test/bv1?p=1"}],
            },
        ],
    }

    items = routing.display_items(page)

    assert items[0]["title"] == ""
    assert items[0]["info"]["title"] == ""


def test_display_items_refresh_control_uses_page_title_and_rejected_status() -> None:
    page = {
        "id": "folder",
        "refreshable": True,
        "title": "Remote playlist",
        "refresh": {"requested": True, "rejected": True},
        "items": [],
    }

    items = routing.display_items(
        page,
        include_refresh=True,
        labels={"refresh_directory": "刷新此列表", "refresh_rejected": "稍后重试"},
    )

    assert items[0]["title"] == "刷新此列表"
    assert items[0]["subtitle"] == "稍后重试"


def test_display_items_skips_refresh_control_when_page_is_not_refreshable() -> None:
    page = {"id": "folder", "items": [{"id": "main", "title": "Main", "is_folder": True}]}

    items = routing.display_items(page, include_refresh=True, labels={"refresh_directory": "刷新此列表"})

    assert [item["title"] for item in items] == ["Main"]
