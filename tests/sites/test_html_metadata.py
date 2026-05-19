import asyncio

from dashbox.config import Config
from dashbox.sites import html_metadata
from dashbox.sites import twitch
from dashbox.sites import youtube


def test_metadata_from_html_extracts_open_graph_values() -> None:
    html = """
    <html>
      <head>
        <meta property="og:title" content="Fast Title">
        <meta property="og:image" content="/thumb.jpg">
        <meta property="og:description" content="Fast Description">
        <meta property="video:duration" content="123">
      </head>
    </html>
    """

    value = html_metadata.metadata_from_html(html, "https://example.test/watch/1")

    assert value == {
        "webpage_url": "https://example.test/watch/1",
        "title": "Fast Title",
        "thumbnail": "https://example.test/thumb.jpg",
        "description": "Fast Description",
        "duration": 123,
    }


def test_metadata_from_html_handles_reordered_attrs_and_title_fallback() -> None:
    html = """
    <html>
      <head>
        <link href="/poster.jpg" rel="image_src">
        <meta content="45" name="duration">
        <title data-id="x">Fallback    Title</title>
      </head>
    </html>
    """

    value = html_metadata.metadata_from_html(html, "https://example.test/watch/1")

    assert value == {
        "webpage_url": "https://example.test/watch/1",
        "title": "Fallback Title",
        "thumbnail": "https://example.test/poster.jpg",
        "duration": 45,
    }


def test_youtube_light_metadata_prefers_html_description(monkeypatch) -> None:
    config = Config()
    called = {}

    async def fake_html_metadata(raw_id: str) -> dict:
        called["html"] = raw_id
        return {
            "webpage_url": raw_id,
            "title": "HTML Title",
            "thumbnail": "https://example.test/html.jpg",
            "description": "HTML description",
        }

    async def fake_oembed_metadata(*_args, **_kwargs) -> dict:
        raise AssertionError("oEmbed should not run when HTML metadata is available")

    monkeypatch.setattr(youtube, "youtube_oembed_metadata", fake_oembed_metadata)

    value = asyncio.run(youtube.display_metadata(
        "https://www.youtube.com/watch?v=AbCdEfGh123",
        config=config,
        html_metadata=fake_html_metadata,
        impersonated_html_metadata=lambda _url: (_ for _ in ()).throw(AssertionError("not used")),
    ))

    assert called["html"] == "https://www.youtube.com/watch?v=AbCdEfGh123"
    assert value["title"] == "HTML Title"
    assert value["thumbnail"] == "https://example.test/html.jpg"
    assert value["description"] == "HTML description"
    assert value["id"] == "AbCdEfGh123"


def test_youtube_light_metadata_fills_incomplete_html_from_oembed(monkeypatch) -> None:
    config = Config()
    called = {}

    async def fake_html_metadata(raw_id: str) -> dict:
        called["html"] = raw_id
        return {
            "webpage_url": "https://consent.youtube.com/m",
            "description": "HTML description",
        }

    async def fake_oembed_metadata(raw_id: str, youtube_id: str, _config: Config, http_client_provider=None) -> dict:
        called["oembed"] = raw_id
        return {
            "webpage_url": youtube.normalize_playable_url(raw_id),
            "id": youtube_id,
            "title": "oEmbed Title",
            "thumbnail": "https://example.test/oembed.jpg",
        }

    monkeypatch.setattr(youtube, "youtube_oembed_metadata", fake_oembed_metadata)

    value = asyncio.run(youtube.display_metadata(
        "https://www.youtube.com/watch?v=AbCdEfGh123",
        config=config,
        html_metadata=fake_html_metadata,
        impersonated_html_metadata=lambda _url: (_ for _ in ()).throw(AssertionError("not used")),
    ))

    assert called == {
        "html": "https://www.youtube.com/watch?v=AbCdEfGh123",
        "oembed": "https://www.youtube.com/watch?v=AbCdEfGh123",
    }
    assert value == {
        "webpage_url": "https://www.youtube.com/watch?v=AbCdEfGh123",
        "id": "AbCdEfGh123",
        "title": "oEmbed Title",
        "thumbnail": "https://example.test/oembed.jpg",
        "description": "HTML description",
    }


def test_twitch_single_video_light_metadata_skips_site_shell_html(monkeypatch) -> None:
    async def fake_html_light_metadata(*_args, **_kwargs) -> dict:
        raise AssertionError("Twitch playable URLs should fall back to yt-dlp metadata")

    value = asyncio.run(twitch.display_metadata(
        "https://www.twitch.tv/videos/100000001",
        config=Config(),
        html_metadata=fake_html_light_metadata,
        impersonated_html_metadata=lambda _url: (_ for _ in ()).throw(AssertionError("not used")),
    ))

    assert value == {}
