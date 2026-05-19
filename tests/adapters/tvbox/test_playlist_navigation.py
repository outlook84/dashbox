import asyncio

import pytest

from dashbox.config import (
    Config,
    Source,
    UrlItem,
)
from dashbox.adapters import tvbox
from dashbox.core import client_selection
from dashbox.core.client_service import DirectorySnapshot
from dashbox.models import MediaNode
from dashbox.core.navigation_resolver import ResolvedCategory
from tests.helpers import (
    config_item_id,
    disable_playable_prewarm,
    make_tvbox_service as MediaService,
    patch_metadata_for_plan,
)
from dashbox.sites import xvideos


@pytest.mark.parametrize(
    ("playlist_url", "title"),
    (
        ("https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000", "Discover the World"),
        ("https://music.youtube.com/playlist?list=PL0000000000000000000000000000000000", "Music Playlist"),
    ),
)
def test_youtube_playlist_url_category_entry_is_folder(monkeypatch, playlist_url: str, title: str) -> None:
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem(playlist_url),
        )),
    ))
    async def fake_playlist_light_metadata(raw_id: str) -> dict:
        return {
            "webpage_url": raw_id,
            "title": title,
            "playlist_count": 12,
        }

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata)

    value = asyncio.run(service.category("main"))

    vod = value["list"][0]
    assert vod["vod_name"] == title
    assert vod["vod_remarks"] == "12项"
    assert vod["type_flag"] == "1"
    assert vod["vod_tag"] == "folder"


def test_playlist_url_category_returns_aggregate_items(monkeypatch) -> None:
    playlist_url = "https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000"
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem(playlist_url),
        )),
    ))
    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        assert url == playlist_url
        assert playlist is True
        assert flat is True
        return {
            "_type": "playlist",
            "title": "Discover the World",
            "entries": [
                {
                    "webpage_url": "https://www.youtube.com/watch?v=111",
                    "title": "First",
                    "thumbnail": "https://example.test/first.jpg",
                },
                {
                    "webpage_url": "https://www.youtube.com/watch?v=222",
                    "title": "Second",
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    value = asyncio.run(service.category(config_item_id(service, "main", 0)))

    assert value["dashbox_category_name"] == "Discover the World"
    directory, first, second = value["list"]
    assert directory["vod_id"].startswith(client_selection.SELECTION_ID_PREFIX)
    assert directory["vod_name"] == "播放此列表"
    assert directory["vod_pic"] == tvbox.icon_url("playlist")
    assert directory["vod_remarks"] == "2项"
    assert directory["dashbox_client_detail"] == "directory"
    assert first["vod_id"].startswith(client_selection.SELECTION_ID_PREFIX)
    assert first["vod_name"] == "First"
    assert first["dashbox_playlist_item"] == "1"
    assert first["dashbox_playlist_name"] == "First"
    assert first["dashbox_playlist_url"] == "https://www.youtube.com/watch?v=111&dashbox_index=1"
    assert first["dashbox_client_detail"] == "playlist"
    assert second["dashbox_playlist_url"] == "https://www.youtube.com/watch?v=222&dashbox_index=2"
    assert second["dashbox_client_detail"] == "playlist"
    assert second["vod_pic"] == tvbox.icon_url("video")
def test_bilibili_favorites_config_entry_is_folder(monkeypatch) -> None:
    favlist_url = "https://space.bilibili.com/123/favlist?fid=456"
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem(favlist_url),
        )),
    ))
    async def fake_favorites_light_metadata(raw_url: str) -> dict:
        assert raw_url == favlist_url
        return {
            "title": "收藏夹",
            "thumbnail": "https://i0.hdslb.com/bfs/fav.jpg",
        }

    async def fail_favorites_metadata(raw_url: str) -> dict:
        raise AssertionError("configured favorite entry should not enumerate entries")

    monkeypatch.setattr(service.site_runtime.bilibili.site, "favorites_light_metadata", fake_favorites_light_metadata)
    monkeypatch.setattr(service.site_runtime.bilibili.site, "favorites_metadata", fail_favorites_metadata)

    value = asyncio.run(service.category("main"))

    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "main", 0)
    assert vod["vod_name"] == "收藏夹"
    assert vod["vod_remarks"] == "收藏夹"
    assert vod["type_flag"] == "1"
    assert vod["vod_tag"] == "folder"


def test_bilibili_medialist_config_entry_uses_light_metadata(monkeypatch) -> None:
    medialist_url = "https://www.bilibili.com/list/ml123"
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem(medialist_url, title="配置标题"),
        )),
    ))
    async def fake_medialist_light_metadata(raw_url: str) -> dict:
        assert raw_url == medialist_url
        return {
            "title": "远程标题",
            "thumbnail": "https://i0.hdslb.com/bfs/list.jpg",
        }

    async def fail_medialist_metadata(raw_url: str) -> dict:
        raise AssertionError("configured medialist entry should not enumerate entries")

    monkeypatch.setattr(service.site_runtime.bilibili.site, "medialist_light_metadata", fake_medialist_light_metadata)
    monkeypatch.setattr(service.site_runtime.bilibili.site, "medialist_metadata", fail_medialist_metadata)

    value = asyncio.run(service.category("main"))

    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "main", 0)
    assert vod["vod_name"] == "配置标题"
    assert vod["vod_pic"] == "https://i0.hdslb.com/bfs/list.jpg"
    assert vod["vod_remarks"] == "播放列表"
    assert vod["type_flag"] == "1"
    assert vod["vod_tag"] == "folder"


def test_bilibili_multi_p_config_entry_is_aggregate_vod(monkeypatch) -> None:
    video_url = "https://www.bilibili.com/video/BV1wx411w7pe"
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem(video_url),
        )),
    ))
    async def fake_video_metadata(raw_url: str) -> dict:
        assert raw_url == video_url
        return {
            "title": "样例合集",
            "pic": "https://i0.hdslb.com/bfs/video.jpg",
            "pages": [
                {"page": 1, "part": "上"},
                {"page": 2, "part": "下"},
            ],
        }

    monkeypatch.setattr(service.site_runtime.bilibili.site, "video_metadata", fake_video_metadata)

    value = asyncio.run(service.category("main"))

    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "main", 0)
    assert vod["vod_name"] == "样例合集"
    assert vod["vod_remarks"] == "2P"
    assert "type_flag" not in vod
    assert "vod_tag" not in vod
def test_playlist_item_detail_puts_selected_url_first(monkeypatch) -> None:
    playlist_url = "https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000"
    selected_url = "https://www.youtube.com/watch?v=9bZkp7q19f0&dashbox_index=2"
    service = MediaService(Config())

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False, require_playable: bool = False):
        if url == playlist_url:
            assert playlist is True
            assert flat is True
            assert require_playable is False
            return {
                "_type": "playlist",
                "webpage_url": playlist_url,
                "title": "Discover the World",
                "entries": [
                    {
                        "webpage_url": "https://www.youtube.com/watch?v=AbCdEfGh123",
                        "title": "First",
                    },
                    {
                        "webpage_url": "https://www.youtube.com/watch?v=9bZkp7q19f0",
                        "title": "Second",
                    },
                ],
            }
        assert url == "https://www.youtube.com/watch?v=9bZkp7q19f0"
        assert playlist is False
        assert flat is False
        assert require_playable is True
        return {
            "webpage_url": url,
            "title": "Second Full",
            "thumbnail": "https://example.test/second.jpg",
            "description": "Second\ndescription",
            "formats": [{"url": "https://cdn.example.test/second.mp4", "vcodec": "avc1", "acodec": "mp4a", "ext": "mp4"}],
        }

    async def fake_light_metadata(raw_id: str) -> dict:
        assert raw_id == "https://www.youtube.com/watch?v=9bZkp7q19f0"
        return {
            "webpage_url": raw_id,
            "title": "Second Light",
            "thumbnail": "https://example.test/second-light.jpg",
            "description": "Second light description",
        }

    monkeypatch.setattr(service, "extract", fake_extract)
    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)

    raw_id = client_selection.encode_selection_id(playlist_url, selected_url)
    value = asyncio.run(service.detail(raw_id))

    vod = value["list"][0]
    assert vod["vod_name"] == "Second Light"
    assert vod["vod_pic"] == "https://example.test/second-light.jpg"
    assert vod["vod_content"] == "Second\u00a0light\u00a0description"
    assert vod["vod_remarks"] == "Second"
    assert vod["vod_play_from"] == "点击播放$$$当前目录"
    selected, directory = vod["vod_play_url"].split("$$$")
    assert selected == "Second$https://www.youtube.com/watch?v=9bZkp7q19f0&dashbox_index=2"
    assert directory == (
        "First$https://www.youtube.com/watch?v=AbCdEfGh123&dashbox_index=1#"
        "Second$https://www.youtube.com/watch?v=9bZkp7q19f0&dashbox_index=2"
    )


def test_playlist_directory_detail_only_returns_directory_line(monkeypatch) -> None:
    playlist_url = "https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000"
    service = MediaService(Config())

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        assert url == playlist_url
        assert playlist is True
        assert flat is True
        return {
            "_type": "playlist",
            "webpage_url": playlist_url,
            "entries": [
                {
                    "webpage_url": "https://www.youtube.com/watch?v=111",
                    "title": "First",
                },
                {
                    "webpage_url": "https://www.youtube.com/watch?v=222",
                    "title": "Second",
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    raw_id = client_selection.encode_selection_id(playlist_url, client_selection.SELECTION_DIRECTORY_SELECTED_URL)
    value = asyncio.run(service.detail(raw_id))

    vod = value["list"][0]
    assert vod["vod_pic"] == tvbox.icon_url("playlist")
    assert vod["vod_play_from"] == "当前目录"
    assert vod["vod_play_url"] == (
        "First$https://www.youtube.com/watch?v=111&dashbox_index=1#"
        "Second$https://www.youtube.com/watch?v=222&dashbox_index=2"
    )


def test_playlist_directory_vod_uses_shared_item_content(monkeypatch) -> None:
    playlist_url = "https://www.twitch.tv/samplechannel/videos?filter=all"
    service = MediaService(Config())

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        assert url == playlist_url
        return {
            "_type": "playlist",
            "webpage_url": playlist_url,
            "entries": [
                {
                    "webpage_url": "https://www.twitch.tv/videos/111",
                    "title": "First",
                    "description": "Shared description",
                },
                {
                    "webpage_url": "https://www.twitch.tv/videos/222",
                    "title": "Second",
                    "description": "Shared description",
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    category = asyncio.run(service.category(playlist_url))
    raw_id = client_selection.encode_selection_id(playlist_url, client_selection.SELECTION_DIRECTORY_SELECTED_URL)
    detail = asyncio.run(service.detail(raw_id))

    assert category["list"][0]["vod_content"] == "Shared\u00a0description"
    assert detail["list"][0]["vod_content"] == "Shared\u00a0description"


def test_xvideos_favorite_category_uses_site_parser(monkeypatch) -> None:
    playlist_url = "https://www.xvideos.com/favorite/91000002/_"
    service = MediaService(Config())

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        raise AssertionError("xvideos favorite category should not run full yt-dlp extraction")

    async def fake_site_api_info(url: str, method_name: str) -> dict:
        assert url == playlist_url
        assert method_name == "site_api_category_info"
        return {
            "title": "To watch later",
            "webpage_url": playlist_url,
            "entries": [
                {
                    "webpage_url": "https://www.xvideos.com/video.one/first",
                    "title": "First",
                    "thumbnail": "https://example.test/one.jpg",
                },
                {
                    "webpage_url": "https://www.xvideos.com/video.two/second",
                    "title": "Second",
                    "thumbnail": "https://example.test/two.jpg",
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)
    monkeypatch.setattr(service, "site_api_info", fake_site_api_info)

    value = asyncio.run(service.category(playlist_url))

    directory, first, second = value["list"]
    assert value["dashbox_category_name"] == "To watch later"
    assert directory["vod_pic"] == tvbox.icon_url("playlist")
    assert first["vod_id"].startswith(client_selection.SELECTION_ID_PREFIX)
    assert first["dashbox_playlist_url"] == "https://www.xvideos.com/video.one/first?dashbox_index=1"
    assert second["dashbox_playlist_url"] == "https://www.xvideos.com/video.two/second?dashbox_index=2"


def test_xvideos_favorite_config_entry_is_light_folder(monkeypatch) -> None:
    playlist_url = "https://www.xvideos.com/favorite/91000002/_"
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem(playlist_url),
        )),
    ))
    def fail_favorite_playlist_info(*args, **kwargs):
        raise AssertionError("configured xvideos favorite entry should not enumerate entries")

    monkeypatch.setattr(xvideos, "favorite_playlist_info", fail_favorite_playlist_info)

    value = asyncio.run(service.category("main"))

    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "main", 0)
    assert vod["vod_name"] == "91000002/_"
    assert vod["vod_pic"] == tvbox.icon_url("playlist")
    assert vod["vod_remarks"] == "播放列表"
    assert vod["type_flag"] == "1"
    assert vod["vod_tag"] == "folder"
def test_xvideos_favorite_playlist_detail_uses_site_parser(monkeypatch) -> None:
    playlist_url = "https://www.xvideos.com/favorite/91000002/_"
    selected_url = "https://www.xvideos.com/video.two/second?dashbox_index=2"
    service = MediaService(Config())

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        raise AssertionError("xvideos favorite detail should not run full yt-dlp extraction")

    async def fake_site_api_info(url: str, method_name: str) -> dict:
        assert url == playlist_url
        assert method_name == "site_api_category_info"
        return {
            "title": "To watch later",
            "webpage_url": playlist_url,
            "entries": [
                {"webpage_url": "https://www.xvideos.com/video.one/first", "title": "First"},
                {"webpage_url": "https://www.xvideos.com/video.two/second", "title": "Second"},
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)
    monkeypatch.setattr(service, "site_api_info", fake_site_api_info)

    raw_id = client_selection.encode_selection_id(playlist_url, selected_url)
    value = asyncio.run(service.detail(raw_id))

    vod = value["list"][0]
    assert vod["vod_name"] == "Second"
    assert vod["vod_play_from"] == "点击播放$$$当前目录"
    selected, directory = vod["vod_play_url"].split("$$$")
    assert selected == "Second$https://www.xvideos.com/video.two/second?dashbox_index=2"
    assert directory == (
        "First$https://www.xvideos.com/video.one/first?dashbox_index=1#"
        "Second$https://www.xvideos.com/video.two/second?dashbox_index=2"
    )


def test_spankbang_playlist_detail_uses_site_playlist_info(monkeypatch) -> None:
    playlist_url = "https://spankbang.com/pl002/playlist/sample+collection"
    selected_url = "https://spankbang.com/pl002-item003/playlist/sample+collection?dashbox_index=1"
    service = MediaService(Config())

    def fake_extract(*args, **kwargs):
        raise AssertionError("spankbang playlist item detail should not use generic yt-dlp flat extraction")

    async def fake_site_api_info(url: str, method_name: str) -> dict:
        assert url == playlist_url
        assert method_name == "site_api_category_info"
        return {
            "extractor_key": "SpankBangPlaylist",
            "title": "Layla Jenner",
            "webpage_url": url,
            "entries": [
                {
                    "_type": "url",
                    "ie_key": "SpankBang",
                    "id": "item003",
                    "url": "https://spankbang.com/pl002-item003/playlist/sample+collection",
                    "webpage_url": "https://spankbang.com/pl002-item003/playlist/sample+collection",
                    "title": "First",
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)
    monkeypatch.setattr(service, "site_api_info", fake_site_api_info)

    raw_id = client_selection.encode_selection_id(playlist_url, selected_url)
    value = asyncio.run(service.detail(raw_id))

    vod = value["list"][0]
    assert vod["vod_name"] == "First"
    selected, directory = vod["vod_play_url"].split("$$$")
    assert selected == "First$https://spankbang.com/pl002-item003/playlist/sample+collection?dashbox_index=1"
    assert directory == "First$https://spankbang.com/pl002-item003/playlist/sample+collection?dashbox_index=1"


def test_twitch_playlist_item_detail_uses_directory_metadata(monkeypatch) -> None:
    playlist_url = "https://www.twitch.tv/samplechannel/videos?filter=all"
    selected_url = "https://www.twitch.tv/videos/100000001?dashbox_index=1"
    service = MediaService(Config())
    prewarms = []

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        assert url == playlist_url
        return {
            "_type": "playlist",
            "title": "Sample Channel - All Videos",
            "webpage_url": playlist_url,
            "entries": [
                {
                    "_type": "url",
                    "ie_key": "TwitchVod",
                    "url": "https://www.twitch.tv/videos/100000001",
                    "webpage_url": "https://www.twitch.tv/videos/100000001",
                    "title": "Twitch Item Title",
                    "thumbnail": "https://static-cdn.jtvnw.net/cf_vods/thumb.jpg",
                    "description": "Twitch item description",
                },
            ],
        }

    async def fail_single_video_detail(raw_id: str, base_url: str = "") -> dict:
        raise AssertionError("Twitch playlist item should use directory metadata")

    monkeypatch.setattr(service, "extract", fake_extract)
    monkeypatch.setattr(service, "single_video_detail", fail_single_video_detail)
    monkeypatch.setattr(service, "start_single_video_playable_prewarm", lambda clean_id, extract_url="": prewarms.append((clean_id, extract_url)))

    value = asyncio.run(service.playlist_item_detail(playlist_url, selected_url))

    assert prewarms == [("https://www.twitch.tv/videos/100000001", "")]
    vod = value["list"][0]
    assert vod["vod_name"] == "Twitch Item Title"
    assert vod["vod_pic"] == "https://static-cdn.jtvnw.net/cf_vods/thumb.jpg"
    assert vod["vod_content"] == "Twitch\u00a0item\u00a0description"
    selected, _directory = vod["vod_play_url"].split("$$$")
    assert selected == "Twitch Item Title$https://www.twitch.tv/videos/100000001?dashbox_index=1"


def test_twitch_category_then_item_detail_reuses_cached_directory_metadata(monkeypatch) -> None:
    playlist_url = "https://www.twitch.tv/samplechannel/videos?filter=all"
    service = MediaService(Config())
    calls = []

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        calls.append(url)
        assert url == playlist_url
        return {
            "_type": "playlist",
            "title": "Sample Channel - All Videos",
            "webpage_url": playlist_url,
            "entries": [
                {
                    "_type": "url",
                    "ie_key": "TwitchVod",
                    "url": "https://www.twitch.tv/videos/100000001",
                    "webpage_url": "https://www.twitch.tv/videos/100000001",
                    "title": "Twitch Item Title",
                    "thumbnail": "https://static-cdn.jtvnw.net/cf_vods/thumb.jpg",
                    "description": "Cached Twitch item description",
                },
            ],
        }

    async def fail_single_video_detail(raw_id: str, base_url: str = "") -> dict:
        raise AssertionError("Twitch playlist item should use cached directory metadata")

    monkeypatch.setattr(service, "extract", fake_extract)
    monkeypatch.setattr(service, "single_video_detail", fail_single_video_detail)
    disable_playable_prewarm(monkeypatch, service)

    category = asyncio.run(service.category(playlist_url))
    item_id = category["list"][1]["vod_id"]
    detail = asyncio.run(service.detail(item_id))

    assert calls == [playlist_url]
    assert category["list"][1]["dashbox_use_playlist_metadata"] == "1"
    vod = detail["list"][0]
    assert vod["vod_name"] == "Twitch Item Title"
    assert vod["vod_pic"] == "https://static-cdn.jtvnw.net/cf_vods/thumb.jpg"
    assert vod["vod_content"] == "Cached\u00a0Twitch\u00a0item\u00a0description"


def test_directory_snapshot_cache_shares_concurrent_loads(monkeypatch) -> None:
    playlist_url = "https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000"
    service = MediaService(Config())
    calls = []

    async def fake_load(url: str, *, force_refresh: bool = False, fallback=None) -> DirectorySnapshot:
        calls.append((url, force_refresh, fallback))
        await asyncio.sleep(0.01)
        return DirectorySnapshot(
            ResolvedCategory([MediaNode("https://example.test/one", "One")], "Directory"),
            stored_at=1.0,
        )

    monkeypatch.setattr(service, "load_directory_snapshot", fake_load)

    async def run() -> tuple[DirectorySnapshot, DirectorySnapshot]:
        first = asyncio.create_task(service.directory_snapshot(playlist_url))
        second = asyncio.create_task(service.directory_snapshot(playlist_url))
        return await first, await second

    first, second = asyncio.run(run())

    assert first is second
    assert calls == [(playlist_url, True, None)]


def test_refresh_shares_inflight_directory_reload(monkeypatch) -> None:
    playlist_url = "https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000"
    service = MediaService(Config())
    started = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def fake_load(url: str, *, force_refresh: bool = False, fallback=None) -> DirectorySnapshot:
        calls.append((url, force_refresh, fallback))
        started.set()
        await release.wait()
        return DirectorySnapshot(
            ResolvedCategory([MediaNode("https://example.test/one", "One")], "Directory"),
            stored_at=1.0,
        )

    monkeypatch.setattr(service, "load_directory_snapshot", fake_load)

    async def run() -> tuple[DirectorySnapshot, DirectorySnapshot]:
        normal = asyncio.create_task(service.directory_snapshot(playlist_url))
        await started.wait()
        refreshed = asyncio.create_task(service.directory_snapshot(playlist_url, refresh=True))
        release.set()
        return await normal, await refreshed

    normal, refreshed = asyncio.run(run())

    assert normal is refreshed
    assert calls == [(playlist_url, True, None)]


def test_refresh_bypasses_flat_playlist_cache(monkeypatch) -> None:
    playlist_url = "https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000"
    service = MediaService(Config())
    titles = ["Old", "Fresh"]
    calls = []

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        calls.append(url)
        title = titles[min(len(calls) - 1, len(titles) - 1)]
        return {
            "_type": "playlist",
            "title": "Directory",
            "webpage_url": playlist_url,
            "entries": [
                {
                    "webpage_url": f"https://www.youtube.com/watch?v={title.lower()}",
                    "title": title,
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    first = asyncio.run(service.category(playlist_url))
    refreshed = asyncio.run(service.category(playlist_url, refresh=True))

    assert calls == [playlist_url, playlist_url]
    assert first["list"][1]["vod_name"] == "Old"
    assert refreshed["list"][1]["vod_name"] == "Fresh"
    assert refreshed["dashbox_refresh"]["requested"] is True
    assert refreshed["dashbox_refresh"]["refreshed"] is True
    assert refreshed["dashbox_refresh"]["rejected"] is False


def test_refresh_bypasses_light_collection_metadata_cache(monkeypatch) -> None:
    playlist_url = "https://music.youtube.com/channel/UC123456789"
    service = MediaService(Config())
    calls = []

    async def fake_playlist_light_metadata(raw_id: str, *, force_refresh: bool = False) -> dict:
        calls.append((raw_id, force_refresh))
        return {
            "webpage_url": raw_id,
            "title": raw_id.rsplit("/", 1)[-1],
            "playlist_count": 2,
        }

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata)

    asyncio.run(service.category(playlist_url))
    asyncio.run(service.category(playlist_url, refresh=True))

    assert calls == [
        (playlist_url, True),
        (f"{playlist_url}/videos", True),
        (f"{playlist_url}/playlists", True),
        (playlist_url, True),
        (f"{playlist_url}/videos", True),
        (f"{playlist_url}/playlists", True),
    ]


def test_refresh_cooldown_returns_existing_directory_snapshot(monkeypatch) -> None:
    playlist_url = "https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000"
    service = MediaService(Config())
    titles = ["Old", "Fresh", "Too Soon"]
    calls = []

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        calls.append(url)
        title = titles[min(len(calls) - 1, len(titles) - 1)]
        return {
            "_type": "playlist",
            "title": "Directory",
            "webpage_url": playlist_url,
            "entries": [
                {
                    "webpage_url": f"https://www.youtube.com/watch?v={title.lower().replace(' ', '-')}",
                    "title": title,
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    asyncio.run(service.category(playlist_url))
    refreshed = asyncio.run(service.category(playlist_url, refresh=True))
    cooled_down = asyncio.run(service.category(playlist_url, refresh=True))

    assert calls == [playlist_url, playlist_url]
    assert refreshed["list"][1]["vod_name"] == "Fresh"
    assert cooled_down["list"][1]["vod_name"] == "Fresh"
    assert cooled_down["dashbox_refresh"]["rejected"] is True
    assert cooled_down["dashbox_refresh"]["refreshed"] is False


def test_refresh_cooldown_without_snapshot_builds_normal_directory(monkeypatch) -> None:
    playlist_url = "https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000"
    service = MediaService(Config())
    service.directory_refresh_cooldown.try_acquire(service.directory_snapshot_cache_key(playlist_url))
    calls = []

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        calls.append(url)
        return {
            "_type": "playlist",
            "title": "Directory",
            "webpage_url": playlist_url,
            "entries": [
                {
                    "webpage_url": "https://www.youtube.com/watch?v=normal",
                    "title": "Normal Load",
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    value = asyncio.run(service.category(playlist_url, refresh=True))

    assert calls == [playlist_url]
    assert value["list"][1]["vod_name"] == "Normal Load"
    assert value["dashbox_refresh"]["requested"] is True
    assert value["dashbox_refresh"]["rejected"] is True
    assert value["dashbox_refresh"]["refreshed"] is False


def test_twitch_collections_category_entries_are_folders(monkeypatch) -> None:
    playlist_url = "https://www.twitch.tv/samplecollection/videos?filter=collections"
    service = MediaService(Config())

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        assert url == playlist_url
        assert playlist is True
        assert flat is True
        return {
            "_type": "playlist",
            "title": "Sample Collection - Collections",
            "webpage_url": playlist_url,
            "entries": [
                {
                    "_type": "url_transparent",
                    "ie_key": "TwitchCollection",
                    "url": "https://www.twitch.tv/collections/abc",
                    "webpage_url": "https://www.twitch.tv/collections/abc",
                    "title": "Collection A",
                    "thumbnail": "https://static-cdn.jtvnw.net/cf_vods/abc.jpg",
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    value = asyncio.run(service.category(playlist_url))

    vod = value["list"][0]
    assert value["dashbox_category_name"] == "Sample Collection - Collections"
    assert vod["vod_id"] == "https://www.twitch.tv/collections/abc"
    assert vod["vod_name"] == "Collection A"
    assert vod["type_flag"] == "1"
    assert vod["vod_tag"] == "folder"
    assert "dashbox_playlist_item" not in vod
    assert "dashbox_client_detail" not in vod


def test_youtube_channel_root_config_id_category_returns_tab_vods(monkeypatch) -> None:
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem("https://www.youtube.com/@Sample_Channel"),
        )),
    ))
    def fake_extract(
        url: str,
        *,
        download: bool,
        playlist: bool,
        flat: bool = False,
        flat_playlist_items: str = "",
    ):
        assert url == "https://www.youtube.com/@Sample_Channel"
        assert playlist is True
        assert flat is True
        assert flat_playlist_items == "1-4"
        return {
            "_type": "playlist",
            "title": "Sample Channel",
            "entries": [
                {
                    "_type": "url",
                    "ie_key": "YoutubeTab",
                    "url": "https://www.youtube.com/@Sample_Channel/videos",
                    "title": "Sample Channel - Videos",
                    "uploader": "Sample Channel",
                },
                {
                    "_type": "url",
                    "ie_key": "YoutubeTab",
                    "url": "https://www.youtube.com/@Sample_Channel/shorts",
                    "title": "Sample Channel - Shorts",
                    "uploader": "Sample Channel",
                },
            ],
        }

    async def fake_playlist_light_metadata(raw_id: str) -> dict:
        raise AssertionError("synthetic playlists tab should not fetch metadata until opened")

    monkeypatch.setattr(service, "extract", fake_extract)
    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata, fallback=False)

    value = asyncio.run(service.category(config_item_id(service, "main", 0)))

    first, second, third = value["list"]
    assert len(value["list"]) == 3
    assert first["vod_id"] == "https://www.youtube.com/@Sample_Channel/videos"
    assert first["vod_name"] == "Sample Channel - Videos"
    assert first["vod_remarks"] == "Sample Channel"
    assert first["type_flag"] == "1"
    assert first["vod_tag"] == "folder"
    assert second["vod_id"] == "https://www.youtube.com/@Sample_Channel/shorts"
    assert second["vod_name"] == "Sample Channel - Shorts"
    assert second["vod_remarks"] == "Sample Channel"
    assert second["type_flag"] == "1"
    assert second["vod_tag"] == "folder"
    assert third["vod_id"] == "https://www.youtube.com/@Sample_Channel/playlists"
    assert third["vod_name"] == "Sample Channel - Playlists"
    assert third["vod_remarks"] == "播放列表"
    assert third["type_flag"] == "1"
    assert third["vod_tag"] == "folder"
def test_url_category_returns_unavailable_vod_when_extraction_fails(monkeypatch) -> None:
    service = MediaService(Config())

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        raise RuntimeError("tab missing")

    monkeypatch.setattr(service, "extract", fake_extract)

    value = asyncio.run(service.category("https://www.youtube.com/@Sample_Channel/streams"))

    vod = value["list"][0]
    assert vod["vod_id"] == "https://www.youtube.com/@Sample_Channel/streams"
    assert vod["vod_remarks"] == "不可用"


def test_detail_returns_unavailable_vod_when_extraction_fails(monkeypatch) -> None:
    service = MediaService(Config())

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        raise RuntimeError("tab missing")

    async def fake_light_metadata(raw_id: str) -> dict:
        return {}

    monkeypatch.setattr(service, "extract", fake_extract)
    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)

    value = asyncio.run(service.detail("https://www.youtube.com/@Sample_Channel/streams"))

    vod = value["list"][0]
    assert vod["vod_id"] == "https://www.youtube.com/@Sample_Channel/streams"
    assert vod["vod_remarks"] == "不可用"
