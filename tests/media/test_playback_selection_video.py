import asyncio
import pytest

from dashbox.media.dash_proxy import DashProxyStore
from dashbox.media.playback import PlaybackSelector
from dashbox.media.scope import PlaybackScope


def test_select_playable_ignores_storyboard_formats() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable({
        "formats": [
            {"url": "https://example.test/sb.mhtml", "ext": "mhtml", "vcodec": "images"},
            {"url": "https://example.test/video.mp4", "ext": "mp4", "vcodec": "avc1", "acodec": "mp4a", "protocol": "https"},
        ],
    }))

    assert selected.url == "https://example.test/video.mp4"
    assert selected.transport == "single_url"


def test_select_playable_uses_direct_url_for_missing_codec_metadata_without_caps() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable({
        "formats": [
            {"url": "https://example.test/video.mp4", "ext": "mp4", "protocol": "https"},
        ],
    }))

    assert selected.url == "https://example.test/video.mp4"
    assert selected.transport == "single_url"


def test_select_playable_rejects_top_level_mhtml_with_missing_codec_metadata() -> None:
    selector = PlaybackSelector()

    with pytest.raises(ValueError, match="no playable format found"):
        asyncio.run(selector.select_playable({"url": "https://example.test/storyboard.mhtml", "ext": "mhtml"}))


def test_select_playable_prefers_height_limited_progressive_format() -> None:
    selector = PlaybackSelector()
    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "url": "https://example.test/1080.mp4",
                    "ext": "mp4",
                    "vcodec": "avc1.640028",
                    "acodec": "mp4a.40.2",
                    "height": 1080,
                    "tbr": 2000,
                    "protocol": "https",
                },
                {
                    "url": "https://example.test/720.mp4",
                    "ext": "mp4",
                    "vcodec": "avc1.64001f",
                    "acodec": "mp4a.40.2",
                    "height": 720,
                    "tbr": 1000,
                    "protocol": "https",
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264", "vp9", "hevc", "av01"),
            max_video_height=720,
        ),
    ))

    assert selected.url == "https://example.test/720.mp4"
    assert selected.transport == "single_url"


def test_select_playable_prefers_height_limited_hls_before_probed_dash() -> None:
    selector = PlaybackSelector(DashProxyStore())
    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "140",
                    "url": "https://cdn.example.test/audio.m4a",
                    "ext": "m4a",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "abr": 128,
                    "protocol": "https",
                },
                {
                    "format_id": "135",
                    "url": "https://cdn.example.test/480-video.mp4",
                    "ext": "mp4",
                    "vcodec": "avc1.4d401e",
                    "acodec": "none",
                    "height": 480,
                    "tbr": 700,
                    "protocol": "https",
                },
                {
                    "format_id": "94",
                    "url": "https://cdn.example.test/480.m3u8",
                    "ext": "mp4",
                    "vcodec": "avc1.4D401E",
                    "acodec": "mp4a.40.2",
                    "height": 480,
                    "tbr": 900,
                    "protocol": "m3u8_native",
                },
                {
                    "format_id": "136",
                    "url": "https://cdn.example.test/720-video.mp4",
                    "ext": "mp4",
                    "vcodec": "avc1.4d401f",
                    "acodec": "none",
                    "height": 720,
                    "tbr": 1200,
                    "protocol": "https",
                },
                {
                    "format_id": "95",
                    "url": "https://cdn.example.test/720.m3u8",
                    "ext": "mp4",
                    "vcodec": "avc1.4D401F",
                    "acodec": "mp4a.40.2",
                    "height": 720,
                    "tbr": 1500,
                    "protocol": "m3u8_native",
                },
            ],
        },
        base_url="http://testserver",
        raw_id="https://example.test/watch",
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264", "vp9", "hevc", "av01"),
            max_video_height=480,
        ),
    ))

    assert selected.url == "https://cdn.example.test/480.m3u8"
    assert selected.format == "m3u8_native"
    assert selected.transport == "single_url"


def test_select_playable_prefers_higher_resolution_over_candidate_transport_order() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "18",
                    "url": "https://cdn.example.test/720.mp4",
                    "ext": "mp4",
                    "protocol": "https",
                    "vcodec": "avc1.64001f",
                    "acodec": "mp4a.40.2",
                    "height": 720,
                },
                {
                    "format_id": "94",
                    "url": "https://cdn.example.test/480.m3u8",
                    "ext": "mp4",
                    "protocol": "m3u8_native",
                    "vcodec": "avc1.4D401E",
                    "acodec": "mp4a.40.2",
                    "height": 480,
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264", "vp9", "hevc", "av01"),
            max_video_height=720,
        ),
    ))

    assert selected.url == "https://cdn.example.test/720.mp4"
    assert selected.transport == "single_url"


def test_select_playable_uses_candidate_transport_order_for_same_quality() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "18",
                    "url": "https://cdn.example.test/720.mp4",
                    "ext": "mp4",
                    "protocol": "https",
                    "vcodec": "avc1.64001f",
                    "acodec": "mp4a.40.2",
                    "height": 720,
                    "fps": 30,
                    "tbr": 1500,
                },
                {
                    "format_id": "95",
                    "url": "https://cdn.example.test/720.m3u8",
                    "ext": "mp4",
                    "protocol": "m3u8_native",
                    "vcodec": "avc1.4D401F",
                    "acodec": "mp4a.40.2",
                    "height": 720,
                    "fps": 30,
                    "tbr": 1500,
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264", "vp9", "hevc", "av01"),
            max_video_height=720,
        ),
    ))

    assert selected.url == "https://cdn.example.test/720.m3u8"
    assert selected.transport == "single_url"


def test_select_playable_proxy_scope_prefers_hls_over_progressive_for_same_quality() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "18",
                    "url": "https://cdn.example.test/720.mp4",
                    "ext": "mp4",
                    "protocol": "https",
                    "vcodec": "avc1.64001f",
                    "acodec": "mp4a.40.2",
                    "height": 720,
                    "fps": 30,
                    "tbr": 1500,
                },
                {
                    "format_id": "95",
                    "url": "https://cdn.example.test/720.m3u8",
                    "ext": "mp4",
                    "protocol": "m3u8_native",
                    "vcodec": "avc1.4D401F",
                    "acodec": "mp4a.40.2",
                    "height": 720,
                    "fps": 30,
                    "tbr": 1500,
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264", "vp9", "hevc", "av01"),
            max_video_height=720,
            proxy_dash_media_url=True,
        ),
    ))

    assert selected.url == "https://cdn.example.test/720.m3u8"
    assert selected.transport == "single_url"


def test_select_playable_proxy_scope_prefers_dash_for_same_quality_even_with_lower_bitrate() -> None:
    selector = PlaybackSelector(DashProxyStore())

    selected = asyncio.run(selector.select_playable(
        {
            "duration": 4,
            "formats": [
                {
                    "format_id": "18",
                    "url": "https://cdn.example.test/720.mp4",
                    "ext": "mp4",
                    "protocol": "https",
                    "vcodec": "avc1.64001f",
                    "acodec": "mp4a.40.2",
                    "height": 720,
                    "fps": 30,
                    "tbr": 1500,
                },
                {
                    "format_id": "95",
                    "url": "https://cdn.example.test/720.m3u8",
                    "ext": "mp4",
                    "protocol": "m3u8_native",
                    "vcodec": "avc1.4D401F",
                    "acodec": "mp4a.40.2",
                    "height": 720,
                    "fps": 30,
                    "tbr": 2200,
                },
                {
                    "format_id": "video",
                    "url": "https://cdn.example.test/720-video.mp4",
                    "vcodec": "avc1.64001f",
                    "acodec": "none",
                    "mime_type": "video/mp4",
                    "height": 720,
                    "fps": 30,
                    "tbr": 1500,
                    "init_range": {"start": 0, "end": 99},
                    "index_range": {"start": 100, "end": 199},
                    "fragments": [
                        {"url": "https://cdn.example.test/video/init"},
                        {"url": "https://cdn.example.test/video/1", "duration": 4},
                    ],
                },
                {
                    "format_id": "audio",
                    "url": "https://cdn.example.test/audio.m4a",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "mime_type": "audio/mp4",
                    "abr": 128,
                    "init_range": {"start": 0, "end": 99},
                    "index_range": {"start": 100, "end": 199},
                    "fragments": [
                        {"url": "https://cdn.example.test/audio/init"},
                        {"url": "https://cdn.example.test/audio/1", "duration": 4},
                    ],
                },
            ],
        },
        base_url="http://testserver",
        raw_id="https://example.test/watch",
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264", "vp9", "hevc", "av01"),
            max_video_height=720,
            proxy_dash_media_url=True,
        ),
    ))

    assert selected.format == "dash"
    assert selected.transport == "dash"
    assert selected.url.startswith("http://testserver/media/")
    assert selected.url.endswith("/manifest.mpd")


def test_select_playable_prefers_higher_fps_progressive_single_url_over_hls() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "18",
                    "url": "https://cdn.example.test/720.mp4",
                    "ext": "mp4",
                    "protocol": "https",
                    "vcodec": "avc1.64001f",
                    "acodec": "mp4a.40.2",
                    "height": 720,
                    "fps": 60,
                    "tbr": 1500,
                },
                {
                    "format_id": "95",
                    "url": "https://cdn.example.test/720.m3u8",
                    "ext": "mp4",
                    "protocol": "m3u8_native",
                    "vcodec": "avc1.4D401F",
                    "acodec": "mp4a.40.2",
                    "height": 720,
                    "fps": 30,
                    "tbr": 1500,
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264", "vp9", "hevc", "av01"),
            max_video_height=720,
        ),
    ))

    assert selected.url == "https://cdn.example.test/720.mp4"
    assert selected.transport == "single_url"
    assert selected.raw_format["fps"] == 60


def test_select_playable_prefers_higher_fps_over_candidate_transport_order() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "dash-720",
                    "url": "https://cdn.example.test/720-dash.mpd",
                    "ext": "mp4",
                    "protocol": "http_dash_segments",
                    "vcodec": "avc1.64001f",
                    "acodec": "mp4a.40.2",
                    "height": 720,
                    "fps": 60,
                    "tbr": 1500,
                    "manifest_url": "https://cdn.example.test/720-dash.mpd",
                },
                {
                    "format_id": "hls-720",
                    "url": "https://cdn.example.test/720.m3u8",
                    "ext": "mp4",
                    "protocol": "m3u8_native",
                    "vcodec": "avc1.4D401F",
                    "acodec": "mp4a.40.2",
                    "height": 720,
                    "fps": 30,
                    "tbr": 1500,
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264", "vp9", "hevc", "av01"),
            max_video_height=720,
        ),
    ))

    assert selected.url == "https://cdn.example.test/720-dash.mpd"
    assert selected.transport == "manifest"


def test_select_playable_prefers_fps_limited_progressive_format() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "720p60",
                    "url": "https://cdn.example.test/720p60.mp4",
                    "ext": "mp4",
                    "protocol": "https",
                    "vcodec": "avc1.64001f",
                    "acodec": "mp4a.40.2",
                    "height": 720,
                    "fps": 60,
                    "tbr": 1800,
                },
                {
                    "format_id": "720p30",
                    "url": "https://cdn.example.test/720p30.mp4",
                    "ext": "mp4",
                    "protocol": "https",
                    "vcodec": "avc1.64001f",
                    "acodec": "mp4a.40.2",
                    "height": 720,
                    "fps": 30,
                    "tbr": 1500,
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264", "vp9", "hevc", "av01"),
            max_video_height=720,
            max_video_fps=30,
        ),
    ))

    assert selected.url == "https://cdn.example.test/720p30.mp4"
    assert selected.transport == "single_url"
    assert selected.raw_format["fps"] == 30


def test_select_playable_uses_other_bucket_before_single_url_filtering() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "progressive-h264-opus",
                    "url": "https://cdn.example.test/video-h264-opus.mp4",
                    "protocol": "https",
                    "vcodec": "avc1.64001f",
                    "acodec": "opus",
                    "height": 720,
                    "tbr": 1200,
                },
                {
                    "format_id": "progressive-vp9-aac",
                    "url": "https://cdn.example.test/video-vp9-aac.mp4",
                    "protocol": "https",
                    "vcodec": "vp09.00.40.08",
                    "acodec": "mp4a.40.2",
                    "height": 1080,
                    "tbr": 2400,
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264",),
            audio_codec_order=("aac", "other"),
        ),
    ))

    assert selected.url == "https://cdn.example.test/video-h264-opus.mp4"


def test_select_playable_does_not_mark_progressive_single_url_as_proxyable() -> None:
    selected = asyncio.run(PlaybackSelector().select_playable({
        "formats": [
            {
                "format_id": "18",
                "url": "https://cdn.example.test/video.mp4",
                "ext": "mp4",
                "protocol": "https",
                "vcodec": "avc1.42001E",
                "acodec": "mp4a.40.2",
                "height": 360,
            },
        ],
    }))

    assert selected.url == "https://cdn.example.test/video.mp4"
    assert "proxyable_media_link" not in selected.raw_format
    assert selected.transport == "single_url"


def test_select_playable_max_video_height_rejects_over_limit_video() -> None:
    selector = PlaybackSelector()

    with pytest.raises(ValueError, match="no playable format found"):
        asyncio.run(selector.select_playable(
            {
                "formats": [
                    {
                        "url": "https://example.test/1080.mp4",
                        "ext": "mp4",
                        "vcodec": "avc1.640028",
                        "acodec": "mp4a.40.2",
                        "height": 1080,
                        "tbr": 2000,
                        "protocol": "https",
                    },
                ],
            },
            scope=PlaybackScope(
                protocol="tvbox",
                sub_id="main",
                video_codec_order=("h264", "vp9", "hevc", "av01"),
                max_video_height=720,
            ),
        ))


def test_select_playable_max_video_fps_rejects_over_limit_video() -> None:
    selector = PlaybackSelector()

    with pytest.raises(ValueError, match="no playable format found"):
        asyncio.run(selector.select_playable(
            {
                "formats": [
                    {
                        "url": "https://example.test/720p60.mp4",
                        "ext": "mp4",
                        "vcodec": "avc1.64001f",
                        "acodec": "mp4a.40.2",
                        "height": 720,
                        "fps": 60,
                        "tbr": 2000,
                        "protocol": "https",
                    },
                ],
            },
            scope=PlaybackScope(
                protocol="tvbox",
                sub_id="main",
                video_codec_order=("h264", "vp9", "hevc", "av01"),
                max_video_height=720,
                max_video_fps=30,
            ),
        ))


def test_select_playable_max_video_fps_rejects_missing_fps_video() -> None:
    selector = PlaybackSelector()

    with pytest.raises(ValueError, match="no playable format found"):
        asyncio.run(selector.select_playable(
            {
                "formats": [
                    {
                        "url": "https://example.test/720-unknown-fps.mp4",
                        "ext": "mp4",
                        "vcodec": "avc1.64001f",
                        "acodec": "mp4a.40.2",
                        "height": 720,
                        "tbr": 2000,
                        "protocol": "https",
                    },
                ],
            },
            scope=PlaybackScope(
                protocol="tvbox",
                sub_id="main",
                video_codec_order=("h264", "vp9", "hevc", "av01"),
                max_video_height=720,
                max_video_fps=30,
            ),
        ))


def test_select_playable_does_not_return_video_only_progressive_as_single_url() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "video-720",
                    "url": "https://cdn.example.test/720-video.mp4",
                    "ext": "mp4",
                    "protocol": "https",
                    "vcodec": "avc1.64001f",
                    "acodec": "none",
                    "height": 720,
                    "fps": 30,
                    "tbr": 1500,
                },
                {
                    "format_id": "muxed-480",
                    "url": "https://cdn.example.test/480.mp4",
                    "ext": "mp4",
                    "protocol": "https",
                    "vcodec": "avc1.4D401E",
                    "acodec": "mp4a.40.2",
                    "height": 480,
                    "fps": 30,
                    "tbr": 900,
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264", "vp9", "hevc", "av01"),
            max_video_height=720,
        ),
    ))

    assert selected.url == "https://cdn.example.test/480.mp4"
    assert selected.transport == "single_url"


def test_select_playable_uses_video_only_direct_url_as_last_fallback() -> None:
    selector = PlaybackSelector(segment_base_prober=None)

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "video-720",
                    "url": "https://cdn.example.test/720-video.mp4",
                    "ext": "mp4",
                    "protocol": "https",
                    "vcodec": "avc1.64001f",
                    "acodec": "none",
                    "height": 720,
                    "fps": 30,
                    "tbr": 1500,
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264", "vp9", "hevc", "av01"),
            max_video_height=720,
        ),
    ))

    assert selected.url == "https://cdn.example.test/720-video.mp4"
    assert selected.transport == "single_url"
    assert selected.debug_source == "video_only_direct_fallback"


def test_select_playable_rejects_video_only_direct_fallback_with_disallowed_codec() -> None:
    selector = PlaybackSelector(segment_base_prober=None)

    with pytest.raises(ValueError, match="no playable format found"):
        asyncio.run(selector.select_playable(
            {
                "formats": [
                    {
                        "format_id": "video-720",
                        "url": "https://cdn.example.test/720-video.webm",
                        "ext": "webm",
                        "protocol": "https",
                        "vcodec": "vp09.00.40.08",
                        "acodec": "none",
                        "height": 720,
                        "fps": 30,
                        "tbr": 1500,
                    },
                ],
            },
            scope=PlaybackScope(
                protocol="tvbox",
                sub_id="main",
                video_codec_order=("h264",),
                max_video_height=720,
            ),
        ))


def test_select_playable_uses_twitch_style_video_ext_only_format_as_last_fallback() -> None:
    selector = PlaybackSelector(segment_base_prober=None)

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "1080",
                    "url": "https://cdn.example.test/twitch-clip.mp4",
                    "ext": "mp4",
                    "protocol": "https",
                    "video_ext": "mp4",
                    "audio_ext": "none",
                    "height": 1080,
                    "fps": 0.0,
                    "resolution": "1080p",
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264",),
            max_video_height=1080,
        ),
    ))

    assert selected.url == "https://cdn.example.test/twitch-clip.mp4"
    assert selected.transport == "single_url"
    assert selected.debug_source == "video_only_direct_fallback"


def test_select_playable_prefers_audio_only_when_separate_direct_video_audio_cannot_be_built() -> None:
    selector = PlaybackSelector(segment_base_prober=None)

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "video-720",
                    "url": "https://cdn.example.test/720-video.mp4",
                    "ext": "mp4",
                    "protocol": "https",
                    "vcodec": "avc1.64001f",
                    "acodec": "none",
                    "height": 720,
                    "fps": 30,
                    "tbr": 1500,
                },
                {
                    "format_id": "audio",
                    "url": "https://cdn.example.test/audio.m4a",
                    "ext": "m4a",
                    "protocol": "https",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "abr": 128,
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264", "vp9", "hevc", "av01"),
            max_video_height=720,
        ),
    ))

    assert selected.url == "https://cdn.example.test/audio.m4a"
    assert selected.transport == "single_url"


def test_select_playable_prefers_manifest_for_manifest_backed_segmented_format() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable({
        "formats": [
            {
                "format_id": "dash-muxed",
                "url": "https://cdn.example.test/segment-template",
                "manifest_url": "https://cdn.example.test/master.mpd",
                "protocol": "http_dash_segments",
                "vcodec": "avc1.640028",
                "acodec": "mp4a.40.2",
                "height": 720,
            },
        ],
    }))

    assert selected.url == "https://cdn.example.test/master.mpd"
    assert selected.format == "http_dash_segments"
    assert selected.transport == "manifest"


def test_select_playable_rejects_top_level_manifest_when_codec_policy_excludes_formats() -> None:
    selector = PlaybackSelector()

    with pytest.raises(ValueError, match="no playable format found"):
        asyncio.run(selector.select_playable(
            {
                "manifest_url": "https://cdn.example.test/master.mpd",
                "formats": [
                    {
                        "format_id": "dash-av1",
                        "url": "https://cdn.example.test/av1-template",
                        "manifest_url": "https://cdn.example.test/master.mpd",
                        "protocol": "http_dash_segments",
                        "vcodec": "av01.0.05M.08",
                        "acodec": "mp4a.40.2",
                        "height": 720,
                    },
                ],
            },
            scope=PlaybackScope(
                protocol="tvbox",
                sub_id="main",
                video_codec_order=("h264",),
            ),
        ))


def test_select_playable_allows_top_level_manifest_when_formats_are_absent() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "manifest_url": "https://cdn.example.test/master.mpd",
            "http_headers": {"User-Agent": "test-agent"},
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264",),
            audio_codec_order=("aac",),
        ),
    ))

    assert selected.url == "https://cdn.example.test/master.mpd"
    assert selected.format == "manifest"
    assert selected.transport == "manifest"
    assert selected.headers == {"User-Agent": "test-agent"}


def test_select_playable_rejects_top_level_manifest_when_audio_policy_excludes_shared_track() -> None:
    selector = PlaybackSelector()

    with pytest.raises(ValueError, match="no playable format found"):
        asyncio.run(selector.select_playable(
            {
                "manifest_url": "https://cdn.example.test/master.mpd",
                "formats": [
                    {
                        "format_id": "dash-video",
                        "url": "https://cdn.example.test/video-template",
                        "manifest_url": "https://cdn.example.test/master.mpd",
                        "protocol": "http_dash_segments",
                        "vcodec": "avc1.640028",
                        "acodec": "none",
                        "height": 720,
                    },
                    {
                        "format_id": "dash-audio-opus",
                        "url": "https://cdn.example.test/audio-template",
                        "manifest_url": "https://cdn.example.test/master.mpd",
                        "protocol": "http_dash_segments",
                        "vcodec": "none",
                        "acodec": "opus",
                        "abr": 128,
                    },
                ],
            },
            scope=PlaybackScope(
                protocol="tvbox",
                sub_id="main",
                video_codec_order=("h264",),
                audio_codec_order=("aac",),
            ),
        ))


def test_select_playable_max_video_height_rejects_over_limit_manifest_format() -> None:
    selector = PlaybackSelector()

    with pytest.raises(ValueError, match="no playable format found"):
        asyncio.run(selector.select_playable(
            {
                "formats": [
                    {
                        "format_id": "dash-muxed",
                        "url": "https://cdn.example.test/segment-template",
                        "manifest_url": "https://cdn.example.test/master.mpd",
                        "protocol": "http_dash_segments",
                        "vcodec": "avc1.640028",
                        "acodec": "mp4a.40.2",
                        "height": 1080,
                    },
                ],
            },
            scope=PlaybackScope(
                protocol="tvbox",
                sub_id="main",
                video_codec_order=("h264", "vp9", "hevc", "av01"),
                max_video_height=720,
            ),
        ))


def test_select_playable_max_video_height_rejects_shared_manifest_with_over_limit_format() -> None:
    selector = PlaybackSelector()

    with pytest.raises(ValueError, match="no playable format found"):
        asyncio.run(selector.select_playable(
            {
                "formats": [
                    {
                        "format_id": "dash-720",
                        "url": "https://cdn.example.test/720-template",
                        "manifest_url": "https://cdn.example.test/master.mpd",
                        "protocol": "http_dash_segments",
                        "vcodec": "avc1.64001f",
                        "acodec": "mp4a.40.2",
                        "height": 720,
                    },
                    {
                        "format_id": "dash-1080",
                        "url": "https://cdn.example.test/1080-template",
                        "manifest_url": "https://cdn.example.test/master.mpd",
                        "protocol": "http_dash_segments",
                        "vcodec": "avc1.640028",
                        "acodec": "mp4a.40.2",
                        "height": 1080,
                    },
                ],
            },
            scope=PlaybackScope(
                protocol="tvbox",
                sub_id="main",
                video_codec_order=("h264", "vp9", "hevc", "av01"),
                max_video_height=720,
            ),
        ))


def test_select_playable_max_video_fps_rejects_shared_manifest_with_over_limit_format() -> None:
    selector = PlaybackSelector()

    with pytest.raises(ValueError, match="no playable format found"):
        asyncio.run(selector.select_playable(
            {
                "formats": [
                    {
                        "format_id": "dash-720p30",
                        "url": "https://cdn.example.test/720p30-template",
                        "manifest_url": "https://cdn.example.test/master.mpd",
                        "protocol": "http_dash_segments",
                        "vcodec": "avc1.64001f",
                        "acodec": "mp4a.40.2",
                        "height": 720,
                        "fps": 30,
                    },
                    {
                        "format_id": "dash-720p60",
                        "url": "https://cdn.example.test/720p60-template",
                        "manifest_url": "https://cdn.example.test/master.mpd",
                        "protocol": "http_dash_segments",
                        "vcodec": "avc1.64001f",
                        "acodec": "mp4a.40.2",
                        "height": 720,
                        "fps": 60,
                    },
                ],
            },
            scope=PlaybackScope(
                protocol="tvbox",
                sub_id="main",
                video_codec_order=("h264", "vp9", "hevc", "av01"),
                max_video_height=720,
                max_video_fps=30,
            ),
        ))


def test_select_playable_does_not_use_top_level_manifest_to_bypass_height_cap() -> None:
    selector = PlaybackSelector()

    with pytest.raises(ValueError, match="no playable format found"):
        asyncio.run(selector.select_playable(
            {
                "manifest_url": "https://cdn.example.test/master.mpd",
                "formats": [
                    {
                        "format_id": "dash-muxed",
                        "url": "https://cdn.example.test/segment-template",
                        "manifest_url": "https://cdn.example.test/master.mpd",
                        "protocol": "http_dash_segments",
                        "vcodec": "avc1.640028",
                        "acodec": "mp4a.40.2",
                        "height": 1080,
                    },
                ],
            },
            scope=PlaybackScope(
                protocol="tvbox",
                sub_id="main",
                video_codec_order=("h264", "vp9", "hevc", "av01"),
                max_video_height=720,
            ),
        ))


def test_select_playable_rejects_direct_url_without_video_metadata_when_height_cap_is_set() -> None:
    selector = PlaybackSelector()

    with pytest.raises(ValueError, match="no playable format found"):
        asyncio.run(selector.select_playable(
            {
                "formats": [
                    {
                        "format_id": "unknown",
                        "url": "https://cdn.example.test/video.mp4",
                        "ext": "mp4",
                        "protocol": "https",
                    },
                ],
            },
            scope=PlaybackScope(
                protocol="tvbox",
                sub_id="main",
                video_codec_order=("h264", "vp9", "hevc", "av01"),
                max_video_height=720,
            ),
        ))
