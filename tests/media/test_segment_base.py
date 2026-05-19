import asyncio
import base64

from dashbox.config import Config
from dashbox.media.dash_proxy import DashProxyStore
from dashbox.media.playback import PlaybackSelector
from dashbox.media.segment_base import build_mpd, probe_webm_segment_base_ranges
from dashbox.media import segment_base
from tests.helpers import data_mpd_xml, make_tvbox_service as MediaService, segment_base_probe_bytes


def test_select_playable_direct_scope_returns_segment_base_data_mpd() -> None:
    store = DashProxyStore()
    selector = PlaybackSelector(store)

    selected = asyncio.run(selector.select_playable(
        {
            "duration": 4,
            "formats": [
                {
                    "format_id": "video",
                    "url": "https://cdn.example.test/video.mp4",
                    "vcodec": "avc1.640028",
                    "acodec": "none",
                    "mime_type": "video/mp4",
                    "height": 720,
                    "tbr": 1200,
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
    ))
    xml = data_mpd_xml(selected.url)

    assert selected.format == "dash"
    assert selected.transport == "dash"
    assert "<BaseURL>https://cdn.example.test/video.mp4</BaseURL>" in xml
    assert "<BaseURL>https://cdn.example.test/audio.m4a</BaseURL>" in xml


def test_select_playable_default_prober_fills_missing_segment_base_ranges(monkeypatch) -> None:
    async def fake_fetch_initial_bytes(self, url, headers, size):
        return segment_base_probe_bytes()

    monkeypatch.setattr(segment_base.SegmentBaseProber, "fetch_initial_bytes", fake_fetch_initial_bytes)

    selected = asyncio.run(PlaybackSelector().select_playable(
        {
            "duration": 4,
            "formats": [
                {
                    "format_id": "video",
                    "url": "https://cdn.example.test/video.mp4",
                    "ext": "mp4",
                    "vcodec": "avc1.640028",
                    "acodec": "none",
                    "mime_type": "video/mp4",
                    "height": 720,
                    "tbr": 1200,
                    "fragments": [{"url": "https://cdn.example.test/video/init"}],
                },
                {
                    "format_id": "audio",
                    "url": "https://cdn.example.test/audio.m4a",
                    "ext": "m4a",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "mime_type": "audio/mp4",
                    "abr": 128,
                    "fragments": [{"url": "https://cdn.example.test/audio/init"}],
                },
            ],
        },
    ))
    xml = data_mpd_xml(selected.url)

    assert selected.format == "dash"
    assert "<Initialization range='0-19'/>" in xml
    assert "indexRange='20-29'" in xml


def test_segment_base_probe_uses_playback_headers(monkeypatch) -> None:
    captured: list[dict[str, str]] = []

    async def fake_fetch_initial_bytes(self, url, headers, size):
        captured.append(headers)
        return segment_base_probe_bytes()

    monkeypatch.setattr(segment_base.SegmentBaseProber, "fetch_initial_bytes", fake_fetch_initial_bytes)
    monkeypatch.setattr(
        segment_base.registry,
        "headers_for_format_urls",
        lambda urls: {"Origin": "https://site.example.test"},
    )

    selected = asyncio.run(PlaybackSelector().select_playable(
        {
            "duration": 4,
            "http_headers": {
                "Cookie": "SESSDATA=test",
                "Referer": "https://site.example.test/",
            },
            "formats": [
                {
                    "format_id": "video",
                    "url": "https://media.example.test/video.m4s",
                    "ext": "mp4",
                    "vcodec": "avc1.640028",
                    "acodec": "none",
                    "mime_type": "video/mp4",
                    "height": 720,
                    "tbr": 1200,
                    "fragments": [{"url": "https://media.example.test/video/init"}],
                },
                {
                    "format_id": "audio",
                    "url": "https://media.example.test/audio.m4s",
                    "ext": "m4a",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "mime_type": "audio/mp4",
                    "abr": 128,
                    "fragments": [{"url": "https://media.example.test/audio/init"}],
                },
            ],
        },
    ))

    assert selected.format == "dash"
    assert captured
    assert all(headers["Cookie"] == "SESSDATA=test" for headers in captured)
    assert all(headers["Referer"] == "https://site.example.test/" for headers in captured)
    assert all(headers["Origin"] == "https://site.example.test" for headers in captured)
    assert all("User-Agent" in headers for headers in captured)


def test_segment_base_probe_uses_current_format_headers(monkeypatch) -> None:
    captured: dict[str, dict[str, str]] = {}

    async def fake_fetch_initial_bytes(self, url, headers, size):
        captured[url] = headers
        return segment_base_probe_bytes()

    monkeypatch.setattr(segment_base.SegmentBaseProber, "fetch_initial_bytes", fake_fetch_initial_bytes)

    selected = asyncio.run(PlaybackSelector().select_playable(
        {
            "duration": 4,
            "http_headers": {"Cookie": "session=common"},
            "formats": [
                {
                    "format_id": "video",
                    "url": "https://cdn.example.test/video.mp4",
                    "ext": "mp4",
                    "vcodec": "avc1.640028",
                    "acodec": "none",
                    "mime_type": "video/mp4",
                    "height": 720,
                    "tbr": 1200,
                    "http_headers": {"Authorization": "Bearer video"},
                    "fragments": [{"url": "https://cdn.example.test/video/init"}],
                },
                {
                    "format_id": "audio",
                    "url": "https://cdn.example.test/audio.m4a",
                    "ext": "m4a",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "mime_type": "audio/mp4",
                    "abr": 128,
                    "http_headers": {"Authorization": "Bearer audio"},
                    "fragments": [{"url": "https://cdn.example.test/audio/init"}],
                },
            ],
        },
    ))

    assert selected.format == "dash"
    assert captured["https://cdn.example.test/video.mp4"]["Cookie"] == "session=common"
    assert captured["https://cdn.example.test/video.mp4"]["Authorization"] == "Bearer video"
    assert captured["https://cdn.example.test/audio.m4a"]["Cookie"] == "session=common"
    assert captured["https://cdn.example.test/audio.m4a"]["Authorization"] == "Bearer audio"


def test_media_service_segment_base_probe_uses_configured_user_agent(monkeypatch) -> None:
    captured: list[dict[str, str]] = []
    service = MediaService(Config(user_agent="Dashbox Custom UA/1.0"))

    async def fake_fetch_initial_bytes(self, url, headers, size):
        captured.append(headers)
        return segment_base_probe_bytes()

    async def fake_playable_info_async(raw_id, extract_url="", *, force_refresh=False):
        return {
            "duration": 4,
            "formats": [
                {
                    "format_id": "video",
                    "url": "https://cdn.example.test/video.mp4",
                    "ext": "mp4",
                    "vcodec": "avc1.640028",
                    "acodec": "none",
                    "mime_type": "video/mp4",
                    "height": 720,
                    "tbr": 1200,
                    "fragments": [{"url": "https://cdn.example.test/video/init"}],
                },
                {
                    "format_id": "audio",
                    "url": "https://cdn.example.test/audio.m4a",
                    "ext": "m4a",
                    "vcodec": "none",
                    "acodec": "mp4a.40.2",
                    "mime_type": "audio/mp4",
                    "abr": 128,
                    "fragments": [{"url": "https://cdn.example.test/audio/init"}],
                },
            ],
        }

    monkeypatch.setattr(segment_base.SegmentBaseProber, "fetch_initial_bytes", fake_fetch_initial_bytes)
    monkeypatch.setattr(service, "playable_info_async", fake_playable_info_async)

    value = asyncio.run(service.play("https://example.test/watch/1"))

    assert value["url"].startswith("data:application/dash+xml;base64,")
    assert captured
    assert all(headers["User-Agent"] == "Dashbox Custom UA/1.0" for headers in captured)
    assert value["header"]["User-Agent"] == "Dashbox Custom UA/1.0"


def test_segment_base_fallback_client_uses_configured_user_agent_and_timeout(monkeypatch) -> None:
    created: dict[str, object] = {}
    streamed: dict[str, object] = {}

    class FakeResponse:
        status_code = 206

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def aiter_bytes(self):
            yield b"abc"

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            created.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method, url, headers):
            streamed.update({"method": method, "url": url, "headers": headers})
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", FakeAsyncClient)

    prober = segment_base.SegmentBaseProber(user_agent="Dashbox Test UA", upstream_timeout=7)
    data = asyncio.run(prober.fetch_initial_bytes("https://cdn.example.test/video.mp4", {"Cookie": "sid=1"}, 3))

    assert data == b"abc"
    assert created["timeout"] == 7
    assert created["follow_redirects"] is True
    assert created["headers"] == {"User-Agent": "Dashbox Test UA"}
    assert streamed["headers"] == {"Cookie": "sid=1", "Range": "bytes=0-2"}


def test_segment_base_probe_logs_fetch_failures(caplog) -> None:
    class FakeClient:
        def stream(self, method, url, headers):
            raise RuntimeError("probe failed at C:\\Users\\anshi\\tmp\\segment.mp4")


def test_build_mpd_treats_missing_vcodec_audio_as_audio() -> None:
    encoded = build_mpd(
        {"duration": 4},
        [
            {
                "format_id": "video",
                "url": "https://cdn.example.test/video.mp4",
                "vcodec": "avc1.640028",
                "acodec": "none",
                "mime_type": "video/mp4",
                "tbr": 200,
                "init_range": {"start": 0, "end": 99},
                "index_range": {"start": 100, "end": 199},
            },
            {
                "format_id": "audio",
                "url": "https://cdn.example.test/audio.m4a",
                "acodec": "mp4a.40.2",
                "mime_type": "audio/mp4",
                "abr": 128,
                "init_range": {"start": 0, "end": 99},
                "index_range": {"start": 100, "end": 199},
            },
        ],
    )
    xml = base64.b64decode(encoded).decode("utf-8")

    assert "contentType='audio'" in xml
    assert "codecs='mp4a.40.2'" in xml
    assert "mimeType='audio/mp4'" in xml


def test_probe_webm_segment_base_ranges_finds_cues() -> None:
    data = (
        b"\x1a\x45\xdf\xa3\x80"
        b"\x18\x53\x80\x67\xff"
        b"\x15\x49\xa9\x66\x80"
        b"\x1c\x53\xbb\x6b\x82xy"
    )

    assert probe_webm_segment_base_ranges(data) == {
        "init": "0-14",
        "index": "15-21",
    }
