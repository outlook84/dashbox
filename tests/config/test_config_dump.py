from __future__ import annotations

from dashbox.config import (
    CodecPreference,
    Config,
    FolderItem,
    ImageProxyMode,
    PUBLIC_BASE_URL_ENV,
    Source,
    Subscription,
    TvboxSubscriptionConfig,
    UrlItem,
    VideoCodec,
    config_to_json_data,
    parse_config_data,
)


BCRYPT_HASH = "$2b$12$012345678901234567890u0123456789012345678901234567890"


def test_config_to_json_data_round_trips_editable_fields() -> None:
    config = Config(
        proxy_media_idle_ttl_seconds=120,
        proxy_dash_media_url=True,
        ytdlp_concurrency=2,
        log_level="debug",
        user_agent="Dashbox Test UA",
        subs=(
            Subscription(
                id="main",
                type="tvbox",
                auth_mode="access_code",
                access_code_hash=BCRYPT_HASH,
                tvbox=TvboxSubscriptionConfig(
                    sources=(
                        Source(
                            "root",
                            "Root",
                            (
                                UrlItem("https://example.test/v", title="Video", pic="https://example.test/v.jpg", id="video"),
                                FolderItem("Folder", (UrlItem("https://example.test/nested", remarks="Nested", id="nested"),), id="folder"),
                            ),
                        ),
                    ),
                    video_codec_preferences=(
                        CodecPreference(VideoCodec.H264, True),
                        CodecPreference(VideoCodec.HEVC, True),
                        CodecPreference(VideoCodec.VP9, False),
                        CodecPreference(VideoCodec.AV01, False),
                    ),
                    max_video_height=1080,
                    vod_style="landscape",
                ),
            ),
        ),
    )

    data = config_to_json_data(config)
    parsed = parse_config_data(data, apply_env=False)

    assert data["subs"][0]["access_code_hash"] == BCRYPT_HASH
    assert "name" not in data["subs"][0]
    assert "access_code" not in data["subs"][0]
    assert "public_base_url" not in data
    assert data["subs"][0]["tvbox"]["video_codec_preferences"] == [
        {"codec": "h264", "enabled": True},
        {"codec": "hevc", "enabled": True},
        {"codec": "vp9", "enabled": False},
        {"codec": "av01", "enabled": False},
    ]
    assert parsed.subs[0].tvbox is not None
    assert parsed.subs[0].tvbox.sources[0].items[0] == UrlItem(
        "https://example.test/v",
        title="Video",
        pic="https://example.test/v.jpg",
        id="video",
    )


def test_config_to_json_data_excludes_runtime_only_config() -> None:
    data = config_to_json_data(Config(
        public_base_url="http://dashbox.local:18990",
        upstream_timeout=12,
        image_proxy_mode="all",
    ))

    assert "upstream_timeout" not in data
    assert "image_proxy_mode" not in data
    assert "public_base_url" not in data


def test_public_base_url_is_runtime_only(monkeypatch) -> None:
    monkeypatch.setenv(PUBLIC_BASE_URL_ENV, " http://dashbox.local:18990/ ")

    config = parse_config_data({"subs": []}, apply_env=True)

    assert config.public_base_url == "http://dashbox.local:18990"


def test_runtime_only_values_are_ignored_from_json_config() -> None:
    config = parse_config_data(
        {
            "public_base_url": "http://json.example.test",
            "upstream_timeout": 12,
            "image_proxy_mode": "all",
            "subs": [],
        },
        apply_env=False,
    )

    assert config.public_base_url == ""
    assert config.upstream_timeout == 30
    assert config.image_proxy_mode is ImageProxyMode.KNOWN
