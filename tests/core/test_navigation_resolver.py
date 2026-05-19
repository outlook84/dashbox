import asyncio

from dashbox.config import Config, UrlItem
from dashbox.models import NodeKind
from dashbox.core.navigation_resolver import resolve_config_item, resolve_url_category, resolve_url_detail
from tests.helpers import make_tvbox_service, patch_metadata_for_plan


def test_resolve_config_item_returns_playlist_directory_node(monkeypatch) -> None:
    url = "https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000"
    service = make_tvbox_service(Config())

    async def fake_playlist_light_metadata(raw_url: str) -> dict:
        assert raw_url == url
        return {
            "webpage_url": raw_url,
            "title": "Discover the World",
            "playlist_count": 12,
        }

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata)

    resolved = asyncio.run(resolve_config_item(service, "cfg:main:item", UrlItem(url)))

    assert resolved.directory is True
    assert resolved.source_url == url
    assert resolved.node.id == url
    assert resolved.node.title == "Discover the World"
    assert resolved.node.kind == "playlist"
    assert resolved.node.remarks == ""
    assert resolved.node.remarks_key == "item_count"
    assert resolved.node.item_count == 12


def test_resolve_config_item_uses_html_metadata_for_unknown_urls(monkeypatch) -> None:
    url = "https://www.tnaflix.com/amateur-porn/example/video9944644"
    service = make_tvbox_service(Config())

    async def fake_playlist_light_metadata(raw_url: str) -> dict:
        assert raw_url == url
        return {}

    async def fake_display_metadata(raw_url: str) -> dict:
        assert raw_url == url
        return {
            "webpage_url": raw_url,
            "title": "Example Scene",
            "thumbnail": "https://example.test/thumb.jpg",
            "duration_string": "1:23",
        }

    async def fake_light_metadata(raw_url: str) -> dict:
        raise AssertionError("generic config URL should not run a second single-video metadata probe")

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata, fallback=False)
    monkeypatch.setattr(service.metadata, "display_metadata", fake_display_metadata)

    resolved = asyncio.run(resolve_config_item(service, "cfg:main:item", UrlItem(url)))

    assert resolved.directory is False
    assert resolved.node.id == url
    assert resolved.node.title == "Example Scene"
    assert resolved.node.thumbnail == "https://example.test/thumb.jpg"
    assert resolved.node.remarks == "1:23"


def test_resolve_config_item_keeps_url_item_overrides_out_of_core(monkeypatch) -> None:
    url = "https://www.youtube.com/watch?v=AbCdEfGh123"
    service = make_tvbox_service(Config())

    async def fake_light_metadata(raw_url: str) -> dict:
        assert raw_url == url
        return {
            "webpage_url": raw_url,
            "title": "Remote title",
            "thumbnail": "https://example.test/remote.jpg",
        }

    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)

    resolved = asyncio.run(resolve_config_item(
        service,
        "cfg:main:item",
        UrlItem(url, title="Manual title", pic="https://example.test/manual.jpg", remarks="Pinned"),
    ))

    assert resolved.node.title == "Remote title"
    assert resolved.node.thumbnail == "https://example.test/remote.jpg"
    assert resolved.node.remarks == ""


def test_resolve_url_category_returns_playlist_directory_nodes(monkeypatch) -> None:
    playlist_url = "https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000"
    service = make_tvbox_service(Config())

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        assert url == playlist_url
        assert download is False
        assert playlist is True
        assert flat is True
        return {
            "_type": "playlist",
            "title": "Discover the World",
            "entries": [
                {
                    "webpage_url": "https://www.youtube.com/watch?v=111",
                    "title": "First",
                    "thumbnail": "https://example.test/first.jpg",
                },
                {
                    "webpage_url": "https://www.youtube.com/watch?v=222",
                    "title": "Second",
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    resolved = asyncio.run(resolve_url_category(service, playlist_url))

    assert resolved.name == "Discover the World"
    assert resolved.playlist_url == playlist_url
    assert resolved.add_play_directory is True
    assert resolved.add_playlist_detail_ids is True
    assert [node.title for node in resolved.nodes] == ["First", "Second"]
    assert [node.playlist_name for node in resolved.nodes] == ["First", "Second"]


def test_resolve_spankbang_category_uses_site_playlist_info(monkeypatch) -> None:
    playlist_url = "https://spankbang.com/pl002/playlist/sample+collection"
    service = make_tvbox_service(Config())

    def fake_extract(*args, **kwargs):
        raise AssertionError("spankbang playlist should not use generic yt-dlp flat extraction")

    async def fake_site_api_info(url: str, method_name: str) -> dict:
        assert url == playlist_url
        assert method_name == "site_api_category_info"
        return {
            "extractor_key": "SpankBangPlaylist",
            "title": "Layla Jenner",
            "webpage_url": url,
            "entries": [
                {
                    "_type": "url",
                    "ie_key": "SpankBang",
                    "id": "item003",
                    "url": "https://spankbang.com/pl002-item003/playlist/sample+collection",
                    "webpage_url": "https://spankbang.com/pl002-item003/playlist/sample+collection",
                    "title": "First",
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)
    monkeypatch.setattr(service, "site_api_info", fake_site_api_info)

    resolved = asyncio.run(resolve_url_category(service, playlist_url))

    assert resolved.name == "Layla Jenner"
    assert resolved.playlist_url == playlist_url
    assert resolved.add_play_directory is True
    assert resolved.add_playlist_detail_ids is True
    assert [node.playlist_name for node in resolved.nodes] == ["First"]


def test_resolve_spankbang_config_item_uses_site_playlist_metadata(monkeypatch) -> None:
    playlist_url = "https://spankbang.com/pl001/playlist/sample+playlist"
    service = make_tvbox_service(Config())

    async def fake_site_api_info(url: str, method_name: str) -> dict:
        assert url == playlist_url
        assert method_name == "site_api_category_info"
        return {
            "extractor_key": "SpankBangPlaylist",
            "title": "Sample Playlist",
            "webpage_url": url,
            "entries": [
                {
                    "_type": "url",
                    "ie_key": "SpankBang",
                    "id": "item002",
                    "url": "https://spankbang.com/pl001-item002/playlist/sample+playlist",
                    "webpage_url": "https://spankbang.com/pl001-item002/playlist/sample+playlist",
                    "title": "First",
                },
            ],
        }

    monkeypatch.setattr(service, "site_api_info", fake_site_api_info)

    resolved = asyncio.run(resolve_config_item(service, "cfg:main:item", UrlItem(playlist_url)))

    assert resolved.directory is True
    assert resolved.node.id == playlist_url
    assert resolved.node.title == "Sample Playlist"
    assert resolved.node.kind == "playlist"


def test_resolve_url_category_returns_unavailable_result_when_extraction_fails(monkeypatch) -> None:
    url = "https://www.youtube.com/@Sample_Channel/streams"
    service = make_tvbox_service(Config())

    def fake_extract(raw_url: str, *, download: bool, playlist: bool, flat: bool = False):
        raise RuntimeError("tab missing")

    monkeypatch.setattr(service, "extract", fake_extract)

    resolved = asyncio.run(resolve_url_category(service, url))

    assert resolved.nodes == []
    assert resolved.name == url
    assert resolved.unavailable_url == url


def test_resolve_url_detail_returns_playlist_directory_result(monkeypatch) -> None:
    playlist_url = "https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000"
    service = make_tvbox_service(Config())

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        assert url == playlist_url
        assert download is False
        assert playlist is True
        assert flat is True
        return {
            "_type": "playlist",
            "title": "Discover the World",
            "entries": [
                {
                    "webpage_url": "https://www.youtube.com/watch?v=111",
                    "title": "First",
                },
                {
                    "webpage_url": "https://www.youtube.com/watch?v=222",
                    "title": "Second",
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    resolved = asyncio.run(resolve_url_detail(service, playlist_url))

    assert resolved.playlist_url == playlist_url
    assert resolved.add_play_directory is True
    assert resolved.add_playlist_detail_ids is True
    assert [node.playlist_url for node in resolved.nodes] == [
        "https://www.youtube.com/watch?v=111&dashbox_index=1",
        "https://www.youtube.com/watch?v=222&dashbox_index=2",
    ]


def test_resolve_url_detail_does_not_cache_flat_playlist_probe(monkeypatch) -> None:
    url = "https://example.test/collection"
    service = make_tvbox_service(Config())
    calls = []

    def fake_extract(raw_url: str, *, download: bool, playlist: bool, flat: bool = False):
        calls.append(raw_url)
        assert raw_url == url
        assert download is False
        assert playlist is True
        assert flat is True
        return {
            "_type": "playlist",
            "title": "Cached Collection",
            "webpage_url": url,
            "entries": [
                {
                    "webpage_url": "https://example.test/watch/1",
                    "title": "First",
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    first = asyncio.run(resolve_url_detail(service, url))
    second = asyncio.run(resolve_url_detail(service, url))

    assert calls == [url, url]
    assert [node.title for node in first.nodes] == ["First"]
    assert [node.title for node in second.nodes] == ["First"]


def test_flat_playlist_probe_survives_cancelled_waiter(monkeypatch) -> None:
    url = "https://example.test/collection"
    service = make_tvbox_service(Config())
    started = asyncio.Event()
    release = asyncio.Event()
    calls = []

    async def fake_extract_flat_playlist_info(
        raw_url: str,
        extract_url: str = "",
        flat_playlist_items: str = "",
    ) -> dict:
        calls.append(raw_url)
        started.set()
        await release.wait()
        return {
            "_type": "playlist",
            "title": "Cached Collection",
            "webpage_url": raw_url,
            "entries": [
                {
                    "webpage_url": "https://example.test/watch/1",
                    "title": "First",
                },
            ],
        }

    monkeypatch.setattr(service, "extract_flat_playlist_info", fake_extract_flat_playlist_info)

    async def run() -> None:
        first = asyncio.create_task(service.extract_flat_playlist_info_async(url))
        await started.wait()
        second = asyncio.create_task(service.extract_flat_playlist_info_async(url))
        first.cancel()
        try:
            await first
        except asyncio.CancelledError:
            pass
        release.set()
        value = await second
        assert value["title"] == "Cached Collection"
        await asyncio.sleep(0)

    asyncio.run(run())

    assert calls == [url]


def test_flat_playlist_probe_does_not_cache_completed_values(monkeypatch) -> None:
    url = "https://www.twitch.tv/samplechannel/videos?filter=all"
    service = make_tvbox_service(Config())
    calls = []

    async def fake_extract_flat_playlist_info(
        raw_url: str,
        extract_url: str = "",
        flat_playlist_items: str = "",
    ) -> dict:
        calls.append(raw_url)
        return {
            "_type": "playlist",
            "title": "Cached Twitch Videos",
            "webpage_url": raw_url,
            "entries": [
                {
                    "webpage_url": "https://www.twitch.tv/videos/100000001",
                    "title": "First",
                },
            ],
        }

    monkeypatch.setattr(service, "extract_flat_playlist_info", fake_extract_flat_playlist_info)

    async def run() -> None:
        first = await service.extract_flat_playlist_info_async(url)
        await asyncio.sleep(0)
        second = await service.extract_flat_playlist_info_async(url)
        assert first["title"] == "Cached Twitch Videos"
        assert second["title"] == "Cached Twitch Videos"

    asyncio.run(run())

    assert calls == [url, url]


def test_resolve_twitch_collections_category_returns_directory_nodes(monkeypatch) -> None:
    playlist_url = "https://www.twitch.tv/samplecollection/videos?filter=collections"
    service = make_tvbox_service(Config())

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        assert url == playlist_url
        assert download is False
        assert playlist is True
        assert flat is True
        return {
            "_type": "playlist",
            "title": "Sample Collection - Collections",
            "webpage_url": playlist_url,
            "entries": [
                {
                    "_type": "url_transparent",
                    "ie_key": "TwitchCollection",
                    "url": "https://www.twitch.tv/collections/abc",
                    "webpage_url": "https://www.twitch.tv/collections/abc",
                    "title": "Collection A",
                    "thumbnail": "https://static-cdn.jtvnw.net/cf_vods/abc.jpg",
                },
                {
                    "_type": "url_transparent",
                    "ie_key": "TwitchCollection",
                    "url": "https://www.twitch.tv/collections/def",
                    "webpage_url": "https://www.twitch.tv/collections/def",
                    "title": "Collection B",
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    resolved = asyncio.run(resolve_url_category(service, playlist_url))

    assert resolved.name == "Sample Collection - Collections"
    assert resolved.playlist_url == ""
    assert resolved.add_play_directory is False
    assert resolved.add_playlist_detail_ids is False
    assert resolved.directory_node_ids == (
        "https://www.twitch.tv/collections/abc",
        "https://www.twitch.tv/collections/def",
    )
    assert [node.title for node in resolved.nodes] == ["Collection A", "Collection B"]


def test_twitch_collection_playlist_info_has_collection_directory_kind() -> None:
    service = make_tvbox_service(Config())
    info = {
        "_type": "playlist",
        "entries": [
            {
                "_type": "url_transparent",
                "ie_key": "TwitchCollection",
                "url": "https://www.twitch.tv/collections/abc",
                "title": "Collection A",
            },
        ],
    }

    assert service.node_kind_from_playlist_info(
        info,
        "https://www.twitch.tv/samplecollection/videos?filter=collections",
    ) == NodeKind.COLLECTION_DIRECTORY
