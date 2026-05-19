from __future__ import annotations

import json


import dashbox.admin as admin
import dashbox.server.app as server
import dashbox.server.static as server_static
from dashbox.server.static import safe_admin_asset_path
from dashbox.config import AuthMode, Config, Subscription, SubscriptionType, TvboxSubscriptionConfig, config_to_json_data
from tests.helpers import no_lifespan_test_client


BCRYPT_HASH = "$2b$12$012345678901234567890u0123456789012345678901234567890"
BCRYPT_HASH_2 = "$2b$12$112345678901234567890u0123456789012345678901234567890"


def write_admin_access_code_hash(config_path, access_code_hash: str = BCRYPT_HASH) -> None:
    (config_path.parent / "admin_access_code_hash").write_text(access_code_hash + "\n", encoding="utf-8")


def test_admin_session_reports_setup_required_and_setup_creates_session(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"subs":[]}\n', encoding="utf-8")
    monkeypatch.setattr(admin, "hash_admin_access_code", lambda code: BCRYPT_HASH)
    app = server.create_app(Config(), config_path=config_path)
    setup_code = (tmp_path / "admin_setup_code").read_text(encoding="utf-8").strip()

    with no_lifespan_test_client(app) as client:
        before = client.get("/admin/api/session")
        setup = client.post(
            "/admin/api/setup",
            json={"setup_code": setup_code, "access_code": "admin-code-1"},
        )
        after = client.get("/admin/api/session")
        status = client.get("/admin/api/status")

    assert before.json() == {"authenticated": False, "setup_required": True}
    assert setup.status_code == 200
    assert setup.json() == {"ok": True}
    assert "httponly" in setup.headers["set-cookie"].lower()
    assert "samesite=strict" in setup.headers["set-cookie"].lower()
    assert "path=/admin" in setup.headers["set-cookie"].lower()
    assert (tmp_path / "admin_access_code_hash").read_text(encoding="utf-8").strip() == BCRYPT_HASH
    assert not (tmp_path / "admin_setup_code").exists()
    assert after.json() == {"authenticated": True, "setup_required": False}
    assert status.status_code == 200


def test_admin_setup_code_uses_data_dir_before_config_dir(tmp_path) -> None:
    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    config_dir.mkdir()
    config_path = config_dir / "config.json"
    config_path.write_text('{"subs":[]}\n', encoding="utf-8")

    app = server.create_app(Config(), config_path=config_path, data_dir=data_dir)

    assert (data_dir / "admin_setup_code").exists()
    assert not (config_dir / "admin_setup_code").exists()
    assert app.state.dashbox.config_path == config_path
    assert app.state.dashbox.data_dir == data_dir


def test_admin_setup_code_uses_config_dir_without_data_dir(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"subs":[]}\n', encoding="utf-8")

    server.create_app(Config(), config_path=config_path)

    assert (tmp_path / "admin_setup_code").exists()


def test_admin_protected_config_requires_session(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"subs":[]}\n', encoding="utf-8")
    app = server.create_app(Config(), config_path=config_path)

    with no_lifespan_test_client(app) as client:
        response = client.get("/admin/api/config")

    assert response.status_code == 401


def test_admin_config_validate_and_save_reload_config(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"subs":[]}\n', encoding="utf-8")
    write_admin_access_code_hash(config_path)
    monkeypatch.setattr(admin, "verify_admin_access_code", lambda code, access_hash: code == "admin-code-1")
    app = server.create_app(Config(), config_path=config_path)

    with no_lifespan_test_client(app) as client:
        login = client.post("/admin/api/login", json={"access_code": "admin-code-1"})
        invalid = client.post("/admin/api/config/validate", json={"config": {"subs": "bad"}})
        save = client.put(
            "/admin/api/config",
            json={
                "config": {
                    "subs": [],
                },
            },
        )
        config_response = client.get("/admin/api/config")

    assert login.status_code == 200
    assert invalid.status_code == 400
    assert invalid.json()["ok"] is False
    assert save.status_code == 200
    assert save.json()["ok"] is True
    assert save.json()["env_overrides"] == {
        "image_proxy_mode": "known",
        "upstream_timeout": 30,
        "public_base_url": "",
    }
    assert save.json()["effective_values"]["user_agent"]
    assert "public_base_url" not in json.loads(config_path.read_text(encoding="utf-8"))
    assert (tmp_path / "config.json.bak").exists()
    assert config_response.json()["env_overrides"] == {
        "image_proxy_mode": "known",
        "upstream_timeout": 30,
        "public_base_url": "",
    }
    assert config_response.json()["effective_values"]["user_agent"]
    assert config_response.headers["cache-control"] == "no-store"


def test_admin_config_normalize_generates_tvbox_source_tree_ids(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"subs":[]}\n', encoding="utf-8")
    write_admin_access_code_hash(config_path)
    monkeypatch.setattr(admin, "verify_admin_access_code", lambda code, access_hash: True)
    app = server.create_app(Config(), config_path=config_path)
    draft = {
        "subs": [
            {
                "id": "main",
                "type": "tvbox",
                "auth_mode": "anonymous",
                "tvbox": {
                    "site_key": "dashbox",
                    "sources": [
                        {
                            "name": "YouTube",
                            "items": [
                                {"title": "Pinned Video", "url": "https://example.test/a"},
                                {"id": "tmp:local", "name": "Folder", "items": [{"url": "https://example.test/b"}]},
                            ],
                        }
                    ],
                },
            }
        ],
    }

    with no_lifespan_test_client(app) as client:
        client.post("/admin/api/login", json={"access_code": "admin-code-1"})
        validated = client.post("/admin/api/config/validate", json={"config": draft})
        normalized = client.post("/admin/api/config/normalize", json={"config": draft})
        saved = client.put("/admin/api/config", json={"config": draft})

    assert validated.status_code == 200
    assert validated.json() == {"ok": True}
    assert normalized.status_code == 200
    data = normalized.json()
    source = data["config"]["subs"][0]["tvbox"]["sources"][0]
    assert source["id"] == "youtube"
    assert source["items"][0]["id"] == "pinned_video"
    assert source["items"][1]["id"] == "folder"
    assert source["items"][1]["items"][0]["id"] == "example_test_b"
    assert [change["field"] for change in data["changes"]] == ["id", "id", "id", "id"]
    assert saved.status_code == 200
    written = json.loads(config_path.read_text(encoding="utf-8"))
    assert written["subs"][0]["tvbox"]["sources"][0]["items"][0]["id"] == "pinned_video"


def test_admin_config_validate_rejects_unsafe_source_url_scheme(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"subs":[]}\n', encoding="utf-8")
    write_admin_access_code_hash(config_path)
    monkeypatch.setattr(admin, "verify_admin_access_code", lambda code, access_hash: True)
    app = server.create_app(Config(), config_path=config_path)
    draft = {
        "subs": [
            {
                "id": "main",
                "type": "tvbox",
                "auth_mode": "anonymous",
                "tvbox": {
                    "site_key": "dashbox",
                    "sources": [
                        {
                            "id": "main",
                            "name": "Main",
                            "items": [{"id": "bad", "url": "javascript:alert(1)"}],
                        }
                    ],
                },
            }
        ],
    }

    with no_lifespan_test_client(app) as client:
        client.post("/admin/api/login", json={"access_code": "admin-code-1"})
        validated = client.post("/admin/api/config/validate", json={"config": draft})
        saved = client.put("/admin/api/config", json={"config": draft})

    assert validated.status_code == 400
    assert validated.json()["ok"] is False
    assert "url scheme must be http or https" in validated.json()["error"]
    assert saved.status_code == 400
    assert saved.json()["ok"] is False


def test_admin_config_redacts_subscription_access_code_hash(tmp_path, monkeypatch) -> None:
    config = Config(subs=(
        Subscription(
            id="main",
            type=SubscriptionType.TVBOX,
            auth_mode=AuthMode.ACCESS_CODE,
            access_code_hash=BCRYPT_HASH,
            tvbox=TvboxSubscriptionConfig(sources=()),
        ),
    ))
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config_to_json_data(config)), encoding="utf-8")
    write_admin_access_code_hash(config_path)
    monkeypatch.setattr(admin, "verify_admin_access_code", lambda code, access_hash: True)
    app = server.create_app(config, config_path=config_path)

    with no_lifespan_test_client(app) as client:
        client.post("/admin/api/login", json={"access_code": "admin-code-1"})
        response = client.get("/admin/api/config")

    sub = response.json()["config"]["subs"][0]
    assert response.headers["cache-control"] == "no-store"
    assert "access_code_hash" not in sub
    assert sub["access_code_hash_set"] is True
    assert sub["access_code_hash_action"] == "keep"


def test_admin_config_normalize_redacts_subscription_access_code_hash(tmp_path, monkeypatch) -> None:
    config = Config(subs=(
        Subscription(
            id="main",
            type=SubscriptionType.TVBOX,
            auth_mode=AuthMode.ACCESS_CODE,
            access_code_hash=BCRYPT_HASH,
            tvbox=TvboxSubscriptionConfig(sources=()),
        ),
    ))
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config_to_json_data(config)), encoding="utf-8")
    write_admin_access_code_hash(config_path)
    monkeypatch.setattr(admin, "verify_admin_access_code", lambda code, access_hash: True)
    hash_calls = []

    def hash_subscription_access_code(code: str) -> str:
        hash_calls.append(code)
        return BCRYPT_HASH_2

    monkeypatch.setattr(admin, "hash_subscription_access_code", hash_subscription_access_code)
    app = server.create_app(config, config_path=config_path)

    with no_lifespan_test_client(app) as client:
        client.post("/admin/api/login", json={"access_code": "admin-code-1"})
        draft = client.get("/admin/api/config").json()["config"]
        keep_response = client.post("/admin/api/config/normalize", json={"config": draft})
        draft["subs"][0]["access_code"] = "123456"
        draft["subs"][0]["access_code_hash_action"] = "replace"
        replace_response = client.post("/admin/api/config/normalize", json={"config": draft})
        normalize_hash_calls = list(hash_calls)
        save_normalized = client.put("/admin/api/config", json={"config": replace_response.json()["config"]})

    assert keep_response.status_code == 200
    assert replace_response.status_code == 200
    keep_sub = keep_response.json()["config"]["subs"][0]
    assert "access_code_hash" not in keep_sub
    assert "access_code" not in keep_sub
    assert keep_sub["access_code_hash_set"] is True
    assert keep_sub["access_code_hash_action"] == "keep"
    assert normalize_hash_calls == []

    replace_sub = replace_response.json()["config"]["subs"][0]
    assert "access_code_hash" not in replace_sub
    assert replace_sub["access_code"] == "123456"
    assert replace_sub["access_code_hash_set"] is True
    assert replace_sub["access_code_hash_action"] == "replace"
    assert hash_calls == ["123456"]
    assert save_normalized.status_code == 200
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["subs"][0]["access_code_hash"] == BCRYPT_HASH_2


def test_admin_save_keeps_and_replaces_subscription_access_code_hash(tmp_path, monkeypatch) -> None:
    config = Config(subs=(
        Subscription(
            id="main",
            type=SubscriptionType.TVBOX,
            auth_mode=AuthMode.ACCESS_CODE,
            access_code_hash=BCRYPT_HASH,
            tvbox=TvboxSubscriptionConfig(sources=()),
        ),
    ))
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config_to_json_data(config)), encoding="utf-8")
    write_admin_access_code_hash(config_path)
    monkeypatch.setattr(admin, "verify_admin_access_code", lambda code, access_hash: True)
    monkeypatch.setattr(admin, "hash_subscription_access_code", lambda code: BCRYPT_HASH_2)
    app = server.create_app(config, config_path=config_path)

    with no_lifespan_test_client(app) as client:
        client.post("/admin/api/login", json={"access_code": "admin-code-1"})
        editable = client.get("/admin/api/config").json()["config"]
        keep = client.put("/admin/api/config", json={"config": editable})
        editable["subs"][0]["access_code"] = "123456"
        editable["subs"][0]["access_code_hash_action"] = "replace"
        replace = client.put("/admin/api/config", json={"config": editable})

    assert keep.status_code == 200
    assert replace.status_code == 200
    saved = json.loads(config_path.read_text(encoding="utf-8"))
    sub = saved["subs"][0]
    assert sub["access_code_hash"] == BCRYPT_HASH_2
    assert "access_code" not in sub
    assert "access_code_hash_action" not in sub
    assert "access_code_hash" not in replace.json()["config"]["subs"][0]


def test_admin_update_access_code_hashes_on_server(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"subs":[]}\n', encoding="utf-8")
    write_admin_access_code_hash(config_path)
    monkeypatch.setattr(admin, "verify_admin_access_code", lambda code, access_hash: code == "old-admin-code" and access_hash == BCRYPT_HASH)
    monkeypatch.setattr(admin, "hash_admin_access_code", lambda code: BCRYPT_HASH_2)
    app = server.create_app(Config(), config_path=config_path)

    with no_lifespan_test_client(app) as client:
        client.post("/admin/api/login", json={"access_code": "old-admin-code"})
        wrong = client.post("/admin/api/access-code", json={"current_access_code": "wrong-code", "new_access_code": "new-admin-code"})
        updated = client.post("/admin/api/access-code", json={"current_access_code": "old-admin-code", "new_access_code": "new-admin-code"})

    assert wrong.status_code == 401
    assert updated.status_code == 200
    assert updated.json() == {"ok": True}
    assert (tmp_path / "admin_access_code_hash").read_text(encoding="utf-8").strip() == BCRYPT_HASH_2


def test_admin_update_access_code_invalidates_other_sessions(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"subs":[]}\n', encoding="utf-8")
    write_admin_access_code_hash(config_path)
    monkeypatch.setattr(admin, "verify_admin_access_code", lambda code, access_hash: code == "old-admin-code")
    monkeypatch.setattr(admin, "hash_admin_access_code", lambda code: BCRYPT_HASH_2)
    app = server.create_app(Config(), config_path=config_path)
    kept_session = app.state.dashbox.admin.sessions.create()
    revoked_session = app.state.dashbox.admin.sessions.create()

    with no_lifespan_test_client(app) as client:
        client.cookies.set(admin.ADMIN_SESSION_COOKIE, kept_session.session_id)
        updated = client.post("/admin/api/access-code", json={"current_access_code": "old-admin-code", "new_access_code": "new-admin-code"})
        kept_status = client.get("/admin/api/status")
        client.cookies.set(admin.ADMIN_SESSION_COOKIE, revoked_session.session_id)
        revoked_status = client.get("/admin/api/status")

    assert updated.status_code == 200
    assert kept_status.status_code == 200
    assert revoked_status.status_code == 401


def test_admin_hash_subscription_access_code_requires_session_and_redacts_input(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"subs":[]}\n', encoding="utf-8")
    write_admin_access_code_hash(config_path)
    monkeypatch.setattr(admin, "hash_subscription_access_code", lambda code: BCRYPT_HASH_2)
    app = server.create_app(Config(), config_path=config_path)
    session = app.state.dashbox.admin.sessions.create()

    with no_lifespan_test_client(app) as client:
        unauthorized = client.post("/admin/api/subscription-access-code/hash", json={"access_code": "123456"})
        client.cookies.set(admin.ADMIN_SESSION_COOKIE, session.session_id)
        hashed = client.post("/admin/api/subscription-access-code/hash", json={"access_code": "123456"})

    assert unauthorized.status_code == 401
    assert hashed.status_code == 200
    assert hashed.json() == {"ok": True, "access_code_hash": BCRYPT_HASH_2}
    assert "access_code" not in hashed.json()


def test_admin_schema_includes_structured_editor_contract(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"subs":[]}\n', encoding="utf-8")
    write_admin_access_code_hash(config_path)
    app = server.create_app(Config(), config_path=config_path)
    session = app.state.dashbox.admin.sessions.create()

    with no_lifespan_test_client(app) as client:
        client.cookies.set(admin.ADMIN_SESSION_COOKIE, session.session_id)
        response = client.get("/admin/api/schema")

    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == 1
    assert data["subscription_type"] == ["tvbox", "kodi"]
    assert data["auth_mode"] == ["anonymous", "access_code"]
    assert data["item_type"] == ["url", "folder"]
    assert data["limits"]["subscription_access_code_max_length"] == 12
    assert data["defaults"]["default_search_provider"] == "ytdlp"
    assert data["defaults"]["ytdlp_search_prefix"] == {"mode": "youtube"}
    assert data["defaults"]["playlist_limit"] == 100


def test_admin_cookies_routes_are_under_admin_api_and_require_session(tmp_path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"subs":[]}\n', encoding="utf-8")
    write_admin_access_code_hash(config_path)
    app = server.create_app(Config(), config_path=config_path)
    session = app.state.dashbox.admin.sessions.create()

    with no_lifespan_test_client(app) as client:
        unauthorized = client.get("/admin/api/cookies")
        old_path = client.get("/admin/cookies")
        client.cookies.set(admin.ADMIN_SESSION_COOKIE, session.session_id)
        status = client.get("/admin/api/cookies")
        reload_cross_origin = client.post(
            "/admin/api/cookies/reload?load=false",
            headers={"Origin": "http://evil.example"},
        )

    assert unauthorized.status_code == 401
    assert old_path.status_code == 404 or "text/html" in old_path.headers.get("content-type", "")
    assert status.status_code == 200
    assert status.headers["cache-control"] == "no-store"
    assert status.json()["enabled"] is False
    assert reload_cross_origin.status_code == 403


def test_admin_save_wraps_write_failures(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"subs":[]}\n', encoding="utf-8")
    write_admin_access_code_hash(config_path)
    monkeypatch.setattr(admin, "verify_admin_access_code", lambda code, access_hash: True)

    def fail_write(*args, **kwargs) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(admin, "write_config_file", fail_write)
    app = server.create_app(Config(), config_path=config_path)

    with no_lifespan_test_client(app) as client:
        client.post("/admin/api/login", json={"access_code": "admin-code-1"})
        response = client.put("/admin/api/config", json={"config": {"subs": []}})

    assert response.status_code == 500
    assert response.json() == {"ok": False, "error": "disk full"}


def test_admin_save_rejects_cross_origin_write(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"subs":[]}\n', encoding="utf-8")
    write_admin_access_code_hash(config_path)
    monkeypatch.setattr(admin, "verify_admin_access_code", lambda code, access_hash: True)
    app = server.create_app(Config(), config_path=config_path)

    with no_lifespan_test_client(app) as client:
        client.post("/admin/api/login", json={"access_code": "admin-code-1"})
        response = client.put(
            "/admin/api/config",
            headers={"Origin": "http://evil.example"},
            json={"config": {"subs": []}},
        )

    assert response.status_code == 403


def test_admin_save_allows_forwarded_https_origin(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text('{"subs":[]}\n', encoding="utf-8")
    write_admin_access_code_hash(config_path)
    monkeypatch.setattr(admin, "verify_admin_access_code", lambda code, access_hash: True)
    app = server.create_app(Config(), config_path=config_path)

    with no_lifespan_test_client(app) as client:
        client.post("/admin/api/login", json={"access_code": "admin-code-1"})
        response = client.put(
            "/admin/api/config",
            headers={
                "Origin": "https://testserver",
                "X-Forwarded-Proto": "https",
            },
            json={"config": {"subs": []}},
        )

    assert response.status_code == 200


def test_admin_save_requires_config_path() -> None:
    app = server.create_app(Config())
    session = app.state.dashbox.admin.sessions.create()

    with no_lifespan_test_client(app) as client:
        client.cookies.set(admin.ADMIN_SESSION_COOKIE, session.session_id)
        response = client.put("/admin/api/config", json={"config": {"subs": []}})

    assert response.status_code == 409


def test_admin_ui_serves_index_and_assets(tmp_path, monkeypatch) -> None:
    asset_dir = tmp_path / "admin"
    (asset_dir / "assets").mkdir(parents=True)
    index_path = asset_dir / "index.html"
    favicon_path = asset_dir / "assets" / "favicon.svg"
    script_path = asset_dir / "assets" / "app.js"
    index_path.write_text('<div id="app"></div><script src="/admin/assets/app.js"></script>', encoding="utf-8")
    favicon_path.write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>', encoding="utf-8")
    script_path.write_text("console.log('admin')\n", encoding="utf-8")
    monkeypatch.setattr(server_static, "ADMIN_ASSET_DIR", asset_dir)
    monkeypatch.setattr(server_static, "ADMIN_INDEX_PATH", index_path)
    app = server.create_app(Config())

    with no_lifespan_test_client(app) as client:
        root = client.get("/admin")
        fallback = client.get("/admin/config")
        asset = client.get("/admin/assets/app.js")
        favicon = client.get("/admin/assets/favicon.svg")
        api = client.get("/admin/api/session")

    assert root.status_code == 200
    assert root.headers["cache-control"] == "no-store"
    assert '<div id="app"></div>' in root.text
    assert fallback.status_code == 200
    assert asset.status_code == 200
    assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/svg+xml")
    assert "<svg" in favicon.text
    assert safe_admin_asset_path("../server.py") is None
    assert api.status_code == 200
    assert api.json() == {"authenticated": False, "setup_required": True}
