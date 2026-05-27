import asyncio


from dashbox.models import NodeKind
from dashbox.sites import bilibili
from tests.sites.bilibili.helpers import FAVLIST_URL


def test_favlist_url_is_detected_like_yt_dlp_favorites() -> None:
    assert bilibili.is_favorites_url(FAVLIST_URL)
    assert bilibili.favorites_id_from_url(FAVLIST_URL) == "139017447"
    assert not bilibili.is_medialist_url(FAVLIST_URL)

    detail_url = "https://www.bilibili.com/medialist/detail/ml139017447"
    assert bilibili.is_favorites_url(detail_url)
    assert bilibili.favorites_id_from_url(detail_url) == "139017447"


def test_single_playable_urls_match_yt_dlp_shapes() -> None:
    assert bilibili.is_single_playable_url("https://www.bilibili.com/video/BV1xx411c7mD")
    assert bilibili.is_single_playable_url("https://www.bilibili.com/video/av10000002")
    assert bilibili.is_single_playable_url("https://www.bilibili.com/festival/2023honkaiimpact3gala?bvid=BV5xx411c7mD")
    assert bilibili.is_single_playable_url("https://www.bilibili.com/bangumi/play/ep30000001")
    assert bilibili.is_single_playable_url("https://www.bilibili.com/cheese/play/ep30000002")
    assert bilibili.is_single_playable_url("https://www.bilibili.com/audio/au40000001")
    assert bilibili.is_single_playable_url("https://www.bilibili.com/opus/500000000000000001")
    assert bilibili.is_single_playable_url("https://player.bilibili.com/player.html?aid=10000001&cid=20000001&page=1")
    assert bilibili.is_single_playable_url("https://t.bilibili.com/500000000000000001")
    assert bilibili.is_single_playable_url("https://live.bilibili.com/196")
    assert bilibili.is_single_playable_url("https://live.bilibili.com/blanc/196")

    assert not bilibili.is_single_playable_url("https://example.test/watch?next=https://www.bilibili.com/video/BV4xx411c7mD")
    assert not bilibili.is_single_playable_url("https://player.bilibili.com/player.html?aid=abc")
    assert not bilibili.is_single_playable_url("http://www.bilibili.tv/video/av10000001/")
    assert not bilibili.is_single_playable_url("https://www.bilibili.com/bangumi/play/ss2493")
    assert not bilibili.is_single_playable_url("https://www.bilibili.com/audio/am80000001")
    assert not bilibili.is_single_playable_url("https://live.bilibili.com/abc")
    assert not bilibili.is_single_playable_url("https://b23.tv/BV1xx411c7mD")


def test_bilibili_live_config_entry_is_leaf_vod() -> None:
    assert bilibili.config_node_kind("https://live.bilibili.com/196") == NodeKind.LEAF_VOD
    assert bilibili.config_node_kind("https://live.bilibili.com/blanc/196") == NodeKind.LEAF_VOD


def test_bilibili_playlist_url_shapes_match_yt_dlp_extractors() -> None:
    assert bilibili.config_node_kind("https://www.bilibili.com/bangumi/play/ss2493") == NodeKind.PLAYLIST_DIRECTORY
    assert bilibili.config_node_kind("https://www.bilibili.com/bangumi/media/md24097891") == NodeKind.PLAYLIST_DIRECTORY
    assert bilibili.config_node_kind("https://www.bilibili.com/cheese/play/ss5918") == NodeKind.PLAYLIST_DIRECTORY
    assert bilibili.config_node_kind("https://www.bilibili.com/watchlater") == NodeKind.PLAYLIST_DIRECTORY
    assert bilibili.config_node_kind("https://www.bilibili.com/v/kichiku/mad") == NodeKind.PLAYLIST_DIRECTORY
    assert bilibili.config_node_kind("https://www.bilibili.com/c/dance") == NodeKind.PLAYLIST_DIRECTORY
    assert bilibili.config_node_kind("https://www.bilibili.com/v/food") == NodeKind.PLAYLIST_DIRECTORY
    assert bilibili.config_node_kind("https://www.bilibili.com/audio/am80000001") == NodeKind.PLAYLIST_DIRECTORY
    assert bilibili.config_node_kind("https://space.bilibili.com/60000001/channel/collectiondetail?sid=70000001") == NodeKind.PLAYLIST_DIRECTORY
    assert bilibili.config_node_kind("https://space.bilibili.com/60000001/lists/3662502") == NodeKind.PLAYLIST_DIRECTORY
    assert bilibili.config_node_kind("https://space.bilibili.com/60000002/channel/seriesdetail?sid=70000002&ctype=0") == NodeKind.PLAYLIST_DIRECTORY
    assert bilibili.config_node_kind("https://space.bilibili.com/60000002/lists/70000002?type=series") == NodeKind.PLAYLIST_DIRECTORY
    assert bilibili.config_node_kind("https://space.bilibili.com/60000004") == NodeKind.PLAYLIST_DIRECTORY
    assert bilibili.config_node_kind("https://space.bilibili.com/60000004/video") == NodeKind.PLAYLIST_DIRECTORY
    assert bilibili.config_node_kind("https://space.bilibili.com/60000004/upload/video") == NodeKind.PLAYLIST_DIRECTORY
    assert bilibili.config_node_kind("https://space.bilibili.com/60000003/audio") == NodeKind.PLAYLIST_DIRECTORY
    assert bilibili.config_node_kind("https://space.bilibili.com/60000003/upload/audio") == NodeKind.PLAYLIST_DIRECTORY
    selected_medialist_url = "https://www.bilibili.com/medialist/play/ml123/BV1xx411c7mD"
    assert bilibili.config_node_kind(selected_medialist_url) == NodeKind.PLAYLIST_DIRECTORY
    assert bilibili.medialist_ids_from_url(selected_medialist_url) == {"type": 3, "biz_id": "123"}

    assert not bilibili.is_single_playable_url("https://www.bilibili.com/bangumi/media/md24097891")
    assert not bilibili.is_single_playable_url("https://www.bilibili.com/cheese/play/ss5918")
    assert not bilibili.is_single_playable_url("https://www.bilibili.com/audio/am80000001")
    assert not bilibili.is_medialist_url("https://www.bilibili.com/list/watchlater")


def test_bilibili_search_url_is_playlist_directory() -> None:
    url = "https://search.bilibili.com/video?keyword=sample"

    assert bilibili.is_search_url(url)
    assert bilibili.search_keyword_from_url(url) == "sample"
    assert bilibili.config_node_kind(url) == NodeKind.PLAYLIST_DIRECTORY


def test_bilibili_category_nodes_returns_none_for_unsupported_url() -> None:
    site = bilibili.BilibiliSite()

    assert asyncio.run(site.category_nodes("https://www.bilibili.com/video/BV1xx411c7mD")) is None
    assert asyncio.run(site.category_nodes("https://example.test/watch?v=1")) is None



def test_bilibili_space_list_urls_are_classified_by_type() -> None:
    collection_url = "https://space.bilibili.com/60000001/lists/3662502"
    season_url = "https://space.bilibili.com/60000001/lists/3662502?type=season"
    series_url = "https://space.bilibili.com/60000002/lists/70000002?type=series"

    assert bilibili.space_collection_ids_from_url(collection_url) == {"mid": "60000001", "sid": "3662502"}
    assert bilibili.space_collection_ids_from_url(season_url) == {"mid": "60000001", "sid": "3662502"}
    assert bilibili.space_series_ids_from_url(series_url) == {"mid": "60000002", "sid": "70000002"}
    assert bilibili.space_collection_ids_from_url(series_url) == {}
    assert bilibili.space_series_ids_from_url(collection_url) == {}
    assert bilibili.space_video_mid_from_url("https://space.bilibili.com/60000004") == "60000004"
    assert bilibili.space_video_mid_from_url("https://space.bilibili.com/60000004/video") == "60000004"
    assert bilibili.space_video_mid_from_url("https://space.bilibili.com/60000004/upload/video") == "60000004"
    assert bilibili.space_video_mid_from_url("https://space.bilibili.com/60000004/dynamic") == ""
    assert bilibili.space_audio_mid_from_url("https://space.bilibili.com/60000003/upload/audio") == "60000003"


def test_bilibili_playlist_url_detection_requires_matching_host_path() -> None:
    external_urls = [
        "https://example.test/?next=https://www.bilibili.com/bangumi/play/ss2493",
        "https://example.test/?next=https://www.bilibili.com/bangumi/media/md24097891",
        "https://example.test/?next=https://www.bilibili.com/cheese/play/ss5918",
        "https://example.test/?next=https://www.bilibili.com/audio/am80000001",
        "https://example.test/?next=https://www.bilibili.com/list/ml139017447",
        "https://example.test/?next=https://space.bilibili.com/207902747/favlist?fid=139017447",
    ]
    for url in external_urls:
        assert bilibili.config_node_kind(url) is None
        assert not bilibili.is_supported_short_url_target(url)

    assert not bilibili.is_bangumi_season_url(external_urls[0])
    assert not bilibili.is_bangumi_media_url(external_urls[1])
    assert not bilibili.is_cheese_season_url(external_urls[2])
    assert not bilibili.is_audio_album_url(external_urls[3])
    assert bilibili.bangumi_season_id_from_url(external_urls[0]) == ""
    assert bilibili.bangumi_media_id_from_url(external_urls[1]) == ""
    assert bilibili.cheese_season_id_from_url(external_urls[2]) == ""
    assert bilibili.audio_album_id_from_url(external_urls[3]) == ""
    assert not bilibili.is_medialist_url(external_urls[4])
    assert bilibili.medialist_ids_from_url(external_urls[4]) == {}
    assert not bilibili.is_favorites_url(external_urls[5])
    assert bilibili.favorites_id_from_url(external_urls[5]) == ""



def test_bilibili_dynamic_light_metadata_urls_need_processing() -> None:
    assert bilibili.ytdlp_light_metadata_needs_processing("https://t.bilibili.com/500000000000000001")
    assert bilibili.ytdlp_light_metadata_needs_processing("https://www.bilibili.com/opus/500000000000000001")

    assert not bilibili.ytdlp_light_metadata_needs_processing("https://www.bilibili.com/video/BV1xx411c7mD")
    assert not bilibili.ytdlp_light_metadata_needs_processing("https://example.test/opus/500000000000000001")


def test_bilibili_video_playlist_info_is_aggregate_vod() -> None:
    info = {
        "_type": "playlist",
        "webpage_url": "https://www.bilibili.com/video/BV1xx411c7mD",
        "entries": [{"title": "P01 开场"}],
    }

    assert bilibili.playlist_info_node_kind(info) == NodeKind.AGGREGATE_VOD
    assert bilibili.playlist_info_node_kind({"_type": "playlist"}, "https://example.test/list") is None


def test_bilibili_player_url_preserves_cid_when_page_resolution_fails() -> None:
    site = bilibili.BilibiliSite()
    player_url = "https://player.bilibili.com/player.html?aid=10000001&cid=20000002"

    async def fake_video_metadata(url: str) -> dict:
        return {"pages": [{"page": 1, "cid": 20000001}]}

    site.video_metadata = fake_video_metadata

    value = asyncio.run(site.resolve_extract_url(player_url))

    assert value == player_url


def test_bilibili_api_metadata_support_rejects_non_bilibili_urls() -> None:
    assert bilibili.supports_video_api_metadata("https://www.bilibili.com/video/BV1xx411c7mD")
    assert bilibili.supports_video_api_metadata("https://www.bilibili.com/video/av10000002")
    assert bilibili.supports_video_api_metadata("https://player.bilibili.com/player.html?aid=10000001")

    assert not bilibili.supports_video_api_metadata("https://example.test/video/av10000002")
    assert not bilibili.supports_video_api_metadata(
        "https://example.test/watch?next=https://www.bilibili.com/video/BV4xx411c7mD"
    )


