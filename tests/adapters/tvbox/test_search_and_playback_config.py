import asyncio

import pytest

from dashbox.config import (
    DEFAULT_YTDLP_SEARCH_LIMIT,
    BrowserCookiesConfig,
    BrowserCookiesMode,
    Config,
    ImageProxyMode,
    SearchProvider,
    Subscription,
    TvboxSubscriptionConfig,
    YtdlpSearchPrefixMode,
)
from dashbox.config.runtime import bind_runtime_config
from dashbox.core import search_urls
from dashbox.models import MediaNode
from tests.helpers import make_tvbox_service as MediaService


def test_search_url_for_key_uses_configured_prefix_and_limit() -> None:
    config = Config(
        default_search_provider="ytdlp",
        ytdlp_search_prefix={"mode": "youtube"},
        ytdlp_search_limit=30,
        bilibili_search_limit=30,
        playlist_limit=100,
        bilibili_list_limit=100,
        subs=(
            Subscription(
                id="main",
                type="tvbox",
                tvbox=TvboxSubscriptionConfig(
                    site_key="dashbox",
                    search_provider="bilibili",
                    ytdlp_search_prefix={"mode": "soundcloud"},
                    ytdlp_search_limit=12,
                    bilibili_search_limit=13,
                    playlist_limit=14,
                    bilibili_list_limit=15,
                    sources=(),
                ),
            ),
        ),
    )

    tvbox_config = config.subs[0].tvbox
    assert tvbox_config.search_provider is SearchProvider.BILIBILI
    assert search_urls.search_url_for_key(config.effective_ytdlp_search_prefix, config.effective_ytdlp_search_limit, "test") == "ytsearch30:test"
    assert tvbox_config.effective_ytdlp_search_prefix == "scsearch"
    assert tvbox_config.effective_ytdlp_search_limit == 12
    assert tvbox_config.effective_bilibili_search_limit == 13
    assert tvbox_config.effective_playlist_limit == 14
    assert tvbox_config.effective_bilibili_list_limit == 15


def test_tvbox_subscription_overrides_do_not_fork_runtime_config(tmp_path) -> None:
    config = Config(cookies_from_browser={"mode": "firefox_data_dir"})
    runtime_config = bind_runtime_config(config, tmp_path)

    service = MediaService(config, tvbox_overrides={"ytdlp_search_limit": 4}, runtime_config=runtime_config)

    assert service.tvbox_config.ytdlp_search_limit == 4
    assert service.runtime_config.data_dir == tmp_path.resolve()
    assert service.ytdlp.runtime_config is service.runtime_config
def test_cookies_from_browser_uses_mode_or_custom_value() -> None:
    simple = Config(cookies_from_browser={"mode": "firefox"})
    data_dir = Config(cookies_from_browser={"mode": "firefox_data_dir"})
    custom = Config(cookies_from_browser={"mode": "custom", "value": "chrome:Profile 1"})

    assert simple.cookies_from_browser == BrowserCookiesConfig(mode=BrowserCookiesMode.FIREFOX)
    assert simple.configured_cookies_from_browser == "firefox"
    assert data_dir.cookies_from_browser == BrowserCookiesConfig(mode=BrowserCookiesMode.FIREFOX_DATA_DIR)
    assert data_dir.configured_cookies_from_browser == "firefox_data_dir"
    assert custom.configured_cookies_from_browser == "chrome:Profile 1"


def test_proxy_media_idle_ttl_seconds_is_configurable() -> None:
    assert Config().proxy_media_idle_ttl_seconds == 21600
    assert Config(proxy_media_idle_ttl_seconds=120).proxy_media_idle_ttl_seconds == 120

    with pytest.raises(ValueError, match="unsupported proxy_media_idle_ttl_seconds"):
        Config(proxy_media_idle_ttl_seconds=0)


def test_proxy_dash_media_url_is_configurable() -> None:
    assert Config().proxy_dash_media_url is False
    assert Config(proxy_dash_media_url=True).proxy_dash_media_url is True

    with pytest.raises(ValueError, match="unsupported proxy_dash_media_url"):
        Config(proxy_dash_media_url=1)


def test_image_proxy_mode_is_configurable() -> None:
    assert Config().image_proxy_mode is ImageProxyMode.KNOWN
    assert Config(image_proxy_mode="off").image_proxy_mode is ImageProxyMode.OFF
    assert Config(image_proxy_mode="all").image_proxy_mode is ImageProxyMode.ALL

    with pytest.raises(ValueError, match="unsupported image_proxy_mode"):
        Config(image_proxy_mode="some")


def test_cookies_from_browser_rejects_invalid_custom_value() -> None:
    with pytest.raises(ValueError, match="invalid cookies_from_browser"):
        Config(cookies_from_browser={"mode": "custom", "value": "chrome:"})


def test_cookies_from_browser_rejects_value_outside_custom_mode() -> None:
    with pytest.raises(ValueError, match="value is only supported in custom mode"):
        Config(cookies_from_browser={"mode": "firefox_data_dir", "value": "firefox:Profile"})
def test_default_search_provider_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="unsupported default_search_provider"):
        Config(default_search_provider="auto")
def test_site_search_urls_are_extract_search_urls() -> None:
    assert search_urls.is_search_extract_url("https://www.youtube.com/results?search_query=test")
    assert search_urls.is_search_extract_url("https://www.pornhub.com/video/search?search=test")


def test_search_uses_ytdlp_provider_by_default(monkeypatch) -> None:
    service = MediaService(Config(ytdlp_search_limit=2))
    extracted = {}

    async def fail_search_nodes(*args, **kwargs):
        raise AssertionError("bilibili should not be used for default ytdlp search")

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False, use_cookies: bool = True):
        extracted["url"] = url
        return {
            "entries": [
                {
                    "id": "abc123",
                    "webpage_url": "https://www.youtube.com/watch?v=abc123",
                    "title": "YTDLP result",
                }
            ]
        }

    monkeypatch.setattr(service.site_runtime.bilibili.site, "search_nodes", fail_search_nodes)
    monkeypatch.setattr(service, "extract", fake_extract)

    value = asyncio.run(service.search("fallback"))

    assert extracted["url"] == "ytsearch2:fallback"
    assert value["list"][0]["vod_id"] == "https://www.youtube.com/watch?v=abc123"
    assert value["list"][0]["vod_name"] == "YTDLP result"


def test_search_uses_bilibili_site_adapter_when_configured(monkeypatch) -> None:
    service = MediaService(Config(default_search_provider="bilibili", bilibili_search_limit=2))
    called = {}

    async def fake_search_nodes(keyword: str, *, limit: int):
        called["keyword"] = keyword
        called["limit"] = limit
        return [
            MediaNode(
                "https://www.bilibili.com/video/BV1xx411c7mD",
                "Bili result",
                thumbnail="https://example.test/pic.jpg",
                remarks="01:02",
            )
        ]

    def fail_extract(*args, **kwargs):
        raise AssertionError("yt-dlp should not be used for bilisearch")

    monkeypatch.setattr(service.site_runtime.bilibili.site, "search_nodes", fake_search_nodes)
    monkeypatch.setattr(service, "extract", fail_extract)

    value = asyncio.run(service.search(" sample "))

    assert called == {"keyword": "sample", "limit": 2}
    assert value["list"][0]["vod_id"] == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert value["list"][0]["vod_name"] == "Bili result"
    assert value["list"][0]["vod_pic"] == "https://example.test/pic.jpg"


def test_image_proxy_mode_all_proxies_bilibili_search_thumbnails(monkeypatch) -> None:
    service = MediaService(Config(default_search_provider="bilibili", image_proxy_mode="all"))

    async def fake_search_nodes(keyword: str, *, limit: int):
        return [
            MediaNode(
                "https://www.bilibili.com/video/BV1xx411c7mD",
                "Bili result",
                thumbnail="https://i0.hdslb.com/bfs/archive/pic.jpg",
            )
        ]

    monkeypatch.setattr(service.site_runtime.bilibili.site, "search_nodes", fake_search_nodes)

    value = asyncio.run(service.search("sample", base_url="http://testserver"))

    assert value["list"][0]["vod_pic"].startswith("http://testserver/image?")


def test_image_proxy_mode_all_proxies_bilibili_detail_thumbnails(monkeypatch) -> None:
    raw_id = "https://www.bilibili.com/video/BV1xx411c7mD"
    service = MediaService(Config(image_proxy_mode="all"))

    async def fake_detail_node(url: str):
        assert url == raw_id
        return MediaNode(
            raw_id,
            "Bili detail",
            thumbnail="https://i0.hdslb.com/bfs/archive/detail.jpg",
            play_from="yt-dlp",
            play_url=raw_id,
        )

    monkeypatch.setattr(service.site_runtime.bilibili.site, "detail_node", fake_detail_node)

    value = asyncio.run(service.detail(raw_id, base_url="http://testserver"))

    assert value["list"][0]["vod_pic"].startswith("http://testserver/image?")


def test_search_uses_subscription_search_provider_override(monkeypatch) -> None:
    service = MediaService(
        Config(default_search_provider="ytdlp", bilibili_search_limit=30),
        tvbox_overrides={"search_provider": "bilibili", "bilibili_search_limit": 3},
    )
    called = {}

    async def fake_search_nodes(keyword: str, *, limit: int):
        called["keyword"] = keyword
        called["limit"] = limit
        return [MediaNode("https://www.bilibili.com/video/BV1xx411c7mD", "Bili result")]

    def fail_extract(*args, **kwargs):
        raise AssertionError("subscription search_provider should select bilibili")

    monkeypatch.setattr(service.site_runtime.bilibili.site, "search_nodes", fake_search_nodes)
    monkeypatch.setattr(service, "extract", fail_extract)

    asyncio.run(service.search("sample"))

    assert called == {"keyword": "sample", "limit": 3}


def test_search_uses_subscription_ytdlp_prefix_and_limit_override(monkeypatch) -> None:
    service = MediaService(
        Config(ytdlp_search_prefix={"mode": "youtube"}, ytdlp_search_limit=30),
        tvbox_overrides={"ytdlp_search_prefix": {"mode": "soundcloud"}, "ytdlp_search_limit": 4},
    )
    extracted = {}

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False, use_cookies: bool = True):
        extracted["url"] = url
        return {"entries": []}

    monkeypatch.setattr(service, "extract", fake_extract)

    asyncio.run(service.search("music"))

    assert extracted["url"] == "scsearch4:music"
@pytest.mark.parametrize(
    ("configured_limit", "expected_playlist_items"),
    (
        (12, "1-12"),
        (0, f"1-{DEFAULT_YTDLP_SEARCH_LIMIT}"),
    ),
)
def test_youtube_search_url_extract_uses_effective_limit(monkeypatch, configured_limit: int, expected_playlist_items: str) -> None:
    search_url = "https://www.youtube.com/results?search_query=test"
    service = MediaService(Config(ytdlp_search_limit=configured_limit))
    captured = {}

    class FakeYoutubeDL:
        def __init__(self, opts: dict) -> None:
            captured.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def extract_info(self, url: str, download: bool):
            assert url == search_url
            return {"entries": []}

    monkeypatch.setattr(service.ytdlp.yt_dlp, "YoutubeDL", FakeYoutubeDL)

    service.extract_once(search_url, download=False, playlist=True, flat=True)

    assert captured["extract_flat"] == "in_playlist"
    assert captured["playlist_items"] == expected_playlist_items


def test_flat_playlist_extract_uses_default_playlist_limit(monkeypatch) -> None:
    playlist_url = "https://www.youtube.com/@Sample_Channel/videos"
    service = MediaService(Config())
    captured = {}

    class FakeYoutubeDL:
        def __init__(self, opts: dict) -> None:
            captured.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def extract_info(self, url: str, download: bool):
            assert url == playlist_url
            return {"entries": []}

    monkeypatch.setattr(service.ytdlp.yt_dlp, "YoutubeDL", FakeYoutubeDL)

    service.extract_once(playlist_url, download=False, playlist=True, flat=True)

    assert captured["extract_flat"] == "in_playlist"
    assert captured["playlist_items"] == "1-100"
def test_youtube_playlist_extract_uses_reverse_playlist_limit(monkeypatch) -> None:
    playlist_url = "https://www.youtube.com/playlist?list=PL1111111111111111111111111111111111"
    service = MediaService(Config(playlist_limit=300))
    captured = {}

    class FakeYoutubeDL:
        def __init__(self, opts: dict) -> None:
            captured.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def extract_info(self, url: str, download: bool):
            assert url == playlist_url
            return {"entries": []}

    monkeypatch.setattr(service.ytdlp.yt_dlp, "YoutubeDL", FakeYoutubeDL)

    service.extract_once(playlist_url, download=False, playlist=True, flat=True)

    assert captured["extract_flat"] == "in_playlist"
    assert captured["playlist_items"] == "1-300"
    assert "playlistreverse" not in captured
