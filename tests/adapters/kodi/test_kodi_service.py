import asyncio
import importlib.util
from pathlib import Path

from dashbox import i18n
from dashbox.adapters import kodi_service
from dashbox.adapters.kodi_service import KodiService, kodi_manifest_type
from dashbox.config import Config, KodiSubscriptionConfig, Subscription, UrlItem
from dashbox.core.client_model import ClientItem, ClientPlay
from dashbox.core.client_service import DirectoryRefreshStatus, DirectorySnapshot, DirectorySnapshotResult
from dashbox.core import client_selection
from dashbox.models import MediaEpisode, MediaNode
from dashbox.core.navigation_resolver import ResolvedCategory, ResolvedConfigItem
from dashbox.models import NodeKind


ROOT = Path(__file__).resolve().parents[3]
ROUTING_PATH = ROOT / "dashbox" / "kodi" / "plugin.video.dashbox" / "resources" / "lib" / "routing.py"


def load_plugin_routing():
    spec = importlib.util.spec_from_file_location("dashbox_kodi_plugin_routing_for_service_test", ROUTING_PATH)
    assert spec is not None and spec.loader is not None
    routing = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(routing)
    return routing


def service_with_items(*items):
    subscription = Subscription(
        id="kodi",
        type="kodi",  # type: ignore[arg-type]
        kodi=KodiSubscriptionConfig(sources=items),
    )
    return KodiService(Config(subs=(subscription,)), subscription)


def test_kodi_playable_item_preserves_deferred_subtitle_fields() -> None:
    service = service_with_items()
    item = ClientItem(
        id="https://example.test/watch",
        title="Video",
        subtitle_key="part_count",
        part_count=2,
    )

    playable = service.with_kodi_playable_item(item)

    assert playable.is_playable is True
    assert playable.play_url == "https://example.test/watch"
    assert playable.subtitle_key == "part_count"
    assert playable.part_count == 2


def test_kodi_config_leaf_url_item_is_directly_playable(monkeypatch) -> None:
    item = UrlItem("https://example.test/watch", title="Pinned", id="pinned")
    service = service_with_items(item)

    async def fake_resolve_config_item(_service, item_id, url_item):
        assert url_item is item
        return ResolvedConfigItem(
            MediaNode("node-id", "Remote", node_kind=NodeKind.LEAF_VOD.value),
            source_url=url_item.url,
        )

    monkeypatch.setattr(kodi_service, "resolve_config_item", fake_resolve_config_item)

    page = asyncio.run(service.root_page())

    assert page.items[0].id.startswith("cfg:kodi:root:")
    assert page.items[0].title == "Pinned"
    assert page.items[0].is_folder is False
    assert page.items[0].is_playable is True
    assert page.items[0].play_url == "https://example.test/watch"
    assert page.items[0].node_kind == NodeKind.LEAF_VOD.value


def test_kodi_root_page_appends_search_entry(monkeypatch) -> None:
    item = UrlItem("https://example.test/watch", title="Pinned", id="pinned")
    service = service_with_items(item)

    async def fake_resolve_config_item(_service, item_id, url_item):
        return ResolvedConfigItem(
            MediaNode(url_item.url, "Remote", node_kind=NodeKind.LEAF_VOD.value),
            source_url=url_item.url,
        )

    monkeypatch.setattr(kodi_service, "resolve_config_item", fake_resolve_config_item)

    page = asyncio.run(service.root_page())

    search = page.items[-1]
    assert search.id == ""
    assert search.title == "YouTube 搜索"
    assert search.kind == "search"
    assert search.is_folder is True
    assert search.is_playable is False


def test_kodi_root_search_entry_uses_current_locale() -> None:
    service = service_with_items()

    with i18n.use_locale("en-US"):
        page = asyncio.run(service.root_page())

    assert page.items[-1].title == "YouTube Search"


def test_kodi_root_search_entry_uses_configured_provider_title() -> None:
    subscription = Subscription(
        id="kodi",
        type="kodi",  # type: ignore[arg-type]
        kodi=KodiSubscriptionConfig(
            search_provider="ytdlp",
            ytdlp_search_prefix={"mode": "soundcloud"},
        ),
    )
    service = KodiService(Config(subs=(subscription,)), subscription)

    page = asyncio.run(service.root_page())

    assert page.items[-1].title == "SoundCloud 搜索"


def test_kodi_root_search_entry_uses_bilibili_provider_title() -> None:
    subscription = Subscription(
        id="kodi",
        type="kodi",  # type: ignore[arg-type]
        kodi=KodiSubscriptionConfig(search_provider="bilibili"),
    )
    service = KodiService(Config(subs=(subscription,)), subscription)

    page = asyncio.run(service.root_page())

    assert page.items[-1].title == "Bilibili 搜索"


def test_kodi_search_page_normalizes_leaf_playable_items(monkeypatch) -> None:
    service = service_with_items()

    async def fake_super_search_page(_self, key, base_url="", *, locale=""):
        assert key == "lofi"
        assert base_url == "http://testserver"
        assert locale == "en-US"
        return service.client_page_from_resolved_category(
            ResolvedCategory(
                [
                    MediaNode(
                        "https://example.test/watch",
                        "Video",
                        node_kind=NodeKind.LEAF_VOD.value,
                    )
                ],
            )
        )

    monkeypatch.setattr(kodi_service.ClientService, "search_page", fake_super_search_page)

    page = asyncio.run(service.search_page("lofi", "http://testserver", locale="en-US"))

    item = page.items[0]
    assert item.is_folder is False
    assert item.is_playable is True
    assert item.play_url == "https://example.test/watch"
    assert item.actions[-1].kind == "play"
    assert item.actions[-1].endpoint == "play"


def test_kodi_config_aggregate_url_item_is_not_directly_playable(monkeypatch) -> None:
    item = UrlItem("https://www.bilibili.com/video/BV1xx411c7mD", title="Multi P", id="multi_p")
    service = service_with_items(item)

    async def fake_resolve_config_item(_service, item_id, url_item):
        assert url_item is item
        return ResolvedConfigItem(
            MediaNode(
                "https://www.bilibili.com/video/BV1xx411c7mD",
                "Multi P",
                kind="playlist",
                node_kind=NodeKind.AGGREGATE_VOD.value,
            ),
            source_url=url_item.url,
        )

    monkeypatch.setattr(kodi_service, "resolve_config_item", fake_resolve_config_item)

    page = asyncio.run(service.root_page())

    assert page.items[0].title == "Multi P"
    assert page.items[0].kind == "playlist"
    assert page.items[0].node_kind == NodeKind.AGGREGATE_VOD.value
    assert page.items[0].is_folder is True
    assert page.items[0].is_playable is False
    assert page.items[0].play_url == ""
    assert [action.kind for action in page.items[0].actions] == ["open"]


def test_kodi_config_aggregate_url_item_opens_detail_page(monkeypatch) -> None:
    item = UrlItem("https://www.bilibili.com/video/BV1xx411c7mD", title="Multi P", id="multi_p")
    service = service_with_items(item)
    item_id = service.config_tree.item_id("root", item)
    calls = []

    async def fake_super_detail_page(_self, raw_id, base_url="", *, locale=""):
        calls.append((raw_id, base_url, locale))
        return service.client_page_from_resolved_category(
            ResolvedCategory(
                [
                    MediaNode(
                        raw_id,
                        "Remote Multi P",
                        kind="playlist",
                        thumbnail="https://example.test/thumb.jpg",
                        content="简介",
                        episodes=(
                            MediaEpisode("P01 上", f"{raw_id}?p=1"),
                        ),
                        node_kind=NodeKind.AGGREGATE_VOD.value,
                    )
                ],
            ),
            page_id=raw_id,
        )

    monkeypatch.setattr(kodi_service.ClientService, "detail_page", fake_super_detail_page)

    page = asyncio.run(service.item_page(item_id, "http://testserver"))

    assert calls == [("https://www.bilibili.com/video/BV1xx411c7mD", "http://testserver", "")]
    assert page.id == item_id
    assert page.title == "Multi P"
    assert page.items[0].title == "Remote Multi P"
    assert page.items[0].summary == "简介"
    assert page.items[0].art.thumb == "https://example.test/thumb.jpg"
    assert page.items[0].episodes[0].title == "P01 上"


def test_kodi_config_aggregate_url_item_preserves_leaf_detail_playback(monkeypatch) -> None:
    item = UrlItem("https://www.bilibili.com/video/BV1xx411c7mD", title="Single P", id="single_p")
    service = service_with_items(item)
    item_id = service.config_tree.item_id("root", item)

    async def fake_super_detail_page(_self, raw_id, base_url="", *, locale=""):
        return service.client_page_from_resolved_category(
            ResolvedCategory(
                [
                    MediaNode(
                        raw_id,
                        "Remote Single P",
                        play_url=raw_id,
                        node_kind=NodeKind.LEAF_VOD.value,
                    )
                ],
            ),
            page_id=raw_id,
        )

    monkeypatch.setattr(kodi_service.ClientService, "detail_page", fake_super_detail_page)

    page = asyncio.run(service.item_page(item_id))

    detail_item = page.items[0]
    assert detail_item.title == "Remote Single P"
    assert detail_item.is_folder is False
    assert detail_item.is_playable is True
    assert detail_item.play_url == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert detail_item.actions[-1].kind == "play"
    assert detail_item.actions[-1].endpoint == "play"


def test_kodi_detail_page_normalizes_leaf_playable_items(monkeypatch) -> None:
    service = service_with_items()

    async def fake_super_detail_page(_self, raw_id, base_url="", *, locale=""):
        return service.client_page_from_resolved_category(
            ResolvedCategory(
                [
                    MediaNode(
                        raw_id,
                        "Remote Single P",
                        play_url=raw_id,
                        node_kind=NodeKind.LEAF_VOD.value,
                    )
                ],
            ),
            page_id=raw_id,
        )

    monkeypatch.setattr(kodi_service.ClientService, "detail_page", fake_super_detail_page)

    page = asyncio.run(service.detail_page("https://www.bilibili.com/video/BV1xx411c7mD"))

    detail_item = page.items[0]
    assert detail_item.is_playable is True
    assert detail_item.play_url == "https://www.bilibili.com/video/BV1xx411c7mD"
    assert detail_item.actions[-1].kind == "play"
    assert detail_item.actions[-1].endpoint == "play"


def test_kodi_bilibili_config_multipart_item_uses_site_detail_metadata(monkeypatch) -> None:
    url = "https://www.bilibili.com/video/BV1wx411w7pe/"
    item = UrlItem(url, title="Pinned Bili", id="pinned_bili")
    service = service_with_items(item)
    item_id = service.config_tree.item_id("root", item)

    async def fake_video_metadata(raw_id):
        assert raw_id == url
        return {
            "title": "样例合集",
            "pic": "https://example.test/thumb.jpg",
            "desc": "简介",
            "pages": [
                {"page": 1, "part": "上"},
                {"page": 2, "part": "下"},
            ],
        }

    monkeypatch.setattr(service.site_runtime.bilibili.site, "video_metadata", fake_video_metadata)

    page = asyncio.run(service.item_page(item_id, "http://testserver"))
    payload = service.page_response(page, "http://testserver")
    routed_items = load_plugin_routing().display_items(payload, labels=payload["labels"])

    parent = payload["items"][0]
    assert parent["title"] == "样例合集"
    assert parent["summary"] == "简介"
    assert parent["info"]["plot"] == "简介"
    assert parent["art"]["thumb"] == "https://example.test/thumb.jpg"
    assert [episode["title"] for episode in parent["episodes"]] == ["P01 上", "P02 下"]
    assert [item["title"] for item in routed_items] == ["播放此列表", "P01 上", "P02 下"]
    assert routed_items[1]["art"]["thumb"] == "https://example.test/thumb.jpg"
    assert routed_items[1]["info"]["plot"] == "简介"


def test_kodi_config_directory_url_item_opens_directory_children(monkeypatch) -> None:
    item = UrlItem("https://example.test/playlist", title="Playlist", id="playlist")
    service = service_with_items(item)
    item_id = service.config_tree.item_id("root", item)

    async def fake_directory_snapshot_result(url, *, refresh=False):
        assert url == item.url
        return DirectorySnapshotResult(
            DirectorySnapshot(
                ResolvedCategory(
                    [
                        MediaNode("https://example.test/one", "One"),
                        MediaNode("https://example.test/two", "Two"),
                    ],
                    "Remote playlist",
                ),
                stored_at=0.0,
            ),
            DirectoryRefreshStatus(requested=refresh),
        )

    monkeypatch.setattr(service, "directory_snapshot_result", fake_directory_snapshot_result)

    page = asyncio.run(service.item_page(item_id))

    assert page.id == item_id
    assert page.title == "Playlist"
    assert [item.title for item in page.items] == ["One", "Two"]
    assert [item.play_url for item in page.items] == [
        "https://example.test/one",
        "https://example.test/two",
    ]
    assert all(item.is_playable for item in page.items)


def test_kodi_play_directory_item_is_clickable_command() -> None:
    service = service_with_items()

    page = service.with_kodi_playable_items(
        service.client_page_from_resolved_category(
            ResolvedCategory(
                [MediaNode("https://example.test/one", "One", playlist_url="https://example.test/one?dashbox_index=1")],
                "Remote playlist",
                playlist_url="https://example.test/playlist",
                add_play_directory=True,
                add_playlist_detail_ids=True,
            )
        )
    )

    directory = page.items[0]
    assert directory.selected_url == client_selection.SELECTION_DIRECTORY_SELECTED_URL
    assert directory.is_folder is False
    assert directory.is_playable is True
    assert directory.play_url == ""
    assert directory.actions[-1].endpoint == "play-directory"


def test_kodi_selection_detail_expands_directory_without_ytdlp(monkeypatch) -> None:
    service = service_with_items()
    playlist_url = "https://www.bilibili.com/list/ml139017447"
    raw_id = client_selection.encode_selection_id(
        playlist_url,
        client_selection.SELECTION_DIRECTORY_SELECTED_URL,
        "u-dd34150eb48d9555",
    )

    async def fake_directory_snapshot(url, *, refresh=False):
        assert url == playlist_url
        return DirectorySnapshot(
            ResolvedCategory(
                [
                    MediaNode("https://example.test/one", "One", playlist_url="https://example.test/one?dashbox_index=1"),
                    MediaNode("https://example.test/two", "Two", playlist_url="https://example.test/two?dashbox_index=2"),
                ],
                "Remote playlist",
                playlist_url=playlist_url,
                add_playlist_detail_ids=True,
            ),
            stored_at=0.0,
        )

    async def fail_super_detail(*_args, **_kwargs):
        raise AssertionError("selection detail should not fall through to yt-dlp detail")

    monkeypatch.setattr(service, "directory_snapshot", fake_directory_snapshot)
    monkeypatch.setattr(kodi_service.ClientService, "detail_page", fail_super_detail)

    page = asyncio.run(service.detail_page(raw_id))

    assert page.id == playlist_url
    assert len(page.items) == 1
    item = page.items[0]
    assert item.selected_url == client_selection.SELECTION_DIRECTORY_SELECTED_URL
    assert [(episode.title, episode.url) for episode in item.episodes] == [
        ("One", "https://example.test/one?dashbox_index=1"),
        ("Two", "https://example.test/two?dashbox_index=2"),
    ]


def test_kodi_play_response_marks_dash_for_inputstream_adaptive() -> None:
    service = service_with_items()

    value = service.play_response(
        ClientPlay(
            url="http://testserver/media/session/manifest.mpd",
            mime_type="application/dash+xml",
            headers={"User-Agent": "UA"},
        )
    )

    assert value["inputstream"]["addon"] == "inputstream.adaptive"
    assert value["inputstream"]["manifest_type"] == "mpd"
    assert value["inputstream"]["manifest_headers"] == {"User-Agent": "UA"}
    assert value["inputstream"]["stream_headers"] == {"User-Agent": "UA"}


def test_kodi_manifest_type_detects_hls_variants() -> None:
    assert kodi_manifest_type("https://example.test/master.m3u8?token=1") == "hls"
    assert kodi_manifest_type("https://example.test/stream", "application/vnd.apple.mpegurl") == "hls"
