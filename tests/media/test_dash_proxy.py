from concurrent.futures import ThreadPoolExecutor
import asyncio

from dashbox.media import dash_proxy
from dashbox.media.scope import PlaybackScope
from dashbox.server.media_proxy import refresh_dash_session
from tests.helpers import fragmented_formats


def fragmented_video_format(video_url: str, *, format_id: str, fps: int) -> dict:
    return {
        "format_id": format_id,
        "url": video_url,
        "vcodec": "avc1.64001f",
        "acodec": "none",
        "mime_type": "video/mp4",
        "height": 720,
        "fps": fps,
        "tbr": 1000 + fps,
        "init_range": {"start": 0, "end": 99},
        "index_range": {"start": 100, "end": 199},
        "fragments": [
            {"url": video_url + "/init"},
            {"url": video_url + "/1", "duration": 4},
        ],
    }


def fragmented_audio_format(audio_url: str) -> dict:
    return {
        "format_id": "audio",
        "url": audio_url,
        "vcodec": "none",
        "acodec": "mp4a.40.2",
        "mime_type": "audio/mp4",
        "abr": 128,
        "init_range": {"start": 0, "end": 99},
        "index_range": {"start": 100, "end": 199},
        "fragments": [
            {"url": audio_url + "/init"},
            {"url": audio_url + "/1", "duration": 4},
        ],
    }


def test_dash_store_uses_idle_ttl(monkeypatch) -> None:
    now = 1000.0
    monkeypatch.setattr(dash_proxy.time, "time", lambda: now)
    store = dash_proxy.DashProxyStore(idle_ttl_seconds=10, max_age_seconds=100)
    session = store.create({"title": "video"}, fragmented_formats("https://old-v", "https://old-a"), "https://page")

    now = 1009.0
    assert store.get(session.token) is session

    now = 1018.0
    assert store.get(session.token) is session

    now = 1029.0
    assert store.get(session.token) is None


def test_dash_store_default_lifetime_uses_six_hour_idle_ttl_without_max_age() -> None:
    store = dash_proxy.DashProxyStore()

    assert store.idle_ttl_seconds == 21600
    assert store.max_age_seconds is None


def test_dash_store_has_no_fixed_max_age_when_disabled(monkeypatch) -> None:
    now = 1000.0
    monkeypatch.setattr(dash_proxy.time, "time", lambda: now)
    store = dash_proxy.DashProxyStore(idle_ttl_seconds=10, max_age_seconds=None)
    session = store.create({"title": "video"}, fragmented_formats("https://old-v", "https://old-a"), "https://page")

    now = 1009.0
    assert store.get(session.token) is session

    now = 2000.0
    session.last_accessed_at = 1999.0
    assert store.get(session.token) is session


def test_dash_store_refresh_replaces_urls_when_structure_matches() -> None:
    store = dash_proxy.DashProxyStore()
    session = store.create({"title": "video"}, fragmented_formats("https://old-v", "https://old-a"), "https://page")

    refreshed = store.refresh(session.token, {"title": "video"}, fragmented_formats("https://new-v", "https://new-a"))

    assert refreshed is not None
    assert refreshed.token == session.token
    assert refreshed.raw_id == "https://page"
    assert refreshed.tracks[0].segments[1].url == "https://new-v/1"
    assert store.get(session.token).tracks[1].segments[1].url == "https://new-a/1"


def test_dash_session_refresh_preserves_max_video_fps_cap() -> None:
    class Service:
        def __init__(self):
            self.calls = []

        def playable_info(self, raw_id: str, *, force_refresh: bool = False):
            raise AssertionError("refresh should use async playable_info")

        async def playable_info_async(self, raw_id: str, extract_url: str = "", *, force_refresh: bool = False):
            self.calls.append((raw_id, extract_url, force_refresh))
            return {
                "duration": 4,
                "formats": [
                    fragmented_audio_format("https://new-a"),
                    fragmented_video_format("https://new-v-30", format_id="video-30", fps=30),
                    fragmented_video_format("https://new-v-60", format_id="video-60", fps=60),
                ],
            }

    class State:
        def __init__(self):
            self.dash_store = dash_proxy.DashProxyStore()
            self.service = Service()

        def service_for_scope(self, scope):
            return self.service

    state = State()
    session = state.dash_store.create(
        {"title": "video", "duration": 4},
        [
            fragmented_audio_format("https://old-a"),
            fragmented_video_format("https://old-v-30", format_id="video-30", fps=30),
        ],
        "https://page",
        scope=PlaybackScope(
            protocol="tvbox",
            sub_id="main",
            video_codec_order=("h264",),
            max_video_height=720,
            max_video_fps=30,
        ),
    )

    refreshed = asyncio.run(refresh_dash_session(session, state))

    assert refreshed is not None
    assert state.service.calls == [("https://page", "", True)]
    assert refreshed.tracks[0].segments[1].url == "https://new-a/1"
    assert refreshed.tracks[1].segments[1].url == "https://new-v-30/1"


def test_dash_session_refresh_uses_async_playable_info_for_bilibili_player_url() -> None:
    raw_id = "https://player.bilibili.com/player.html?aid=10000001&cid=20000002"

    class Service:
        def __init__(self):
            self.calls = []

        def playable_info(self, raw_id: str, *, force_refresh: bool = False):
            raise AssertionError("refresh should not use blocking playable_info")

        async def playable_info_async(self, raw_id: str, extract_url: str = "", *, force_refresh: bool = False):
            self.calls.append((raw_id, extract_url, force_refresh))
            return {
                "duration": 4,
                "formats": [
                    fragmented_audio_format("https://new-a"),
                    fragmented_video_format("https://new-v", format_id="video", fps=30),
                ],
            }

    class State:
        def __init__(self):
            self.dash_store = dash_proxy.DashProxyStore()
            self.service = Service()

        def service_for_scope(self, scope):
            return self.service

    state = State()
    session = state.dash_store.create(
        {"title": "video", "duration": 4},
        [
            fragmented_audio_format("https://old-a"),
            fragmented_video_format("https://old-v", format_id="video", fps=30),
        ],
        raw_id,
    )

    refreshed = asyncio.run(refresh_dash_session(session, state))

    assert refreshed is not None
    assert state.service.calls == [(raw_id, "", True)]
    assert refreshed.raw_id == raw_id
    assert refreshed.tracks[0].segments[1].url == "https://new-a/1"
    assert refreshed.tracks[1].segments[1].url == "https://new-v/1"


def test_dash_store_refresh_keeps_old_session_when_structure_changes() -> None:
    store = dash_proxy.DashProxyStore()
    session = store.create({"title": "video"}, fragmented_formats("https://old-v", "https://old-a"), "https://page")

    refreshed = store.refresh(
        session.token,
        {"title": "video"},
        fragmented_formats("https://new-v", "https://new-a", extra_video_segment=True),
    )

    assert refreshed is None
    assert store.get(session.token).tracks[0].segments[1].url == "https://old-v/1"


def test_dash_store_allows_concurrent_access() -> None:
    store = dash_proxy.DashProxyStore()
    seed = store.create({"title": "video"}, fragmented_formats("https://seed-v", "https://seed-a"), "https://page")

    def worker(index: int) -> None:
        session = store.create(
            {"title": f"video-{index}"},
            fragmented_formats(f"https://old-v-{index}", f"https://old-a-{index}"),
            f"https://page-{index}",
        )
        assert store.get(session.token) is not None
        store.refresh(session.token, {"title": f"video-{index}"}, fragmented_formats(f"https://new-v-{index}", f"https://new-a-{index}"))
        store.get(seed.token)
        store.prune()

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(worker, range(32)))

    assert store.get(seed.token) is not None
