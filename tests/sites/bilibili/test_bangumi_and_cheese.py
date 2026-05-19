import asyncio


from dashbox.config import Config, Source, UrlItem
from dashbox.sites import bilibili
from tests.helpers import config_item_id, make_tvbox_service as MediaService
from tests.sites.bilibili.helpers import BANGUMI_URL, bangumi_metadata


def test_bangumi_season_category_uses_bilibili_metadata(monkeypatch) -> None:
    service = MediaService(Config(), sources=(
        Source("bilibili", "Bilibili", (UrlItem(BANGUMI_URL),)),
    ))
    async def fake_metadata(url: str) -> dict:
        return bangumi_metadata()

    monkeypatch.setattr(service.site_runtime.bilibili.site, "bangumi_season_metadata", fake_metadata)

    value = asyncio.run(service.category("bilibili"))

    vod = value["list"][0]
    assert vod["vod_id"] == config_item_id(service, "bilibili", 0)
    assert vod["vod_name"] == "少女革命 样例正片"
    assert vod["vod_pic"] == "https://i0.hdslb.com/bfs/bangumi/cover.jpg"
    assert vod["vod_remarks"] == "1项"


def test_bangumi_season_detail_uses_title_cover_and_episodes(monkeypatch) -> None:
    service = MediaService(Config())
    async def fake_metadata(url: str) -> dict:
        return bangumi_metadata()

    monkeypatch.setattr(service.site_runtime.bilibili.site, "bangumi_season_metadata", fake_metadata)

    value = asyncio.run(service.detail(BANGUMI_URL))

    vod = value["list"][0]
    assert vod["vod_name"] == "少女革命 样例正片"
    assert vod["vod_pic"] == "https://i0.hdslb.com/bfs/bangumi/cover.jpg"
    assert vod["vod_remarks"] == "1项"
    assert vod["vod_content"] == "番剧 简介 第二行"
    assert vod["vod_play_url"] == "1 样例正片$https://www.bilibili.com/bangumi/play/ep30000001"



def test_bangumi_media_resolves_season_id_from_initial_state(monkeypatch) -> None:
    calls = []

    class FakeResponse:
        text = 'window.__INITIAL_STATE__={"mediaInfo":{"season_id":2493,"title":"媒体页标题"}};(function'

        def raise_for_status(self) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        async def get(self, url: str, headers: dict):
            calls.append(url)
            return FakeResponse()

    site = bilibili.BilibiliSite()

    async def fake_bangumi_season_metadata(url: str) -> dict:
        calls.append(url)
        return bangumi_metadata()

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(site, "bangumi_season_metadata", fake_bangumi_season_metadata)

    value = asyncio.run(site.bangumi_media_metadata("https://www.bilibili.com/bangumi/media/md24097891"))

    assert calls == [
        "https://www.bilibili.com/bangumi/media/md24097891",
        "https://www.bilibili.com/bangumi/play/ss2493",
    ]
    assert value["title"] == "媒体页标题"


def test_parse_initial_state_handles_braces_inside_strings() -> None:
    html = (
        'window.__INITIAL_STATE__ = {"mediaInfo":{"season_id":2493,'
        '"title":"标题 {不是 JSON 结束} \\"quoted\\""}};'
        "window.more = true;"
    )

    value = bilibili.parse_initial_state(html)

    assert value["mediaInfo"]["season_id"] == 2493
    assert value["mediaInfo"]["title"] == '标题 {不是 JSON 结束} "quoted"'


def test_cheese_season_detail_builds_episode_playlist(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_cheese_season_metadata(url: str) -> dict:
        return {
            "title": "课程",
            "cover": "https://i0.hdslb.com/bfs/cheese.jpg",
            "subtitle": "课程 简介",
            "episodes": [
                {"id": 30000002, "index": 1, "title": "样例课时", "cover": "https://i0.hdslb.com/bfs/ep.jpg", "duration": 221},
            ],
        }

    monkeypatch.setattr(service.site_runtime.bilibili.site, "cheese_season_metadata", fake_cheese_season_metadata)

    value = asyncio.run(service.detail("https://www.bilibili.com/cheese/play/ss5918"))

    vod = value["list"][0]
    assert vod["vod_name"] == "课程"
    assert vod["vod_content"] == "课程 简介"
    assert vod["vod_play_url"] == "1 - 样例课时$https://www.bilibili.com/cheese/play/ep30000002"


def test_bangumi_category_applies_season_description_to_directory_and_children(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_metadata(url: str) -> dict:
        return bangumi_metadata()

    monkeypatch.setattr(service.site_runtime.bilibili.site, "bangumi_season_metadata", fake_metadata)

    value = asyncio.run(service.category(BANGUMI_URL))

    directory, episode = value["list"]
    assert value["dashbox_category_name"] == "少女革命 样例正片"
    assert directory["vod_name"] == "播放此列表"
    assert episode["vod_content"] == "番剧 简介 第二行"


def test_cheese_category_applies_season_description_to_directory_and_children(monkeypatch) -> None:
    service = MediaService(Config())
    url = "https://www.bilibili.com/cheese/play/ss5918"

    async def fake_cheese_season_metadata(raw_url: str) -> dict:
        assert raw_url == url
        return {
            "title": "课程",
            "cover": "https://i0.hdslb.com/bfs/cheese.jpg",
            "brief": {"content": "课程 简介\n第二行"},
            "episodes": [
                {"id": 30000002, "index": 1, "title": "样例课时", "cover": "https://i0.hdslb.com/bfs/ep.jpg", "duration": 221},
            ],
        }

    monkeypatch.setattr(service.site_runtime.bilibili.site, "cheese_season_metadata", fake_cheese_season_metadata)

    value = asyncio.run(service.category(url))

    directory, episode = value["list"]
    assert value["dashbox_category_name"] == "课程"
    assert directory["vod_name"] == "播放此列表"
    assert episode["vod_content"] == "课程 简介 第二行"


