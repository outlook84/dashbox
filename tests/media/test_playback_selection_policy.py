import asyncio
import pytest

from dashbox.media.playback import PlaybackSelector
from dashbox.media.playback_policy import best_video_format_by_codec_policy
from dashbox.media.playback_single_url import select_progressive_format
from dashbox.media.scope import PlaybackScope
from tests.helpers import data_mpd_xml


def test_select_playable_dash_returns_same_quality_candidate_used_for_ranking() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "duration": 4,
            "formats": [
                {
                    "format_id": "dash-h264-720",
                    "url": "https://cdn.example.test/dash-720.mp4",
                    "vcodec": "avc1.64001f",
                    "acodec": "none",
                    "mime_type": "video/mp4",
                    "height": 720,
                    "tbr": 1200,
                    "init_range": {"start": 0, "end": 99},
                    "index_range": {"start": 100, "end": 199},
                    "fragments": [{"url": "https://cdn.example.test/dash-720/init"}],
                },
                {
                    "format_id": "dash-vp9-1080",
                    "url": "https://cdn.example.test/dash-1080.webm",
                    "vcodec": "vp09.00.51.08",
                    "acodec": "none",
                    "mime_type": "video/webm",
                    "height": 1080,
                    "tbr": 2500,
                    "init_range": {"start": 0, "end": 99},
                    "index_range": {"start": 100, "end": 199},
                    "fragments": [{"url": "https://cdn.example.test/dash-1080/init"}],
                },
                {
                    "format_id": "dash-audio",
                    "url": "https://cdn.example.test/audio.m4a",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "mime_type": "audio/mp4",
                    "abr": 128,
                    "init_range": {"start": 0, "end": 99},
                    "index_range": {"start": 100, "end": 199},
                    "fragments": [{"url": "https://cdn.example.test/audio/init"}],
                },
                {
                    "format_id": "progressive-1080",
                    "url": "https://cdn.example.test/1080.mp4",
                    "vcodec": "vp09.00.51.08",
                    "acodec": "mp4a.40.2",
                    "ext": "mp4",
                    "height": 1080,
                    "tbr": 2400,
                    "protocol": "https",
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264", "vp9", "hevc", "av01"),
            max_video_height=1080,
            proxy_dash_media_url=True,
        ),
    ))

    xml = data_mpd_xml(selected.url)

    assert selected.format == "dash"
    assert selected.transport == "dash"
    assert "id='dash-vp9-1080'" in xml
    assert "id='dash-h264-720'" not in xml


def test_select_playable_ignores_requested_formats_without_formats() -> None:
    selector = PlaybackSelector()

    with pytest.raises(ValueError, match="no playable format found"):
        asyncio.run(selector.select_playable(
            {
                "title": "video",
                "requested_formats": [
                    {
                        "format_id": "h264-720",
                        "url": "https://cdn.example.test/720.mp4",
                        "vcodec": "avc1.64001f",
                        "acodec": "mp4a.40.2",
                        "ext": "mp4",
                        "height": 720,
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


def test_select_playable_uses_top_level_url_when_formats_are_absent() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable({
        "url": "https://cdn.example.test/video.mp4",
        "vcodec": "avc1.64001f",
        "acodec": "mp4a.40.2",
        "ext": "mp4",
        "height": 720,
        "protocol": "https",
    }))

    assert selected.url == "https://cdn.example.test/video.mp4"
    assert selected.transport == "single_url"


def test_select_playable_prefers_formats_over_top_level_url() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable({
        "url": "https://cdn.example.test/top-level.mp4",
        "vcodec": "avc1.64001f",
        "acodec": "mp4a.40.2",
        "ext": "mp4",
        "height": 720,
        "protocol": "https",
        "formats": [
            {
                "url": "https://cdn.example.test/format.mp4",
                "vcodec": "avc1.640028",
                "acodec": "mp4a.40.2",
                "ext": "mp4",
                "height": 1080,
                "protocol": "https",
            },
        ],
    }))

    assert selected.url == "https://cdn.example.test/format.mp4"


def test_select_playable_uses_top_level_url_when_formats_exceed_height_cap() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "url": "https://cdn.example.test/top-level-720.mp4",
            "vcodec": "avc1.64001f",
            "acodec": "mp4a.40.2",
            "ext": "mp4",
            "height": 720,
            "protocol": "https",
            "formats": [
                {
                    "url": "https://cdn.example.test/format-1080.mp4",
                    "vcodec": "avc1.640028",
                    "acodec": "mp4a.40.2",
                    "ext": "mp4",
                    "height": 1080,
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

    assert selected.url == "https://cdn.example.test/top-level-720.mp4"
    assert selected.transport == "single_url"


def test_select_playable_uses_top_level_url_when_formats_exceed_fps_cap() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "url": "https://cdn.example.test/top-level-720p30.mp4",
            "vcodec": "avc1.64001f",
            "acodec": "mp4a.40.2",
            "ext": "mp4",
            "height": 720,
            "fps": 30,
            "protocol": "https",
            "formats": [
                {
                    "url": "https://cdn.example.test/format-720p60.mp4",
                    "vcodec": "avc1.64001f",
                    "acodec": "mp4a.40.2",
                    "ext": "mp4",
                    "height": 720,
                    "fps": 60,
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

    assert selected.url == "https://cdn.example.test/top-level-720p30.mp4"
    assert selected.transport == "single_url"


def test_best_video_format_by_codec_policy_applies_height_cap() -> None:
    selected = best_video_format_by_codec_policy(
        [
            {
                "format_id": "h264-1080",
                "url": "https://cdn.example.test/1080.mp4",
                "vcodec": "avc1.640028",
                "height": 1080,
            },
            {
                "format_id": "h264-720",
                "url": "https://cdn.example.test/720.mp4",
                "vcodec": "avc1.64001f",
                "height": 720,
            },
        ],
        ("h264",),
        max_video_height=720,
    )

    assert selected["format_id"] == "h264-720"


def test_best_video_format_by_codec_policy_applies_fps_cap() -> None:
    selected = best_video_format_by_codec_policy(
        [
            {
                "format_id": "h264-720p60",
                "url": "https://cdn.example.test/720p60.mp4",
                "vcodec": "avc1.64001f",
                "height": 720,
                "fps": 60,
            },
            {
                "format_id": "h264-720p30",
                "url": "https://cdn.example.test/720p30.mp4",
                "vcodec": "avc1.64001f",
                "height": 720,
                "fps": 30,
            },
        ],
        ("h264",),
        max_video_height=720,
        max_video_fps=30,
    )

    assert selected["format_id"] == "h264-720p30"


def test_best_video_format_by_codec_policy_keeps_codec_as_soft_tiebreaker() -> None:
    selected = best_video_format_by_codec_policy(
        [
            {
                "format_id": "h264-720",
                "url": "https://cdn.example.test/720.mp4",
                "vcodec": "avc1.64001f",
                "height": 720,
            },
            {
                "format_id": "vp9-1080",
                "url": "https://cdn.example.test/1080.webm",
                "vcodec": "vp09.00.51.08",
                "height": 1080,
            },
        ],
        ("h264", "vp9"),
        max_video_height=1080,
    )

    assert selected["format_id"] == "vp9-1080"


def test_best_video_format_by_codec_policy_prefers_codec_over_bitrate() -> None:
    selected = best_video_format_by_codec_policy(
        [
            {
                "format_id": "h264-720",
                "url": "https://cdn.example.test/720.mp4",
                "vcodec": "avc1.64001f",
                "height": 720,
                "tbr": 1000,
            },
            {
                "format_id": "vp9-720",
                "url": "https://cdn.example.test/720.webm",
                "vcodec": "vp09.00.51.08",
                "height": 720,
                "tbr": 2500,
            },
        ],
        ("h264", "vp9"),
        max_video_height=720,
    )

    assert selected["format_id"] == "h264-720"


def test_best_video_format_by_codec_policy_uses_bitrate_for_same_codec() -> None:
    selected = best_video_format_by_codec_policy(
        [
            {
                "format_id": "h264-720-low",
                "url": "https://cdn.example.test/720-low.mp4",
                "vcodec": "avc1.64001f",
                "height": 720,
                "tbr": 1000,
            },
            {
                "format_id": "h264-720-high",
                "url": "https://cdn.example.test/720-high.mp4",
                "vcodec": "avc1.64001f",
                "height": 720,
                "tbr": 2500,
            },
        ],
        ("h264", "vp9"),
        max_video_height=720,
    )

    assert selected["format_id"] == "h264-720-high"


def test_select_progressive_format_uses_bitrate_for_same_codec() -> None:
    selected = select_progressive_format(
        [
            {
                "format_id": "progressive-high",
                "url": "https://cdn.example.test/720-high.mp4",
                "protocol": "https",
                "vcodec": "avc1.64001f",
                "acodec": "mp4a.40.2",
                "height": 720,
                "tbr": 2500,
            },
            {
                "format_id": "progressive-low",
                "url": "https://cdn.example.test/720-low.mp4",
                "protocol": "https",
                "vcodec": "avc1.64001f",
                "acodec": "mp4a.40.2",
                "height": 720,
                "tbr": 1000,
            },
        ],
        ("h264", "vp9"),
        max_video_height=720,
    )

    assert selected["format_id"] == "progressive-high"


def test_select_playable_falls_back_to_audio_when_no_video_exists() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable({
        "formats": [
            {
                "format_id": "audio-low",
                "url": "https://cdn.example.test/audio-low.m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "ext": "m4a",
                "abr": 64,
            },
            {
                "format_id": "audio-high",
                "url": "https://cdn.example.test/audio-high.m4a",
                "vcodec": "none",
                "acodec": "mp4a.40.2",
                "ext": "m4a",
                "abr": 128,
            },
        ],
    }))

    assert selected.url == "https://cdn.example.test/audio-high.m4a"


def test_select_playable_prefers_audio_codec_before_bitrate() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "audio-aac",
                    "url": "https://cdn.example.test/audio.m4a",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "ext": "m4a",
                    "abr": 128,
                },
                {
                    "format_id": "audio-opus",
                    "url": "https://cdn.example.test/audio.opus",
                    "vcodec": "none",
                    "acodec": "opus",
                    "ext": "opus",
                    "abr": 160,
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            audio_codec_order=("aac", "opus", "eac3", "ac3", "flac"),
        ),
    ))

    assert selected.url == "https://cdn.example.test/audio.m4a"


def test_select_playable_honors_custom_audio_codec_order() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "audio-aac",
                    "url": "https://cdn.example.test/audio.m4a",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "ext": "m4a",
                    "abr": 128,
                },
                {
                    "format_id": "audio-opus",
                    "url": "https://cdn.example.test/audio.opus",
                    "vcodec": "none",
                    "acodec": "opus",
                    "ext": "opus",
                    "abr": 96,
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            audio_codec_order=("opus", "aac", "eac3", "ac3", "flac"),
        ),
    ))

    assert selected.url == "https://cdn.example.test/audio.opus"


def test_select_playable_keeps_unknown_audio_codec_when_audio_order_is_not_configured() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "audio-low",
                    "url": "https://cdn.example.test/audio-low.weird",
                    "vcodec": "none",
                    "acodec": "x-custom",
                    "ext": "weird",
                    "abr": 64,
                },
                {
                    "format_id": "audio-high",
                    "url": "https://cdn.example.test/audio-high.weird",
                    "vcodec": "none",
                    "acodec": "x-custom",
                    "ext": "weird",
                    "abr": 128,
                },
            ],
        },
    ))

    assert selected.url == "https://cdn.example.test/audio-high.weird"


def test_select_playable_filters_unknown_audio_codec_when_order_is_configured() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "audio-aac",
                    "url": "https://cdn.example.test/audio.m4a",
                    "vcodec": "none",
                    "acodec": "aac",
                    "ext": "m4a",
                    "abr": 96,
                },
                {
                    "format_id": "audio-custom",
                    "url": "https://cdn.example.test/audio.weird",
                    "vcodec": "none",
                    "acodec": "x-custom",
                    "ext": "weird",
                    "abr": 192,
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            audio_codec_order=("aac", "opus", "eac3", "ac3", "flac"),
        ),
    ))

    assert selected.url == "https://cdn.example.test/audio.m4a"


def test_select_playable_keeps_unknown_audio_codec_with_other_bucket() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "audio-mp3",
                    "url": "https://cdn.example.test/audio.mp3",
                    "vcodec": "none",
                    "acodec": "mp3",
                    "ext": "mp3",
                    "abr": 192,
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            audio_codec_order=("aac", "opus", "eac3", "ac3", "flac", "other"),
        ),
    ))

    assert selected.url == "https://cdn.example.test/audio.mp3"


def test_select_playable_allows_partial_audio_codec_order() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "audio-aac",
                    "url": "https://cdn.example.test/audio.m4a",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "ext": "m4a",
                    "abr": 128,
                },
                {
                    "format_id": "audio-opus",
                    "url": "https://cdn.example.test/audio.opus",
                    "vcodec": "none",
                    "acodec": "opus",
                    "ext": "opus",
                    "abr": 256,
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            audio_codec_order=("aac",),
        ),
    ))

    assert selected.url == "https://cdn.example.test/audio.m4a"


def test_select_playable_applies_audio_codec_order_to_hls_direct_plan() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "hls-opus",
                    "url": "https://cdn.example.test/stream-opus.m3u8",
                    "protocol": "m3u8_native",
                    "vcodec": "avc1.64001f",
                    "acodec": "opus",
                    "height": 720,
                    "tbr": 2000,
                },
                {
                    "format_id": "dash-video",
                    "url": "https://cdn.example.test/video.mp4",
                    "protocol": "http_dash_segments",
                    "vcodec": "avc1.64001f",
                    "acodec": "none",
                    "height": 720,
                    "tbr": 1800,
                    "init_range": {"start": 0, "end": 99},
                    "index_range": {"start": 100, "end": 199},
                    "fragments": [{"url": "https://cdn.example.test/video/init"}],
                },
                {
                    "format_id": "dash-audio",
                    "url": "https://cdn.example.test/audio.m4a",
                    "protocol": "http_dash_segments",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "abr": 128,
                    "init_range": {"start": 0, "end": 99},
                    "index_range": {"start": 100, "end": 199},
                    "fragments": [{"url": "https://cdn.example.test/audio/init"}],
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264", "vp9", "hevc", "av01"),
            audio_codec_order=("aac",),
            max_video_height=720,
        ),
    ))

    xml = data_mpd_xml(selected.url)

    assert selected.format == "dash"
    assert selected.transport == "dash"
    assert "id='dash-video'" in xml
    assert "id='dash-audio'" in xml
    assert "codecs='mp4a.40.2'" in xml
    assert "https://cdn.example.test/stream-opus.m3u8" not in xml


def test_select_playable_prefers_allowed_dash_audio_over_higher_bitrate_hls() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "hls-opus",
                    "url": "https://cdn.example.test/stream-opus.m3u8",
                    "protocol": "m3u8_native",
                    "vcodec": "avc1.64001f",
                    "acodec": "opus",
                    "height": 720,
                    "tbr": 2500,
                },
                {
                    "format_id": "dash-video",
                    "url": "https://cdn.example.test/video.mp4",
                    "protocol": "http_dash_segments",
                    "vcodec": "avc1.64001f",
                    "acodec": "none",
                    "height": 720,
                    "tbr": 1800,
                    "init_range": {"start": 0, "end": 99},
                    "index_range": {"start": 100, "end": 199},
                    "fragments": [{"url": "https://cdn.example.test/video/init"}],
                },
                {
                    "format_id": "dash-audio",
                    "url": "https://cdn.example.test/audio.m4a",
                    "protocol": "http_dash_segments",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "abr": 128,
                    "init_range": {"start": 0, "end": 99},
                    "index_range": {"start": 100, "end": 199},
                    "fragments": [{"url": "https://cdn.example.test/audio/init"}],
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264", "vp9", "hevc", "av01"),
            audio_codec_order=("aac", "opus", "eac3", "ac3", "flac"),
        ),
    ))

    xml = data_mpd_xml(selected.url)

    assert selected.format == "dash"
    assert selected.transport == "dash"
    assert "id='dash-video'" in xml
    assert "id='dash-audio'" in xml
    assert "codecs='mp4a.40.2'" in xml
    assert "https://cdn.example.test/stream-opus.m3u8" not in xml


def test_select_playable_applies_audio_codec_order_to_progressive_direct_plan() -> None:
    selector = PlaybackSelector()

    selected = asyncio.run(selector.select_playable(
        {
            "formats": [
                {
                    "format_id": "progressive-opus",
                    "url": "https://cdn.example.test/video-opus.mp4",
                    "protocol": "https",
                    "vcodec": "avc1.64001f",
                    "acodec": "opus",
                    "height": 720,
                    "tbr": 2000,
                },
                {
                    "format_id": "progressive-aac",
                    "url": "https://cdn.example.test/video-aac.mp4",
                    "protocol": "https",
                    "vcodec": "avc1.64001f",
                    "acodec": "mp4a.40.2",
                    "height": 720,
                    "tbr": 1000,
                },
            ],
        },
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264", "vp9", "hevc", "av01"),
            audio_codec_order=("aac",),
            max_video_height=720,
        ),
    ))

    assert selected.url == "https://cdn.example.test/video-aac.mp4"


def test_select_playable_rejects_direct_url_with_disallowed_audio_codec() -> None:
    selector = PlaybackSelector()

    with pytest.raises(ValueError, match="no playable format found"):
        asyncio.run(selector.select_playable(
            {
                "formats": [
                    {
                        "format_id": "unknown-opus",
                        "url": "https://cdn.example.test/video-opus.mp4",
                        "protocol": "http_unknown",
                        "vcodec": "avc1.64001f",
                        "acodec": "opus",
                        "tbr": 2000,
                    },
                ],
            },
            scope=PlaybackScope(
                protocol="tvbox",
                sub_id="main",
                video_codec_order=("h264", "vp9", "hevc", "av01"),
                audio_codec_order=("aac",),
                max_video_height=720,
            ),
        ))
