import asyncio


from dashbox.config import (
    Config,
    Source,
    UrlItem,
)
from dashbox.adapters import tvbox
from dashbox.core import client_selection
from dashbox.core import media_mapper
from dashbox.core.client_model import item_from_media_node
from tests.helpers import (
    config_item_id,
    disable_playable_prewarm,
    make_tvbox_service as MediaService,
    patch_metadata_for_plan,
)
from dashbox.sites import youtube


def test_config_url_detail_applies_title_override(monkeypatch) -> None:
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem("https://www.youtube.com/watch?v=AbCdEfGh123", title="Override title"),
        )),
    ))
    async def fake_light_metadata(raw_id: str) -> dict:
        return {"webpage_url": raw_id, "title": "Remote title"}

    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)
    disable_playable_prewarm(monkeypatch, service)
    async def fail_flat_extract(*args, **kwargs):
        raise AssertionError("configured leaf detail should use light single-video detail")

    monkeypatch.setattr(service, "extract_flat_playlist_info_async", fail_flat_extract)

    value = asyncio.run(service.detail(config_item_id(service, "main", 0)))

    vod = value["list"][0]
    assert vod["vod_name"] == "Override title"
    assert vod["vod_play_url"] == "Override title$https://www.youtube.com/watch?v=AbCdEfGh123"


def test_youtube_playlists_tab_detail_returns_multiple_vods(monkeypatch) -> None:
    service = MediaService(Config())

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        assert url == "https://www.youtube.com/@Sample_Channel/playlists"
        assert playlist is True
        assert flat is True
        return {
            "_type": "playlist",
            "title": "Sample Channel - Playlists",
            "entries": [
                {
                    "_type": "url",
                    "ie_key": "YoutubeTab",
                    "id": "PL1111111111111111111111111111111111",
                    "url": "https://www.youtube.com/playlist?list=PL1111111111111111111111111111111111",
                    "title": "First Playlist",
                    "playlist_count": 12,
                },
                {
                    "_type": "url",
                    "ie_key": "YoutubeTab",
                    "id": "PL2222222222222222222222222222222222",
                    "url": "https://www.youtube.com/playlist?list=PL2222222222222222222222222222222222",
                    "title": "Second Playlist",
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)
    async def fake_playlist_light_metadata(raw_id: str) -> dict:
        raise AssertionError("playlist collection entries should render from flat yt-dlp metadata")

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata, fallback=False)

    value = asyncio.run(service.detail("https://www.youtube.com/@Sample_Channel/playlists"))

    first, second = value["list"]
    assert len(value["list"]) == 2
    assert first["vod_id"] == "https://www.youtube.com/playlist?list=PL1111111111111111111111111111111111"
    assert first["vod_name"] == "First Playlist"
    assert first["vod_remarks"] == "12项"
    assert "vod_play_url" not in first
    assert second["vod_id"] == "https://www.youtube.com/playlist?list=PL2222222222222222222222222222222222"
    assert second["vod_name"] == "Second Playlist"
    assert second["vod_remarks"] == "播放列表"


def test_youtube_playlists_tab_category_entry_is_folder(monkeypatch) -> None:
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem("https://www.youtube.com/@Sample_Channel/playlists"),
        )),
    ))
    async def fake_playlist_light_metadata(raw_id: str) -> dict:
        assert raw_id == "https://www.youtube.com/@Sample_Channel/playlists"
        return {
            "webpage_url": raw_id,
            "title": "Sample Channel - Playlists",
            "playlist_count": 22,
        }

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata)

    value = asyncio.run(service.category("main"))

    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "main", 0)
    assert vod["vod_name"] == "Sample Channel - Playlists"
    assert vod["vod_remarks"] == "22项"
    assert vod["type_flag"] == "1"
    assert vod["vod_tag"] == "folder"


def test_youtube_playlists_tab_url_category_returns_playlist_vods(monkeypatch) -> None:
    service = MediaService(Config())

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        assert url == "https://www.youtube.com/@Sample_Channel/playlists"
        assert playlist is True
        assert flat is True
        return {
            "_type": "playlist",
            "title": "Sample Channel - Playlists",
            "entries": [
                {
                    "_type": "url",
                    "ie_key": "YoutubeTab",
                    "url": "https://www.youtube.com/playlist?list=PL1111111111111111111111111111111111",
                    "title": "First Playlist",
                    "playlist_count": 12,
                },
                {
                    "_type": "url",
                    "ie_key": "YoutubeTab",
                    "url": "https://www.youtube.com/playlist?list=PL2222222222222222222222222222222222",
                    "title": "Second Playlist",
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)
    async def fake_playlist_light_metadata(raw_id: str) -> dict:
        raise AssertionError("playlist collection entries should render from flat yt-dlp metadata")

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata, fallback=False)

    value = asyncio.run(service.category("https://www.youtube.com/@Sample_Channel/playlists"))

    first, second = value["list"]
    assert len(value["list"]) == 2
    assert first["vod_id"] == "https://www.youtube.com/playlist?list=PL1111111111111111111111111111111111"
    assert first["vod_name"] == "First Playlist"
    assert first["vod_remarks"] == "12项"
    assert first["dashbox_index"] == 1
    assert second["vod_id"] == "https://www.youtube.com/playlist?list=PL2222222222222222222222222222222222"
    assert second["vod_name"] == "Second Playlist"
    assert second["vod_remarks"] == "播放列表"
    assert second["dashbox_index"] == 2
def test_youtube_channel_root_category_entry_is_folder(monkeypatch) -> None:
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem("https://www.youtube.com/@Sample_Channel"),
        )),
    ))
    async def fake_playlist_light_metadata(raw_id: str) -> dict:
        assert raw_id == "https://www.youtube.com/@Sample_Channel"
        return {
            "webpage_url": raw_id,
            "title": "Sample Channel",
            "playlist_count": 2,
        }

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata)

    value = asyncio.run(service.category("main"))

    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "main", 0)
    assert vod["vod_name"] == "Sample Channel"
    assert vod["vod_remarks"] == "2项"
    assert vod["type_flag"] == "1"
    assert vod["vod_tag"] == "folder"


def test_youtube_search_url_category_entry_is_folder_when_metadata_fails(monkeypatch) -> None:
    search_url = "https://www.youtube.com/results?search_query=%E6%AD%A9%E5%85%B5"
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem(search_url),
        )),
    ))
    async def fake_playlist_light_metadata(raw_id: str) -> dict:
        assert raw_id == search_url
        return {}

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata, fallback=False)

    value = asyncio.run(service.category("main"))

    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "main", 0)
    assert vod["vod_name"] == youtube.search_title_from_url(search_url)
    assert vod["vod_pic"] == tvbox.icon_url("search")
    assert vod["vod_remarks"] == "搜索"
    assert vod["type_flag"] == "1"
    assert vod["vod_tag"] == "folder"
def test_youtube_search_folder_result_uses_search_kind() -> None:
    info = {
        "entries": [
            {
                "_type": "url",
                "ie_key": "YoutubeTab",
                "url": "https://www.youtube.com/results?search_query=lofi",
                "title": "More results",
                "playlist_count": 10,
            }
        ]
    }

    vods = [
        tvbox.vod_from_client_item(item_from_media_node(node))
        for node in media_mapper.search_nodes_from_info(info)
    ]

    assert vods[0]["vod_id"] == "https://www.youtube.com/results?search_query=lofi"
    assert vods[0]["vod_pic"] == tvbox.icon_url("search")
    assert vods[0]["type_flag"] == "1"
    assert vods[0]["vod_tag"] == "folder"


def test_youtube_special_feed_config_entry_is_folder(monkeypatch) -> None:
    url = "https://www.youtube.com/feed/subscriptions"
    service = MediaService(Config(), sources=(
        Source("main", "Main", (
            UrlItem(url),
        )),
    ))
    async def fake_playlist_light_metadata(raw_id: str) -> dict:
        assert raw_id == url
        return {
            "webpage_url": raw_id,
            "title": "subscriptions",
            "playlist_count": 5,
        }

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata)

    value = asyncio.run(service.category("main"))

    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "main", 0)
    assert vod["vod_name"] == "subscriptions"
    assert vod["vod_remarks"] == "5项"
    assert vod["type_flag"] == "1"
    assert vod["vod_tag"] == "folder"
def test_youtube_hashtag_category_returns_video_vods(monkeypatch) -> None:
    url = "https://www.youtube.com/hashtag/sampletag"
    service = MediaService(Config())

    def fake_extract(raw_url: str, *, download: bool, playlist: bool, flat: bool = False):
        assert raw_url == url
        assert playlist is True
        assert flat is True
        return {
            "_type": "playlist",
            "webpage_url": url,
            "title": "sampletag - All",
            "entries": [
                {
                    "_type": "url",
                    "ie_key": "Youtube",
                    "id": "ZzYyXxWw123",
                    "title": "CCTV9 Ident History",
                    "url": "https://www.youtube.com/watch?v=ZzYyXxWw123",
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    value = asyncio.run(service.category(url))

    vod = value["list"][1]
    assert value["dashbox_category_name"] == "sampletag - All"
    assert vod["vod_id"].startswith(client_selection.SELECTION_ID_PREFIX)
    assert vod["vod_name"] == "CCTV9 Ident History"
    assert vod["dashbox_playlist_url"] == "https://www.youtube.com/watch?v=ZzYyXxWw123&dashbox_index=1"
def test_youtube_search_url_category_returns_each_result_as_vod(monkeypatch) -> None:
    search_url = "https://www.youtube.com/results?search_query=%E6%AD%A9%E5%85%B5"
    service = MediaService(Config())

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        assert url == search_url
        assert playlist is True
        assert flat is True
        return {
            "_type": "playlist",
            "title": "歩兵",
            "entries": [
                {
                    "_type": "url",
                    "ie_key": "Youtube",
                    "id": "AbCdEfGh123",
                    "url": "https://www.youtube.com/watch?v=AbCdEfGh123",
                    "title": "Video Result",
                    "duration_string": "3:33",
                },
                {
                    "_type": "url",
                    "ie_key": "YoutubeTab",
                    "url": "https://www.youtube.com/playlist?list=PL1111111111111111111111111111111111",
                    "title": "Playlist Result",
                    "playlist_count": 12,
                },
                {
                    "_type": "url",
                    "ie_key": "YoutubeTab",
                    "url": "https://www.youtube.com/playlist?list=RDsample12345",
                    "title": "Radio Result",
                },
                {
                    "_type": "url",
                    "ie_key": "YoutubeTab",
                    "url": "https://www.youtube.com/@SomeChannel",
                    "title": "Channel Result",
                    "uploader": "Some Channel",
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    value = asyncio.run(service.category(search_url))

    first, second, third = value["list"]
    assert len(value["list"]) == 3
    assert first["vod_id"] == "https://www.youtube.com/watch?v=AbCdEfGh123"
    assert first["vod_name"] == "Video Result"
    assert first["vod_remarks"] == "3:33"
    assert "vod_tag" not in first
    assert second["vod_id"] == "https://www.youtube.com/playlist?list=PL1111111111111111111111111111111111"
    assert second["vod_name"] == "Playlist Result"
    assert second["vod_remarks"] == "12项"
    assert second["vod_tag"] == "folder"
    assert third["vod_id"] == "https://www.youtube.com/@SomeChannel"
    assert third["vod_name"] == "Channel Result"
    assert third["type_flag"] == "1"
    assert all("dashbox_index" not in vod for vod in value["list"])
    assert third["vod_tag"] == "folder"


def test_youtube_search_result_with_id_only_url_maps_to_video_node() -> None:
    info = {
        "_type": "playlist",
        "title": "Search",
        "entries": [
            {
                "_type": "url",
                "ie_key": "Youtube",
                "id": "AbCdEfGh123",
                "url": "AbCdEfGh123",
                "title": "Video Result",
                "duration_string": "3:33",
            },
        ],
    }

    nodes = media_mapper.search_nodes_from_info(info)

    assert len(nodes) == 1
    assert nodes[0].id == "https://www.youtube.com/watch?v=AbCdEfGh123"
    assert nodes[0].title == "Video Result"
    assert nodes[0].remarks == "3:33"
