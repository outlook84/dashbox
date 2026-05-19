import asyncio

from dashbox.config import Config
from dashbox.core.site_runtime import SiteRuntimeRegistry
from dashbox.media.ytdlp_client import YtdlpClient


def make_runtime() -> SiteRuntimeRegistry:
    return SiteRuntimeRegistry(Config(), YtdlpClient(Config()))


def test_playable_extract_url_skips_runtime_for_unknown_urls(monkeypatch) -> None:
    runtime = make_runtime()

    async def fail_resolve_extract_url(_url: str) -> str:
        raise AssertionError("unknown URLs should not use Bilibili runtime")

    monkeypatch.setattr(runtime.bilibili.site, "resolve_extract_url", fail_resolve_extract_url)

    assert asyncio.run(runtime.playable_extract_url("https://example.test/watch/1")) == ""
    assert runtime.blocking_playable_extract_url("https://example.test/watch/1") == "https://example.test/watch/1"


def test_playable_extract_url_dispatches_bilibili_urls(monkeypatch) -> None:
    runtime = make_runtime()
    calls = []

    async def fake_resolve_extract_url(url: str) -> str:
        calls.append(url)
        return "https://www.bilibili.com/video/av1?p=2"

    monkeypatch.setattr(runtime.bilibili.site, "resolve_extract_url", fake_resolve_extract_url)

    value = asyncio.run(runtime.playable_extract_url("https://player.bilibili.com/player.html?aid=1&cid=2"))

    assert calls == ["https://player.bilibili.com/player.html?aid=1&cid=2"]
    assert value == "https://www.bilibili.com/video/av1?p=2"
