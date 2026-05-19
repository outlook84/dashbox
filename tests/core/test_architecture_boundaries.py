import asyncio

from dashbox.config import DEFAULT_USER_AGENT, Config
from dashbox.core import config_tree, display_metadata_runtime, image_policy, media_mapper, search_urls, site_runtime
from dashbox.media import segment_base, ytdlp_client
from dashbox.models import NodeKind


def test_config_tree_canonical_url_uses_registry_normalizer(monkeypatch) -> None:
    calls: list[str] = []

    def fake_normalize(url: str) -> str:
        calls.append(url)
        return "https://example.test/watch?dashbox_index=2&v=1"

    monkeypatch.setattr(config_tree.registry, "normalize_config_url", fake_normalize)

    assert config_tree.ConfigTree.canonical_url("youtube:abc") == "https://example.test/watch?v=1"
    assert calls == ["youtube:abc"]


def test_site_runtime_registry_builds_and_dispatches_registered_runtimes(monkeypatch) -> None:
    class FakeRuntime:
        name = "fake"

        def __init__(self, config, ytdlp, *, http_client_provider=None):
            self.config = config
            self.ytdlp = ytdlp
            self.http_client_provider = http_client_provider

        def supports_url(self, url: str) -> bool:
            return url.startswith("fake:")

        async def playable_extract_url(self, raw_id: str, extract_url: str = "") -> str:
            return "extract:" + raw_id

        def blocking_playable_extract_url(self, raw_id: str, extract_url: str = "") -> str:
            return "blocking:" + raw_id

        async def normalize_config_url(self, url: str) -> str:
            return url.replace("fake:", "normalized:")

    monkeypatch.setattr(site_runtime.registry, "runtime_factories", lambda: (FakeRuntime,))

    runtime_registry = site_runtime.SiteRuntimeRegistry(Config(), object(), http_client_provider=lambda: object())

    assert runtime_registry.runtime_for_url("fake:item").name == "fake"
    assert runtime_registry.runtime_for_url("https://example.test") is None
    assert asyncio.run(runtime_registry.playable_extract_url("fake:item")) == "extract:fake:item"
    assert runtime_registry.blocking_playable_extract_url("fake:item") == "blocking:fake:item"
    assert asyncio.run(runtime_registry.normalize_config_url("fake:item")) == "normalized:item"
    assert asyncio.run(runtime_registry.normalize_config_url("https://example.test")) == "https://example.test"


def test_display_metadata_runtime_uses_registry_selected_adapter(monkeypatch) -> None:
    adapter = object()
    captured: dict[str, object] = {}

    async def fake_display_metadata(raw_id: str, **kwargs):
        captured["raw_id"] = raw_id
        captured["kwargs"] = kwargs
        return {"title": "from adapter"}

    monkeypatch.setattr(display_metadata_runtime.registry, "resolve", lambda raw_id: adapter)
    monkeypatch.setattr(
        display_metadata_runtime.registry,
        "default_callable",
        lambda selected, name: fake_display_metadata if selected is adapter and name == "display_metadata" else None,
    )

    runtime = display_metadata_runtime.DisplayMetadataRuntime(
        Config(),
        download_impersonated=lambda url: "",
        http_client_provider=lambda: object(),
    )

    assert asyncio.run(runtime.fetch("site://video")) == {"title": "from adapter"}
    assert captured["raw_id"] == "site://video"
    assert callable(captured["kwargs"]["html_metadata"])
    assert callable(captured["kwargs"]["impersonated_html_metadata"])


def test_media_mapper_uses_registry_adapter_hooks(monkeypatch) -> None:
    adapter = object()
    info = {"webpage_url": "fake://raw", "title": "Title", "thumbnail": "thumb.jpg"}

    monkeypatch.setattr(media_mapper.registry, "resolve_info", lambda value, fallback_url="": adapter)
    monkeypatch.setattr(media_mapper.registry, "call", lambda selected, name, *args: "fake://normalized")
    monkeypatch.setattr(media_mapper.registry, "default_callable", lambda selected, name: lambda value, url="": "fake-thumb.jpg")
    monkeypatch.setattr(media_mapper.image_policy, "proxied_thumbnail_url", lambda url, base_url, mode: f"{base_url}/{url}")

    node = media_mapper.node_from_info(info, base_url="http://dashbox")

    assert node.id == "fake://normalized"
    assert node.thumbnail == "http://dashbox/fake-thumb.jpg"
    assert node.node_kind == NodeKind.LEAF_VOD.value


def test_search_url_detection_combines_registry_and_ytdlp_prefixes(monkeypatch) -> None:
    calls: list[str] = []

    def fake_is_extract_search_url(url: str) -> bool:
        calls.append(url)
        return url == "site-search:cats"

    monkeypatch.setattr(search_urls.registry, "is_extract_search_url", fake_is_extract_search_url)

    assert search_urls.is_search_extract_url("site-search:cats") is True
    assert search_urls.is_search_extract_url("ytsearch5:cats") is True
    assert search_urls.is_search_extract_url("https://example.test/watch") is False
    assert calls == ["site-search:cats", "ytsearch5:cats", "https://example.test/watch"]


def test_segment_base_headers_include_registry_site_headers(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_headers_for_format_urls(urls: list[str]) -> dict[str, str]:
        calls.append(urls)
        return {"Referer": "https://site.example.test/"}

    monkeypatch.setattr(segment_base.registry, "headers_for_format_urls", fake_headers_for_format_urls)

    headers = segment_base.headers_for_format(
        {"http_headers": {"User-Agent": "custom"}},
        {"url": "https://cdn.example.test/video.mp4"},
    )

    assert headers["Referer"] == "https://site.example.test/"
    assert headers["User-Agent"] == "custom"
    assert calls == [["https://cdn.example.test/video.mp4"]]


def test_ytdlp_flat_playlist_enrichment_uses_registry_contract(monkeypatch) -> None:
    enriched: dict[str, object] = {}
    client = ytdlp_client.YtdlpClient(Config(playlist_limit=7, ytdlp_concurrency=3))

    monkeypatch.setattr(ytdlp_client.registry, "supports_flat_playlist_info", lambda info: True)
    monkeypatch.setattr(client, "download_webpage_with_impersonation", lambda url: "<html>playlist</html>")

    def fake_enrich_flat_playlist_info(info, webpage, url, **kwargs) -> bool:
        enriched.update(info=info, webpage=webpage, url=url, kwargs=kwargs)
        return True

    monkeypatch.setattr(ytdlp_client.registry, "enrich_flat_playlist_info", fake_enrich_flat_playlist_info)

    info = {"webpage_url": "https://site.example.test/playlist"}
    client.enrich_flat_playlist_info(info)

    assert enriched["info"] is info
    assert enriched["webpage"] == "<html>playlist</html>"
    assert enriched["url"] == "https://site.example.test/playlist"
    assert enriched["kwargs"]["limit"] == 7
    assert enriched["kwargs"]["concurrency"] == 3


def test_image_policy_uses_registry_for_proxyable_urls_and_referers(monkeypatch) -> None:
    monkeypatch.setattr(image_policy.registry, "image_url_is_proxyable", lambda url: url == "https://img.example.test/a.jpg")
    monkeypatch.setattr(image_policy.registry, "image_referer_for_url", lambda url: "https://source.example.test/")

    assert image_policy.is_proxyable_thumbnail_url("https://img.example.test/a.jpg") is True
    assert image_policy.is_proxyable_thumbnail_url("https://other.example/a.jpg") is False
    assert image_policy.with_image_headers("https://img.example.test/a.jpg") == (
        f"https://img.example.test/a.jpg@Referer=https://source.example.test/@User-Agent={DEFAULT_USER_AGENT}"
    )
