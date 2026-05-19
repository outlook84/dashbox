from dashbox.models import NodeKind
from dashbox.core.media_service import MediaService
from dashbox.sites import bilibili, generic, pornhub, registry, twitch, youtube
from dashbox.sites.types import MetadataStrategy


def test_registry_resolves_known_sites_and_generic_fallback() -> None:
    assert registry.resolve("https://www.youtube.com/watch?v=AbCdEfGh123") is youtube
    assert registry.resolve("https://www.bilibili.com/video/BV1xx411c7mD") is bilibili
    assert registry.resolve("https://www.pornhub.com/model/sample_model") is pornhub
    assert registry.resolve("https://www.twitch.tv/videos/100000001") is twitch
    assert registry.resolve("https://example.test/watch/1") is generic


def test_youtube_playlist_config_url_uses_playlist_ytdlp_plan() -> None:
    plan = youtube.metadata_plan_for_config_url("PL0000000000000000000000000000000000")

    assert plan.node_kind == NodeKind.PLAYLIST_DIRECTORY
    assert plan.strategy == MetadataStrategy.PLAYLIST_YTDLP
    assert plan.canonical_url == "https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000"
    assert plan.ytdlp is not None
    assert plan.ytdlp.extract_url == "https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000"
    assert plan.ytdlp.noplaylist is False
    assert plan.ytdlp.extract_flat == "in_playlist"
    assert plan.ytdlp.playlist_items == "1"


def test_youtube_single_config_url_uses_display_plan() -> None:
    plan = youtube.metadata_plan_for_config_url("https://youtu.be/AbCdEfGh123")

    assert plan.node_kind == NodeKind.LEAF_VOD
    assert plan.strategy == MetadataStrategy.DISPLAY
    assert plan.ytdlp is None


def test_bilibili_single_config_url_uses_single_ytdlp_plan() -> None:
    plan = bilibili.metadata_plan_for_config_url("https://www.bilibili.com/opus/500000000000000001")

    assert plan.node_kind == NodeKind.LEAF_VOD
    assert plan.strategy == MetadataStrategy.SINGLE_YTDLP
    assert plan.ytdlp is not None
    assert plan.ytdlp.extract_url == "https://www.bilibili.com/opus/500000000000000001"
    assert plan.ytdlp.noplaylist is True
    assert plan.ytdlp.process is True


def test_bilibili_collection_config_url_uses_site_api_plan() -> None:
    plan = bilibili.metadata_plan_for_config_url("https://www.bilibili.com/bangumi/play/ss2493")

    assert plan.node_kind == NodeKind.PLAYLIST_DIRECTORY
    assert plan.strategy == MetadataStrategy.SITE_API
    assert plan.ytdlp is None


def test_generic_config_url_uses_display_or_none_plan() -> None:
    assert generic.metadata_plan_for_config_url("https://example.test/videos").strategy == MetadataStrategy.DISPLAY
    assert generic.metadata_plan_for_config_url(":ytfav").strategy == MetadataStrategy.NONE


def test_media_service_node_kind_uses_site_plan() -> None:
    assert MediaService.node_kind_from_config_url("https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000") == NodeKind.PLAYLIST_DIRECTORY
    assert MediaService.node_kind_from_config_url("https://www.bilibili.com/video/BV1xx411c7mD") == NodeKind.AGGREGATE_VOD
    assert MediaService.node_kind_from_config_url("https://www.pornhub.com/model/sample_model") == NodeKind.PLAYLIST_DIRECTORY
    assert MediaService.node_kind_from_config_url("https://example.test/watch/1") == NodeKind.LEAF_VOD
