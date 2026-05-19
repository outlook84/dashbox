import asyncio
import json

import pytest

import dashbox.server.app as server
from dashbox.server.images import scope_image_urls
from dashbox.adapters.tvbox_service import TvboxService
from dashbox.config import (
    AudioCodec,
    AuthMode,
    CodecPreference,
    Config,
    KodiSubscriptionConfig,
    SearchProvider,
    Subscription,
    SubscriptionType,
    Source,
    TvboxLocale,
    TvboxSubscriptionConfig,
    UrlItem,
    VideoCodec,
    VodStyle,
    YtdlpSearchPrefixMode,
    load_config,
)
from dashbox.core import image_proxy
from dashbox.core.config_tree import ConfigTree
from tests.helpers import no_lifespan_test_client


def tvbox_sub(
    sub_id: str,
    *,
    source_id: str = "main",
    site_key: str = "dashbox",
    site_name: str | None = None,
    locale: str = "zh-CN",
    video_enabled_order: tuple[str | VideoCodec, ...] = (
        VideoCodec.H264,
        VideoCodec.HEVC,
        VideoCodec.VP9,
        VideoCodec.AV01,
    ),
    audio_enabled_order: tuple[str | AudioCodec, ...] = (
        AudioCodec.AAC,
        AudioCodec.OPUS,
        AudioCodec.EAC3,
        AudioCodec.AC3,
        AudioCodec.FLAC,
        AudioCodec.OTHER,
    ),
    max_video_height: int = 0,
    max_video_fps: int = 0,
    vod_style: str = "list",
) -> Subscription:
    return Subscription(
        id=sub_id,
        type="tvbox",
        tvbox=TvboxSubscriptionConfig(
            site_key=site_key,
            site_name=site_name or sub_id.title(),
            locale=locale,
            sources=(Source(source_id, "Main", (UrlItem("https://example.test/a", id="a"),)),),
            video_codec_preferences=codec_preferences(video_enabled_order, (
                VideoCodec.H264,
                VideoCodec.HEVC,
                VideoCodec.VP9,
                VideoCodec.AV01,
            )),
            audio_codec_preferences=codec_preferences(audio_enabled_order, (
                AudioCodec.AAC,
                AudioCodec.OPUS,
                AudioCodec.EAC3,
                AudioCodec.AC3,
                AudioCodec.FLAC,
                AudioCodec.OTHER,
            )),
            max_video_height=max_video_height,
            max_video_fps=max_video_fps,
            vod_style=vod_style,
        ),
    )


def codec_preferences(enabled_order, all_codecs):
    enabled = {codec_value(codec) for codec in enabled_order}
    ordered = [*enabled_order, *(codec for codec in all_codecs if codec_value(codec) not in enabled)]
    return tuple(CodecPreference(codec, codec_value(codec) in enabled) for codec in ordered)


def codec_preferences_json(enabled_order, all_codecs):
    enabled = {codec_value(codec) for codec in enabled_order}
    ordered = [*enabled_order, *(codec for codec in all_codecs if codec_value(codec) not in enabled)]
    return [{"codec": codec_value(codec), "enabled": codec_value(codec) in enabled} for codec in ordered]


def codec_value(codec):
    return codec.value if hasattr(codec, "value") else str(codec)


def kodi_sub(sub_id: str) -> Subscription:
    return Subscription(id=sub_id, type="kodi", kodi=KodiSubscriptionConfig(root={"items": []}))


def test_valid_multi_sub_config_parses(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {
                "id": "main",
                "type": "tvbox",
                "auth_mode": "anonymous",
                "tvbox": {
                    "site_key": "dashbox",
                    "site_name": "Dashbox",
                    "sources": [{"id": "youtube", "name": "YouTube", "items": [{"id": "a", "url": "https://example.test/a"}]}],
                },
            },
            {"id": "kodi-main", "type": "kodi", "auth_mode": "anonymous", "kodi": {"root": {"items": []}}},
        ]
    }), encoding="utf-8")

    config = load_config(str(path))

    assert [sub.id for sub in config.subs] == ["main", "kodi-main"]
    assert config.subs[0].type is SubscriptionType.TVBOX
    assert config.subs[0].auth_mode is AuthMode.ANONYMOUS
    assert config.subs[1].type is SubscriptionType.KODI
    assert config.subs[0].tvbox.sources[0].id == "youtube"


def test_kodi_subscription_sources_allow_root_url_items(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {
                "id": "kodi-main",
                "type": "kodi",
                "auth_mode": "anonymous",
                "kodi": {
                        "sources": [
                            {"id": "pinned", "url": "https://example.test/a", "title": "Pinned"},
                            {"id": "folder", "name": "Folder", "items": [{"id": "nested", "url": "https://example.test/b"}]},
                    ],
                },
            },
        ],
    }), encoding="utf-8")

    config = load_config(str(path))
    sub = config.subs[0]

    assert isinstance(sub.kodi.sources[0], UrlItem)
    assert sub.kodi.sources[0].title == "Pinned"
    assert sub.kodi.sources[0].id == "pinned"
    assert sub.kodi.sources[1].name == "Folder"


def test_kodi_subscription_search_and_resource_limits_parse_from_config(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {
                "id": "kodi-main",
                "type": "kodi",
                "auth_mode": "anonymous",
                "kodi": {
                    "sources": [],
                    "search_provider": "bilibili",
                    "ytdlp_search_prefix": {"mode": "soundcloud"},
                    "ytdlp_search_limit": 12,
                    "bilibili_search_limit": 13,
                    "playlist_limit": 14,
                    "bilibili_list_limit": 15,
                },
            },
        ],
    }), encoding="utf-8")

    config = load_config(str(path))
    kodi_config = config.subs[0].kodi

    assert kodi_config.search_provider is SearchProvider.BILIBILI
    assert kodi_config.ytdlp_search_prefix.mode is YtdlpSearchPrefixMode.SOUNDCLOUD
    assert kodi_config.ytdlp_search_limit == 12
    assert kodi_config.bilibili_search_limit == 13
    assert kodi_config.playlist_limit == 14
    assert kodi_config.bilibili_list_limit == 15


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("ytdlp_search_limit", 201),
        ("bilibili_search_limit", 201),
        ("playlist_limit", 1001),
        ("bilibili_list_limit", 1001),
        ("playlist_limit", -1),
        ("playlist_limit", True),
    ),
)
def test_kodi_subscription_rejects_invalid_resource_limits(tmp_path, field: str, value: object) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {
                "id": "kodi-main",
                "type": "kodi",
                "auth_mode": "anonymous",
                "kodi": {
                    "sources": [],
                    field: value,
                },
            },
        ],
    }), encoding="utf-8")

    with pytest.raises(ValueError, match=f"kodi.{field}"):
        load_config(str(path))


def test_tvbox_subscription_search_overrides_parse_from_config(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {
                "id": "main",
                "type": "tvbox",
                "auth_mode": "anonymous",
                "tvbox": {
                    "site_key": "dashbox",
                    "search_provider": "bilibili",
                    "ytdlp_search_prefix": {"mode": "soundcloud"},
                    "ytdlp_search_limit": 12,
                    "bilibili_search_limit": 13,
                    "playlist_limit": 14,
                    "bilibili_list_limit": 15,
                    "sources": [],
                },
            },
        ],
    }), encoding="utf-8")

    config = load_config(str(path))
    tvbox_config = config.subs[0].tvbox

    assert tvbox_config.search_provider is SearchProvider.BILIBILI
    assert tvbox_config.ytdlp_search_prefix.mode is YtdlpSearchPrefixMode.SOUNDCLOUD
    assert tvbox_config.ytdlp_search_limit == 12
    assert tvbox_config.bilibili_search_limit == 13
    assert tvbox_config.playlist_limit == 14
    assert tvbox_config.bilibili_list_limit == 15
def test_duplicate_sub_ids_fail(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {"id": "main", "type": "kodi", "auth_mode": "anonymous", "kodi": {"root": {}}},
            {"id": "main", "type": "kodi", "auth_mode": "anonymous", "kodi": {"root": {}}},
        ]
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate subscription id"):
        load_config(str(path))


def test_duplicate_tvbox_site_keys_fail(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {
                "id": "main",
                "type": "tvbox",
                "auth_mode": "anonymous",
                "tvbox": {"site_key": "dashbox", "sources": []},
            },
            {
                "id": "alt",
                "type": "tvbox",
                "auth_mode": "anonymous",
                "tvbox": {"site_key": "dashbox", "sources": []},
            },
        ]
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate tvbox site_key: dashbox"):
        load_config(str(path))


def test_tvbox_site_key_is_required(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {"id": "main", "type": "tvbox", "auth_mode": "anonymous", "tvbox": {"sources": []}},
        ]
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="tvbox.site_key is required"):
        load_config(str(path))


def test_empty_tvbox_site_key_is_required(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {"id": "main", "type": "tvbox", "auth_mode": "anonymous", "tvbox": {"site_key": " ", "sources": []}},
        ]
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="tvbox.site_key is required"):
        load_config(str(path))


def test_wrong_type_payload_combination_fails(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [{"id": "main", "type": "tvbox", "auth_mode": "anonymous", "kodi": {"root": {}}}]
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="type tvbox"):
        load_config(str(path))


def test_config_tree_ids_include_subscription_id() -> None:
    config = tvbox_sub("main").tvbox
    tree = ConfigTree("main", config)
    item = config.sources[0].items[0]

    item_id = tree.item_id("main", item)

    assert item_id == "cfg:main:main:i-a"
    assert tree.url_item_by_id(item_id) is item


def test_config_tree_accepts_sources_directly() -> None:
    sub = tvbox_sub("main")
    tree = ConfigTree("main", sub.tvbox.sources)
    item = sub.tvbox.sources[0].items[0]

    item_id = tree.item_id("main", item)

    assert item_id == "cfg:main:main:i-a"
    assert tree.url_item_by_id(item_id) is item


def test_tvbox_subscription_default_codec_preferences() -> None:
    config = tvbox_sub("main").tvbox

    assert config.video_codec_preferences == tuple(CodecPreference(codec, True) for codec in (
        VideoCodec.H264,
        VideoCodec.HEVC,
        VideoCodec.VP9,
        VideoCodec.AV01,
    ))
    assert config.audio_codec_preferences == tuple(CodecPreference(codec, True) for codec in (
        AudioCodec.AAC,
        AudioCodec.OPUS,
        AudioCodec.EAC3,
        AudioCodec.AC3,
        AudioCodec.FLAC,
        AudioCodec.OTHER,
    ))
    assert config.max_video_height == 0
    assert config.max_video_fps == 0
    assert config.locale is TvboxLocale.ZH_CN


def test_tvbox_subscription_parses_locale_enum_values(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {
                "id": "main",
                "type": "tvbox",
                "auth_mode": "anonymous",
                "tvbox": {
                    "site_key": "dashbox",
                    "locale": "en-US",
                    "sources": [{"id": "youtube", "name": "YouTube", "items": []}],
                },
            },
        ]
    }), encoding="utf-8")

    config = load_config(str(path))

    assert config.subs[0].tvbox.locale is TvboxLocale.EN_US
def test_tvbox_subscription_parses_video_codec_preferences(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {
                "id": "main",
                "type": "tvbox",
                "auth_mode": "anonymous",
                "tvbox": {
                    "site_key": "dashbox",
                    "video_codec_preferences": [
                        {"codec": "h264", "enabled": True},
                        {"codec": "vp9", "enabled": False},
                        {"codec": "hevc", "enabled": True},
                        {"codec": "av01", "enabled": True},
                    ],
                    "sources": [{"id": "youtube", "name": "YouTube", "items": []}],
                },
            },
        ]
    }), encoding="utf-8")

    config = load_config(str(path))

    assert config.subs[0].tvbox.video_codec_preferences == (
        CodecPreference(VideoCodec.H264, True),
        CodecPreference(VideoCodec.VP9, False),
        CodecPreference(VideoCodec.HEVC, True),
        CodecPreference(VideoCodec.AV01, True),
    )


def test_tvbox_subscription_parses_audio_codec_preferences(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {
                "id": "main",
                "type": "tvbox",
                "auth_mode": "anonymous",
                "tvbox": {
                    "site_key": "dashbox",
                    "audio_codec_preferences": codec_preferences_json(
                        ("opus", "aac", "other"),
                        (AudioCodec.AAC, AudioCodec.OPUS, AudioCodec.EAC3, AudioCodec.AC3, AudioCodec.FLAC, AudioCodec.OTHER),
                    ),
                    "sources": [{"id": "youtube", "name": "YouTube", "items": []}],
                },
            },
        ]
    }), encoding="utf-8")

    config = load_config(str(path))

    assert config.subs[0].tvbox.audio_codec_preferences[:3] == (
        CodecPreference(AudioCodec.OPUS, True),
        CodecPreference(AudioCodec.AAC, True),
        CodecPreference(AudioCodec.OTHER, True),
    )
    assert all(not preference.enabled for preference in config.subs[0].tvbox.audio_codec_preferences[3:])


def test_tvbox_subscription_rejects_partial_audio_codec_preferences(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {
                "id": "main",
                "type": "tvbox",
                "auth_mode": "anonymous",
                "tvbox": {
                    "site_key": "dashbox",
                    "audio_codec_preferences": [{"codec": "aac", "enabled": True}],
                    "sources": [{"id": "youtube", "name": "YouTube", "items": []}],
                },
            },
        ]
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="audio_codec_preferences must contain every supported codec exactly once"):
        load_config(str(path))


def test_tvbox_subscription_parses_max_video_height(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {
                "id": "main",
                "type": "tvbox",
                "auth_mode": "anonymous",
                "tvbox": {
                    "site_key": "dashbox",
                    "max_video_height": 720,
                    "sources": [{"id": "youtube", "name": "YouTube", "items": []}],
                },
            },
        ]
    }), encoding="utf-8")

    config = load_config(str(path))

    assert config.subs[0].tvbox.max_video_height == 720


def test_tvbox_subscription_parses_max_video_fps(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {
                "id": "main",
                "type": "tvbox",
                "auth_mode": "anonymous",
                "tvbox": {
                    "site_key": "dashbox",
                    "max_video_fps": 60,
                    "sources": [{"id": "youtube", "name": "YouTube", "items": []}],
                },
            },
        ]
    }), encoding="utf-8")

    config = load_config(str(path))

    assert config.subs[0].tvbox.max_video_fps == 60


@pytest.mark.parametrize("value", ("720p", "hd", 360, 8640, True))
def test_tvbox_subscription_rejects_invalid_max_video_height(tmp_path, value: object) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {
                "id": "main",
                "type": "tvbox",
                "auth_mode": "anonymous",
                "tvbox": {
                    "site_key": "dashbox",
                    "max_video_height": value,
                    "sources": [{"id": "youtube", "name": "YouTube", "items": []}],
                },
            },
        ]
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="max_video_height"):
        load_config(str(path))


@pytest.mark.parametrize("value", ("60fps", "ntsc", 25, 50, 240, True))
def test_tvbox_subscription_rejects_invalid_max_video_fps(tmp_path, value: object) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {
                "id": "main",
                "type": "tvbox",
                "auth_mode": "anonymous",
                "tvbox": {
                    "site_key": "dashbox",
                    "max_video_fps": value,
                    "sources": [{"id": "youtube", "name": "YouTube", "items": []}],
                },
            },
        ]
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="max_video_fps"):
        load_config(str(path))


@pytest.mark.parametrize("value", ("mp3", "vorbis", 123, True))
def test_tvbox_subscription_rejects_invalid_audio_codec_preference_item(tmp_path, value: object) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {
                "id": "main",
                "type": "tvbox",
                "auth_mode": "anonymous",
                "tvbox": {
                    "site_key": "dashbox",
                    "audio_codec_preferences": [
                        {"codec": "aac", "enabled": True},
                        {"codec": "opus", "enabled": True},
                        {"codec": value, "enabled": True},
                        {"codec": "ac3", "enabled": True},
                        {"codec": "flac", "enabled": True},
                        {"codec": "other", "enabled": True},
                    ],
                    "sources": [{"id": "youtube", "name": "YouTube", "items": []}],
                },
            },
        ]
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported audio_codec_preferences"):
        load_config(str(path))


def test_tvbox_subscription_rejects_duplicate_audio_codec_preference(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {
                "id": "main",
                "type": "tvbox",
                "auth_mode": "anonymous",
                "tvbox": {
                    "site_key": "dashbox",
                    "audio_codec_preferences": [
                        {"codec": "aac", "enabled": True},
                        {"codec": "aac", "enabled": False},
                        {"codec": "eac3", "enabled": True},
                        {"codec": "ac3", "enabled": True},
                        {"codec": "flac", "enabled": True},
                        {"codec": "other", "enabled": True},
                    ],
                    "sources": [{"id": "youtube", "name": "YouTube", "items": []}],
                },
            },
        ]
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate audio_codec_preferences codec"):
        load_config(str(path))


def test_tvbox_subscription_rejects_all_disabled_audio_codec_preferences(tmp_path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "subs": [
            {
                "id": "main",
                "type": "tvbox",
                "auth_mode": "anonymous",
                "tvbox": {
                    "site_key": "dashbox",
                    "audio_codec_preferences": [
                        {"codec": "aac", "enabled": False},
                        {"codec": "opus", "enabled": False},
                        {"codec": "eac3", "enabled": False},
                        {"codec": "ac3", "enabled": False},
                        {"codec": "flac", "enabled": False},
                        {"codec": "other", "enabled": False},
                    ],
                    "sources": [{"id": "youtube", "name": "YouTube", "items": []}],
                },
            },
        ]
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="audio_codec_preferences must enable at least one codec"):
        load_config(str(path))


def test_tvbox_playback_policy_hash_includes_audio_codec_preferences() -> None:
    default = Config(subs=(tvbox_sub("main"),))
    custom = Config(subs=(tvbox_sub("main", audio_enabled_order=(AudioCodec.OPUS, AudioCodec.AAC)),))

    default_service = TvboxService(default, default.subs[0])
    custom_service = TvboxService(custom, custom.subs[0])

    assert default_service.playback_policy_hash() != custom_service.playback_policy_hash()


def test_sub_route_requires_explicit_subscription_id() -> None:
    config = Config(subs=(
        tvbox_sub("main", site_key="main-site", site_name="Main Site"),
        kodi_sub("kodi-main"),
        tvbox_sub("alt"),
    ))

    with no_lifespan_test_client(server.create_app(config)) as client:
        response = client.get("/sub")

    assert response.status_code == 404


def test_named_sub_route_emits_one_tvbox_subscription() -> None:
    config = Config(subs=(
        tvbox_sub("main"),
        kodi_sub("kodi-main"),
        tvbox_sub("alt", site_key="alt-site", site_name="Alt Site", locale="en-US"),
    ))

    with no_lifespan_test_client(server.create_app(config)) as client:
        response = client.get("/sub/alt")
        non_tvbox = client.get("/sub/kodi-main")

    assert response.status_code == 200
    sites = response.json()["sites"]
    assert sites[0]["key"].startswith("alt-site_u")
    assert sites[0]["key"] != "alt-site"
    assert sites[0]["name"] == "Alt Site"
    ext = json.loads(sites[0]["ext"])
    assert ext["gateway"].endswith("/tvbox/alt")
    assert ext["assetBase"] == "http://testserver"
    assert ext["skey"].startswith("dashbox_tvbox_alt_u")
    assert ext["locale"] == "en-US"
    assert ext["labels"]["refreshDirectory"] == "Refresh list"
    assert ext["labels"]["refreshRejected"] == "Try again later"
    assert ext["labels"]["currentDirectory"] == "Current directory"
    assert ext["labels"]["playCurrentDirectory"] == "Play$$$Current directory"
    assert ext["labels"]["authTitle"] == "Access code"
    assert ext["labels"]["authPrompt"] == "Enter access code"
    assert ext["labels"]["authSuccessRestart"] == "Authenticated. Restart the app"
    assert response.json()["lives"] == [{
        "name": "Dashbox",
        "type": "0",
        "url": "",
    }]
    assert non_tvbox.status_code == 404


def test_sub_route_emits_configured_box_style() -> None:
    config = Config(subs=(tvbox_sub("main", vod_style="landscape"),))

    with no_lifespan_test_client(server.create_app(config)) as client:
        response = client.get("/sub/main")

    assert response.status_code == 200
    site = response.json()["sites"][0]
    assert site["style"] == {"type": "rect", "ratio": 1.78}
    assert json.loads(site["ext"])["vodStyle"] == "landscape"
    assert config.subs[0].tvbox.vod_style is VodStyle.LANDSCAPE


def test_tvbox_locale_controls_backend_generated_copy() -> None:
    config = Config(subs=(
        Subscription(
            id="english",
            type="tvbox",
            tvbox=TvboxSubscriptionConfig(locale="en-US"),
        ),
    ))
    service = TvboxService(config, config.subs[0])

    home = service.home()
    demo = asyncio.run(service.category("demo"))

    assert home["class"][0]["type_name"] == "Demo"
    assert home["filters"]["demo"][0]["name"] == "Order"
    assert home["filters"]["demo"][0]["value"] == [
        {"n": "Source order", "v": "source"},
        {"n": "Reverse", "v": "reverse"},
    ]
    assert demo["dashbox_category_name"] == "Demo"
    assert demo["list"][0]["vod_name"] == "Demo YouTube Video"
    assert demo["list"][0]["vod_remarks"] == "Configure sources in config.json to replace this"


def test_tvbox_routes_reject_unknown_or_non_tvbox_subscriptions() -> None:
    config = Config(subs=(tvbox_sub("main"), kodi_sub("kodi-main")))

    with no_lifespan_test_client(server.create_app(config)) as client:
        unknown = client.get("/tvbox/missing/home")
        non_tvbox = client.get("/tvbox/kodi-main/home")

    assert unknown.status_code == 404
    assert non_tvbox.status_code == 404


def test_image_prefetch_is_scoped_by_protocol_and_subscription() -> None:
    async def run() -> None:
        index = image_proxy.ImagePrefetchIndex()
        await index.register("same", ["https://example.test/shared.jpg", "https://example.test/main.jpg"], protocol="tvbox", sub_id="main")
        await index.register("same", ["https://example.test/shared.jpg", "https://example.test/alt.jpg"], protocol="tvbox", sub_id="alt")

        main = await index.trigger("https://example.test/shared.jpg", protocol="tvbox", sub_id="main")
        alt = await index.trigger("https://example.test/shared.jpg", protocol="tvbox", sub_id="alt")

        assert main == ("https://example.test/main.jpg",)
        assert alt == ("https://example.test/alt.jpg",)

    asyncio.run(run())


def test_tvbox_image_urls_include_subscription_scope() -> None:
    page = {
        "list": [
            {
                "vod_pic": (
                    "http://testserver/image?"
                    "url=https%3A%2F%2Fimg.example.test%2Ft%2Fthumb.jpg"
                ),
            },
            {"vod_pic": "https://example.test/thumb.jpg"},
        ],
    }

    scope_image_urls(page, protocol="tvbox", sub_id="main")

    assert page["list"][0]["vod_pic"] == (
        "http://testserver/image?"
        "url=https%3A%2F%2Fimg.example.test%2Ft%2Fthumb.jpg"
        "&protocol=tvbox&sub_id=main"
    )
    assert page["list"][1]["vod_pic"] == "https://example.test/thumb.jpg"
