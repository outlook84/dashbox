import base64
import hashlib
import sys
import types
import zipfile
import xml.etree.ElementTree as ET
from io import BytesIO

import httpx

import dashbox.server.app as server
from dashbox.adapters import kodi_repository
from dashbox.auth.tokens import issue_access_token, issue_media_token
from dashbox.config import Config, FolderItem, KodiSubscriptionConfig, Subscription, TvboxSubscriptionConfig
from dashbox.media.scope import PlaybackScope
from tests.helpers import fragmented_formats, no_lifespan_test_client


def kodi_sub(sub_id: str, *, auth_mode: str = "anonymous", access_code_hash: str = "") -> Subscription:
    return Subscription(
        id=sub_id,
        type="kodi",
        auth_mode=auth_mode,  # type: ignore[arg-type]
        access_code_hash=access_code_hash,
        kodi=KodiSubscriptionConfig(
            sources=(FolderItem("Folder", id="folder"),),
        ),
    )


def test_kodi_api_requires_kodi_access_token() -> None:
    config = Config(subs=(kodi_sub("main"),))

    with no_lifespan_test_client(server.create_app(config)) as client:
        unauthorized = client.get("/api/v1/subs/main/home")
        auth = client.post("/api/v1/subs/main/auth", json={"client": "kodi"})
        authorized = client.get("/api/v1/subs/main/home", headers={"X-Access-Token": auth.json()["access_token"]})

    assert unauthorized.status_code == 401
    assert auth.status_code == 200
    assert auth.json()["ok"] is True
    assert authorized.status_code == 200
    assert authorized.json()["version"] == 2
    assert authorized.json()["items"][0]["id"].startswith("cfg:main:root:")


def test_kodi_routes_reject_unknown_or_non_kodi_subscriptions() -> None:
    config = Config(subs=(kodi_sub("main"), Subscription(id="tv", type="tvbox", tvbox=TvboxSubscriptionConfig())))

    with no_lifespan_test_client(server.create_app(config)) as client:
        unknown = client.post("/api/v1/subs/missing/auth", json={})
        non_kodi = client.post("/api/v1/subs/tv/auth", json={})

    assert unknown.status_code == 404
    assert non_kodi.status_code == 404


def test_kodi_items_returns_protocol_neutral_page() -> None:
    config = Config(subs=(kodi_sub("main"),))
    app = server.create_app(config)
    token, _ = issue_access_token(
        secret=app.state.dashbox.token_secret,
        sub_id="main",
        audience="kodi",
        access_code_hash="",
    )

    with no_lifespan_test_client(app) as client:
        home = client.get("/api/v1/subs/main/home", headers={"X-Access-Token": token})
        root_id = home.json()["items"][0]["id"]
        response = client.get("/api/v1/subs/main/items", params={"id": root_id}, headers={"X-Access-Token": token})

    assert response.status_code == 200
    value = response.json()
    assert value["version"] == 2
    assert value["title"] == "Folder"
    assert value["items"] == []


def test_kodi_play_attaches_media_token_to_headers(monkeypatch) -> None:
    config = Config(subs=(kodi_sub("main"),))
    app = server.create_app(config)
    session = app.state.dashbox.dash_store.create(
        {"title": "video"},
        fragmented_formats("https://old-v", "https://old-a"),
        "https://page",
        scope=PlaybackScope("kodi", "main"),
    )
    token, _ = issue_access_token(
        secret=app.state.dashbox.token_secret,
        sub_id="main",
        audience="kodi",
        access_code_hash="",
    )

    async def fake_play(_id: str, _base_url: str, _playback_preferences=None) -> dict:
        return {
            "version": 2,
            "url": f"http://testserver/media/{session.token}/manifest.mpd",
            "headers": {"User-Agent": "upstream", "X-Media-Token": "old"},
        }

    monkeypatch.setattr(app.state.dashbox.kodi_service("main"), "play", fake_play)

    with no_lifespan_test_client(app) as client:
        response = client.post(
            "/api/v1/subs/main/play",
            json={"id": "video"},
            headers={"X-Access-Token": token},
        )

    assert response.status_code == 200
    headers = response.json()["headers"]
    assert headers["User-Agent"] == "upstream"
    assert headers["X-Media-Token"]

    with no_lifespan_test_client(app) as client:
        dash_response = client.get(f"/media/{session.token}/manifest.mpd", headers={"X-Media-Token": headers["X-Media-Token"]})

    assert dash_response.status_code == 200


def test_kodi_play_attaches_media_token_to_dash_stream_headers(monkeypatch) -> None:
    config = Config(subs=(kodi_sub("main"),))
    app = server.create_app(config)
    session = app.state.dashbox.dash_store.create(
        {"title": "video"},
        fragmented_formats("https://old-v", "https://old-a"),
        "https://page",
        scope=PlaybackScope("kodi", "main"),
    )
    token, _ = issue_access_token(
        secret=app.state.dashbox.token_secret,
        sub_id="main",
        audience="kodi",
        access_code_hash="",
    )

    async def fake_play(_id: str, _base_url: str, _playback_preferences=None) -> dict:
        return {
            "version": 2,
            "url": f"http://testserver/media/{session.token}/manifest.mpd",
            "headers": {"User-Agent": "upstream", "X-Media-Token": "old"},
            "inputstream": {
                "addon": "inputstream.adaptive",
                "manifest_type": "mpd",
                "manifest_headers": {"User-Agent": "upstream", "X-Media-Token": "old"},
                "stream_headers": {"User-Agent": "upstream", "X-Media-Token": "old"},
            },
        }

    monkeypatch.setattr(app.state.dashbox.kodi_service("main"), "play", fake_play)

    with no_lifespan_test_client(app) as client:
        response = client.post(
            "/api/v1/subs/main/play",
            json={"id": "video"},
            headers={"X-Access-Token": token},
        )

    assert response.status_code == 200
    value = response.json()
    media_token = value["headers"]["X-Media-Token"]
    assert media_token
    assert value["inputstream"]["manifest_headers"]["X-Media-Token"] == media_token
    assert value["inputstream"]["stream_headers"]["X-Media-Token"] == media_token
    assert value["inputstream"]["stream_headers"]["User-Agent"] == "upstream"


def test_kodi_play_localizes_data_mpd_manifest(monkeypatch) -> None:
    config = Config(subs=(kodi_sub("main"),))
    app = server.create_app(config)
    token, _ = issue_access_token(
        secret=app.state.dashbox.token_secret,
        sub_id="main",
        audience="kodi",
        access_code_hash="",
    )
    mpd = "<?xml version='1.0' encoding='UTF-8'?><MPD xmlns='urn:mpeg:dash:schema:mpd:2011' type='static'></MPD>"
    data_url = "data:application/dash+xml;base64," + base64.b64encode(mpd.encode()).decode()

    async def fake_play(_id: str, _base_url: str, _playback_preferences=None) -> dict:
        return {
            "version": 2,
            "url": data_url,
            "headers": {"Referer": "https://media.example.test/video/BV1"},
            "inputstream": {
                "addon": "inputstream.adaptive",
                "manifest_type": "mpd",
                "manifest_headers": {"Referer": "https://media.example.test/video/BV1"},
                "stream_headers": {"Referer": "https://media.example.test/video/BV1"},
            },
        }

    monkeypatch.setattr(app.state.dashbox.kodi_service("main"), "play", fake_play)

    with no_lifespan_test_client(app) as client:
        response = client.post(
            "/api/v1/subs/main/play",
            json={"id": "video"},
            headers={"X-Access-Token": token},
        )

        assert response.status_code == 200
        value = response.json()
        assert value["url"].startswith("http://testserver/media/")
        assert value["url"].endswith("/manifest.mpd")
        assert value["headers"]["X-Media-Token"]
        assert value["inputstream"]["manifest_headers"]["X-Media-Token"] == value["headers"]["X-Media-Token"]
        assert "X-Media-Token" not in value["inputstream"]["stream_headers"]

        manifest = client.get(value["url"], headers={"X-Media-Token": value["headers"]["X-Media-Token"]})

    assert manifest.status_code == 200
    assert manifest.text == mpd
    assert manifest.headers["content-type"].startswith("application/dash+xml")


def test_kodi_play_adds_bilibili_danmaku_as_ass_subtitle(monkeypatch) -> None:
    config = Config(subs=(kodi_sub("main"),))
    app = server.create_app(config)
    token, _ = issue_access_token(
        secret=app.state.dashbox.token_secret,
        sub_id="main",
        audience="kodi",
        access_code_hash="",
    )

    async def fake_play(_id: str, _base_url: str, _playback_preferences=None) -> dict:
        return {
            "version": 2,
            "url": "https://cdn.example.test/video.mp4",
            "subtitles": [{"url": "https://cdn.example.test/en.vtt", "name": "en", "format": "vtt"}],
            "danmaku_url": "http://testserver/danmaku/bilibili/20000001.xml",
        }

    monkeypatch.setattr(app.state.dashbox.kodi_service("main"), "play", fake_play)

    with no_lifespan_test_client(app) as client:
        response = client.post(
            "/api/v1/subs/main/play",
            json={"id": "video", "playback": {"danmaku_font_size": 36}},
            headers={"X-Access-Token": token},
        )

    assert response.status_code == 200
    subtitles = response.json()["subtitles"]
    assert subtitles[-1] == {
        "url": "http://testserver/danmaku/bilibili/20000001.ass?font_size=36",
        "name": "Danmaku",
        "language": "zh",
        "format": "ass",
    }


def test_kodi_play_skips_bilibili_danmaku_when_disabled(monkeypatch) -> None:
    config = Config(subs=(kodi_sub("main"),))
    app = server.create_app(config)
    token, _ = issue_access_token(
        secret=app.state.dashbox.token_secret,
        sub_id="main",
        audience="kodi",
        access_code_hash="",
    )

    async def fake_play(_id: str, _base_url: str, _playback_preferences=None) -> dict:
        return {
            "version": 2,
            "url": "https://cdn.example.test/video.mp4",
            "subtitles": [{"url": "https://cdn.example.test/en.vtt", "name": "en", "format": "vtt"}],
            "danmaku_url": "http://testserver/danmaku/bilibili/20000001.xml",
        }

    monkeypatch.setattr(app.state.dashbox.kodi_service("main"), "play", fake_play)

    with no_lifespan_test_client(app) as client:
        response = client.post(
            "/api/v1/subs/main/play",
            json={"id": "video", "playback": {"danmaku_enabled": False, "danmaku_font_size": 36}},
            headers={"X-Access-Token": token},
        )

    assert response.status_code == 200
    assert response.json()["subtitles"] == [{"url": "https://cdn.example.test/en.vtt", "name": "en", "format": "vtt"}]


def test_kodi_play_wraps_extensionless_subtitle_urls(monkeypatch) -> None:
    config = Config(subs=(kodi_sub("main"),))
    app = server.create_app(config)
    token, _ = issue_access_token(
        secret=app.state.dashbox.token_secret,
        sub_id="main",
        audience="kodi",
        access_code_hash="",
    )
    real_url = "https://www.youtube.com/api/timedtext?v=abc&lang=zh-Hans&fmt=srt"

    async def fake_play(_id: str, _base_url: str, _playback_preferences=None) -> dict:
        return {
            "version": 2,
            "url": "https://cdn.example.test/video.mp4",
            "subtitles": [{"url": real_url, "name": "Chinese", "language": "zh-Hans", "format": "srt"}],
        }

    monkeypatch.setattr(app.state.dashbox.kodi_service("main"), "play", fake_play)

    with no_lifespan_test_client(app) as client:
        response = client.post(
            "/api/v1/subs/main/play",
            json={"id": "video"},
            headers={"X-Access-Token": token},
        )
        subtitle_url = response.json()["subtitles"][0]["url"]
        redirect = client.get(subtitle_url, follow_redirects=False)

    assert response.status_code == 200
    assert subtitle_url.startswith("http://testserver/subtitle/zh-Hans.srt?")
    assert redirect.status_code == 302
    assert redirect.headers["location"] == real_url


def test_kodi_play_leaves_named_subtitle_urls_unchanged(monkeypatch) -> None:
    config = Config(subs=(kodi_sub("main"),))
    app = server.create_app(config)
    token, _ = issue_access_token(
        secret=app.state.dashbox.token_secret,
        sub_id="main",
        audience="kodi",
        access_code_hash="",
    )

    async def fake_play(_id: str, _base_url: str, _playback_preferences=None) -> dict:
        return {
            "version": 2,
            "url": "https://cdn.example.test/video.mp4",
            "subtitles": [{"url": "https://cdn.example.test/en.vtt", "name": "en", "format": "vtt"}],
        }

    monkeypatch.setattr(app.state.dashbox.kodi_service("main"), "play", fake_play)

    with no_lifespan_test_client(app) as client:
        response = client.post(
            "/api/v1/subs/main/play",
            json={"id": "video"},
            headers={"X-Access-Token": token},
        )

    assert response.status_code == 200
    assert response.json()["subtitles"] == [{"url": "https://cdn.example.test/en.vtt", "name": "en", "format": "vtt"}]


def test_kodi_play_leaves_non_youtube_extensionless_subtitle_urls_unchanged(monkeypatch) -> None:
    config = Config(subs=(kodi_sub("main"),))
    app = server.create_app(config)
    token, _ = issue_access_token(
        secret=app.state.dashbox.token_secret,
        sub_id="main",
        audience="kodi",
        access_code_hash="",
    )
    real_url = "https://cdn.example.test/subtitle?id=abc&fmt=srt"

    async def fake_play(_id: str, _base_url: str, _playback_preferences=None) -> dict:
        return {
            "version": 2,
            "url": "https://cdn.example.test/video.mp4",
            "subtitles": [{"url": real_url, "name": "en", "format": "srt"}],
        }

    monkeypatch.setattr(app.state.dashbox.kodi_service("main"), "play", fake_play)

    with no_lifespan_test_client(app) as client:
        response = client.post(
            "/api/v1/subs/main/play",
            json={"id": "video"},
            headers={"X-Access-Token": token},
        )

    assert response.status_code == 200
    assert response.json()["subtitles"] == [{"url": real_url, "name": "en", "format": "srt"}]


def test_subtitle_redirect_rejects_non_http_targets() -> None:
    with no_lifespan_test_client(server.create_app(Config(subs=(kodi_sub("main"),)))) as client:
        response = client.get("/subtitle/zh-Hans.srt", params={"url": "file:///etc/passwd"}, follow_redirects=False)

    assert response.status_code == 400


def test_subtitle_redirect_rejects_non_youtube_targets() -> None:
    with no_lifespan_test_client(server.create_app(Config(subs=(kodi_sub("main"),)))) as client:
        response = client.get("/subtitle/zh-Hans.srt", params={"url": "https://evil.example/phish"}, follow_redirects=False)

    assert response.status_code == 400


def test_bilibili_danmaku_ass_route_converts_upstream_xml(monkeypatch) -> None:
    config = Config(subs=(kodi_sub("main"),))
    app = server.create_app(config)
    calls = []

    class FakeHttpClient:
        async def get(self, url, headers=None, timeout=None):
            calls.append({"url": url, "headers": headers, "timeout": timeout})
            return httpx.Response(200, content=b"<i><d p=\"1,1,25,16777215,0,0,0,0\">hello</d></i>")

    def fake_convert_to_ass(xml, width, height, **kwargs):
        calls.append({"xml": xml, "width": width, "height": height, "kwargs": kwargs})
        return "[Script Info]\nTitle: test\n"

    fake_client = FakeHttpClient()
    monkeypatch.setattr(app.state.dashbox.http_client, "client", lambda: fake_client)
    monkeypatch.setitem(sys.modules, "biliass", types.SimpleNamespace(convert_to_ass=fake_convert_to_ass))

    with no_lifespan_test_client(app) as client:
        response = client.get("/danmaku/bilibili/20000001.ass", params={"width": "1280", "height": "720", "font_size": "28"})

    assert response.status_code == 200
    assert response.text.startswith("[Script Info]")
    assert response.headers["content-type"].startswith("text/x-ssa")
    assert calls[0]["url"] == "https://comment.bilibili.com/20000001.xml"
    assert calls[1]["xml"].startswith(b"<i>")
    assert calls[1]["width"] == 1280
    assert calls[1]["height"] == 720
    assert calls[1]["kwargs"]["font_size"] == 28
    assert calls[1]["kwargs"]["input_format"] == "xml"


def test_media_segment_head_uses_upstream_head_without_body() -> None:
    config = Config(subs=(kodi_sub("main"),))
    app = server.create_app(config)
    session = app.state.dashbox.dash_store.create(
        {"title": "video"},
        fragmented_formats("https://old-v", "https://old-a"),
        "https://page",
        scope=PlaybackScope("kodi", "main"),
    )
    media_token = issue_media_token(
        secret=app.state.dashbox.token_secret,
        session_id=session.token,
        sub_id="main",
        audience="kodi",
        access_code_hash="",
    )
    seen_methods = []

    class FakeStreamClient:
        is_closed = False

        def build_request(self, method, url, headers):
            seen_methods.append(method)
            return httpx.Request(method, url, headers=headers)

        async def send(self, request, stream=True):
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": "12345",
                    "Accept-Ranges": "bytes",
                },
                request=request,
            )

        async def aclose(self):
            self.is_closed = True

    with no_lifespan_test_client(app) as client:
        app.state.dashbox.stream_http_client._client = FakeStreamClient()
        response = client.head(
            f"/media/{session.token}/0/0",
            headers={"X-Media-Token": media_token},
        )

    assert response.status_code == 200
    assert seen_methods == ["HEAD"]
    assert response.headers["content-length"] == "12345"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"].startswith("video/mp4")
    assert response.content == b""


def test_kodi_media_manifest_rejects_tvbox_media_token() -> None:
    config = Config(subs=(kodi_sub("main"),))
    app = server.create_app(config)
    session = app.state.dashbox.dash_store.create(
        {"title": "video"},
        fragmented_formats("https://old-v", "https://old-a"),
        "https://page",
        scope=PlaybackScope("kodi", "main"),
    )
    tvbox_token = issue_media_token(
        secret=app.state.dashbox.token_secret,
        session_id=session.token,
        sub_id="main",
        audience="tvbox",
        access_code_hash="",
    )

    with no_lifespan_test_client(app) as client:
        response = client.get(f"/media/{session.token}/manifest.mpd", headers={"X-Media-Token": tvbox_token})

    assert response.status_code == 401


def test_kodi_repository_serves_current_addon_metadata_and_package() -> None:
    config = Config(subs=(kodi_sub("main"),))
    repository_filename = "repository.dashbox-0.1.1-u" + hashlib.sha256(b"http://testserver/repo/").hexdigest()[:8] + ".zip"
    addon_version = kodi_repository.addon_version()
    addon_package = f"plugin.video.dashbox-{addon_version}.zip"

    with no_lifespan_test_client(server.create_app(config)) as client:
        index = client.get("/repo/")
        addons = client.get("/repo/addons.xml")
        addons_md5 = client.get("/repo/addons.xml.md5")
        repository_index = client.get("/repo/repository.dashbox/")
        repository_shortcut = client.get("/repo.zip")
        repository_package = client.get(f"/repo/repository.dashbox/{repository_filename}")
        addon_index = client.get("/repo/plugin.video.dashbox/")
        package = client.get(f"/repo/plugin.video.dashbox/{addon_package}")
        package_head = client.head(f"/repo/plugin.video.dashbox/{addon_package}")

    assert index.status_code == 200
    assert repository_filename in index.text
    assert addon_package in index.text
    assert addons.status_code == 200
    assert b'id="plugin.video.dashbox"' in addons.content
    assert f'version="{addon_version}"'.encode("utf-8") in addons.content
    assert (
        hashlib.sha256(b"http://testserver/repo/").hexdigest()[:8].encode("utf-8")
        in addons.content
    )
    assert addons_md5.text == hashlib.md5(addons.content).hexdigest()
    assert repository_index.status_code == 200
    assert repository_filename in repository_index.text
    assert repository_shortcut.status_code == 200
    assert repository_shortcut.headers["content-disposition"] == f'attachment; filename="{repository_filename}"'
    assert repository_shortcut.headers["cache-control"] == "no-store"
    assert repository_package.status_code == 200
    with zipfile.ZipFile(BytesIO(repository_package.content)) as archive:
        repo_addon_xml = archive.read("repository.dashbox/addon.xml")
    repo_addon = ET.fromstring(repo_addon_xml)
    assert repo_addon.attrib["id"] == "repository.dashbox"
    assert repo_addon.attrib["version"] == "0.1.1"
    assert repo_addon.find(".//info").text == "http://testserver/repo/addons.xml"
    assert repo_addon.find(".//checksum").text == "http://testserver/repo/addons.xml.md5"
    assert repo_addon.find(".//datadir").text == "http://testserver/repo/"
    assert repo_addon.find(".//artdir").text == "http://testserver/repo/"
    assert repo_addon.find(".//hashes").text == "false"
    assert addon_index.status_code == 200
    assert addon_package in addon_index.text
    assert package.status_code == 200
    assert package_head.status_code == 200
    assert package_head.headers["content-length"] == str(len(package.content))
    assert package_head.headers["content-disposition"] == f'attachment; filename="{addon_package}"'
    assert package_head.headers["cache-control"] == "no-store"
    assert package_head.content == b""
    with zipfile.ZipFile(BytesIO(package.content)) as archive:
        names = archive.namelist()
        settings_xml = archive.read("plugin.video.dashbox/resources/settings.xml")
    assert {name.split("/", 1)[0] for name in names if name} == {"plugin.video.dashbox"}
    assert "plugin.video.dashbox/addon.xml" in names
    settings = ET.fromstring(settings_xml)
    assert settings.find(".//setting[@id='gateway']/default").text == "http://testserver"


def test_kodi_repository_zip_uses_public_base_url_when_configured() -> None:
    config = Config(public_base_url="http://dashbox.local:18990", subs=(kodi_sub("main"),))
    repository_filename = "repository.dashbox-0.1.1-u" + hashlib.sha256(b"http://dashbox.local:18990/repo/").hexdigest()[:8] + ".zip"
    addon_package = f"plugin.video.dashbox-{kodi_repository.addon_version()}.zip"

    with no_lifespan_test_client(server.create_app(config)) as client:
        addons = client.get("/repo/addons.xml")
        addons_md5 = client.get("/repo/addons.xml.md5")
        response = client.get(f"/repo/repository.dashbox/{repository_filename}")
        plugin_response = client.get(f"/repo/plugin.video.dashbox/{addon_package}")

    assert addons.status_code == 200
    assert (
        hashlib.sha256(b"http://dashbox.local:18990/repo/").hexdigest()[:8].encode("utf-8")
        in addons.content
    )
    assert addons_md5.text == hashlib.md5(addons.content).hexdigest()
    assert response.status_code == 200
    assert response.headers["content-disposition"] == f'attachment; filename="{repository_filename}"'
    with zipfile.ZipFile(BytesIO(response.content)) as archive:
        repo_addon_xml = archive.read("repository.dashbox/addon.xml")
    repo_addon = ET.fromstring(repo_addon_xml)
    assert repo_addon.find(".//info").text == "http://dashbox.local:18990/repo/addons.xml"
    assert repo_addon.find(".//checksum").text == "http://dashbox.local:18990/repo/addons.xml.md5"
    assert repo_addon.find(".//datadir").text == "http://dashbox.local:18990/repo/"
    assert repo_addon.find(".//artdir").text == "http://dashbox.local:18990/repo/"
    assert repo_addon.find(".//hashes").text == "false"
    assert plugin_response.status_code == 200
    with zipfile.ZipFile(BytesIO(plugin_response.content)) as archive:
        settings_xml = archive.read("plugin.video.dashbox/resources/settings.xml")
    settings = ET.fromstring(settings_xml)
    assert settings.find(".//setting[@id='gateway']/default").text == "http://dashbox.local:18990"
