import asyncio


from dashbox.config import Config, Source, UrlItem
from dashbox.core import client_selection
from dashbox.sites import bilibili
from tests.helpers import config_item_id, make_tvbox_service as MediaService
from tests.sites.bilibili.helpers import FAVLIST_URL


def test_favlist_config_entry_uses_bilibili_favorites_light_metadata(monkeypatch) -> None:
    service = MediaService(Config(), sources=(
        Source("bilibili", "Bilibili", (UrlItem(FAVLIST_URL),)),
    ))
    called = False

    async def fake_favorites_light_metadata(url: str) -> dict:
        nonlocal called
        called = True
        assert url == FAVLIST_URL
        return {
            "title": "收藏夹",
            "thumbnail": "https://i0.hdslb.com/bfs/fav.jpg",
            "total": 22,
        }

    async def fail_favorites_metadata(url: str) -> dict:
        raise AssertionError("configured favlist entry should not enumerate favorites")

    async def fail_medialist_metadata(url: str) -> dict:
        raise AssertionError("favlist should not use medialist parser")

    monkeypatch.setattr(service.site_runtime.bilibili.site, "favorites_light_metadata", fake_favorites_light_metadata)
    monkeypatch.setattr(service.site_runtime.bilibili.site, "favorites_metadata", fail_favorites_metadata)
    monkeypatch.setattr(service.site_runtime.bilibili.site, "medialist_metadata", fail_medialist_metadata)

    value = asyncio.run(service.category("bilibili"))

    assert called
    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "bilibili", 0)
    assert vod["vod_name"] == "收藏夹"
    assert vod["vod_pic"] == "https://i0.hdslb.com/bfs/fav.jpg"
    assert vod["vod_remarks"] == "22项"


def test_favlist_detail_uses_bilibili_favorites_metadata(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_favorites_metadata(url: str) -> dict:
        return {
            "title": "收藏夹",
            "thumbnail": "https://i0.hdslb.com/bfs/fav.jpg",
            "total": 22,
            "entries": [{"bv_id": "BV1xx411c7mD", "title": "样例视频一", "pages": [{"page": 1, "part": "正片"}]}],
        }

    monkeypatch.setattr(service.site_runtime.bilibili.site, "favorites_metadata", fake_favorites_metadata)

    value = asyncio.run(service.detail(FAVLIST_URL))

    vod = value["list"][0]
    assert vod["vod_name"] == "收藏夹"
    assert vod["vod_pic"] == "https://i0.hdslb.com/bfs/fav.jpg"
    assert vod["vod_remarks"] == "22项"
    assert vod["vod_play_url"] == "样例视频一$https://www.bilibili.com/video/BV1xx411c7mD?dashbox_index=1"


def test_favlist_category_expands_aggregate_vods(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_favorites_metadata(url: str) -> dict:
        return {
            "title": "收藏夹",
            "thumbnail": "https://i0.hdslb.com/bfs/fav.jpg",
            "entries": [
                {"bv_id": "BV1xx411c7mD", "title": "样例视频一", "pages": [{"page": 1, "part": "正片"}]},
                {"bv_id": "BV2xx411c7mD", "title": "视频二", "pages": [{"page": 1, "part": "正片"}]},
            ],
        }

    monkeypatch.setattr(service.site_runtime.bilibili.site, "favorites_metadata", fake_favorites_metadata)

    value = asyncio.run(service.category(FAVLIST_URL))

    directory, first, second = value["list"]
    assert directory["vod_id"].startswith(client_selection.SELECTION_ID_PREFIX)
    assert directory["vod_name"] == "播放此列表"
    assert directory["vod_remarks"] == "2项"
    assert directory["dashbox_client_detail"] == "directory"
    assert first["vod_id"].startswith(client_selection.SELECTION_ID_PREFIX)
    assert first["dashbox_playlist_item"] == "1"
    assert first["dashbox_playlist_name"] == "样例视频一"
    assert first["dashbox_playlist_url"] == "https://www.bilibili.com/video/BV1xx411c7mD?dashbox_index=1"
    assert first["dashbox_client_detail"] == "playlist"
    assert second["dashbox_playlist_url"] == "https://www.bilibili.com/video/BV2xx411c7mD?dashbox_index=2"
    assert second["dashbox_client_detail"] == "playlist"


def test_favlist_category_excludes_multi_p_from_aggregate_vods(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_favorites_metadata(url: str) -> dict:
        return {
            "title": "收藏夹",
            "thumbnail": "https://i0.hdslb.com/bfs/fav.jpg",
            "entries": [
                {
                    "bv_id": "BV1xx411c7mD",
                    "title": "样例合集",
                    "pages": [{"page": 1, "part": "上"}, {"page": 2, "part": "下"}],
                },
                {"bv_id": "BV2xx411c7mD", "title": "样例单集", "pages": [{"page": 1, "part": "正片"}]},
            ],
        }

    monkeypatch.setattr(service.site_runtime.bilibili.site, "favorites_metadata", fake_favorites_metadata)

    value = asyncio.run(service.category(FAVLIST_URL))

    directory, multi_p, single_p = value["list"]
    assert directory["vod_name"] == "播放此列表"
    assert directory["vod_remarks"] == "1项"
    assert directory["dashbox_client_detail"] == "directory"
    assert multi_p["vod_id"] == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert multi_p["vod_remarks"] == "2P"
    assert "dashbox_playlist_item" not in multi_p
    assert "dashbox_client_detail" not in multi_p
    assert single_p["dashbox_playlist_url"] == "https://www.bilibili.com/video/BV2xx411c7mD?dashbox_index=2"
    assert single_p["dashbox_client_detail"] == "playlist"


def test_favlist_category_enriches_missing_pages_before_aggregate(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_favorites_metadata(url: str) -> dict:
        return {
            "title": "收藏夹",
            "entries": [
                {"bv_id": "BV1xx411c7mD", "title": "样例合集"},
                {"bv_id": "BV2xx411c7mD", "title": "样例单集", "pages": [{"page": 1, "part": "正片"}]},
            ],
        }

    async def fake_video_metadata(url: str) -> dict:
        if url.endswith("BV1xx411c7mD"):
            return {"videos": 2, "pages": [{"page": 1, "part": "上"}, {"page": 2, "part": "下"}]}
        return {"videos": 1, "pages": [{"page": 1, "part": "正片"}]}

    monkeypatch.setattr(service.site_runtime.bilibili.site, "favorites_metadata", fake_favorites_metadata)
    monkeypatch.setattr(service.site_runtime.bilibili.site, "video_metadata", fake_video_metadata)

    value = asyncio.run(service.category(FAVLIST_URL))

    directory, multi_p, single_p = value["list"]
    assert directory["vod_remarks"] == "1项"
    assert multi_p["vod_id"] == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert multi_p["vod_remarks"] == "2P"
    assert "dashbox_playlist_url" not in multi_p
    assert single_p["dashbox_playlist_url"] == "https://www.bilibili.com/video/BV2xx411c7mD?dashbox_index=2"


def test_favlist_category_excludes_entries_when_page_count_is_unknown(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_favorites_metadata(url: str) -> dict:
        return {
            "title": "收藏夹",
            "entries": [{"bv_id": "BV1xx411c7mD", "title": "未知分P"}],
        }

    async def fake_video_metadata(url: str) -> dict:
        return {}

    monkeypatch.setattr(service.site_runtime.bilibili.site, "favorites_metadata", fake_favorites_metadata)
    monkeypatch.setattr(service.site_runtime.bilibili.site, "video_metadata", fake_video_metadata)

    value = asyncio.run(service.category(FAVLIST_URL))

    vod = value["list"][0]
    assert vod["vod_id"] == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert "dashbox_playlist_url" not in vod


def test_favlist_category_uses_view_videos_count_for_multi_p(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_favorites_metadata(url: str) -> dict:
        return {
            "title": "收藏夹",
            "entries": [{"bv_id": "BV1xx411c7mD", "title": "实际多P"}],
        }

    async def fake_video_metadata(url: str) -> dict:
        return {
            "videos": 26,
            "pages": [{"page": index, "part": f"P{index:02d}"} for index in range(1, 27)],
        }

    monkeypatch.setattr(service.site_runtime.bilibili.site, "favorites_metadata", fake_favorites_metadata)
    monkeypatch.setattr(service.site_runtime.bilibili.site, "video_metadata", fake_video_metadata)

    value = asyncio.run(service.category(FAVLIST_URL))

    vod = value["list"][0]
    assert vod["vod_id"] == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert vod["vod_remarks"] == "26P"
    assert "dashbox_playlist_url" not in vod


def test_favlist_multi_p_item_detail_returns_own_pages_not_directory_aggregate(monkeypatch) -> None:
    service = MediaService(Config())
    playlist_url = FAVLIST_URL
    selected_url = "https://www.bilibili.com/video/BV1xx411c7mD"

    async def fake_favorites_metadata(url: str) -> dict:
        return {
            "title": "收藏夹",
            "entries": [
                {
                    "bv_id": "BV1xx411c7mD",
                    "title": "样例合集",
                    "pages": [{"page": 1, "part": "上"}, {"page": 2, "part": "下"}],
                },
                {"bv_id": "BV2xx411c7mD", "title": "样例单集", "pages": [{"page": 1, "part": "正片"}]},
            ],
        }

    async def fake_video_metadata(url: str) -> dict:
        assert url == selected_url
        return {
            "title": "样例合集",
            "pages": [{"page": 1, "part": "上"}, {"page": 2, "part": "下"}],
        }

    monkeypatch.setattr(service.site_runtime.bilibili.site, "favorites_metadata", fake_favorites_metadata)
    monkeypatch.setattr(service.site_runtime.bilibili.site, "video_metadata", fake_video_metadata)

    value = asyncio.run(service.playlist_item_detail(playlist_url, selected_url))

    vod = value["list"][0]
    assert vod["vod_name"] == "样例合集"
    assert vod["vod_play_from"] == "yt-dlp"
    assert vod["vod_play_url"] == (
        "P01 上$https://www.bilibili.com/video/BV1xx411c7mD?p=1#"
        "P02 下$https://www.bilibili.com/video/BV1xx411c7mD?p=2"
    )


def test_favlist_detail_excludes_multi_p_from_play_url_after_enrich(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_favorites_metadata(url: str) -> dict:
        return {
            "title": "收藏夹",
            "entries": [
                {"bv_id": "BV1xx411c7mD", "title": "样例合集"},
                {"bv_id": "BV2xx411c7mD", "title": "样例单集"},
            ],
        }

    async def fake_video_metadata(url: str) -> dict:
        if url.endswith("BV1xx411c7mD"):
            return {"videos": 2, "pages": [{"page": 1, "part": "上"}, {"page": 2, "part": "下"}]}
        return {"videos": 1, "pages": [{"page": 1, "part": "正片"}]}

    monkeypatch.setattr(service.site_runtime.bilibili.site, "favorites_metadata", fake_favorites_metadata)
    monkeypatch.setattr(service.site_runtime.bilibili.site, "video_metadata", fake_video_metadata)

    value = asyncio.run(service.detail(FAVLIST_URL))

    vod = value["list"][0]
    assert vod["vod_play_url"] == "样例单集$https://www.bilibili.com/video/BV2xx411c7mD?dashbox_index=2"


def test_bilibili_multi_p_category_does_not_mark_aggregate(monkeypatch) -> None:
    url = "https://www.bilibili.com/video/BV1xx411c7mD"
    service = MediaService(Config())

    async def fake_video_metadata(raw_url: str) -> dict:
        return {
            "title": "样例合集",
            "pic": "https://i0.hdslb.com/bfs/video.jpg",
            "pages": [
                {"page": 1, "part": "上"},
                {"page": 2, "part": "下"},
            ],
        }

    monkeypatch.setattr(service.site_runtime.bilibili.site, "video_metadata", fake_video_metadata)

    async def fake_flat_playlist(*args, **kwargs) -> dict:
        return {
            "webpage_url": url,
            "extractor_key": "BiliBili",
            "title": "样例合集",
            "entries": [
                {"webpage_url": f"{url}?p=1", "title": "上"},
                {"webpage_url": f"{url}?p=2", "title": "下"},
            ],
        }

    monkeypatch.setattr(service, "extract_flat_playlist_info_async", fake_flat_playlist)

    value = asyncio.run(service.category(url))

    vod = value["list"][0]
    assert vod["vod_id"] == url
    assert "dashbox_playlist_item" not in vod

def test_favorites_metadata_reloads_cookies_once_on_403(monkeypatch) -> None:
    calls: list[dict] = []
    cookies = ["old-cookie"]
    reloads = 0

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, params: dict, headers: dict):
            calls.append({"url": url, "params": params, "headers": headers})
            if len(calls) == 1:
                return FakeResponse({"code": -403, "message": "Forbidden"})
            return FakeResponse({
                "code": 0,
                "data": {
                    "info": {"title": "收藏夹", "cover": "https://i0.hdslb.com/bfs/fav.jpg"},
                    "medias": [{"bvid": "BV1xx411c7mD", "title": "视频"}],
                    "has_more": False,
                },
            })

    def reload_cookie() -> None:
        nonlocal reloads
        reloads += 1
        cookies[0] = "fresh-cookie"

    site = bilibili.BilibiliSite(
        cookie_header_provider=lambda url: cookies[0],
        cookie_reload=reload_cookie,
    )
    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)

    value = asyncio.run(site.favorites_metadata(FAVLIST_URL))

    assert reloads == 1
    assert value["title"] == "收藏夹"
    assert value["entries"] == [{"bvid": "BV1xx411c7mD", "title": "视频"}]
    assert [call["headers"]["Cookie"] for call in calls] == ["old-cookie", "fresh-cookie"]


def test_bilibili_site_default_list_limit_uses_bounded_page_cap() -> None:
    site = bilibili.BilibiliSite()

    assert site.list_limit == 100
    assert site.list_page_limit() == 5
    assert site.channel_page_limit() == 5


def test_favorites_metadata_honors_configured_list_limit(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, params: dict, headers: dict):
            calls.append({"url": url, "params": params, "headers": headers})
            return FakeResponse({
                "code": 0,
                "data": {
                    "info": {"title": "收藏夹", "cover": "https://i0.hdslb.com/bfs/fav.jpg", "media_count": 2},
                    "medias": [
                        {"bvid": "BV1", "title": "样例视频一"},
                        {"bvid": "BV2", "title": "视频二"},
                    ],
                    "has_more": True,
                },
            })

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)
    site = bilibili.BilibiliSite(list_limit=1)

    value = asyncio.run(site.favorites_metadata(FAVLIST_URL))

    assert len(calls) == 1
    assert value["total"] == 2
    assert value["entries"] == [{"bvid": "BV1", "title": "样例视频一"}]


def test_favorites_light_metadata_fetches_first_item_only(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "code": 0,
                "data": {
                    "info": {"title": "收藏夹", "cover": "https://i0.hdslb.com/bfs/fav.jpg", "media_count": 22},
                    "medias": [{"bvid": "BV1"}, {"bvid": "BV2"}],
                    "has_more": True,
                },
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, params: dict, headers: dict):
            calls.append({"url": url, "params": params, "headers": headers})
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)
    site = bilibili.BilibiliSite()

    value = asyncio.run(site.favorites_light_metadata(FAVLIST_URL))

    assert len(calls) == 1
    assert calls[0]["params"] == {"media_id": "139017447", "pn": 1, "ps": 1}
    assert value == {
        "title": "收藏夹",
        "thumbnail": "https://i0.hdslb.com/bfs/fav.jpg",
        "total": 22,
    }


def test_favorites_metadata_does_not_reload_cookies_repeatedly(monkeypatch) -> None:
    reloads = 0

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"code": -403, "message": "Forbidden"}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, params: dict, headers: dict):
            return FakeResponse()

    def reload_cookie() -> None:
        nonlocal reloads
        reloads += 1

    site = bilibili.BilibiliSite(
        cookie_header_provider=lambda url: "cookie",
        cookie_reload=reload_cookie,
    )
    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)

    value = asyncio.run(site.favorites_metadata(FAVLIST_URL))

    assert value == {}
    assert reloads == 1

