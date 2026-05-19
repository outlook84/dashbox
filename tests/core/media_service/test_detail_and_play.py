import asyncio


from dashbox.config import Config
from tests.helpers import disable_playable_prewarm, make_tvbox_service as MediaService, patch_metadata_for_plan


def test_detail_uses_light_metadata_for_single_video(monkeypatch) -> None:
    service = MediaService(Config())

    async def fake_light_metadata(raw_id: str) -> dict:
        assert raw_id == "https://www.youtube.com/watch?v=AbCdEfGh123"
        return {
            "webpage_url": raw_id,
            "title": "Light Title",
            "thumbnail": "https://example.test/light.jpg",
            "description": "Light\ndescription",
        }

    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)
    disable_playable_prewarm(monkeypatch, service)

    value = asyncio.run(service.detail("https://www.youtube.com/watch?v=AbCdEfGh123"))

    vod = value["list"][0]
    assert vod["vod_name"] == "Light Title"
    assert vod["vod_pic"] == "https://example.test/light.jpg"
    assert vod["vod_content"] == "Light\u00a0description"
    assert vod["vod_play_url"] == "Light Title$https://www.youtube.com/watch?v=AbCdEfGh123"


def test_play_reuses_single_video_detail_extract(monkeypatch) -> None:
    service = MediaService(Config())
    calls: list[str] = []

    async def fake_light_metadata(raw_id: str) -> dict:
        return {"webpage_url": raw_id, "title": "Light Title"}

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False, require_playable: bool = False):
        assert url == "https://www.youtube.com/watch?v=AbCdEfGh123"
        assert download is False
        assert playlist is False
        assert flat is False
        assert require_playable is True
        calls.append(url)
        return {
            "webpage_url": url,
            "title": "Cached Title",
            "formats": [{"url": "https://cdn.example.test/cached.mp4", "vcodec": "avc1", "acodec": "mp4a", "ext": "mp4"}],
        }

    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)
    monkeypatch.setattr(service, "extract", fake_extract)

    async def run_detail_then_play() -> dict:
        detail = await service.detail("https://www.youtube.com/watch?v=AbCdEfGh123")
        for _index in range(20):
            if calls:
                break
            await asyncio.sleep(0.01)
        play_value = detail["list"][0]["vod_play_url"].split("$", 1)[1]
        return await service.play(play_value, "http://127.0.0.1:18990")

    play = asyncio.run(run_detail_then_play())

    assert calls == ["https://www.youtube.com/watch?v=AbCdEfGh123"]
    assert play["url"] == "https://cdn.example.test/cached.mp4"
    assert "dashbox_playback_source" not in play


def test_detail_canonicalizes_single_video_url_before_extract(monkeypatch) -> None:
    service = MediaService(Config())
    source_url = "https://www.youtube.com/watch?v=AbCdEfGh123&list=RDabc&index=3"
    canonical_url = "https://www.youtube.com/watch?v=AbCdEfGh123"
    captured = {}

    async def fake_light_metadata(raw_id: str) -> dict:
        assert raw_id == canonical_url
        return {"webpage_url": raw_id, "title": "Canonical Light"}

    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)
    monkeypatch.setattr(
        service,
        "start_single_video_playable_prewarm",
        lambda clean_id, extract_url="": captured.update(clean_id=clean_id, extract_url=extract_url),
    )

    value = asyncio.run(service.detail(source_url))

    vod = value["list"][0]
    assert captured == {"clean_id": canonical_url, "extract_url": canonical_url}
    assert vod["vod_name"] == "Canonical Light"


def test_generic_known_single_video_detail_uses_fast_placeholder_and_prewarms(monkeypatch) -> None:
    service = MediaService(Config())
    raw_id = "https://spankbang.com/pl001-item001/playlist/sample+playlist?dashbox_index=21"
    clean_id = "https://spankbang.com/pl001-item001/playlist/sample+playlist"
    prewarms = []

    def fake_extract(url: str, *, download: bool, playlist: bool, flat: bool = False, require_playable: bool = False):
        raise AssertionError("non-YouTube/Bilibili detail should not wait for full yt-dlp extraction")

    async def fake_light_metadata(raw_id: str) -> dict:
        raise AssertionError("generic known single detail should not wait for light metadata")

    monkeypatch.setattr(service, "extract", fake_extract)
    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)
    monkeypatch.setattr(service, "start_single_video_playable_prewarm", lambda clean_id, extract_url="": prewarms.append((clean_id, extract_url)))

    value = asyncio.run(service.detail(raw_id))

    assert prewarms == [(clean_id, "")]
    vod = value["list"][0]
    assert vod["vod_name"] == clean_id
    assert vod["vod_play_url"] == f"{clean_id}${clean_id}"


def test_twitch_single_video_detail_reuses_light_metadata(monkeypatch) -> None:
    service = MediaService(Config())
    raw_id = "https://www.twitch.tv/videos/100000001"
    prewarms = []

    async def fake_light_metadata(raw_id: str) -> dict:
        assert raw_id == "https://www.twitch.tv/videos/100000001"
        return {
            "webpage_url": raw_id,
            "title": "Twitch VOD Title",
            "thumbnail": "https://static-cdn.jtvnw.net/cf_vods/thumb.jpg",
        }

    patch_metadata_for_plan(monkeypatch, service, single=fake_light_metadata)
    monkeypatch.setattr(service, "start_single_video_playable_prewarm", lambda clean_id, extract_url="": prewarms.append((clean_id, extract_url)))

    value = asyncio.run(service.detail(raw_id))

    assert prewarms == [(raw_id, "")]
    vod = value["list"][0]
    assert vod["vod_name"] == "Twitch VOD Title"
    assert vod["vod_pic"] == "https://static-cdn.jtvnw.net/cf_vods/thumb.jpg"
    assert vod["vod_play_url"] == f"Twitch VOD Title${raw_id}"
