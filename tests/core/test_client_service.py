import asyncio

from dashbox.config import Config, FolderItem, SearchProvider, Source, UrlItem
from dashbox.core import client_selection
from dashbox.core.client_service import ClientService
from dashbox.models import MediaNode
from dashbox.core.navigation_resolver import ResolvedCategory
from dashbox.media.scope import PlaybackScope
from dashbox.sites.types import MetadataStrategy
from tests.helpers import patch_metadata_for_plan


def test_home_page_returns_protocol_neutral_source_items() -> None:
    service = ClientService(
        Config(),
        "sub",
        (
            Source("main", "Main", (UrlItem("https://example.test/video", id="video"),)),
            Source("more", "More", ()),
        ),
    )

    page = service.home_page()

    assert page.total_items == 2
    assert [item.id for item in page.items] == ["main", "more"]
    assert [item.title for item in page.items] == ["Main", "More"]
    assert all(item.kind == "folder" for item in page.items)
    assert all(item.is_folder for item in page.items)
    assert page.items[0].actions[0].endpoint == "items"
    assert not hasattr(page.items[0], "type_flag")


def test_item_page_expands_config_items_to_protocol_neutral_items(monkeypatch) -> None:
    url = "https://www.youtube.com/watch?v=AbCdEfGh123"
    service = ClientService(
        Config(),
        "sub",
        (
            Source("main", "Main", (
                UrlItem(url, title="Pinned", remarks="Manual", id="pinned"),
                FolderItem("Folder", (UrlItem("https://example.test/nested", id="nested"),), id="folder"),
            )),
        ),
    )

    async def fake_light_metadata(raw_id: str) -> dict:
        assert raw_id == url
        return {
            "webpage_url": raw_id,
            "title": "Remote title",
            "thumbnail": "https://example.test/thumb.jpg",
        }

    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)

    page = asyncio.run(service.item_page("main"))

    assert page.id == "main"
    assert page.title == "Main"
    first, second = page.items
    assert first.title == "Pinned"
    assert first.subtitle == "Manual"
    assert first.is_folder is False
    assert second.title == "Folder"
    assert second.is_folder is True
    assert not hasattr(first, "vod_id")


def test_resolved_category_page_adds_selection_items() -> None:
    service = ClientService(Config(), "sub", ())
    page = service.client_page_from_resolved_category(
        ResolvedCategory(
            [
                MediaNode(
                    "https://example.test/watch?v=1",
                    "First",
                    playlist_name="Episode 1",
                    playlist_url="https://example.test/watch?v=1&dashbox_index=1",
                ),
            ],
            "Playlist",
            playlist_url="https://example.test/playlist",
            add_play_directory=True,
            add_playlist_detail_ids=True,
        )
    )

    directory, first = page.items
    assert directory.id.startswith(client_selection.SELECTION_ID_PREFIX)
    assert directory.selected_url == client_selection.SELECTION_DIRECTORY_SELECTED_URL
    assert directory.title == ""
    assert directory.subtitle == ""
    assert directory.item_count == 1
    assert first.id.startswith(client_selection.SELECTION_ID_PREFIX)
    assert first.playlist_url == "https://example.test/playlist"
    assert first.selected_url == "https://example.test/watch?v=1&dashbox_index=1"
    assert first.playlist_title == "Episode 1"


def test_playlist_detail_page_preserves_matched_selected_url() -> None:
    service = ClientService(Config(), "sub", ())
    page = service.client_page_from_resolved_category(
        ResolvedCategory(
            [
                MediaNode(
                    "https://example.test/watch?v=1",
                    "First",
                    playlist_name="Episode 1",
                    playlist_url="https://example.test/watch?v=1&dashbox_index=1",
                ),
            ],
            "Playlist",
            playlist_url="https://example.test/playlist",
            add_playlist_detail_ids=True,
        )
    )

    detail = service.client_playlist_detail_page(
        page,
        "https://example.test/playlist",
        "https://example.test/watch?v=1",
    )

    item = detail.items[0]
    assert item.selected_url == "https://example.test/watch?v=1&dashbox_index=1"
    assert item.episodes[0].url == "https://example.test/watch?v=1&dashbox_index=1"
    assert not hasattr(item, "vod_play_url")


def test_resolved_detail_page_marks_leaf_playable_url() -> None:
    service = ClientService(Config(), "sub", ())
    page = service.client_page_from_resolved_detail(
        ResolvedCategory(
            [MediaNode("https://example.test/watch", "Video")],
            leaf_playable_url="https://cdn.example.test/video.mp4",
        )
    )

    item = page.items[0]
    assert item.is_playable is True
    assert item.play_url == "https://cdn.example.test/video.mp4"
    assert item.actions[-1].kind == "play"


def test_resolved_detail_page_represents_unavailable_url() -> None:
    service = ClientService(Config(), "sub", ())
    page = service.client_page_from_resolved_detail(
        ResolvedCategory([], unavailable_url="https://example.test/missing")
    )

    item = page.items[0]
    assert item.kind == "error"
    assert item.id == "https://example.test/missing"
    assert item.subtitle == ""
    assert item.subtitle_key == "unavailable"


def test_search_page_returns_url_item_without_protocol_fields() -> None:
    service = ClientService(Config(), "sub", ())

    page = asyncio.run(service.search_page("https://example.test/watch"))

    assert page.total_items == 1
    item = page.items[0]
    assert item.id == "https://example.test/watch"
    assert item.subtitle == "URL"
    assert not hasattr(item, "vod_id")


def test_detail_page_uses_site_detail_node(monkeypatch) -> None:
    service = ClientService(Config(), "sub", ())

    async def fake_site_detail_node(raw_id: str) -> MediaNode:
        assert raw_id == "https://example.test/detail"
        return MediaNode(raw_id, "Detail")

    monkeypatch.setattr(service, "site_detail_node", fake_site_detail_node)

    page = asyncio.run(service.detail_page("https://example.test/detail"))

    assert page.id == "https://example.test/detail"
    assert page.items[0].title == "Detail"
    assert not hasattr(page.items[0], "vod_id")


def test_url_item_detail_page_reuses_cached_display_metadata(monkeypatch) -> None:
    url = "https://example.test/watch"
    service = ClientService(Config(), "sub", ())

    async def fake_metadata_for_plan(raw_id: str, plan, *, force_refresh: bool = False) -> dict:
        if plan.strategy == MetadataStrategy.PLAYLIST_YTDLP:
            assert raw_id == url
            return {}
        return {}

    async def fake_fetch_display_metadata(raw_id: str) -> dict:
        assert raw_id == url
        return {
            "webpage_url": raw_id,
            "title": "Remote",
            "thumbnail": "https://example.test/thumb.jpg",
        }

    monkeypatch.setattr(service.metadata, "metadata_for_plan", fake_metadata_for_plan)
    monkeypatch.setattr(service.metadata, "fetch_display_metadata", fake_fetch_display_metadata)

    asyncio.run(service.url_item_client_item("item-1", UrlItem(url, title="Manual")))
    page = asyncio.run(service.url_item_detail_page(UrlItem(url, title="Manual")))

    item = page.items[0]
    assert item.title == "Manual"
    assert item.play_url == url
    assert item.art.thumb == "https://example.test/thumb.jpg"
    assert not hasattr(item, "vod_id")


def test_search_page_uses_site_search_nodes_for_bilibili(monkeypatch) -> None:
    service = ClientService(Config(default_search_provider=SearchProvider.BILIBILI), "sub", ())

    async def fake_site_search_nodes(key: str) -> list[MediaNode]:
        assert key == "query"
        return [MediaNode("https://example.test/result", "Result")]

    monkeypatch.setattr(service, "site_search_nodes", fake_site_search_nodes)

    page = asyncio.run(service.search_page(" query "))

    assert page.total_items == 1
    assert page.items[0].title == "Result"


def test_client_play_from_info_returns_protocol_neutral_play() -> None:
    service = ClientService(Config(), "sub", ())

    play = asyncio.run(service.client_play_from_info(
        {
            "title": "Playable",
            "http_headers": {"User-Agent": "UA"},
            "formats": [
                {
                    "url": "https://cdn.example.test/video.mp4",
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                    "ext": "mp4",
                    "http_headers": {"Referer": "https://example.test/"},
                },
            ],
            "subtitles": {
                "en": [
                    {"url": "https://cdn.example.test/en.vtt", "ext": "vtt"},
                ],
            },
        },
        "https://example.test/watch",
    ))

    assert play.url == "https://cdn.example.test/video.mp4"
    assert play.title == "Playable"
    assert play.headers == {"User-Agent": "UA", "Referer": "https://example.test/"}
    assert play.subtitles[0].url == "https://cdn.example.test/en.vtt"
    assert play.subtitles[0].format == "vtt"
    assert not hasattr(play, "parse")


def test_client_play_from_info_uses_youtube_automatic_original_captions_with_scope() -> None:
    service = ClientService(Config(), "sub", ())

    play = asyncio.run(service.client_play_from_info(
        {
            "extractor_key": "Youtube",
            "title": "Playable",
            "formats": [
                {
                    "url": "https://cdn.example.test/video.mp4",
                    "vcodec": "avc1",
                    "acodec": "mp4a",
                    "ext": "mp4",
                },
            ],
            "automatic_captions": {
                "en-orig": [
                    {"url": "https://cdn.example.test/en.srt", "ext": "srt"},
                ],
            },
        },
        "https://www.youtube.com/watch?v=AbCdEfGh123",
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="sub",
            subtitle_languages=("zh-CN",),
            youtube_subtitles=True,
        ),
    ))

    assert play.subtitles[0].language == "en-orig"
    assert play.subtitles[0].url == "https://cdn.example.test/en.srt"
