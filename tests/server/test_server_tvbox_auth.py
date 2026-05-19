
import asyncio

import pytest
from fastapi import HTTPException

import dashbox.server.app as server
from dashbox.auth.tokens import issue_access_token, issue_media_token
from dashbox.config import Config, Source, Subscription, TvboxSubscriptionConfig, UrlItem
from dashbox.media.scope import PlaybackScope
from tests.helpers import fragmented_formats, no_lifespan_test_client


BCRYPT_HASH = "$2b$12$012345678901234567890u0123456789012345678901234567890"


def tvbox_sub(sub_id: str, *, auth_mode: str = "anonymous", access_code_hash: str = "") -> Subscription:
    return Subscription(
        id=sub_id,
        type="tvbox",
        auth_mode=auth_mode,  # type: ignore[arg-type]
        access_code_hash=access_code_hash,
        tvbox=TvboxSubscriptionConfig(
            site_key=f"{sub_id}-site",
            site_name=f"{sub_id.title()} Site",
            sources=(Source("main", "Main", (UrlItem("https://example.test/a", id="a"),)),),
        ),
    )


def test_tvbox_api_requires_token_for_anonymous_subscription() -> None:
    config = Config(subs=(tvbox_sub("main"),))
    app = server.create_app(config)

    with no_lifespan_test_client(app) as client:
        response = client.get("/tvbox/main/home")
        auth = client.post("/tvbox/main/auth", json={})
        authorized = client.get("/tvbox/main/home", headers={"X-Access-Token": auth.json()["access_token"]})

    assert response.status_code == 401
    assert auth.status_code == 200
    assert auth.json()["ok"] is True
    assert auth.json()["access_token"]
    assert auth.json()["expires_at"] > 0
    assert authorized.status_code == 200
    assert "class" in authorized.json()


def test_app_state_uses_configured_proxy_media_idle_ttl() -> None:
    app = server.create_app(Config(proxy_media_idle_ttl_seconds=120, subs=(tvbox_sub("main"),)))

    assert app.state.dashbox.dash_store.idle_ttl_seconds == 120


def test_app_state_reload_rebuilds_config_services_and_preserves_runtime_state() -> None:
    app = server.create_app(Config(proxy_media_idle_ttl_seconds=120, subs=(tvbox_sub("main"),)))
    state = app.state.dashbox
    token_secret = state.token_secret
    dash_store = state.dash_store
    inline_manifest_store = state.inline_manifest_store
    playable_cache = state.playable_cache
    session = dash_store.create(
        {"title": "video"},
        fragmented_formats("https://old-v", "https://old-a"),
        "https://page",
        scope=PlaybackScope("tvbox", "main"),
    )

    asyncio.run(state.reload_config(Config(
        public_base_url="http://dashbox.local:18990",
        proxy_dash_media_url=True,
        ytdlp_concurrency=2,
        log_level="debug",
        user_agent="Dashbox Test UA",
        proxy_media_idle_ttl_seconds=240,
        subs=(tvbox_sub("alt"),),
    )))

    assert state.token_secret is token_secret
    assert state.dash_store is dash_store
    assert state.inline_manifest_store is inline_manifest_store
    assert state.playable_cache is playable_cache
    assert state.dash_store.get(session.token, touch=False) is session
    assert state.dash_store.idle_ttl_seconds == 240
    assert state.inline_manifest_store.idle_ttl_seconds == 240
    assert state.config.public_base_url == "http://dashbox.local:18990"
    assert state.service.config.user_agent == "Dashbox Test UA"
    assert state.tvbox_service("alt").playback_scope().proxy_dash_media_url is True
    with pytest.raises(HTTPException) as exc_info:
        state.tvbox_service("main")
    assert exc_info.value.status_code == 404


def test_app_state_reload_does_not_rebuild_shared_http_client() -> None:
    app = server.create_app(Config(upstream_timeout=12, subs=(tvbox_sub("main"),)))
    state = app.state.dashbox
    original_config = state.http_client.config

    class FakeClient:
        is_closed = False

        async def aclose(self) -> None:
            self.is_closed = True

    async def exercise_reload() -> tuple[object, bool]:
        state.http_client._client = FakeClient()
        original_client = state.http_client.client()
        await state.reload_config(Config(upstream_timeout=24, subs=(tvbox_sub("alt"),)))
        try:
            return original_client, state.http_client.client() is original_client
        finally:
            await state.http_client.aclose()

    original_client, kept_client = asyncio.run(exercise_reload())

    assert state.http_client._client is None
    assert kept_client is True
    assert state.http_client.config is original_config
    assert state.http_client.config.upstream_timeout == 12
    assert state.config.upstream_timeout == 24
    assert original_client.is_closed


def test_tvbox_home_rejects_access_code_subscription_without_token() -> None:
    config = Config(subs=(tvbox_sub("main", auth_mode="access_code", access_code_hash=BCRYPT_HASH),))

    with no_lifespan_test_client(server.create_app(config)) as client:
        missing = client.get("/tvbox/main/home")
        wrong = client.get("/tvbox/main/home", headers={"X-Access-Token": "bad"})

    assert missing.status_code == 401
    assert missing.json() == {"error": "unauthorized"}
    assert wrong.status_code == 401
    assert wrong.json() == {"error": "unauthorized"}
def test_tvbox_api_accepts_valid_access_token() -> None:
    config = Config(subs=(tvbox_sub("main", auth_mode="access_code", access_code_hash=BCRYPT_HASH),))
    app = server.create_app(config)
    token, _expires_at = issue_access_token(
        secret=app.state.dashbox.token_secret,
        sub_id="main",
        audience="tvbox",
        access_code_hash=BCRYPT_HASH,
    )

    with no_lifespan_test_client(app) as client:
        response = client.get("/tvbox/main/home", headers={"X-Access-Token": token})

    assert response.status_code == 200
    assert "class" in response.json()
def test_tvbox_auth_route_issues_token_after_valid_code(monkeypatch) -> None:
    config = Config(subs=(tvbox_sub("main", auth_mode="access_code", access_code_hash=BCRYPT_HASH),))
    app = server.create_app(config)
    monkeypatch.setattr(server, "verify_access_code", lambda code, access_code_hash: code == "1234" and access_code_hash == BCRYPT_HASH)

    with no_lifespan_test_client(app) as client:
        wrong = client.post("/tvbox/main/auth", json={"code": "0000"})
        ok = client.post("/tvbox/main/auth", json={"code": "1234"})
        authorized = client.get("/tvbox/main/home", headers={"X-Access-Token": ok.json()["access_token"]})

    assert wrong.status_code == 401
    assert wrong.json() == {"ok": False}
    assert ok.status_code == 200
    assert ok.json()["ok"] is True
    assert ok.json()["expires_at"] > 0
    assert authorized.status_code == 200


def test_media_manifest_rejects_missing_wrong_or_protocol_token_for_scoped_session() -> None:
    config = Config(subs=(tvbox_sub("main"), tvbox_sub("alt")))
    app = server.create_app(config)
    session = app.state.dashbox.dash_store.create(
        {"title": "video"},
        fragmented_formats("https://old-v", "https://old-a"),
        "https://page",
        scope=PlaybackScope("tvbox", "main"),
    )
    access_token, _ = issue_access_token(
        secret=app.state.dashbox.token_secret,
        sub_id="main",
        audience="tvbox",
        access_code_hash="",
    )
    alt_token = issue_media_token(
        secret=app.state.dashbox.token_secret,
        session_id=session.token,
        sub_id="alt",
        audience="tvbox",
        access_code_hash="",
    )
    kodi_token = issue_media_token(
        secret=app.state.dashbox.token_secret,
        session_id=session.token,
        sub_id="main",
        audience="kodi",
        access_code_hash="",
    )
    wrong_session_token = issue_media_token(
        secret=app.state.dashbox.token_secret,
        session_id="other-session",
        sub_id="main",
        audience="tvbox",
        access_code_hash="",
    )
    main_token = issue_media_token(
        secret=app.state.dashbox.token_secret,
        session_id=session.token,
        sub_id="main",
        audience="tvbox",
        access_code_hash="",
    )

    with no_lifespan_test_client(app) as client:
        missing = client.get(f"/media/{session.token}/manifest.mpd")
        protocol_token = client.get(f"/media/{session.token}/manifest.mpd", headers={"X-Access-Token": access_token})
        wrong_sub = client.get(f"/media/{session.token}/manifest.mpd", headers={"X-Media-Token": alt_token})
        wrong_audience = client.get(f"/media/{session.token}/manifest.mpd", headers={"X-Media-Token": kodi_token})
        wrong_session = client.get(f"/media/{session.token}/manifest.mpd", headers={"X-Media-Token": wrong_session_token})
        ok = client.get(f"/media/{session.token}/manifest.mpd", headers={"X-Media-Token": main_token})

    assert missing.status_code == 401
    assert protocol_token.status_code == 401
    assert wrong_sub.status_code == 401
    assert wrong_audience.status_code == 401
    assert wrong_session.status_code == 401
    assert ok.status_code == 200
    assert "<MPD" in ok.text
def test_tvbox_play_attaches_media_token_for_media_proxy_url(monkeypatch) -> None:
    config = Config(subs=(tvbox_sub("main"),))
    app = server.create_app(config)
    session = app.state.dashbox.dash_store.create(
        {"title": "video"},
        fragmented_formats("https://old-v", "https://old-a"),
        "https://page",
        scope=PlaybackScope("tvbox", "main"),
    )
    auth_token, _ = issue_access_token(
        secret=app.state.dashbox.token_secret,
        sub_id="main",
        audience="tvbox",
        access_code_hash="",
    )

    async def fake_play(_id: str, _base_url: str) -> dict:
        return {
            "parse": 0,
            "url": f"http://testserver/media/{session.token}/manifest.mpd",
            "header": {"User-Agent": "upstream", "X-Media-Token": "old"},
        }

    monkeypatch.setattr(app.state.dashbox.tvbox_service("main"), "play", fake_play)

    with no_lifespan_test_client(app) as client:
        response = client.get("/tvbox/main/play", params={"id": "video"}, headers={"X-Access-Token": auth_token})

    assert response.status_code == 200
    headers = response.json()["header"]
    assert headers["User-Agent"] == "upstream"
    assert headers["X-Media-Token"]
    assert "X-Access-Token" not in headers

    with no_lifespan_test_client(app) as client:
        dash_response = client.get(f"/media/{session.token}/manifest.mpd", headers={"X-Media-Token": headers["X-Media-Token"]})

    assert dash_response.status_code == 200
def test_tvbox_play_does_not_attach_access_token_for_progressive_url(monkeypatch) -> None:
    config = Config(subs=(tvbox_sub("main"),))
    app = server.create_app(config)
    auth_token, _ = issue_access_token(
        secret=app.state.dashbox.token_secret,
        sub_id="main",
        audience="tvbox",
        access_code_hash="",
    )

    async def fake_play(_id: str, _base_url: str) -> dict:
        return {"parse": 0, "url": "https://cdn.example.test/video.mp4", "header": {"User-Agent": "upstream"}}

    monkeypatch.setattr(app.state.dashbox.tvbox_service("main"), "play", fake_play)

    with no_lifespan_test_client(app) as client:
        response = client.get("/tvbox/main/play", params={"id": "video"}, headers={"X-Access-Token": auth_token})

    assert response.status_code == 200
    assert response.json()["header"] == {"User-Agent": "upstream"}
