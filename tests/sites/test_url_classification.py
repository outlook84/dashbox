import asyncio
import pytest

from dashbox.config import Config
from dashbox.config import UrlItem
from dashbox.sites import bilibili
from dashbox.sites import pornhub
from dashbox.sites import spankbang
from dashbox.sites import twitch
from dashbox.sites import xvideos
from dashbox.sites import youtube
from dashbox.models import NodeKind
from tests.helpers import make_tvbox_service as MediaService, patch_metadata_for_plan



async def url_item_client_vod(service: MediaService, item_id: str, item: UrlItem) -> dict:
    return service.vod_from_client_item(await service.url_item_client_item(item_id, item))

def test_youtube_canonical_single_video_url_removes_playlist_query() -> None:
    assert youtube.canonical_single_video_url("https://www.youtube.com/watch?v=ZzYyXxWw123&list=RDabc&index=3") == (
        "https://www.youtube.com/watch?v=ZzYyXxWw123"
    )
    assert youtube.canonical_single_video_url("https://youtu.be/AbCdEfGh123?list=PLabc") == "https://www.youtube.com/watch?v=AbCdEfGh123"
    assert youtube.canonical_single_video_url("https://example.test/watch?v=AbCdEfGh123") == "https://example.test/watch?v=AbCdEfGh123"


@pytest.mark.parametrize(
    ("url", "kind"),
    (
        ("https://www.youtube.com/", "folder"),
        ("https://www.youtube.com/results?search_query=test", "search"),
        ("https://www.youtube.com/hashtag/sampletag", "folder"),
        ("https://www.youtube.com/feed/subscriptions", "folder"),
        ("https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000", "playlist"),
        ("https://www.youtube.com/playlist?list=RDsample12345", ""),
        ("https://www.youtube.com/@Sample_Channel", "folder"),
        ("https://www.youtube.com/@Sample_Channel/videos", "folder"),
        ("https://www.youtube.com/@Sample_Channel/playlists", "folder"),
        ("https://music.youtube.com/search?q=sample", "search"),
        ("https://music.youtube.com/channel/UC0000000000000000000000", "folder"),
        ("https://music.youtube.com/browse/VLPL0000000000000000000000000000000000", "folder"),
        ("https://music.youtube.com/playlist?list=PL0000000000000000000000000000000000", "playlist"),
        ("https://www.youtubekids.com/channel/UC0000000000000000000000", "folder"),
        ("https://www.youtubekids.com/search?q=sample", ""),
        ("https://www.youtubekids.com/results?search_query=sample", ""),
        ("https://example.test/@Sample_Channel/videos", ""),
    ),
)
def test_youtube_folder_url_kind_classifies_directory_urls(url: str, kind: str) -> None:
    assert youtube.folder_url_kind(url) == kind


def test_youtube_collection_and_search_entry_behavior() -> None:
    playlist_url = "https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000"
    search_url = "https://www.youtube.com/results?search_query=test"

    assert youtube.collection_url_kind(search_url) == ""
    assert youtube.search_entry_kind({"url": search_url}) == "search"
    assert youtube.collection_url_kind(playlist_url) == "playlist"
def test_bare_youtube_playlist_id_config_item_uses_playlist_metadata(monkeypatch) -> None:
    service = MediaService(Config())
    captured = {}

    async def fake_playlist_light_metadata(raw_id: str) -> dict:
        captured["url"] = raw_id
        return {
            "webpage_url": raw_id,
            "title": "Playlist Title",
            "playlist_count": 3,
        }

    patch_metadata_for_plan(monkeypatch, service, playlist=fake_playlist_light_metadata)

    value = asyncio.run(url_item_client_vod(service, "item-1", UrlItem(url="PL0000000000000000000000000000000000")))

    assert captured["url"] == "https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000"
    assert value["vod_id"] == "item-1"
    assert value["vod_name"] == "Playlist Title"
    assert value["vod_remarks"] == "3项"


def test_url_item_watch_with_playlist_parameter_prefers_single_video(monkeypatch) -> None:
    service = MediaService(Config())

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        raise AssertionError("watch URL with list parameter should not run full playlist extraction")

    async def fake_light_metadata(raw_id: str) -> dict:
        assert raw_id == "https://www.youtube.com/watch?v=AbCdEfGh123"
        return {
            "webpage_url": raw_id,
            "title": "Single Video",
        }

    monkeypatch.setattr(service, "extract", fake_extract)
    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)

    value = asyncio.run(url_item_client_vod(
        service,
        "item-1",
        UrlItem(url="https://www.youtube.com/watch?list=PL0000000000000000000000000000000000&v=AbCdEfGh123"),
    ))

    assert value["vod_id"] == "item-1"
    assert value["vod_name"] == "Single Video"
def test_site_host_matching_rejects_lookalike_domains() -> None:
    assert not youtube.is_url("https://notyoutube.com/watch?v=AbCdEfGh123")
    assert not xvideos.is_single_video_url("https://notxvideos.com/video123/title")
    assert not spankbang.matches_url("https://evilspankbang.com/abc/video/title")
    assert not pornhub.matches_url("https://notpornhub.com/view_video.php?viewkey=abc")
    assert not bilibili.is_video_url("https://example.test/watch?next=https://www.bilibili.com/video/BV4xx411c7mD")


def test_xvideos_single_video_url_variants_match_ytdlp_shapes() -> None:
    assert xvideos.is_single_video_url("https://xvideos2.com/video90000001/title")
    assert xvideos.is_single_video_url("https://www.xvideos.es/video90000001/title")
    assert xvideos.is_single_video_url("https://flashservice.xvideos.com/embedframe/90000001")
    assert xvideos.is_single_video_url("http://static-hw.xvideos.com/swf/xv-player.swf?id_video=90000001")
    assert xvideos.is_single_video_url("https://www.xvideos.com/profiles/name#quickies/a/samplequickie1")


def test_pornhub_single_video_url_matches_ytdlp_shapes() -> None:
    assert pornhub.is_single_video_url("https://www.pornhub.com/view_video.php?viewkey=ph0000000000001")
    assert pornhub.is_single_video_url("https://www.pornhub.com/video/show?viewkey=600000001")
    assert pornhub.is_single_video_url("https://www.pornhub.com/embed/ph0000000000001")
    assert not pornhub.is_single_video_url("https://www.pornhub.com/view_video.php?viewkey=中文")
    assert not pornhub.is_single_video_url("https://www.pornhub.com/model/sample_model")
    assert not pornhub.is_single_video_url("https://www.pornhub.com/video/search?search=123")
    assert not pornhub.is_single_video_url("https://www.pornhub.com/categories/sample-category")


def test_twitch_single_playable_urls_match_ytdlp_shapes() -> None:
    assert twitch.is_single_playable_url("https://www.twitch.tv/videos/100000001")
    assert twitch.is_single_playable_url("https://www.twitch.tv/samplechannel/v/100000001?t=5m10s")
    assert twitch.is_single_playable_url("https://www.twitch.tv/samplechannel/schedule?vodID=100000002")
    assert twitch.is_single_playable_url("https://player.twitch.tv/?video=v100000001")
    assert twitch.is_single_playable_url("https://clips.twitch.tv/SampleClipSlug")
    assert twitch.is_single_playable_url("https://www.twitch.tv/samplechannel/clip/SampleNestedClipSlug-abc123")
    assert twitch.is_single_playable_url("https://www.twitch.tv/samplechannel")
    assert twitch.is_single_playable_url("https://player.twitch.tv/?channel=samplechannel")
    assert not twitch.is_single_playable_url("https://notwitch.tv/videos/100000001")
    assert not twitch.is_single_playable_url("https://www.twitch.tv/samplechannel/videos?filter=all")
    assert not twitch.is_single_playable_url("https://www.twitch.tv/collections/SampleCollectionSlug")


def test_bilibili_single_playable_urls_are_site_owned() -> None:
    assert bilibili.is_single_playable_url("https://www.bilibili.com/video/av10000002")
    assert bilibili.is_single_playable_url("https://www.bilibili.com/festival/2023honkaiimpact3gala?bvid=BV5xx411c7mD")
    assert bilibili.is_single_playable_url("https://www.bilibili.com/bangumi/play/ep30000001")
    assert bilibili.is_single_playable_url("https://www.bilibili.com/cheese/play/ep30000002")
    assert bilibili.is_single_playable_url("https://www.bilibili.com/audio/au40000001")
    assert bilibili.is_single_playable_url("https://www.bilibili.com/opus/500000000000000001")
    assert bilibili.is_single_playable_url("https://player.bilibili.com/player.html?aid=10000001&cid=20000001&page=1")
    assert not bilibili.is_single_playable_url("http://www.bilibili.tv/video/av10000001/")
    assert bilibili.is_single_playable_url("https://t.bilibili.com/500000000000000001")
    assert not bilibili.is_single_playable_url("https://www.bilibili.com/watchlater/#/list")


def test_pornhub_collection_urls_are_config_directories() -> None:
    assert pornhub.config_node_kind("https://www.pornhub.com/model/sample_model") == NodeKind.PLAYLIST_DIRECTORY
    assert pornhub.config_node_kind("https://www.pornhub.com/pornstar/sample-star/videos/upload") == NodeKind.PLAYLIST_DIRECTORY
    assert pornhub.config_node_kind("https://www.pornhub.com/video") == NodeKind.PLAYLIST_DIRECTORY
    assert pornhub.config_node_kind("https://www.pornhub.com/playlist/44000001") == NodeKind.PLAYLIST_DIRECTORY
    assert pornhub.config_node_kind("https://www.pornhub.com/view_video.php?viewkey=ph0000000000001") is None


def test_twitch_config_urls_use_site_classification() -> None:
    assert twitch.config_node_kind("https://www.twitch.tv/samplechannel/videos?filter=all") == NodeKind.PLAYLIST_DIRECTORY
    assert twitch.config_node_kind("https://www.twitch.tv/samplechannel/videos?filter=archives") == NodeKind.PLAYLIST_DIRECTORY
    assert twitch.config_node_kind("https://www.twitch.tv/samplechannel/clips?filter=clips&range=all") == NodeKind.PLAYLIST_DIRECTORY
    assert twitch.config_node_kind("https://www.twitch.tv/samplechannel/videos?filter=collections") == NodeKind.PLAYLIST_DIRECTORY
    assert twitch.config_node_kind("https://www.twitch.tv/collections/SampleCollectionSlug") == NodeKind.PLAYLIST_DIRECTORY
    assert twitch.config_node_kind("https://www.twitch.tv/videos/100000001") == NodeKind.LEAF_VOD
    assert twitch.config_node_kind("https://www.twitch.tv/samplechannel") == NodeKind.LEAF_VOD
    assert twitch.config_node_kind("https://www.twitch.tv/directory/category/sample-category") is None
    assert twitch.config_node_kind("https://www.twitch.tv/search?term=sample-query") is None


def test_twitch_playlist_collection_info_matches_collection_entries() -> None:
    info = {
        "entries": [
            {
                "_type": "url_transparent",
                "ie_key": "TwitchCollection",
                "url": "https://www.twitch.tv/collections/abc",
                "title": "Collection A",
            },
            {
                "_type": "url_transparent",
                "ie_key": "TwitchCollection",
                "url": "https://www.twitch.tv/collections/def",
                "title": "Collection B",
            },
        ],
    }

    assert twitch.is_playlist_collection_info(info)
    assert not twitch.is_playlist_collection_info({
        "entries": [
            {
                "_type": "url",
                "ie_key": "TwitchVod",
                "url": "https://www.twitch.tv/videos/100000001",
                "title": "Video",
            },
        ],
    })


def test_spankbang_playlist_video_urls_are_known_single_urls() -> None:
    assert spankbang.is_playlist_video_url(
        "https://spankbang.com/pl001-item001/playlist/sample+playlist?dashbox_index=21"
    )


def test_pornhub_title_from_url_uses_collection_shape() -> None:
    assert pornhub.title_from_url("https://www.pornhub.com/video") == "Pornhub Videos"
    assert pornhub.title_from_url("https://www.pornhub.com/video/search?search=sample+query") == "Pornhub 搜索: sample query"
    assert pornhub.is_search_url("https://www.pornhub.com/video/search?search=sample+query")
    assert not pornhub.is_search_url("https://www.pornhub.com/video")
    assert pornhub.title_from_url("https://www.pornhub.com/categories/sample-category") == "Pornhub Category: sample category"
    assert pornhub.title_from_url("https://www.pornhub.com/model/sample_model") == "Pornhub Model: sample model"
    assert pornhub.title_from_url("https://www.pornhub.com/pornstar/sample-star-two") == "Pornhub Pornstar: sample star two"
    assert pornhub.title_from_url("https://www.pornhub.com/playlist/44000001") == "Pornhub Playlist 44000001"
    assert pornhub.title_from_url("https://www.pornhub.com/view_video.php?viewkey=ph0000000000001") == ""

