import asyncio
import json
import logging
from pathlib import Path

import httpx
import pytest

import dashbox.server.app as app_server
import dashbox.server.cli as server_cli
import dashbox.server.utils as server_utils
from fastapi import HTTPException
from fastapi.responses import Response
from dashbox.config import Config
from dashbox.core import image_policy, image_proxy
from tests.helpers import no_lifespan_test_client


async def allow_image_proxy_host(host: str) -> bool:
    return False


async def fake_image_fetch_client(self):
    return object()


def test_dashbox_logger_uses_uvicorn_default_handler() -> None:
    log_config = server_cli.uvicorn_log_config()

    assert log_config["loggers"]["dashbox"] == {
        "handlers": ["default"],
        "level": "INFO",
        "propagate": False,
    }
    assert log_config["handlers"]["default"]["formatter"] == "default"
    assert "uvicorn.access" in log_config["loggers"]
    assert log_config["loggers"]["uvicorn"]["level"] == "INFO"
    assert log_config["loggers"]["uvicorn.error"]["level"] == "INFO"
    assert log_config["loggers"]["uvicorn.access"]["level"] == "INFO"


def test_dashbox_logger_level_is_configurable() -> None:
    log_config = server_cli.uvicorn_log_config("debug")

    assert log_config["loggers"]["dashbox"]["level"] == "DEBUG"
    assert log_config["loggers"]["uvicorn"]["level"] == "DEBUG"
    assert log_config["loggers"]["uvicorn.error"]["level"] == "DEBUG"
    assert log_config["loggers"]["uvicorn.access"]["level"] == "DEBUG"


def test_runtime_log_level_updates_app_and_uvicorn_loggers() -> None:
    logger_names = ("dashbox", "uvicorn", "uvicorn.error", "uvicorn.access")
    original_levels = {name: logging.getLogger(name).level for name in logger_names}

    try:
        server_cli.apply_runtime_log_level("debug")

        for name in logger_names:
            assert logging.getLogger(name).level == logging.DEBUG
    finally:
        for name, level in original_levels.items():
            logging.getLogger(name).setLevel(level)


def test_server_startup_settings_default_to_env_fallbacks(monkeypatch) -> None:
    monkeypatch.delenv(server_cli.DASHBOX_CONFIG_ENV, raising=False)
    monkeypatch.delenv(server_cli.DASHBOX_DATA_DIR_ENV, raising=False)
    monkeypatch.delenv(server_cli.DASHBOX_HOST_ENV, raising=False)
    monkeypatch.delenv(server_cli.DASHBOX_PORT_ENV, raising=False)
    monkeypatch.delenv(server_cli.DASHBOX_RELOAD_ENV, raising=False)

    assert server_cli.config_path_from_env() == ""
    assert server_cli.data_dir_from_env() == ""
    assert server_cli.config_path_from_startup_options() == ""
    assert server_cli.host_from_env() == "0.0.0.0"
    assert server_cli.port_from_env() == 18990
    assert server_cli.reload_from_env() is False


def test_server_startup_settings_read_env(monkeypatch) -> None:
    monkeypatch.setenv(server_cli.DASHBOX_CONFIG_ENV, "config.json")
    monkeypatch.setenv(server_cli.DASHBOX_DATA_DIR_ENV, "data")
    monkeypatch.setenv(server_cli.DASHBOX_HOST_ENV, "127.0.0.1")
    monkeypatch.setenv(server_cli.DASHBOX_PORT_ENV, "19000")
    monkeypatch.setenv(server_cli.DASHBOX_RELOAD_ENV, "true")

    assert server_cli.config_path_from_env() == "config.json"
    assert server_cli.data_dir_from_env() == "data"
    assert server_cli.config_path_from_startup_options() == "config.json"
    assert server_cli.host_from_env() == "127.0.0.1"
    assert server_cli.port_from_env() == 19000
    assert server_cli.reload_from_env() is True


def test_server_startup_settings_cli_values_override_env(monkeypatch) -> None:
    monkeypatch.setenv(server_cli.DASHBOX_CONFIG_ENV, "env.json")
    monkeypatch.setenv(server_cli.DASHBOX_DATA_DIR_ENV, "env-data")
    monkeypatch.setenv(server_cli.DASHBOX_HOST_ENV, "0.0.0.0")
    monkeypatch.setenv(server_cli.DASHBOX_PORT_ENV, "18990")
    monkeypatch.setenv(server_cli.DASHBOX_RELOAD_ENV, "false")

    assert server_cli.config_path_from_env("cli.json") == "cli.json"
    assert server_cli.data_dir_from_env("cli-data") == "cli-data"
    assert server_cli.config_path_from_startup_options(None, "cli-data") == "env.json"
    assert server_cli.config_path_from_startup_options("cli.json", "cli-data") == "cli.json"
    assert server_cli.host_from_env("127.0.0.1") == "127.0.0.1"
    assert server_cli.port_from_env(19000) == 19000
    assert server_cli.reload_from_env(True) is True


def test_server_accepts_public_base_url_cli_flag(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["dashbox", "--public-base-url", "http://dashbox.local:18990/"])

    args = server_cli.parse_args()

    assert args.public_base_url == "http://dashbox.local:18990/"


def test_server_accepts_data_dir_cli_flag(monkeypatch) -> None:
    monkeypatch.setattr("sys.argv", ["dashbox", "--data-dir", "data"])

    args = server_cli.parse_args()

    assert args.data_dir == "data"


def test_data_dir_supplies_config_path_when_config_is_unset(monkeypatch) -> None:
    monkeypatch.delenv(server_cli.DASHBOX_CONFIG_ENV, raising=False)
    monkeypatch.setenv(server_cli.DASHBOX_DATA_DIR_ENV, "env-data")

    assert server_cli.config_path_from_startup_options(None, "cli-data") == str(Path("cli-data") / "config.json")
    assert server_cli.config_path_from_startup_options() == str(Path("env-data") / "config.json")


def test_data_dir_config_is_created_when_missing(tmp_path) -> None:
    data_dir = tmp_path / "data"
    config_path = data_dir / "config.json"

    server_cli.ensure_data_dir_config(str(config_path), str(data_dir))

    assert json.loads(config_path.read_text(encoding="utf-8")) == {"subs": []}


def test_public_base_url_cli_value_overrides_env(monkeypatch) -> None:
    monkeypatch.setenv(server_cli.PUBLIC_BASE_URL_ENV, "http://env.example.test")

    server_cli.apply_public_base_url_arg(" http://cli.example.test ")

    assert server_cli.load_config(None).public_base_url == "http://cli.example.test"


@pytest.mark.parametrize("value", ("0", "false", "no", "off"))
def test_server_reload_env_accepts_false_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv(server_cli.DASHBOX_RELOAD_ENV, value)

    assert server_cli.reload_from_env() is False


@pytest.mark.parametrize("value", ("0", "65536", "abc"))
def test_server_port_env_rejects_invalid_values(monkeypatch, value: str) -> None:
    monkeypatch.setenv(server_cli.DASHBOX_PORT_ENV, value)

    with pytest.raises(ValueError, match=server_cli.DASHBOX_PORT_ENV):
        server_cli.port_from_env()


def test_server_reload_env_rejects_invalid_values(monkeypatch) -> None:
    monkeypatch.setenv(server_cli.DASHBOX_RELOAD_ENV, "maybe")

    with pytest.raises(ValueError, match=server_cli.DASHBOX_RELOAD_ENV):
        server_cli.reload_from_env()


def test_startup_logs_detected_js_runtimes(caplog) -> None:
    state = type("State", (), {
        "service": type("Service", (), {
            "ytdlp": type("Ytdlp", (), {"js_runtimes": {"node": {}, "deno": {}}})()
        })()
    })()

    with caplog.at_level(logging.INFO, logger="dashbox"):
        server_utils.log_js_environment(state)

    assert "yt-dlp JavaScript runtimes detected at startup: deno, node" in caplog.text


def test_startup_logs_missing_js_runtimes(caplog) -> None:
    state = type("State", (), {
        "service": type("Service", (), {
            "ytdlp": type("Ytdlp", (), {"js_runtimes": {}})()
        })()
    })()

    with caplog.at_level(logging.INFO, logger="dashbox"):
        server_utils.log_js_environment(state)

    assert "yt-dlp JavaScript runtimes not found at startup" in caplog.text


def test_startup_logs_dashbox_and_ytdlp_versions(caplog) -> None:
    state = type("State", (), {
        "service": type("Service", (), {
            "ytdlp": type("Ytdlp", (), {
                "yt_dlp": type("YtDlp", (), {
                    "version": type("Version", (), {"__version__": "2026.5.16"})()
                })()
            })()
        })()
    })()

    with caplog.at_level(logging.INFO, logger="dashbox"):
        server_utils.log_startup_versions(state)

    assert f"dashbox version={server_utils.__version__} yt-dlp version=2026.5.16" in caplog.text


def test_image_fetch_manager_coalesces_concurrent_requests(monkeypatch) -> None:
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_fetch_image(client, url: str, config: Config, request_headers: dict[str, str]):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return b"image", "image/jpeg", {"Cache-Control": "public, max-age=86400"}

    async def run() -> None:
        monkeypatch.setattr(image_proxy, "fetch_image_with_client", fake_fetch_image)
        monkeypatch.setattr(image_proxy.ImageFetchManager, "_get_client", fake_image_fetch_client)
        fetcher = image_proxy.ImageFetchManager()
        try:
            first = asyncio.create_task(fetcher.get("https://img.example.test/a.jpg", Config(), {}))
            await started.wait()
            second = asyncio.create_task(fetcher.get("https://img.example.test/a.jpg", Config(), {}))
            await asyncio.sleep(0)
            release.set()

            assert await first == (b"image", "image/jpeg", {"Cache-Control": "public, max-age=86400"})
            assert await second == (b"image", "image/jpeg", {"Cache-Control": "public, max-age=86400"})
        finally:
            await fetcher.aclose()


    asyncio.run(run())

    assert calls == 1


def test_icon_route_serves_png_assets() -> None:
    with no_lifespan_test_client(app_server.create_app(Config())) as client:
        responses = [
            client.get(f"/assets/icons/{name}.png")
            for name in ("folder", "playlist", "refresh", "search", "video")
        ]

    for response in responses:
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert response.content.startswith(b"\x89PNG")


def test_spider_route_serves_configured_asset_path(monkeypatch, tmp_path) -> None:
    asset_path = tmp_path / "dashbox.test.js"
    asset_path.write_bytes(b"console.log('dashbox test spider');\n")
    monkeypatch.setattr(app_server, "SPIDER_ASSET_PATH", asset_path)

    with no_lifespan_test_client(app_server.create_app(Config())) as client:
        response = client.get(f"/spider/{asset_path.name}")

    assert response.status_code == 200
    assert response.content == asset_path.read_bytes()


def test_image_route_is_disabled_when_image_proxy_mode_is_off() -> None:
    with no_lifespan_test_client(app_server.create_app(Config(image_proxy_mode="off"))) as client:
        response = client.get("/image?url=https%3A%2F%2Fimg.example.test%2Fa.jpg")

    assert response.status_code == 404
    assert response.json()["detail"] == "image proxy disabled"


def test_image_route_all_mode_accepts_generic_https_image(monkeypatch) -> None:
    async def fake_proxy_image(url, config, request, cache, fetcher):
        return Response(content=url.encode(), media_type="image/jpeg")

    monkeypatch.setattr(app_server, "proxy_image", fake_proxy_image)

    with no_lifespan_test_client(app_server.create_app(Config(image_proxy_mode="all"))) as client:
        response = client.get("/image?url=https%3A%2F%2Fexample.test%2Fa.jpg")

    assert response.status_code == 200
    assert response.content == b"https://example.test/a.jpg"


def test_image_route_accepts_head_without_body(monkeypatch) -> None:
    async def fake_proxy_image(url, config, request, cache, fetcher):
        raise AssertionError("HEAD should not use GET image proxy")

    async def fake_proxy_image_head(url, config, request, cache):
        return Response(content=b"", media_type="image/jpeg", headers={"Content-Length": str(len(b"image-bytes"))})

    monkeypatch.setattr(app_server, "proxy_image", fake_proxy_image)
    monkeypatch.setattr(app_server, "proxy_image_head", fake_proxy_image_head)

    with no_lifespan_test_client(app_server.create_app(Config(image_proxy_mode="all"))) as client:
        response = client.head("/image?url=https%3A%2F%2Fexample.test%2Fa.jpg")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["content-length"] == str(len(b"image-bytes"))
    assert response.content == b""


def test_image_route_known_mode_rejects_generic_https_image() -> None:
    with no_lifespan_test_client(app_server.create_app(Config(image_proxy_mode="known"))) as client:
        response = client.get("/image?url=https%3A%2F%2Fexample.test%2Fa.jpg")

    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported image upstream"


@pytest.mark.parametrize(
    "url",
    (
        "http://localhost/a.jpg",
        "http://127.0.0.1/a.jpg",
        "http://[::1]/a.jpg",
        "http://169.254.1.1/a.jpg",
        "http://224.0.0.1/a.jpg",
        "http://255.255.255.255/a.jpg",
        "http://[::ffff:255.255.255.255]/a.jpg",
    ),
)
def test_image_route_all_mode_rejects_local_and_link_local_upstreams(url: str) -> None:
    with no_lifespan_test_client(app_server.create_app(Config(image_proxy_mode="all"))) as client:
        response = client.get("/image", params={"url": url})

    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported image upstream"


def test_image_route_all_mode_allows_private_upstreams(monkeypatch) -> None:
    async def fake_proxy_image(url, config, request, cache, fetcher):
        return Response(content=url.encode(), media_type="image/jpeg")

    monkeypatch.setattr(app_server, "proxy_image", fake_proxy_image)

    with no_lifespan_test_client(app_server.create_app(Config(image_proxy_mode="all"))) as client:
        response = client.get("/image", params={"url": "http://10.0.0.1/a.jpg"})

    assert response.status_code == 200
    assert response.content == b"http://10.0.0.1/a.jpg"


def test_image_address_filter_allows_reserved_proxy_fake_ip() -> None:
    assert image_policy.is_blocked_image_proxy_address("198.19.1.62") is False
    assert image_policy.is_blocked_image_proxy_address("169.254.1.1") is True
    assert image_policy.is_blocked_image_proxy_address("::ffff:255.255.255.255") is True


def test_image_fetch_manager_fetches_distinct_urls_concurrently(monkeypatch) -> None:
    active = 0
    max_active = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def fake_fetch_image(client, url: str, config: Config, request_headers: dict[str, str]):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active == 3:
            started.set()
        await release.wait()
        active -= 1
        return url.encode(), "image/jpeg", {"Cache-Control": "public, max-age=86400"}

    async def run() -> None:
        monkeypatch.setattr(image_proxy, "fetch_image_with_client", fake_fetch_image)
        monkeypatch.setattr(image_proxy.ImageFetchManager, "_get_client", fake_image_fetch_client)
        fetcher = image_proxy.ImageFetchManager(concurrency=3)
        try:
            tasks = [
                asyncio.create_task(fetcher.get(f"https://img.example.test/{index}.jpg", Config(), {}))
                for index in range(3)
            ]
            await asyncio.wait_for(started.wait(), timeout=1)
            release.set()

            assert [item[0] for item in await asyncio.gather(*tasks)] == [
                b"https://img.example.test/0.jpg",
                b"https://img.example.test/1.jpg",
                b"https://img.example.test/2.jpg",
            ]
        finally:
            await fetcher.aclose()

    asyncio.run(run())

    assert max_active == 3


def test_image_fetch_manager_prioritizes_foreground_over_queued_prefetch(monkeypatch) -> None:
    started: list[str] = []
    first_started = asyncio.Event()
    release = asyncio.Event()

    async def fake_fetch_image(client, url: str, config: Config, request_headers: dict[str, str]):
        started.append(url)
        if len(started) == 1:
            first_started.set()
            await release.wait()
        return url.encode(), "image/jpeg", {"Cache-Control": "public, max-age=86400"}

    async def run() -> None:
        monkeypatch.setattr(image_proxy, "fetch_image_with_client", fake_fetch_image)
        monkeypatch.setattr(image_proxy.ImageFetchManager, "_get_client", fake_image_fetch_client)
        fetcher = image_proxy.ImageFetchManager(concurrency=1)
        try:
            background = [
                asyncio.create_task(
                    fetcher.get(
                        f"https://img.example.test/background-{index}.jpg",
                        Config(),
                        {},
                        image_proxy.IMAGE_FETCH_PRIORITY_BACKGROUND,
                    )
                )
                for index in range(3)
            ]
            await first_started.wait()
            foreground = asyncio.create_task(
                fetcher.get("https://img.example.test/foreground.jpg", Config(), {})
            )
            await asyncio.sleep(0)
            release.set()

            await foreground
            await asyncio.gather(*background)
        finally:
            await fetcher.aclose()

    asyncio.run(run())

    assert started[:3] == [
        "https://img.example.test/background-0.jpg",
        "https://img.example.test/foreground.jpg",
        "https://img.example.test/background-1.jpg",
    ]


def test_image_fetch_manager_promotes_matching_queued_prefetch(monkeypatch) -> None:
    calls = 0
    first_started = asyncio.Event()
    release = asyncio.Event()

    async def fake_fetch_image(client, url: str, config: Config, request_headers: dict[str, str]):
        nonlocal calls
        calls += 1
        if calls == 1:
            first_started.set()
            await release.wait()
        return url.encode(), "image/jpeg", {"Cache-Control": "public, max-age=86400"}

    async def run() -> None:
        monkeypatch.setattr(image_proxy, "fetch_image_with_client", fake_fetch_image)
        monkeypatch.setattr(image_proxy.ImageFetchManager, "_get_client", fake_image_fetch_client)
        fetcher = image_proxy.ImageFetchManager(concurrency=1)
        try:
            first = asyncio.create_task(
                fetcher.get(
                    "https://img.example.test/first.jpg",
                    Config(),
                    {},
                    image_proxy.IMAGE_FETCH_PRIORITY_BACKGROUND,
                )
            )
            queued_background = asyncio.create_task(
                fetcher.get(
                    "https://img.example.test/promoted.jpg",
                    Config(),
                    {},
                    image_proxy.IMAGE_FETCH_PRIORITY_BACKGROUND,
                )
            )
            await first_started.wait()
            foreground = asyncio.create_task(fetcher.get("https://img.example.test/promoted.jpg", Config(), {}))
            await asyncio.sleep(0)
            release.set()

            assert await foreground == await queued_background
            await first
        finally:
            await fetcher.aclose()

    asyncio.run(run())

    assert calls == 2


def test_fetch_cached_image_uses_cache_before_fetcher() -> None:
    async def run() -> None:
        cache = image_proxy.ImageCache()
        fetcher = image_proxy.ImageFetchManager()
        await cache.set("https://img.example.test/a.jpg", b"cached", "image/jpeg", {"Cache-Control": "hit"})

        result = await image_proxy.fetch_cached_image("https://img.example.test/a.jpg", Config(), {}, cache, fetcher)

        assert result == (b"cached", "image/jpeg", {"Cache-Control": "hit"})

    asyncio.run(run())


def test_image_cache_evicts_oldest_item_over_byte_limit() -> None:
    async def run() -> None:
        cache = image_proxy.ImageCache(max_bytes=6, max_item_bytes=6)
        await cache.set("https://example.test/1.jpg", b"111", "image/jpeg", {})
        await cache.set("https://example.test/2.jpg", b"222", "image/jpeg", {})
        await cache.set("https://example.test/3.jpg", b"333", "image/jpeg", {})

        assert await cache.get("https://example.test/1.jpg") is None
        assert await cache.get("https://example.test/2.jpg") == (b"222", "image/jpeg", {})
        assert await cache.get("https://example.test/3.jpg") == (b"333", "image/jpeg", {})

    asyncio.run(run())


def test_image_cache_get_refreshes_lru_order() -> None:
    async def run() -> None:
        cache = image_proxy.ImageCache(max_bytes=6, max_item_bytes=6)
        await cache.set("https://example.test/1.jpg", b"111", "image/jpeg", {})
        await cache.set("https://example.test/2.jpg", b"222", "image/jpeg", {})

        assert await cache.get("https://example.test/1.jpg") == (b"111", "image/jpeg", {})
        await cache.set("https://example.test/3.jpg", b"333", "image/jpeg", {})

        assert await cache.get("https://example.test/1.jpg") == (b"111", "image/jpeg", {})
        assert await cache.get("https://example.test/2.jpg") is None
        assert await cache.get("https://example.test/3.jpg") == (b"333", "image/jpeg", {})

    asyncio.run(run())


def test_image_cache_skips_items_over_single_item_limit() -> None:
    async def run() -> None:
        cache = image_proxy.ImageCache(max_bytes=10, max_item_bytes=4)
        await cache.set("https://example.test/large.jpg", b"12345", "image/jpeg", {})

        assert await cache.get("https://example.test/large.jpg") is None

    asyncio.run(run())


def test_proxy_image_returns_304_for_cached_etag_match() -> None:
    async def run() -> None:
        cache = image_proxy.ImageCache()
        await cache.set("https://example.test/a.jpg", b"image", "image/jpeg", {
            "Cache-Control": "public, max-age=86400",
            "etag": '"abc"',
        })
        request = request_with_headers({"if-none-match": '"abc"'})

        response = await image_proxy.proxy_image("https://example.test/a.jpg", Config(), request, cache, None)

        assert response.status_code == 304
        assert response.body == b""

    asyncio.run(run())


def test_proxy_image_returns_304_for_cached_last_modified_match() -> None:
    async def run() -> None:
        cache = image_proxy.ImageCache()
        await cache.set("https://example.test/a.jpg", b"image", "image/jpeg", {
            "Cache-Control": "public, max-age=86400",
            "last-modified": "Tue, 05 May 2026 00:00:00 GMT",
        })
        request = request_with_headers({"if-modified-since": "Tue, 05 May 2026 00:00:00 GMT"})

        response = await image_proxy.proxy_image("https://example.test/a.jpg", Config(), request, cache, None)

        assert response.status_code == 304
        assert response.body == b""

    asyncio.run(run())


def test_proxy_image_does_not_forward_client_conditionals_on_cache_miss() -> None:
    async def run() -> None:
        seen_headers = None

        async def fake_fetch_image(url: str, config: Config, request_headers: dict[str, str]):
            nonlocal seen_headers
            seen_headers = request_headers
            return b"image", "image/jpeg", {"Cache-Control": "public, max-age=86400"}

        request = request_with_headers({
            "if-none-match": '"abc"',
            "if-modified-since": "Tue, 05 May 2026 00:00:00 GMT",
        })
        original = image_proxy.fetch_image
        image_proxy.fetch_image = fake_fetch_image
        try:
            response = await image_proxy.proxy_image("https://example.test/a.jpg", Config(), request, image_proxy.ImageCache(), None)
        finally:
            image_proxy.fetch_image = original

        assert response.status_code == 200
        assert response.body == b"image"
        assert seen_headers == {}

    asyncio.run(run())


def test_fetch_image_head_uses_upstream_head_without_body() -> None:
    seen_methods = []

    class FakeClient:
        def build_request(self, method, url, headers):
            seen_methods.append(method)
            return httpx.Request(method, url, headers=headers)

        async def send(self, request, stream=True, follow_redirects=False):
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "image/png",
                    "Content-Length": "12345",
                    "ETag": '"abc"',
                },
                request=request,
            )

    async def run() -> None:
        media_type, headers = await image_proxy.fetch_image_head_with_client(
            FakeClient(),
            "https://example.test/a.png",
            Config(image_proxy_mode="all"),
            {},
            host_resolves_to_blocked_address=allow_image_proxy_host,
        )

        assert media_type == "image/png"
        assert headers["content-length"] == "12345"
        assert headers["etag"] == '"abc"'

    asyncio.run(run())
    assert seen_methods == ["HEAD"]


def test_fetch_image_follows_proxyable_redirects(monkeypatch) -> None:
    seen_urls = []
    monkeypatch.setattr(
        image_proxy.image_policy,
        "is_supported_image_proxy_url",
        lambda url, mode: url in {"https://img.example.test/a.jpg", "https://redirect.example.test/b.jpg"},
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        if str(request.url) == "https://img.example.test/a.jpg":
            return httpx.Response(302, headers={"Location": "https://redirect.example.test/b.jpg"})
        return httpx.Response(200, content=b"image", headers={"Content-Type": "image/jpeg"})

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
            result = await image_proxy.fetch_image_with_client(
                client,
                "https://img.example.test/a.jpg",
                Config(),
                {},
                allow_image_proxy_host,
            )

        assert result == (b"image", "image/jpeg", {"Cache-Control": "public, max-age=86400"})

    asyncio.run(run())
    assert seen_urls == ["https://img.example.test/a.jpg", "https://redirect.example.test/b.jpg"]


def test_fetch_image_rejects_redirects_outside_image_allowlist(monkeypatch) -> None:
    monkeypatch.setattr(
        image_proxy.image_policy,
        "is_supported_image_proxy_url",
        lambda url, mode: url == "https://img.example.test/a.jpg",
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://example.test/b.jpg"})

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
            with pytest.raises(HTTPException) as exc_info:
                await image_proxy.fetch_image_with_client(
                    client,
                    "https://img.example.test/a.jpg",
                    Config(image_proxy_mode="known"),
                    {},
                    allow_image_proxy_host,
                )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "unsupported image upstream"

    asyncio.run(run())


def test_fetch_image_all_mode_follows_generic_https_redirects() -> None:
    seen_urls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        if str(request.url) == "https://example.test/a.jpg":
            return httpx.Response(302, headers={"Location": "https://cdn.example.test/b.jpg"})
        return httpx.Response(200, content=b"image", headers={"Content-Type": "image/jpeg"})

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
            result = await image_proxy.fetch_image_with_client(
                client,
                "https://example.test/a.jpg",
                Config(image_proxy_mode="all"),
                {},
                allow_image_proxy_host,
            )

        assert result == (b"image", "image/jpeg", {"Cache-Control": "public, max-age=86400"})

    asyncio.run(run())
    assert seen_urls == ["https://example.test/a.jpg", "https://cdn.example.test/b.jpg"]


def test_fetch_image_all_mode_rejects_hostname_resolving_to_blocked_address() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"image", headers={"Content-Type": "image/jpeg"})

    async def resolves_to_blocked_address(host: str) -> bool:
        return host == "attacker.example"

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(HTTPException) as exc_info:
                await image_proxy.fetch_image_with_client(
                    client,
                    "https://attacker.example/a.jpg",
                    Config(image_proxy_mode="all"),
                    {},
                    resolves_to_blocked_address,
                )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "unsupported image upstream"

    asyncio.run(run())


def test_fetch_image_all_mode_rejects_redirect_hostname_resolving_to_blocked_address() -> None:
    seen_urls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        if str(request.url) == "https://example.test/a.jpg":
            return httpx.Response(302, headers={"Location": "https://attacker.example/b.jpg"})
        return httpx.Response(200, content=b"image", headers={"Content-Type": "image/jpeg"})

    async def resolves_to_blocked_address(host: str) -> bool:
        return host == "attacker.example"

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(HTTPException) as exc_info:
                await image_proxy.fetch_image_with_client(
                    client,
                    "https://example.test/a.jpg",
                    Config(image_proxy_mode="all"),
                    {},
                    resolves_to_blocked_address,
                )

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "unsupported image upstream"

    asyncio.run(run())
    assert seen_urls == ["https://example.test/a.jpg"]


def test_fetch_image_rejects_non_image_content_type() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html></html>", headers={"Content-Type": "text/html"})

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(HTTPException) as exc_info:
                await image_proxy.fetch_image_with_client(
                    client,
                    "https://example.test/a.jpg",
                    Config(image_proxy_mode="all"),
                    {},
                    allow_image_proxy_host,
                )

        assert exc_info.value.status_code == 415
        assert exc_info.value.detail == "image upstream returned non-image content"

    asyncio.run(run())


@pytest.mark.parametrize("headers", ({}, {"Content-Type": ""}, {"Content-Type": "   "}))
def test_fetch_image_defaults_blank_content_type_to_jpeg(headers: dict[str, str]) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"image", headers=headers)

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            result = await image_proxy.fetch_image_with_client(
                client,
                "https://example.test/a.jpg",
                Config(image_proxy_mode="all"),
                {},
                allow_image_proxy_host,
            )

        assert result == (b"image", "image/jpeg", {"Cache-Control": "public, max-age=86400"})

    asyncio.run(run())


def test_fetch_image_rejects_content_length_over_item_limit() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"",
            headers={"Content-Length": str(image_proxy.IMAGE_CACHE_MAX_ITEM_BYTES + 1)},
        )

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(HTTPException) as exc_info:
                await image_proxy.fetch_image_with_client(
                    client,
                    "https://img.example.test/a.jpg",
                    Config(image_proxy_mode="all"),
                    {},
                    allow_image_proxy_host,
                )

        assert exc_info.value.status_code == 413
        assert exc_info.value.detail == "image upstream too large"

    asyncio.run(run())


def test_fetch_image_rejects_stream_over_item_limit_without_content_length() -> None:
    class LargeBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"1" * image_proxy.IMAGE_CACHE_MAX_ITEM_BYTES
            yield b"2"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=LargeBody())

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(HTTPException) as exc_info:
                await image_proxy.fetch_image_with_client(
                    client,
                    "https://img.example.test/a.jpg",
                    Config(image_proxy_mode="all"),
                    {},
                    allow_image_proxy_host,
                )

        assert exc_info.value.status_code == 413
        assert exc_info.value.detail == "image upstream too large"

    asyncio.run(run())


def test_fetch_image_maps_stream_read_errors_to_upstream_failure() -> None:
    class FailingBody(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"partial"
            raise httpx.ReadError("upstream dropped connection")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=FailingBody())

    async def run() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(HTTPException) as exc_info:
                await image_proxy.fetch_image_with_client(
                    client,
                    "https://img.example.test/a.jpg",
                    Config(image_proxy_mode="all"),
                    {},
                    allow_image_proxy_host,
                )

        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == "image upstream failed"

    asyncio.run(run())


def request_with_headers(headers: dict[str, str]):
    return type("Request", (), {"headers": headers})()
