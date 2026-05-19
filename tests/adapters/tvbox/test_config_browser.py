import asyncio

import pytest

from dashbox.config import (
    Config,
    FolderItem,
    Source,
    UrlItem,
)
from dashbox.adapters import tvbox
from dashbox.core import image_policy
from dashbox.sites.types import MetadataStrategy
from tests.helpers import config_item_id, make_tvbox_service as MediaService, nested_config_item_id, patch_metadata_for_plan


def test_category_shows_folders_as_folders_and_urls_as_content(monkeypatch) -> None:
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem("https://www.youtube.com/watch?v=AbCdEfGh123", title="Override", remarks="Pinned"),
            FolderItem("Folder", (UrlItem("https://example.test/folder-video"),)),
        )),
    ))
    async def fake_light_metadata(raw_id: str) -> dict:
        return {
            "webpage_url": raw_id,
            "title": "Remote title",
            "thumbnail": "https://example.test/thumb.jpg",
        }

    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)

    value = asyncio.run(service.category("main"))

    assert value["dashbox_category_name"] == "Main"
    first, second = value["list"]
    assert first["vod_id"] == config_item_id(service, "main", 0)
    assert first["vod_name"] == "Override"
    assert first["vod_remarks"] == "Pinned"
    assert "vod_tag" not in first
    assert second["vod_id"] == config_item_id(service, "main", 1)
    assert second["vod_name"] == "Folder"
    assert second["vod_pic"] == tvbox.icon_url("folder")
    assert second["vod_tag"] == "folder"


def test_generic_url_item_detail_reuses_config_probe_metadata(monkeypatch) -> None:
    url = "https://example.test/watch/1"
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem(url, title="Manual title"),
        )),
    ))
    playlist_calls = []
    display_calls = []

    original_metadata_for_plan = service.metadata.metadata_for_plan

    async def fake_metadata_for_plan(raw_id: str, plan, *, force_refresh: bool = False) -> dict:
        if plan.strategy == MetadataStrategy.PLAYLIST_YTDLP:
            playlist_calls.append(raw_id)
            assert raw_id == url
            return {}
        return await original_metadata_for_plan(raw_id, plan, force_refresh=force_refresh)

    async def fake_fetch_display_metadata(raw_id: str) -> dict:
        display_calls.append(raw_id)
        assert raw_id == url
        return {
            "webpage_url": raw_id,
            "title": "Remote title",
            "thumbnail": "https://example.test/thumb.jpg",
        }

    async def fake_extract_flat_playlist_info(
        raw_url: str,
        extract_url: str = "",
        flat_playlist_items: str = "",
    ) -> dict:
        raise AssertionError("generic config leaf detail should reuse config metadata instead of flat playlist probing")

    monkeypatch.setattr(service.metadata, "metadata_for_plan", fake_metadata_for_plan)
    monkeypatch.setattr(service.metadata, "fetch_display_metadata", fake_fetch_display_metadata)
    monkeypatch.setattr(service, "extract_flat_playlist_info", fake_extract_flat_playlist_info)

    item_id = config_item_id(service, "main", 0)
    category_value = asyncio.run(service.category("main"))
    detail_value = asyncio.run(service.detail(item_id))

    assert playlist_calls == [url]
    assert display_calls == [url]
    assert category_value["list"][0]["vod_name"] == "Manual title"
    vod = detail_value["list"][0]
    assert vod["vod_name"] == "Manual title"
    assert vod["vod_pic"] == "https://example.test/thumb.jpg"
    assert vod["vod_play_url"] == f"Manual title${url}"
def test_home_classes_use_subscription_vod_style() -> None:
    service = MediaService(Config(), sources=(
        Source("main", "Main", ()),
    ))

    value = service.home()

    assert value["class"][0]["style"] == {"type": "list", "ratio": 1.0}
    assert value["class"][0]["ratio"] == 1.0
    assert value["class"][0]["type_flag"] == "1"
def test_category_uses_subscription_vod_style(monkeypatch) -> None:
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem("https://www.youtube.com/watch?v=AbCdEfGh123"),
        )),
    ), vod_style="landscape")

    async def fake_light_metadata(raw_id: str) -> dict:
        return {"webpage_url": raw_id, "title": "Video"}

    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)

    value = asyncio.run(service.category("main"))

    assert value["style"] == {"type": "rect", "ratio": 1.78}
    assert value["land"] == 1
    assert value["list"][0]["style"] == {"type": "rect", "ratio": 1.78}
    assert value["list"][0]["land"] == 1
def test_folder_category_uses_nested_config_ids(monkeypatch) -> None:
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            FolderItem("Folder", (UrlItem("https://www.youtube.com/watch?v=AbCdEfGh123"),)),
        )),
    ))
    async def fake_light_metadata(raw_id: str) -> dict:
        return {"webpage_url": raw_id, "title": "Nested title"}

    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)

    value = asyncio.run(service.category(config_item_id(service, "main", 0)))

    assert value["dashbox_category_name"] == "Folder"
    vod = value["list"][0]
    assert vod["vod_id"] == nested_config_item_id(service, "main", 0, 0)
    assert vod["vod_name"] == "Nested title"


def test_category_uses_light_playlist_metadata_before_detail(monkeypatch) -> None:
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem("https://www.youtube.com/@Sample_Channel/videos"),
        )),
    ))
    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        raise AssertionError("category should not enumerate long configured URLs")

    monkeypatch.setattr(service, "extract", fake_extract)
    async def fake_playlist_light_metadata(raw_id: str) -> dict:
        assert raw_id == "https://www.youtube.com/@Sample_Channel/videos"
        return {
            "webpage_url": raw_id,
            "title": "Sample Channel",
            "playlist_count": 699,
            "thumbnail": "https://example.test/channel.jpg",
        }

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata)

    value = asyncio.run(service.category("main"))

    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "main", 0)
    assert vod["vod_name"] == "Sample Channel"
    assert vod["vod_remarks"] == "699项"
    assert vod["vod_pic"] == "https://example.test/channel.jpg"


def test_generic_config_url_with_probe_entries_is_folder(monkeypatch) -> None:
    url = "https://www.dailymotion.com/playlist/xsample001"
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem(url),
        )),
    ))

    async def fake_playlist_light_metadata(raw_id: str) -> dict:
        assert raw_id == url
        return {
            "webpage_url": raw_id,
            "entries": [
                {
                    "webpage_url": "https://www.dailymotion.com/video/xsample002",
                    "title": "First",
                },
            ],
        }

    async def fake_light_metadata(raw_id: str) -> dict:
        raise AssertionError("generic playlist config should not probe single-video metadata")

    async def fake_display_metadata(raw_id: str) -> dict:
        assert raw_id == url
        return {
            "webpage_url": raw_id,
            "title": "Dailymotion playlist HTML",
            "thumbnail": "https://example.test/dailymotion.jpg",
        }

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata, single=fake_light_metadata, fallback=False)
    monkeypatch.setattr(service.metadata, "display_metadata", fake_display_metadata)

    value = asyncio.run(service.category("main"))

    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "main", 0)
    assert vod["vod_name"] == "Dailymotion playlist HTML"
    assert vod["vod_pic"] == "https://example.test/dailymotion.jpg"
    assert vod["vod_remarks"] == "播放列表"
    assert vod["type_flag"] == "1"
    assert vod["vod_tag"] == "folder"


def test_category_marks_unavailable_config_url_when_light_metadata_fails(monkeypatch) -> None:
    url = "https://example.test/unknown"
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem(url),
        )),
    ))
    async def fake_playlist_light_metadata(raw_id: str) -> dict:
        assert raw_id == url
        return {}

    async def fake_light_metadata(raw_id: str) -> dict:
        raise AssertionError("unknown config URL should not run a second yt-dlp light metadata fetch")

    async def fake_display_metadata(raw_id: str) -> dict:
        assert raw_id == url
        return {}

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata, single=fake_light_metadata, fallback=False)
    monkeypatch.setattr(service.metadata, "display_metadata", fake_display_metadata)
    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)

    value = asyncio.run(service.category("main"))

    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "main", 0)
    assert vod["vod_name"] == url
    assert vod["vod_remarks"] == "点击进入详情"
    assert "type_flag" not in vod
    assert "vod_tag" not in vod


def test_spankbang_playlist_config_is_folder_when_light_metadata_fails(monkeypatch) -> None:
    url = "https://spankbang.com/pl002/playlist/sample+collection"
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem(url, title="Layla Jenner"),
        )),
    ))
    async def fake_playlist_light_metadata(raw_id: str) -> dict:
        assert raw_id == url
        return {}

    async def fake_light_metadata(raw_id: str) -> dict:
        raise AssertionError("playlist fallback should not probe single light metadata")

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata, single=fake_light_metadata, fallback=False)

    value = asyncio.run(service.category("main"))

    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "main", 0)
    assert vod["vod_name"] == "Layla Jenner"
    assert vod["vod_remarks"] == "点击进入"
    assert vod["type_flag"] == "1"
    assert vod["vod_tag"] == "folder"


def test_pornhub_collection_config_uses_url_title_when_light_metadata_has_no_title(monkeypatch) -> None:
    url = "https://www.pornhub.com/video/search?search=sample+query"
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem(url),
        )),
    ))
    async def fake_playlist_light_metadata(raw_id: str) -> dict:
        assert raw_id == url
        return {
            "webpage_url": raw_id,
            "id": "video/search",
            "entries": [],
        }

    async def fake_light_metadata(raw_id: str) -> dict:
        raise AssertionError("Pornhub collection should not probe single light metadata")

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata, single=fake_light_metadata, fallback=False)

    value = asyncio.run(service.category("main"))

    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "main", 0)
    assert vod["vod_name"] == "Pornhub 搜索: sample query"
    assert vod["vod_pic"] == tvbox.icon_url("search")
    assert vod["type_flag"] == "1"
    assert vod["vod_tag"] == "folder"


def test_unknown_config_url_uses_html_metadata_when_probe_is_empty(monkeypatch) -> None:
    url = "https://www.tnaflix.com/amateur-porn/Eva-Green-Breasts%2C-Butt-Scene-in-The-Dreamers/video9944644"
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem(url),
        )),
    ))
    async def fake_playlist_light_metadata(raw_id: str) -> dict:
        assert raw_id == url
        return {}

    async def fake_display_metadata(raw_id: str) -> dict:
        assert raw_id == url
        return {
            "webpage_url": raw_id,
            "title": "Eva Green Scene",
            "thumbnail": "https://example.test/thumb.jpg",
            "duration_string": "1:23",
        }

    async def fake_light_metadata(raw_id: str) -> dict:
        raise AssertionError("unknown config URL should not run a second yt-dlp light metadata fetch")

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata, single=fake_light_metadata, fallback=False)
    monkeypatch.setattr(service.metadata, "display_metadata", fake_display_metadata)

    value = asyncio.run(service.category("main"))

    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "main", 0)
    assert vod["vod_name"] == "Eva Green Scene"
    assert vod["vod_remarks"] == "1:23"
    assert "type_flag" not in vod
    assert "vod_tag" not in vod


@pytest.mark.parametrize(
    ("mode", "thumbnail", "expected_prefix"),
    (
        ("known", "https://img.example.test/videos/thumb.jpg", "http://testserver/image?"),
        ("all", "https://example.test/thumb.jpg", "http://testserver/image?"),
        ("off", "https://img.example.test/videos/thumb.jpg", "https://img.example.test/videos/thumb.jpg"),
    ),
)
def test_image_proxy_mode_controls_config_metadata_thumbnails(
    monkeypatch,
    mode: str,
    thumbnail: str,
    expected_prefix: str,
) -> None:
    url = "https://www.tnaflix.com/amateur-porn/example/video1"
    monkeypatch.setattr(
        image_policy.registry,
        "image_url_is_proxyable",
        lambda value: value == "https://img.example.test/videos/thumb.jpg",
    )
    service = MediaService(Config(image_proxy_mode=mode), sources=(
        Source("main", "Main", (
            UrlItem(url),
        )),
    ))

    async def fake_playlist_light_metadata(raw_id: str) -> dict:
        assert raw_id == url
        return {}

    async def fake_display_metadata(raw_id: str) -> dict:
        assert raw_id == url
        return {
            "webpage_url": raw_id,
            "title": "Example",
            "thumbnail": thumbnail,
        }

    async def fake_light_metadata(raw_id: str) -> dict:
        raise AssertionError("unknown config URL should not run a second yt-dlp light metadata fetch")

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata, single=fake_light_metadata, fallback=False)
    monkeypatch.setattr(service.metadata, "display_metadata", fake_display_metadata)
    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)

    value = asyncio.run(service.category("main", base_url="http://testserver"))

    vod_pic = value["list"][0]["vod_pic"]
    assert vod_pic.startswith(expected_prefix)
    if mode == "off":
        assert "/image?" not in vod_pic


def test_image_proxy_mode_controls_search_thumbnails(monkeypatch) -> None:
    service = MediaService(Config(image_proxy_mode="all"))

    def fake_extract(url: str, **kwargs) -> dict:
        return {
            "entries": [
                {
                    "webpage_url": "https://example.test/video",
                    "title": "Search result",
                    "thumbnail": "https://example.test/search.jpg",
                }
            ]
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    value = asyncio.run(service.search("fallback", base_url="http://testserver"))

    assert value["list"][0]["vod_pic"].startswith("http://testserver/image?")


def test_image_proxy_mode_controls_detail_thumbnails(monkeypatch) -> None:
    raw_id = "https://example.test/video"
    service = MediaService(Config(image_proxy_mode="all"))

    def fake_extract(url: str, **kwargs) -> dict:
        assert url == raw_id
        return {
            "webpage_url": raw_id,
            "title": "Detail result",
            "thumbnail": "https://example.test/detail.jpg",
        }

    async def fake_light_metadata(url: str) -> dict:
        assert url == raw_id
        return {}

    monkeypatch.setattr(service, "extract", fake_extract)
    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)

    value = asyncio.run(service.detail(raw_id, base_url="http://testserver"))

    assert value["list"][0]["vod_pic"].startswith("http://testserver/image?")


def test_unknown_config_playlist_url_waits_for_light_probe_and_marks_folder(monkeypatch) -> None:
    url = "https://example.test/playlist"
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem(url),
        )),
    ))
    async def fake_playlist_light_metadata(raw_id: str) -> dict:
        assert raw_id == url
        return {
            "webpage_url": raw_id,
            "title": "Example Playlist",
            "thumbnail": "https://example.test/thumb.jpg",
            "playlist_count": 12,
        }

    async def fake_light_metadata(raw_id: str) -> dict:
        raise AssertionError("playlist probe should classify the unknown URL before single metadata")

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata, single=fake_light_metadata, fallback=False)

    value = asyncio.run(service.category("main"))

    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "main", 0)
    assert vod["vod_name"] == "Example Playlist"
    assert vod["vod_pic"] == "https://example.test/thumb.jpg"
    assert vod["vod_remarks"] == "12项"
    assert vod["type_flag"] == "1"
    assert vod["vod_tag"] == "folder"


