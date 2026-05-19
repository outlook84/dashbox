import asyncio

import pytest

from dashbox.config import Config
from dashbox.sites import bilibili
from tests.helpers import make_tvbox_service as MediaService


def test_bilibili_player_url_normalizes_to_supported_av_url() -> None:
    assert (
        bilibili.normalize_extract_url("https://player.bilibili.com/player.html?aid=10000001&cid=20000001&page=2")
        == "https://www.bilibili.com/video/av10000001?p=2"
    )
    assert (
        bilibili.normalize_extract_url("https://player.bilibili.com/player.html?aid=10000001&cid=20000001&p=3")
        == "https://www.bilibili.com/video/av10000001?p=3"
    )
    assert bilibili.normalize_extract_url("http://www.bilibili.tv/video/av10000001/") == "http://www.bilibili.tv/video/av10000001/"


def test_bilibili_player_url_resolves_cid_to_page() -> None:
    site = bilibili.BilibiliSite()
    calls = []

    async def fake_video_metadata(url: str) -> dict:
        calls.append(url)
        return {
            "pages": [
                {"page": 1, "cid": 20000001, "part": "上"},
                {"page": 2, "cid": 20000002, "part": "下"},
            ],
        }

    site.video_metadata = fake_video_metadata

    value = asyncio.run(
        site.resolve_extract_url("https://player.bilibili.com/player.html?aid=10000001&cid=20000002")
    )

    assert calls == ["https://www.bilibili.com/video/av10000001"]
    assert value == "https://www.bilibili.com/video/av10000001?p=2"


def test_bilibili_blocking_extract_url_normalizes_player_url_with_page() -> None:
    site = bilibili.BilibiliSite()

    value = site._extract_url_for_blocking_call("https://player.bilibili.com/player.html?aid=10000001&cid=20000002&page=2")

    assert value == "https://www.bilibili.com/video/av10000001?p=2"


def test_bilibili_blocking_extract_url_rejects_player_cid_without_page() -> None:
    site = bilibili.BilibiliSite()

    with pytest.raises(RuntimeError, match="async playback API"):
        site._extract_url_for_blocking_call("https://player.bilibili.com/player.html?aid=10000001&cid=20000002")


def test_bilibili_blocking_extract_url_rejects_short_url() -> None:
    site = bilibili.BilibiliSite()

    with pytest.raises(RuntimeError, match="async playback API"):
        site._extract_url_for_blocking_call("https://b23.tv/abc123")


def test_bilibili_short_url_resolves_to_supported_target() -> None:
    async def fake_resolver(url: str) -> str:
        assert url == "https://b23.tv/abc123"
        return "https://www.bilibili.com/video/BV1xx411c7mD?p=2"

    site = bilibili.BilibiliSite(short_url_resolver=fake_resolver)

    value = asyncio.run(site.resolve_extract_url("https://b23.tv/abc123"))

    assert value == "https://www.bilibili.com/video/BV1xx411c7mD?p=2"


def test_bilibili_short_url_resolves_player_cid_to_page() -> None:
    async def fake_resolver(url: str) -> str:
        assert url == "https://b23.tv/abc123"
        return "https://player.bilibili.com/player.html?aid=10000001&cid=20000002"

    site = bilibili.BilibiliSite(short_url_resolver=fake_resolver)
    calls = []

    async def fake_video_metadata(url: str) -> dict:
        calls.append(url)
        return {
            "pages": [
                {"page": 1, "cid": 20000001, "part": "上"},
                {"page": 2, "cid": 20000002, "part": "下"},
            ],
        }

    site.video_metadata = fake_video_metadata

    value = asyncio.run(site.resolve_extract_url("https://b23.tv/abc123"))

    assert calls == ["https://www.bilibili.com/video/av10000001"]
    assert value == "https://www.bilibili.com/video/av10000001?p=2"


def test_bilibili_short_url_resolves_to_live_target() -> None:
    async def fake_resolver(url: str) -> str:
        return "https://live.bilibili.com/blanc/196"

    site = bilibili.BilibiliSite(short_url_resolver=fake_resolver)

    value = asyncio.run(site.resolve_extract_url("https://b23.tv/live"))

    assert value == "https://live.bilibili.com/blanc/196"


def test_bilibili_short_url_preserves_unsupported_target() -> None:
    async def fake_resolver(url: str) -> str:
        return "https://example.test/watch"

    site = bilibili.BilibiliSite(short_url_resolver=fake_resolver)

    value = asyncio.run(site.resolve_extract_url("https://b23.tv/abc123"))

    assert value == "https://b23.tv/abc123"


def test_bilibili_short_url_detail_uses_resolved_target(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_resolver(url: str) -> str:
        return "https://www.bilibili.com/video/BV1xx411c7mD"

    async def fake_video_metadata(url: str) -> dict:
        assert url == "https://www.bilibili.com/video/BV1xx411c7mD"
        return {
            "title": "短链视频",
            "pic": "https://i0.hdslb.com/bfs/video.jpg",
            "duration": 120,
            "pages": [{"page": 1, "part": "正片"}],
        }

    service.site_runtime.bilibili.site.short_url_resolver = fake_resolver
    monkeypatch.setattr(service.site_runtime.bilibili.site, "video_metadata", fake_video_metadata)

    value = asyncio.run(service.detail("https://b23.tv/abc123"))

    vod = value["list"][0]
    assert vod["vod_id"] == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert vod["vod_name"] == "短链视频"


