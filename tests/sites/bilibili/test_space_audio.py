import asyncio


from dashbox.config import Config, Source, UrlItem
from dashbox.sites import bilibili
from tests.helpers import make_tvbox_service as MediaService


def test_audio_album_metadata_reads_nested_song_list(monkeypatch) -> None:
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
            calls.append({"url": url, "params": params})
            if url.endswith("/song/of-menu"):
                return FakeResponse({
                    "code": 0,
                    "data": {
                        "data": [
                            {
                                "id": 2478206,
                                "title": "【Mitchie M】Nechusho No!No!",
                                "cover": "https://i0.hdslb.com/bfs/song.jpg",
                                "duration": 112,
                            },
                        ],
                    },
                })
            return FakeResponse({
                "code": 0,
                "data": {
                    "title": "新曲推荐",
                    "intro": "每天11:00更新",
                    "cover": "https://i0.hdslb.com/bfs/audio.jpg",
                },
            })

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)
    site = bilibili.BilibiliSite()

    value = asyncio.run(site.audio_album_metadata("https://www.bilibili.com/audio/am80000001"))

    assert calls[0]["params"] == {"sid": "80000001", "pn": 1, "ps": 100}
    assert value["title"] == "新曲推荐"
    assert value["entries"][0]["title"] == "【Mitchie M】Nechusho No!No!"


def test_audio_album_metadata_paginates_song_list(monkeypatch) -> None:
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
            calls.append({"url": url, "params": params})
            if url.endswith("/song/of-menu"):
                page_num = params["pn"]
                return FakeResponse({
                    "code": 0,
                    "data": {
                        "curPage": page_num,
                        "pageCount": 2,
                        "totalSize": 3,
                        "pageSize": 2 if page_num == 1 else 1,
                        "data": [
                            {"id": f"{page_num}-1", "title": f"歌曲{page_num}-1"},
                            *([{"id": "1-2", "title": "歌曲1-2"}] if page_num == 1 else []),
                        ],
                    },
                })
            return FakeResponse({"code": 0, "data": {"title": "分页歌单"}})

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)
    site = bilibili.BilibiliSite(list_limit=3)

    value = asyncio.run(site.audio_album_metadata("https://www.bilibili.com/audio/am80000001"))

    song_calls = [call for call in calls if call["url"].endswith("/song/of-menu")]
    assert [call["params"]["pn"] for call in song_calls] == [1, 2]
    assert [entry["title"] for entry in value["entries"]] == ["歌曲1-1", "歌曲1-2", "歌曲2-1"]


def test_audio_album_detail_builds_audio_playlist(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_audio_album_metadata(url: str) -> dict:
        return {
            "title": "新曲推荐",
            "thumbnail": "https://i0.hdslb.com/bfs/audio.jpg",
            "entries": [{"id": 40000001, "title": "Sample Song", "cover": "https://i0.hdslb.com/bfs/song.jpg", "duration": 183}],
        }

    monkeypatch.setattr(service.site_runtime.bilibili.site, "audio_album_metadata", fake_audio_album_metadata)

    value = asyncio.run(service.detail("https://www.bilibili.com/audio/am80000001"))

    vod = value["list"][0]
    assert vod["vod_name"] == "新曲推荐"
    assert vod["vod_play_url"] == "Sample Song$https://www.bilibili.com/audio/au40000001?dashbox_index=1"


def test_space_collection_metadata_uses_seasons_archives_api(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "code": 0,
                "data": {
                    "meta": {
                        "name": "合集",
                        "cover": "https://archive.biliimg.com/bfs/archive/cover.jpg",
                        "description": "合集简介",
                    },
                    "archives": [{"bvid": "BV1xx411c7mD", "title": "合集视频", "cover": "https://i0.hdslb.com/bfs/archive.jpg"}],
                    "page": {"total": 12, "page_size": 30},
                },
            }

    class FakeAsyncClient:
        async def get(self, url: str, params: dict, headers: dict):
            calls.append({"url": url, "params": params, "headers": headers})
            return FakeResponse()

    site = bilibili.BilibiliSite(http_client_provider=lambda: FakeAsyncClient())

    value = asyncio.run(site.space_collection_metadata("https://space.bilibili.com/60000001/channel/collectiondetail?sid=70000001"))

    assert calls[0]["url"] == "https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"
    assert calls[0]["params"] == {"mid": "60000001", "season_id": "70000001", "page_num": 1, "page_size": 30}
    assert value["title"] == "合集"
    assert value["thumbnail"] == "https://archive.biliimg.com/bfs/archive/cover.jpg"
    assert value["total"] == 12
    assert value["entries"][0]["bvid"] == "BV1xx411c7mD"


def test_space_series_metadata_uses_series_apis(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    class FakeAsyncClient:
        async def get(self, url: str, params: dict, headers: dict):
            calls.append({"url": url, "params": params, "headers": headers})
            if url.endswith("/x/series/series"):
                return FakeResponse({"code": 0, "data": {"meta": {"name": "系列", "description": "系列简介"}}})
            return FakeResponse({
                "code": 0,
                "data": {
                    "archives": [{"bvid": "BV3xx411c7mD", "title": "系列视频", "pic": "https://i0.hdslb.com/bfs/archive.jpg"}],
                    "page": {"total": 513, "size": 30},
                },
            })

    site = bilibili.BilibiliSite(http_client_provider=lambda: FakeAsyncClient())

    value = asyncio.run(site.space_series_metadata("https://space.bilibili.com/60000002/lists/70000002?type=series"))

    assert calls[0]["url"] == "https://api.bilibili.com/x/series/series"
    assert calls[0]["params"] == {"series_id": "70000002"}
    assert calls[1]["url"] == "https://api.bilibili.com/x/series/archives"
    assert calls[1]["params"] == {"mid": "60000002", "series_id": "70000002", "pn": 1, "ps": 30}
    assert value["title"] == "系列"
    assert value["total"] == 513
    assert value["entries"][0]["bvid"] == "BV3xx411c7mD"


def test_space_audio_metadata_uses_upper_audio_api(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "code": 0,
                "data": {
                    "data": [{"id": 40000001, "title": "Sample Song", "cover": "https://i0.hdslb.com/bfs/song.jpg"}],
                    "pageCount": 1,
                    "pageSize": 30,
                    "totalSize": 7,
                },
            }

    class FakeAsyncClient:
        async def get(self, url: str, params: dict, headers: dict):
            calls.append({"url": url, "params": params, "headers": headers})
            return FakeResponse()

    site = bilibili.BilibiliSite(http_client_provider=lambda: FakeAsyncClient())

    value = asyncio.run(site.space_audio_metadata("https://space.bilibili.com/60000003/upload/audio"))

    assert calls[0]["url"] == "https://api.bilibili.com/audio/music-service/web/song/upper"
    assert calls[0]["params"] == {"uid": "60000003", "pn": 1, "ps": 30, "order": 1}
    assert value["title"] == "60000003 - 音频"
    assert value["total"] == 7
    assert value["entries"][0]["id"] == 40000001


def test_space_audio_metadata_keeps_total_when_list_limit_stops_first_page(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "code": 0,
                "data": {
                    "data": [
                        {"id": 40000001, "title": "Sample Song"},
                        {"id": 1003143, "title": "GREEN"},
                    ],
                    "pageCount": 2,
                    "pageSize": 30,
                    "totalSize": 7,
                },
            }

    class FakeAsyncClient:
        async def get(self, url: str, params: dict, headers: dict):
            calls.append({"url": url, "params": params, "headers": headers})
            return FakeResponse()

    site = bilibili.BilibiliSite(list_limit=1, http_client_provider=lambda: FakeAsyncClient())

    value = asyncio.run(site.space_audio_metadata("https://space.bilibili.com/60000003/upload/audio"))

    assert len(calls) == 1
    assert value["total"] == 7
    assert value["entries"] == [{"id": 40000001, "title": "Sample Song"}]


def test_space_series_category_expands_aggregate_vods(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_space_series_metadata(url: str) -> dict:
        return {
            "title": "系列",
            "total": 3,
            "entries": [{"bvid": "BV3xx411c7mD", "title": "系列视频", "pages": [{"page": 1, "part": "正片"}]}],
        }

    monkeypatch.setattr(service.site_runtime.bilibili.site, "space_series_metadata", fake_space_series_metadata)

    value = asyncio.run(service.category("https://space.bilibili.com/60000002/lists/70000002?type=series"))

    directory, first = value["list"]
    assert directory["vod_name"] == "播放此列表"
    assert directory["vod_remarks"] == "1项"
    assert first["dashbox_playlist_name"] == "系列视频"
    assert first["dashbox_playlist_url"] == "https://www.bilibili.com/video/BV3xx411c7mD?dashbox_index=1"


def test_space_light_nodes_show_total_counts(monkeypatch) -> None:
    service = MediaService(Config(), sources=(
        Source("bilibili", "Bilibili", (
            UrlItem("https://space.bilibili.com/60000001/channel/collectiondetail?sid=70000001"),
            UrlItem("https://space.bilibili.com/60000002/lists/70000002?type=series"),
            UrlItem("https://space.bilibili.com/60000003/upload/audio"),
        )),
    ))
    async def fake_collection_light_metadata(url: str) -> dict:
        return {"title": "合集", "total": 12}

    async def fake_series_light_metadata(url: str) -> dict:
        return {"title": "系列", "total": 513}

    async def fake_audio_light_metadata(url: str) -> dict:
        return {"title": "音频", "total": 7}

    monkeypatch.setattr(service.site_runtime.bilibili.site, "space_collection_light_metadata", fake_collection_light_metadata)
    monkeypatch.setattr(service.site_runtime.bilibili.site, "space_series_light_metadata", fake_series_light_metadata)
    monkeypatch.setattr(service.site_runtime.bilibili.site, "space_audio_light_metadata", fake_audio_light_metadata)

    value = asyncio.run(service.category("bilibili"))

    assert [vod["vod_remarks"] for vod in value["list"]] == ["12项", "513项", "7项"]


def test_watchlater_config_entry_shows_total_count(monkeypatch) -> None:
    service = MediaService(Config(), sources=(
        Source("bilibili", "Bilibili", (UrlItem("https://www.bilibili.com/watchlater"),)),
    ))
    async def fake_watchlater_light_metadata(url: str) -> dict:
        return {"title": "稍后再看", "total": 9}

    monkeypatch.setattr(service.site_runtime.bilibili.site, "watchlater_light_metadata", fake_watchlater_light_metadata)

    value = asyncio.run(service.category("bilibili"))

    assert value["list"][0]["vod_name"] == "稍后再看"
    assert value["list"][0]["vod_remarks"] == "9项"


