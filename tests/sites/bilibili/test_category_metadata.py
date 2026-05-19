import asyncio


from dashbox.config import DEFAULT_BILIBILI_SEARCH_LIMIT, Config, Source, UrlItem
from dashbox.models import MediaNode
from dashbox.sites import bilibili
from tests.helpers import config_item_id, make_tvbox_service as MediaService, patch_metadata_for_plan


def test_bilibili_search_url_category_uses_wbi_search(monkeypatch) -> None:
    url = "https://search.bilibili.com/video?keyword=sample"
    service = MediaService(Config(bilibili_search_limit=7, bilibili_list_limit=50))

    async def fake_search_nodes(keyword: str, *, limit: int):
        assert keyword == "sample"
        assert limit == 7
        return [
            MediaNode(
                "https://www.bilibili.com/video/BV1xx411c7mD",
                "Bili search result",
                remarks="01:02",
            )
        ]

    monkeypatch.setattr(service.site_runtime.bilibili.site, "search_nodes", fake_search_nodes)

    value = asyncio.run(service.category(url))

    assert value["list"][0]["vod_id"] == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert value["list"][0]["vod_name"] == "Bili search result"


def test_bilibili_search_url_zero_limit_uses_default_limit(monkeypatch) -> None:
    url = "https://search.bilibili.com/video?keyword=sample"
    service = MediaService(Config(bilibili_search_limit=0))
    called = {}

    async def fake_search_nodes(keyword: str, *, limit: int):
        called["keyword"] = keyword
        called["limit"] = limit
        return []

    def fail_extract(*args, **kwargs):
        raise AssertionError("yt-dlp should not be used for empty bilibili search categories")

    monkeypatch.setattr(service.site_runtime.bilibili.site, "search_nodes", fake_search_nodes)
    monkeypatch.setattr(service, "extract", fail_extract)

    value = asyncio.run(service.category(url))

    assert called == {"keyword": "sample", "limit": DEFAULT_BILIBILI_SEARCH_LIMIT}
    assert value.get("list", []) == []


def test_bilibili_search_url_config_entry_uses_search_icon(monkeypatch) -> None:
    url = "https://search.bilibili.com/video?keyword=sample"
    service = MediaService(Config(), sources=(Source("bilibili", "Bilibili", (UrlItem(url),)),))

    value = asyncio.run(service.category("bilibili"))

    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "bilibili", 0)
    assert vod["vod_name"] == "Bilibili 搜索: sample"
    assert vod["vod_pic"].endswith("/assets/icons/search.png")
    assert vod["type_flag"] == "1"
    assert vod["vod_tag"] == "folder"



def test_watchlater_detail_uses_toview_entries(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_watchlater_metadata(url: str) -> dict:
        return {
            "title": "稍后再看",
            "total": 9,
            "entries": [{"bvid": "BV1xx411c7mD", "title": "样例稍后视频", "pages": [{"page": 1, "part": "正片"}]}],
        }

    monkeypatch.setattr(service.site_runtime.bilibili.site, "watchlater_metadata", fake_watchlater_metadata)

    value = asyncio.run(service.detail("https://www.bilibili.com/watchlater"))

    vod = value["list"][0]
    assert vod["vod_name"] == "稍后再看"
    assert vod["vod_remarks"] == "9项"
    assert vod["vod_play_url"] == "样例稍后视频$https://www.bilibili.com/video/BV1xx411c7mD?dashbox_index=1"


def test_bilibili_category_uses_newlist_api(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "code": 0,
                "data": {
                    "archives": [{"bvid": "BV1xx411c7mD", "title": "鬼畜视频", "pic": "https://i0.hdslb.com/bfs/archive.jpg"}],
                    "page": {"count": 1, "size": 20},
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
            calls.append({"url": url, "params": params})
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)
    site = bilibili.BilibiliSite()

    value = asyncio.run(site.category_metadata("https://www.bilibili.com/v/kichiku/mad"))

    assert calls[0]["url"] == "https://api.bilibili.com/x/web-interface/newlist"
    assert calls[0]["params"]["rid"] == 26
    assert value["title"] == "kichiku: mad"
    assert value["entries"][0]["bvid"] == "BV1xx411c7mD"


def test_bilibili_category_allows_supported_underscore_slug(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "code": 0,
                "data": {
                    "archives": [{"bvid": "BV1xx411c7mD", "title": "鬼畜调教"}],
                    "page": {"count": 1, "size": 20},
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
            calls.append({"url": url, "params": params})
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)
    site = bilibili.BilibiliSite()

    value = asyncio.run(site.category_metadata("https://www.bilibili.com/v/kichiku/manual_vocaloid"))

    assert calls[0]["params"]["rid"] == 126
    assert value["title"] == "kichiku: manual_vocaloid"
    assert value["entries"][0]["title"] == "鬼畜调教"


def test_bilibili_channel_uses_kv_tid_and_region_feed(monkeypatch) -> None:
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
            if url.endswith("/x/kv-frontend/namespace/data"):
                return FakeResponse({
                    "code": 0,
                    "data": {
                        "data": {
                            "channel_list.food": (
                                '{"channelId":17,"tid":1020,"route":"food",'
                                '"name":"美食","url":"//www.bilibili.com/c/food/"}'
                            ),
                        },
                    },
                })
            return FakeResponse({
                "code": 0,
                "data": {
                    "archives": [
                        {
                            "bvid": "BV1JtBQBzEHu",
                            "title": "吃货请回避！！！",
                            "cover": "https://i0.hdslb.com/bfs/archive.jpg",
                            "duration": 124,
                        },
                    ],
                },
            })

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)
    site = bilibili.BilibiliSite()

    value = asyncio.run(site.channel_metadata("https://www.bilibili.com/v/food"))

    assert calls[0]["params"] == {"appKey": "333.1339", "nscode": 10, "versionId": ""}
    assert calls[1]["url"] == "https://api.bilibili.com/x/web-interface/region/feed/rcmd"
    assert calls[1]["params"]["from_region"] == 1020
    assert value["title"] == "美食"
    assert value["entries"][0]["title"] == "吃货请回避！！！"



def test_av_video_metadata_uses_aid_query(monkeypatch) -> None:
    calls: list[dict] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "code": 0,
                "data": {
                    "title": "AV 视频",
                    "pic": "https://i0.hdslb.com/bfs/archive.jpg",
                    "duration": 120,
                    "pages": [{"page": 1, "part": "正片"}],
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

    value = asyncio.run(site.video_metadata("https://www.bilibili.com/video/av10000002"))

    assert calls[0]["params"] == {"aid": "10000002"}
    assert value["title"] == "AV 视频"



def test_bilibili_video_playlist_detail_uses_api_description_without_ytdlp(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_video_metadata(url: str) -> dict:
        assert url == "https://www.bilibili.com/video/av10000002"
        return {
            "title": "多P AV 视频",
            "pic": "https://i0.hdslb.com/bfs/video.jpg",
            "duration": 120,
            "desc": "多P 简介",
            "pages": [{"page": 1, "part": "上"}, {"page": 2, "part": "下"}],
        }

    def fail_playable_info(*args, **kwargs):
        raise AssertionError("yt-dlp should not be used for Bilibili API detail metadata")

    monkeypatch.setattr(service.site_runtime.bilibili.site, "video_metadata", fake_video_metadata)
    monkeypatch.setattr(service, "playable_info", fail_playable_info)

    value = asyncio.run(service.detail("https://www.bilibili.com/video/av10000002"))

    vod = value["list"][0]
    assert vod["vod_name"] == "多P AV 视频"
    assert vod["vod_content"] == "多P 简介"


def test_bilibili_episode_details_use_api_description_without_ytdlp(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_bangumi_episode_metadata(url: str) -> dict:
        assert url == "https://www.bilibili.com/bangumi/play/ep30000001"
        return {
            "title": "少女革命 样例正片",
            "cover": "https://i0.hdslb.com/bfs/bangumi/cover.jpg",
            "evaluate": "番剧 简介\n第二行",
            "episodes": [
                {
                    "id": 30000001,
                    "title": "1",
                    "long_title": "样例正片",
                    "cover": "https://i0.hdslb.com/bfs/bangumi/ep.jpg",
                    "duration": 5110355,
                },
            ],
        }

    async def fake_cheese_episode_metadata(url: str) -> dict:
        assert url == "https://www.bilibili.com/cheese/play/ep30000002"
        return {
            "title": "课程",
            "cover": "https://i0.hdslb.com/bfs/cheese/cover.jpg",
            "subtitle": "课程 简介",
            "episodes": [
                {
                    "id": 30000002,
                    "index": 1,
                    "title": "样例课时",
                    "cover": "https://i0.hdslb.com/bfs/cheese/ep.jpg",
                    "duration": 120,
                },
            ],
        }

    def fail_playable_info(*args, **kwargs):
        raise AssertionError("yt-dlp should not be used for Bilibili API detail metadata")

    monkeypatch.setattr(service.site_runtime.bilibili.site, "bangumi_episode_metadata", fake_bangumi_episode_metadata)
    monkeypatch.setattr(service.site_runtime.bilibili.site, "cheese_episode_metadata", fake_cheese_episode_metadata)
    monkeypatch.setattr(service, "playable_info", fail_playable_info)

    bangumi_value = asyncio.run(service.detail("https://www.bilibili.com/bangumi/play/ep30000001"))
    cheese_value = asyncio.run(service.detail("https://www.bilibili.com/cheese/play/ep30000002"))

    bangumi_vod = bangumi_value["list"][0]
    cheese_vod = cheese_value["list"][0]
    assert bangumi_vod["vod_name"] == "1 样例正片"
    assert bangumi_vod["vod_content"] == "番剧 简介 第二行"
    assert cheese_vod["vod_name"] == "1 - 样例课时"
    assert cheese_vod["vod_content"] == "课程 简介"


def test_bilibili_live_not_live_metadata_is_visible_in_config_item(monkeypatch) -> None:
    service = MediaService(Config(), sources=(
        Source("bilibili", "Bilibili", (UrlItem("https://live.bilibili.com/196", title="样例直播"),)),
    ))
    def fake_ytdlp_light_metadata(raw_id: str, extract_url: str = "") -> dict:
        return {
            "webpage_url": raw_id,
            "title": "直播未开播",
            "dashbox_unavailable_reason": "直播未开播",
        }

    patch_metadata_for_plan(monkeypatch, service, single=fake_ytdlp_light_metadata)

    value = asyncio.run(service.category("bilibili"))

    vod = value["list"][0]
    assert vod["vod_name"] == "样例直播"
    assert vod["vod_remarks"] == "直播未开播"


def test_bilibili_live_not_live_detail_is_unavailable_with_reason(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_light_metadata(raw_id: str) -> dict:
        return {
            "webpage_url": raw_id,
            "title": "直播未开播",
            "dashbox_unavailable_reason": "直播未开播",
        }

    async def fail_playable_info(*args, **kwargs):
        raise RuntimeError("live is not playable")

    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)
    monkeypatch.setattr(service, "playable_info_async", fail_playable_info)

    value = asyncio.run(service.detail("https://live.bilibili.com/196"))

    vod = value["list"][0]
    assert vod["vod_name"] == "直播未开播"
    assert vod["vod_remarks"] == "直播未开播"
    assert "vod_play_url" not in vod


