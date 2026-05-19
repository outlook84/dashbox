
from dashbox.server import app as server
from dashbox.adapters.tvbox_service import TvboxService
from dashbox.core.client_service import DirectorySnapshot
from dashbox.config import Config, Subscription, TvboxSubscriptionConfig
from dashbox.models import MediaNode
from dashbox.core.navigation_resolver import ResolvedCategory
from tests.helpers import no_lifespan_test_client


def test_tvbox_category_route_passes_refresh(monkeypatch) -> None:
    calls = []

    async def fake_category(self: TvboxService, tid: str, base_url: str = "", *, refresh: bool = False):
        calls.append((tid, refresh))
        return {"list": []}

    monkeypatch.setattr(TvboxService, "category", fake_category)
    config = Config(subs=(
        Subscription(
            id="main",
            type="tvbox",
            auth_mode="anonymous",
            tvbox=TvboxSubscriptionConfig(sources=()),
        ),
    ))

    with no_lifespan_test_client(server.create_app(config)) as client:
        auth = client.post("/tvbox/main/auth", json={})
        response = client.get(
            "/tvbox/main/category",
            params={"tid": "playlist", "refresh": "1"},
            headers={"X-Access-Token": auth.json()["access_token"]},
        )

    assert response.status_code == 200
    assert calls == [("playlist", True)]


def test_tvbox_category_refresh_cooldown_reuses_cached_snapshot(monkeypatch) -> None:
    playlist_url = "https://example.test/playlist"
    calls = []

    async def fake_load_directory_snapshot(
        self: TvboxService,
        url: str,
        *,
        force_refresh: bool = False,
        fallback: DirectorySnapshot | None = None,
    ) -> DirectorySnapshot:
        calls.append((url, force_refresh, fallback))
        return DirectorySnapshot(
            ResolvedCategory([MediaNode(f"{url}/item", f"Item {len(calls)}")], "Directory"),
            stored_at=1.0,
        )

    monkeypatch.setattr(TvboxService, "load_directory_snapshot", fake_load_directory_snapshot)
    config = Config(subs=(
        Subscription(
            id="main",
            type="tvbox",
            auth_mode="anonymous",
            tvbox=TvboxSubscriptionConfig(sources=()),
        ),
    ))

    with no_lifespan_test_client(server.create_app(config)) as client:
        auth = client.post("/tvbox/main/auth", json={})
        headers = {"X-Access-Token": auth.json()["access_token"]}
        first = client.get("/tvbox/main/category", params={"tid": playlist_url, "refresh": "1"}, headers=headers)
        second = client.get("/tvbox/main/category", params={"tid": playlist_url, "refresh": "1"}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert [vod["vod_name"] for vod in first.json()["list"]] == ["Item 1"]
    assert [vod["vod_name"] for vod in second.json()["list"]] == ["Item 1"]
    assert calls == [(playlist_url, True, None)]


def test_tvbox_category_auth_runs_before_refresh_work(monkeypatch) -> None:
    async def fail_category(self: TvboxService, tid: str, base_url: str = "", *, refresh: bool = False):
        raise AssertionError("unauthorized refresh should not call TvboxService.category")

    monkeypatch.setattr(TvboxService, "category", fail_category)
    config = Config(subs=(
        Subscription(
            id="main",
            type="tvbox",
            auth_mode="anonymous",
            tvbox=TvboxSubscriptionConfig(sources=()),
        ),
    ))

    with no_lifespan_test_client(server.create_app(config)) as client:
        response = client.get("/tvbox/main/category", params={"tid": "playlist", "refresh": "1"})

    assert response.status_code == 401
