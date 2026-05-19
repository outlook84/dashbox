import asyncio

import pytest

from dashbox.config import Config
from dashbox.core.client_model import ClientArt, ClientItem, ClientPage
from dashbox.sites import youtube
from dashbox.adapters import tvbox
from tests.helpers import make_tvbox_service as MediaService, patch_metadata_for_plan
from dashbox.adapters import tvbox_text


def test_play_strips_internal_episode_index(monkeypatch) -> None:
    service = MediaService(Config())
    captured = {}

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False, require_playable: bool = False):
        captured["url"] = url
        return {
            "formats": [
                {
                    "url": "https://cdn.example.test/video.mp4",
                    "vcodec": "avc1.640028",
                    "acodec": "mp4a.40.2",
                    "ext": "mp4",
                }
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    value = asyncio.run(service.play("https://www.youtube.com/watch?v=AbCdEfGh123&dashbox_index=12&list=PLabc"))

    assert captured["url"] == "https://www.youtube.com/watch?v=AbCdEfGh123&list=PLabc"
    assert value["url"] == "https://cdn.example.test/video.mp4"


def test_play_restores_tvbox_play_value_before_extraction(monkeypatch) -> None:
    service = MediaService(Config())
    raw_id = "https://example.test/watch#frag$part?x=%23"
    play_value = tvbox_text.safe_play_value(raw_id)
    captured = {}

    async def fake_playable_info_async(raw_id: str, extract_url: str = "", *, force_refresh: bool = False):
        captured["raw_id"] = raw_id
        captured["extract_url"] = extract_url
        captured["force_refresh"] = force_refresh
        return {"url": "https://cdn.example.test/video.mp4"}

    monkeypatch.setattr(service, "playable_info_async", fake_playable_info_async)

    value = asyncio.run(service.play(play_value, "http://testserver"))

    assert captured["raw_id"] == raw_id
    assert captured["extract_url"] == ""
    assert captured["force_refresh"] is False
    assert value["url"] == "https://cdn.example.test/video.mp4"


def test_play_reuses_cached_playable_info(monkeypatch) -> None:
    service = MediaService(Config())
    calls = []

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False, require_playable: bool = False):
        calls.append(url)
        return {
            "formats": [
                {
                    "url": f"https://cdn.example.test/video-{len(calls)}.mp4",
                    "vcodec": "avc1.640028",
                    "acodec": "mp4a.40.2",
                    "ext": "mp4",
                }
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    first = asyncio.run(service.play("https://example.test/watch/1"))
    second = asyncio.run(service.play("https://example.test/watch/1"))

    assert len(calls) == 1
    assert first["url"] == "https://cdn.example.test/video-1.mp4"
    assert second["url"] == "https://cdn.example.test/video-1.mp4"


def test_playable_info_async_checks_cache_before_resolving_extract_url(monkeypatch) -> None:
    service = MediaService(Config())
    calls = []

    async def fake_resolve_extract_url(url: str) -> str:
        calls.append(("resolve", url))
        return "https://www.bilibili.com/video/av10000001?p=2"

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False, require_playable: bool = False):
        calls.append(("extract", url))
        return {
            "formats": [
                {
                    "url": "https://cdn.example.test/video.mp4",
                    "vcodec": "avc1.640028",
                    "acodec": "mp4a.40.2",
                    "ext": "mp4",
                }
            ],
        }

    monkeypatch.setattr(service.site_runtime.bilibili.site, "resolve_extract_url", fake_resolve_extract_url)
    monkeypatch.setattr(service, "extract", fake_extract)

    raw_id = "https://player.bilibili.com/player.html?aid=10000001&cid=20000002"
    first = asyncio.run(service.playable_info_async(raw_id))
    second = asyncio.run(service.playable_info_async(raw_id))

    assert calls == [
        ("resolve", raw_id),
        ("extract", "https://www.bilibili.com/video/av10000001?p=2"),
    ]
    assert first is second


def test_extract_playable_info_rejects_bilibili_player_cid_without_page_blocking() -> None:
    service = MediaService(Config())

    with pytest.raises(RuntimeError, match="async playback API"):
        service.extract_playable_info("https://player.bilibili.com/player.html?aid=10000001&cid=20000002")


def test_extract_playable_info_uses_explicit_bilibili_extract_url_blocking(monkeypatch) -> None:
    service = MediaService(Config())
    calls = []

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False, require_playable: bool = False):
        calls.append(url)
        return {
            "url": url,
            "formats": [
                {
                    "url": "https://cdn.example.test/video.mp4",
                    "vcodec": "avc1.640028",
                    "acodec": "mp4a.40.2",
                    "ext": "mp4",
                }
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    info = service.extract_playable_info(
        "https://player.bilibili.com/player.html?aid=10000001&cid=20000002",
        "https://www.bilibili.com/video/av10000001?p=2",
    )

    assert calls == ["https://www.bilibili.com/video/av10000001?p=2"]
    assert info["url"] == "https://www.bilibili.com/video/av10000001?p=2"


def test_extract_playable_info_rejects_running_event_loop() -> None:
    service = MediaService(Config())

    async def run() -> None:
        with pytest.raises(RuntimeError, match="blocking internal API"):
            service.extract_playable_info("https://player.bilibili.com/player.html?aid=10000001&cid=20000002")

    asyncio.run(run())


def test_playable_info_normalizes_bilibili_player_iframe(monkeypatch) -> None:
    service = MediaService(Config())
    calls = []

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False, require_playable: bool = False):
        calls.append({
            "url": url,
            "download": download,
            "playlist": playlist,
            "flat": flat,
            "require_playable": require_playable,
        })
        return {
            "url": "https://cdn.example.test/video.mp4",
            "vcodec": "avc1",
            "acodec": "mp4a",
            "cid": 20000001,
            "extractor_key": "Bilibili",
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    value = asyncio.run(service.play(
        "https://player.bilibili.com/player.html?aid=10000001&cid=20000001&page=1",
        base_url="http://testserver",
    ))

    assert calls == [{
        "url": "https://www.bilibili.com/video/av10000001?p=1",
        "download": False,
        "playlist": False,
        "flat": False,
        "require_playable": True,
    }]
    assert value["url"] == "https://cdn.example.test/video.mp4"
    assert value["danmaku"] == "http://testserver/danmaku/bilibili/20000001.xml"


def test_youtube_thumbnail_from_info_uses_best_stable_playlist_thumbnail() -> None:
    value = youtube.thumbnail_from_info({
        "id": "OLAK5sampleplaylist0000000000000000000000",
        "thumbnails": [
            {"url": "https://i9.ytimg.com/s_p/OLAK5sampleplaylist0000000000000000000000/maxresdefault.jpg", "width": 1200, "height": 1200},
            {"url": "https://lh3.googleusercontent.com/example=w180-h180-l90-rj", "width": 180, "height": 180},
            {"url": "https://lh3.googleusercontent.com/example=w640-h640-l90-rj", "width": 640, "height": 640},
        ],
    })

    assert value == "https://lh3.googleusercontent.com/example=w640-h640-l90-rj"
def test_detail_watch_with_playlist_parameter_returns_single_video(monkeypatch) -> None:
    service = MediaService(Config())
    source_url = "https://www.youtube.com/watch?list=PL0000000000000000000000000000000000&v=AbCdEfGh123"
    canonical_url = "https://www.youtube.com/watch?v=AbCdEfGh123"
    captured = {}

    async def fake_light_metadata(raw_id: str) -> dict:
        assert raw_id == canonical_url
        return {"webpage_url": raw_id, "title": "Single Video", "description": "Single description"}

    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)
    monkeypatch.setattr(
        service,
        "start_single_video_playable_prewarm",
        lambda clean_id, extract_url="": captured.update(clean_id=clean_id, extract_url=extract_url),
    )

    value = asyncio.run(service.detail(source_url))

    vod = value["list"][0]
    assert captured == {"clean_id": canonical_url, "extract_url": canonical_url}
    assert vod["vod_name"] == "Single Video"
    assert vod["vod_content"] == "Single\u00a0description"
    assert vod["vod_play_url"] == f"Single Video${canonical_url}"


def test_plain_playlist_detail_returns_directory(monkeypatch) -> None:
    service = MediaService(Config())
    playlist_url = "https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000"

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False):
        assert url == playlist_url
        assert playlist is True
        assert flat is True
        return {
            "title": "Playlist Title",
            "webpage_url": url,
            "entries": [
                {
                    "title": "First Video",
                    "webpage_url": "https://www.youtube.com/watch?v=AbCdEfGh123",
                },
            ],
        }

    monkeypatch.setattr(service, "extract", fake_extract)

    value = asyncio.run(service.detail(playlist_url))

    directory, vod = value["list"]
    assert directory["vod_name"] == "播放此列表"
    assert "vod_play_url" not in directory
    assert vod["dashbox_playlist_url"] == "https://www.youtube.com/watch?v=AbCdEfGh123&dashbox_index=1"


def test_shorts_url_uses_canonical_light_detail(monkeypatch) -> None:
    service = MediaService(Config())
    canonical_url = "https://www.youtube.com/watch?v=ZzYyXxWw123"
    captured = {}

    async def fake_light_metadata(raw_id: str) -> dict:
        assert raw_id == canonical_url
        return {"webpage_url": raw_id, "title": "Short Video", "description": "Short description"}

    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)
    monkeypatch.setattr(
        service,
        "start_single_video_playable_prewarm",
        lambda clean_id, extract_url="": captured.update(clean_id=clean_id, extract_url=extract_url),
    )

    value = asyncio.run(service.detail("https://www.youtube.com/shorts/ZzYyXxWw123"))

    vod = value["list"][0]
    assert captured == {"clean_id": canonical_url, "extract_url": canonical_url}
    assert vod["vod_name"] == "Short Video"
    assert vod["vod_content"] == "Short\u00a0description"
    assert vod["vod_play_url"] == f"Short Video${canonical_url}"


def test_clip_url_uses_url_detail_when_light_metadata_fails(monkeypatch) -> None:
    service = MediaService(Config())
    clip_url = "https://www.youtube.com/clip/Ugysampleclip1234567890"

    async def fake_light_metadata(raw_id: str) -> dict:
        assert raw_id == clip_url
        return {}

    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata, fallback=False)
    monkeypatch.setattr(
        service,
        "start_single_video_playable_prewarm",
        lambda clean_id, extract_url="": (_ for _ in ()).throw(AssertionError("clip should not prewarm full extraction")),
    )
    monkeypatch.setattr(
        service,
        "single_video_full_detail",
        lambda clean_id: (_ for _ in ()).throw(AssertionError("clip should not use full extraction")),
    )

    value = asyncio.run(service.detail(clip_url))

    vod = value["list"][0]
    assert vod["vod_name"] == clip_url
    assert vod["vod_play_url"] == f"{clip_url}${clip_url}"


def test_playlist_item_keeps_list_metadata_when_full_detail_falls_back_to_url(monkeypatch) -> None:
    service = MediaService(Config())
    playlist_url = "https://www.youtube.com/playlist?list=PL0000000000000000000000000000000000"
    clip_url = "https://www.youtube.com/clip/Ugysampleclip1234567890"
    selected_url = tvbox.with_episode_index(clip_url, 1)
    page = ClientPage(items=(ClientItem(
        id="clip-id",
        title="List Clip Title",
        art=ClientArt(thumb="https://example.test/list.jpg"),
        playlist_title="List Clip Title",
        selected_url=selected_url,
    ),))

    async def fake_playlist_item_full_detail(raw_id: str, base_url: str = "") -> dict:
        assert raw_id == clip_url
        return service.tvbox_detail_from_client_page(service.client_page_from_metadata(
            clip_url,
            {"webpage_url": clip_url, "title": clip_url},
        ))

    monkeypatch.setattr(service, "single_video_detail", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("playlist item should not call single_video_detail")))
    monkeypatch.setattr(service, "playlist_item_full_detail", fake_playlist_item_full_detail)

    value = asyncio.run(service.playlist_item_detail_page_with_metadata(page, playlist_url, selected_url))

    vod = value["list"][0]
    assert vod["vod_name"] == "List Clip Title"
    assert vod["vod_pic"] == "https://example.test/list.jpg"


def test_non_youtube_playlist_item_detail_prewarms_playable_info(monkeypatch) -> None:
    service = MediaService(Config())
    playlist_url = "https://www.xvideos.com/favorite/91000002/_"
    selected_url = "https://www.xvideos.com/video.two/second?dashbox_index=2"
    clean_selected = "https://www.xvideos.com/video.two/second"
    prewarms = []
    page = ClientPage(items=(ClientItem(
        id=clean_selected,
        title="Second",
        art=ClientArt(thumb="https://example.test/list.jpg"),
        playlist_title="Second",
        selected_url=selected_url,
    ),))

    async def fail_single_video_detail(raw_id: str) -> dict:
        raise AssertionError("non-YouTube/Bilibili playlist item should use existing list metadata")

    monkeypatch.setattr(service, "single_video_detail", fail_single_video_detail)
    monkeypatch.setattr(service, "start_single_video_playable_prewarm", lambda clean_id, extract_url="": prewarms.append((clean_id, extract_url)))

    value = asyncio.run(service.playlist_item_detail_page_with_metadata(page, playlist_url, selected_url))

    assert prewarms == [(clean_selected, "")]
    vod = value["list"][0]
    assert vod["vod_name"] == "Second"
    assert vod["vod_pic"] == "https://example.test/list.jpg"
    selected, _directory = vod["vod_play_url"].split("$$$")
    assert selected == "Second$https://www.xvideos.com/video.two/second?dashbox_index=2"


