from dashbox.config import Config
from dashbox.config.runtime import FIREFOX_DATA_DIR_PROFILE_DIRNAME, RuntimeConfigValues, bind_runtime_config
from dashbox.media.ytdlp_client import YtdlpClient, ytdlp_version
from tests.helpers import make_tvbox_service as MediaService


def patch_browser_cookie_loader(monkeypatch, service) -> list:
    cookiesfrombrowser_calls = []

    class FakeYoutubeDL:
        def __init__(self, opts: dict) -> None:
            cookiesfrombrowser_calls.append(opts.get("cookiesfrombrowser"))
            self.cookiejar = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

    monkeypatch.setattr(service.ytdlp.yt_dlp, "YoutubeDL", FakeYoutubeDL)
    return cookiesfrombrowser_calls


def test_ytdlp_opts_enables_detected_js_runtimes(monkeypatch) -> None:
    monkeypatch.setattr(YtdlpClient, "detect_js_runtimes", lambda self: {"node": {}})
    service = MediaService(Config(cookies_from_browser={"mode": "firefox"}))

    opts = service.ytdlp_opts(quiet=True)

    assert opts["quiet"] is True
    assert opts["js_runtimes"] == {"node": {}}
    assert "http_headers" not in opts
    assert "cookiesfrombrowser" not in opts
    assert service.browser_cookie_status()["enabled"] is True


def test_ytdlp_js_runtime_detection_is_cached(monkeypatch) -> None:
    calls = []

    def fake_command_available(command: str) -> bool:
        calls.append(command)
        return command == "deno"

    monkeypatch.setattr(YtdlpClient, "_js_runtimes_cache", None)
    monkeypatch.setattr(YtdlpClient, "command_available", staticmethod(fake_command_available))
    monkeypatch.setattr(YtdlpClient, "node_is_supported", classmethod(lambda cls: False))

    first_config = Config()
    second_config = Config()
    first = YtdlpClient(first_config).detect_js_runtimes()
    second = YtdlpClient(second_config).detect_js_runtimes()

    assert first == {"deno": {}}
    assert second == {"deno": {}}
    assert calls == ["deno", "bun", "quickjs", "qjs"]


def test_ytdlp_version_reads_version_module() -> None:
    module = type("YtDlp", (), {
        "version": type("Version", (), {"__version__": "2026.05.16.233954"})()
    })()

    assert ytdlp_version(module) == "2026.05.16.233954"


def test_ytdlp_opts_uses_explicit_user_agent_only() -> None:
    service = MediaService(Config(user_agent="Custom UA"))

    opts = service.ytdlp_opts(http_headers={"Referer": "https://example.test/"})

    assert opts["http_headers"] == {
        "Referer": "https://example.test/",
        "User-Agent": "Custom UA",
    }


def test_ytdlp_opts_for_site_adds_impersonate_target(monkeypatch) -> None:
    service = MediaService(Config())
    calls = []

    def fake_impersonate_target_for_url(url: str) -> str:
        calls.append(url)
        return "chrome"

    monkeypatch.setattr(service.ytdlp, "impersonate_target_for_url", fake_impersonate_target_for_url)

    opts = service.ytdlp.opts_for_url("mock-site://video/1")

    assert str(opts["impersonate"]) == "chrome"
    assert calls == ["mock-site://video/1"]


def test_browser_cookie_reload_clears_cached_cookiejar(monkeypatch) -> None:
    service = MediaService(Config(cookies_from_browser={"mode": "firefox"}))
    jars = [["first"], ["second"]]
    load_count = 0
    extract_cookiejars = []

    class FakeYoutubeDL:
        def __init__(self, opts: dict) -> None:
            nonlocal load_count
            if opts.get("cookiesfrombrowser") == ("firefox", None, None, None):
                self.cookiejar = jars[load_count]
                load_count += 1
            else:
                self.cookiejar = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def extract_info(self, url: str, download: bool):
            extract_cookiejars.append(self.__dict__.get("cookiejar"))
            return {"url": url}

    monkeypatch.setattr(service.ytdlp.yt_dlp, "YoutubeDL", FakeYoutubeDL)

    service.extract_once("https://example.test/one", download=False, playlist=False)
    service.reload_browser_cookies()
    service.extract_once("https://example.test/two", download=False, playlist=False)

    assert load_count == 2
    assert extract_cookiejars == [jars[0], jars[1]]


def test_browser_cookie_resolution_updates_effective_source_and_cache_key(tmp_path) -> None:
    data_dir = tmp_path / "data"
    config = Config(cookies_from_browser={"mode": "firefox_data_dir"})
    runtime_config = bind_runtime_config(config, data_dir)
    service = MediaService(
        config,
        runtime_config=runtime_config,
    )
    expected = f"firefox:{(data_dir / FIREFOX_DATA_DIR_PROFILE_DIRNAME).resolve()}"

    assert service.ytdlp.browser_cookies.cookies_from_browser == expected
    assert service.browser_cookie_status()["source"] == "firefox:<data-dir>/firefox-profile"
    assert expected in service.playable_cache_key("video-id")


def test_firefox_data_dir_mode_allows_direct_service_and_client_construction() -> None:
    config = Config(cookies_from_browser={"mode": "firefox_data_dir"})

    client = YtdlpClient(config)
    service = MediaService(config)

    assert client.browser_cookies.cookies_from_browser == "firefox_data_dir"
    assert client.browser_cookies.status()["source"] == "firefox:<data-dir>/firefox-profile"
    assert service.ytdlp.browser_cookies.cookies_from_browser == "firefox_data_dir"
    assert service.browser_cookie_status()["source"] == "firefox:<data-dir>/firefox-profile"


def test_firefox_data_dir_cookie_load_requires_runtime_data_dir(monkeypatch) -> None:
    service = MediaService(Config(cookies_from_browser={"mode": "firefox_data_dir"}))

    class FakeYoutubeDL:
        def __init__(self, opts: dict) -> None:
            raise AssertionError("cookie load should fail before YoutubeDL is constructed")

    monkeypatch.setattr(service.ytdlp.yt_dlp, "YoutubeDL", FakeYoutubeDL)

    status = service.reload_browser_cookies(load=True)

    assert status["enabled"] is True
    assert "requires --data-dir or DASHBOX_DATA_DIR" in status["last_error"]
    assert status["cookie_count"] == 0


def test_firefox_data_dir_cookie_load_uses_runtime_data_dir(monkeypatch, tmp_path) -> None:
    data_dir = tmp_path / "data"
    config = Config(cookies_from_browser={"mode": "firefox_data_dir"})
    runtime_config = bind_runtime_config(config, data_dir)
    service = MediaService(config, runtime_config=runtime_config)
    cookiesfrombrowser_calls = patch_browser_cookie_loader(monkeypatch, service)

    status = service.reload_browser_cookies(load=True)

    expected_profile = str((data_dir / FIREFOX_DATA_DIR_PROFILE_DIRNAME).resolve())
    assert cookiesfrombrowser_calls == [("firefox", expected_profile, None, None)]
    assert status["last_error"] == ""


def test_browser_cookie_runtime_override_is_used_for_cookie_load(monkeypatch) -> None:
    config = Config(cookies_from_browser={"mode": "firefox_data_dir"})
    runtime_config = RuntimeConfigValues(
        cookies_from_browser="firefox:C:\\cookies\\firefox-profile",
        cookies_from_browser_display="firefox:<data-dir>/firefox-profile",
    )
    service = MediaService(config, runtime_config=runtime_config)
    cookiesfrombrowser_calls = patch_browser_cookie_loader(monkeypatch, service)

    status = service.reload_browser_cookies(load=True)

    assert cookiesfrombrowser_calls == [("firefox", "C:\\cookies\\firefox-profile", None, None)]
    assert status["source"] == "firefox:<data-dir>/firefox-profile"
    assert status["last_error"] == ""


def test_extract_accepts_direct_url_with_missing_codec_metadata(monkeypatch) -> None:
    service = MediaService(Config(cookies_from_browser={"mode": "firefox"}))
    calls = []

    def fake_extract_once(url: str, *, download: bool, playlist: bool, flat: bool = False, use_cookies: bool = True):
        calls.append(use_cookies)
        return {"url": "https://example.test/video.mp4"}

    monkeypatch.setattr(service, "extract_once", fake_extract_once)

    info = service.extract("https://example.test/watch", download=False, playlist=False, require_playable=True)

    assert info["url"] == "https://example.test/video.mp4"
    assert calls == [True]

