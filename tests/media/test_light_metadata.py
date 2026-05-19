import asyncio


from dashbox.config import Config
from dashbox.sites import html_metadata
from dashbox.sites import registry
from dashbox.sites.types import MetadataStrategy, SiteMetadataPlan, YtdlpMetadataOptions
from dashbox.models import NodeKind
from tests.helpers import make_tvbox_service as MediaService


def test_spankbang_display_metadata_uses_impersonated_html(monkeypatch) -> None:
    service = MediaService(Config())
    called = False

    def fake_download(url: str) -> str:
        nonlocal called
        called = True
        assert url == "https://spankbang.com/abc-video/title"
        return """
        <meta property="og:title" content="Impersonated Title">
        <meta property="og:image" content="https://spankbang.com/thumb.jpg">
        """

    monkeypatch.setattr(service, "download_webpage_with_ytdlp_impersonation", fake_download)
    monkeypatch.setattr(html_metadata, "html_light_metadata", lambda raw_id, config: (_ for _ in ()).throw(AssertionError("must not use httpx html path")))

    value = asyncio.run(service.metadata.display_metadata("https://spankbang.com/abc-video/title"))

    assert called
    assert value["title"] == "Impersonated Title"
    assert value["thumbnail"] == "https://spankbang.com/thumb.jpg"


def test_display_metadata_is_cached(monkeypatch) -> None:
    service = MediaService(Config())
    url = "https://example.test/watch/1"
    calls: list[str] = []

    async def fake_fetch(raw_id: str) -> dict:
        calls.append(raw_id)
        return {"webpage_url": raw_id, "title": "Display Title"}

    monkeypatch.setattr(service.metadata, "fetch_display_metadata", fake_fetch)

    first = asyncio.run(service.metadata.display_metadata(url))
    second = asyncio.run(service.metadata.display_metadata(url))

    assert first == {"webpage_url": url, "title": "Display Title"}
    assert second == first
    assert calls == [url]
    assert list(service.metadata.display_cache) == [url]


def test_display_metadata_force_refresh_bypasses_cache(monkeypatch) -> None:
    service = MediaService(Config())
    url = "https://example.test/watch/1"
    calls: list[str] = []

    async def fake_fetch(raw_id: str) -> dict:
        calls.append(raw_id)
        return {"webpage_url": raw_id, "title": f"Display Title {len(calls)}"}

    monkeypatch.setattr(service.metadata, "fetch_display_metadata", fake_fetch)

    first = asyncio.run(service.metadata.display_metadata(url))
    cached = asyncio.run(service.metadata.display_metadata(url))
    refreshed = asyncio.run(service.metadata.display_metadata(url, force_refresh=True))

    assert first["title"] == "Display Title 1"
    assert cached["title"] == "Display Title 1"
    assert refreshed["title"] == "Display Title 2"
    assert calls == [url, url]


def test_light_metadata_cache_keeps_youtube_watch_playlist_params_distinct(monkeypatch) -> None:
    service = MediaService(Config())
    canonical_url = "https://www.youtube.com/watch?v=ZzYyXxWw123"
    playlist_item_url = f"{canonical_url}&list=RDsample12345&index=3"
    calls: list[str] = []

    async def fake_fetch(raw_id: str, plan: SiteMetadataPlan, *, force_refresh: bool = False) -> dict:
        calls.append(raw_id)
        return {"webpage_url": raw_id, "title": "Video Title"}

    monkeypatch.setattr(service.metadata, "fetch_light_metadata_for_plan", fake_fetch)
    plan = SiteMetadataPlan(
        node_kind=NodeKind.LEAF_VOD,
        strategy=MetadataStrategy.SINGLE_YTDLP,
        ytdlp=YtdlpMetadataOptions(extract_url=canonical_url, noplaylist=True),
    )

    first = asyncio.run(service.metadata.metadata_for_plan(canonical_url, plan))
    second = asyncio.run(service.metadata.metadata_for_plan(playlist_item_url, plan))

    assert first == {"webpage_url": canonical_url, "title": "Video Title"}
    assert second == {"webpage_url": playlist_item_url, "title": "Video Title"}
    assert calls == [canonical_url, playlist_item_url]
    assert list(service.metadata.light_cache) == [
        service.metadata.plan_cache_key(canonical_url, plan),
        service.metadata.plan_cache_key(playlist_item_url, plan),
    ]


def test_twitch_light_metadata_falls_back_to_ytdlp_when_display_is_empty(monkeypatch) -> None:
    service = MediaService(Config())
    url = "https://www.twitch.tv/videos/100000001"
    calls: list[str] = []

    async def fake_display_metadata(raw_id: str, *, force_refresh: bool = False) -> dict:
        assert raw_id == url
        return {}

    def fake_ytdlp_metadata_for_plan(raw_id: str, plan) -> dict:
        calls.append(raw_id)
        assert plan.ytdlp is not None
        assert plan.ytdlp.extract_url == url
        return {
            "webpage_url": url,
            "id": "v100000001",
            "title": "Real Twitch VOD Title",
            "thumbnail": "https://static-cdn.jtvnw.net/cf_vods/thumb.jpg",
        }

    monkeypatch.setattr(service.metadata, "display_metadata", fake_display_metadata)
    monkeypatch.setattr(service.metadata, "ytdlp_metadata_for_plan", fake_ytdlp_metadata_for_plan)

    plan = registry.resolve(url).metadata_plan_for_config_url(url)
    value = asyncio.run(service.metadata.metadata_for_plan(url, plan))

    assert value["title"] == "Real Twitch VOD Title"
    assert value["thumbnail"] == "https://static-cdn.jtvnw.net/cf_vods/thumb.jpg"
    assert calls == [url]


def test_playlist_light_metadata_uses_in_playlist_flat_extract(monkeypatch) -> None:
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
            return {
                "_type": "playlist",
                "webpage_url": url,
                "title": "Royalty Free Music",
                "thumbnails": [{"url": "https://example.test/thumb.jpg", "width": 100, "height": 100}],
                "playlist_count": 42,
            }

    monkeypatch.setattr(service.ytdlp.yt_dlp, "YoutubeDL", FakeYoutubeDL)

    url = "https://music.youtube.com/browse/VLPL0000000000000000000000000000000000"
    value = service.metadata.ytdlp_metadata_for_plan(url, registry.resolve(url).metadata_plan_for_config_url(url))

    assert captured["extract_flat"] == "in_playlist"
    assert captured["playlist_items"] == "1"
    assert value["title"] == "Royalty Free Music"
    assert value["thumbnail"] == "https://example.test/thumb.jpg"


def test_pornhub_playlist_light_metadata_uses_impersonation(monkeypatch) -> None:
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
            return {"_type": "playlist", "webpage_url": url, "title": "Pornhub Videos"}

    monkeypatch.setattr(service.ytdlp.yt_dlp, "YoutubeDL", FakeYoutubeDL)

    url = "https://www.pornhub.com/video/search?search=test"
    service.metadata.ytdlp_metadata_for_plan(url, registry.resolve(url).metadata_plan_for_config_url(url))

    assert str(captured["impersonate"]) == "chrome"


def test_site_api_metadata_plan_uses_site_api_info(monkeypatch) -> None:
    url = "https://spankbang.com/pl001/playlist/sample+playlist"
    service = MediaService(Config())

    async def fake_site_api_info(raw_url: str, method_name: str) -> dict:
        assert raw_url == url
        assert method_name == "site_api_category_info"
        return {
            "webpage_url": raw_url,
            "title": "Sample Playlist",
            "entries": [
                {"webpage_url": "https://spankbang.com/pl001-item002/playlist/sample+playlist"},
            ],
        }

    monkeypatch.setattr(service, "site_api_info", fake_site_api_info)

    value = asyncio.run(service.metadata.metadata_for_plan(url, registry.resolve(url).metadata_plan_for_config_url(url)))

    assert value["title"] == "Sample Playlist"
    assert value["entries"] == [
        {"webpage_url": "https://spankbang.com/pl001-item002/playlist/sample+playlist"},
    ]


def test_site_api_metadata_plan_falls_back_to_empty_on_failure(monkeypatch) -> None:
    url = "https://spankbang.com/pl001/playlist/sample+playlist"
    service = MediaService(Config())

    async def fake_site_api_info(raw_url: str, method_name: str) -> dict:
        raise RuntimeError("transient site api failure")

    monkeypatch.setattr(service, "site_api_info", fake_site_api_info)

    value = asyncio.run(service.metadata.metadata_for_plan(url, registry.resolve(url).metadata_plan_for_config_url(url)))

    assert value == {}
