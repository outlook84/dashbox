from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from typing import Any

import yt_dlp

from ..config import Config
from ..config.runtime import RuntimeConfigValues, default_runtime_config
from ..config.validation import parse_cookies_from_browser
from ..utils.errors import exception_reason
from ..sites import registry

logger = logging.getLogger("dashbox.ytdlp")
BROWSER_COOKIE_AUTO_RELOAD_COOLDOWN_SECONDS = 30.0


class YtdlpClient:
    _js_runtimes_cache: dict[str, dict[str, Any]] | None = None
    _js_runtimes_lock = threading.Lock()

    def __init__(
        self,
        config: Config,
        runtime_config: RuntimeConfigValues | None = None,
        *,
        ytdlp_search_limit: int | None = None,
        playlist_limit: int | None = None,
    ) -> None:
        self.config = config
        self.runtime_config = runtime_config or default_runtime_config(config)
        self.ytdlp_search_limit = config.effective_ytdlp_search_limit if ytdlp_search_limit is None else ytdlp_search_limit
        self.playlist_limit = config.effective_playlist_limit if playlist_limit is None else playlist_limit
        self.yt_dlp = yt_dlp
        self.js_runtimes = self.detect_js_runtimes()
        self.browser_cookies = BrowserCookieProvider(self)

    def version(self) -> str:
        return ytdlp_version(self.yt_dlp)

    def detect_js_runtimes(self) -> dict[str, dict[str, Any]]:
        cls = type(self)
        with cls._js_runtimes_lock:
            if cls._js_runtimes_cache is None:
                cls._js_runtimes_cache = self._detect_js_runtimes_uncached()
            return {name: dict(options) for name, options in cls._js_runtimes_cache.items()}

    def _detect_js_runtimes_uncached(self) -> dict[str, dict[str, Any]]:
        runtimes: dict[str, dict[str, Any]] = {}
        if self.command_available("deno"):
            runtimes["deno"] = {}
        if self.node_is_supported():
            runtimes["node"] = {}
        if self.command_available("bun"):
            runtimes["bun"] = {}
        if self.command_available("quickjs") or self.command_available("qjs"):
            runtimes["quickjs"] = {}
        return runtimes

    @staticmethod
    def command_available(command: str) -> bool:
        return shutil.which(command) is not None

    @classmethod
    def node_is_supported(cls) -> bool:
        if not cls.command_available("node"):
            return False
        try:
            completed = subprocess.run(
                ["node", "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except Exception:
            return False
        raw_version = (completed.stdout or completed.stderr).strip().lstrip("v")
        major_text = raw_version.split(".", 1)[0]
        try:
            return int(major_text) >= 20
        except ValueError:
            return False

    def opts(self, *, use_cookies: bool = True, **opts: Any) -> dict[str, Any]:
        out = dict(opts)
        if self.js_runtimes:
            out["js_runtimes"] = dict(self.js_runtimes)
        headers = dict(out.get("http_headers") or {})
        if self.config.user_agent:
            headers.setdefault("User-Agent", self.config.user_agent)
        if headers:
            out["http_headers"] = headers
        return out

    def opts_for_url(self, url: str, *, use_cookies: bool = True, **opts: Any) -> dict[str, Any]:
        out = self.opts(use_cookies=use_cookies, **opts)
        impersonate = self.impersonate_target_for_url(url)
        if impersonate is not None:
            out["impersonate"] = impersonate
        return out

    @staticmethod
    def impersonate_target_for_url(url: str) -> Any | None:
        target = registry.call_for_url(url, "ytdlp_impersonate_target", url)
        if not target:
            return None
        from yt_dlp.networking.impersonate import ImpersonateTarget

        if target is True:
            return ImpersonateTarget()
        if isinstance(target, str):
            return ImpersonateTarget.from_str(target)
        return target

    def youtube_dl(self, opts: dict[str, Any], *, use_cookies: bool = True) -> Any:
        ydl = self.yt_dlp.YoutubeDL(opts)
        if use_cookies:
            self.browser_cookies.apply_to(ydl)
        return ydl

    def extract_once(
        self,
        url: str,
        *,
        download: bool,
        playlist: bool,
        flat: bool = False,
        use_cookies: bool = True,
        is_search_extract_url: bool,
        flat_playlist_items: str,
    ) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": not playlist,
            "skip_download": not download,
            "socket_timeout": self.config.upstream_timeout,
            "format": "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/bv*[ext=mp4]+ba[ext=m4a]/best[ext=mp4]/best",
        }
        opts = self.opts_for_url(url, **opts, use_cookies=use_cookies)
        if flat:
            opts["extract_flat"] = "in_playlist"
            if is_search_extract_url and self.ytdlp_search_limit > 0:
                opts["playlist_items"] = f"1-{self.ytdlp_search_limit}"
            elif not is_search_extract_url and self.playlist_limit > 0:
                opts["playlist_items"] = flat_playlist_items
        started_at = time.monotonic()
        logger.debug("yt-dlp extract start url=%s playlist=%s flat=%s", url, playlist, flat)
        with self.youtube_dl(opts, use_cookies=use_cookies) as ydl:
            info = ydl.extract_info(url, download=download)
        if not isinstance(info, dict):
            raise ValueError("yt-dlp returned an invalid response")
        if flat:
            self.enrich_flat_playlist_info(info)
        entries = info.get("entries")
        entry_count = len(entries) if isinstance(entries, list) else 0
        logger.debug(
            "yt-dlp extract done url=%s playlist=%s flat=%s entries=%s seconds=%.2f",
            url,
            playlist,
            flat,
            entry_count,
            time.monotonic() - started_at,
        )
        return info

    def flat_playlist_items(self, _url: str) -> str:
        limit = self.playlist_limit
        return f"1-{limit}"

    def enrich_flat_playlist_info(self, info: dict[str, Any]) -> None:
        if not registry.supports_flat_playlist_info(info):
            return
        url = str(info.get("webpage_url") or info.get("original_url") or "")
        if not url:
            return
        try:
            webpage = self.download_webpage_with_impersonation(url)
        except Exception as exc:
            logger.debug("flat playlist metadata enrichment failed url=%s error=%s", url, exc)
            return
        registry.enrich_flat_playlist_info(
            info,
            webpage,
            url,
            download_webpage=self.download_webpage_with_impersonation,
            limit=self.playlist_limit,
            concurrency=self.config.ytdlp_concurrency,
        )

    def download_webpage_with_impersonation(self, url: str) -> str:
        from yt_dlp.networking import Request

        opts = self.opts(quiet=True, no_warnings=True, socket_timeout=self.config.upstream_timeout)
        with self.youtube_dl(opts) as ydl:
            target, _requested = ydl._parse_impersonate_targets(True)
            response = ydl.urlopen(Request(url, extensions={"impersonate": target}))
            return response.read().decode("utf-8", "replace")


def ytdlp_version(module: Any = yt_dlp) -> str:
    version = getattr(module, "__version__", "")
    if version:
        return str(version)
    version_module = getattr(module, "version", None)
    version = getattr(version_module, "__version__", "") if version_module is not None else ""
    if version:
        return str(version)
    try:
        from yt_dlp import version as imported_version
    except Exception:
        return ""
    return str(getattr(imported_version, "__version__", ""))


class BrowserCookieProvider:
    def __init__(self, client: YtdlpClient) -> None:
        self.client = client
        self.lock = threading.Lock()
        self.cookiejar: Any | None = None
        self.loaded = False
        self.loaded_at: float | None = None
        self.last_error: str = ""
        self.last_auto_reload_at: float | None = None
        self.auto_reload_cooldown_seconds = BROWSER_COOKIE_AUTO_RELOAD_COOLDOWN_SECONDS
        self.reload_generation = 0
        self.next_load_action = "loaded"

    def apply_to(self, ydl: Any) -> None:
        cookiejar = self.get_cookiejar()
        if cookiejar is not None:
            ydl.__dict__["cookiejar"] = cookiejar

    @property
    def cookies_from_browser(self) -> str:
        return self.client.runtime_config.cookies_from_browser.strip()

    @property
    def display_source(self) -> str:
        return self.client.runtime_config.cookies_from_browser_display.strip()

    @property
    def enabled(self) -> bool:
        return bool(self.cookies_from_browser)

    def get_cookiejar(self) -> Any | None:
        if not self.enabled:
            return None
        with self.lock:
            if self.loaded:
                return self.cookiejar
            self._load_locked()
            return self.cookiejar

    def reload(self) -> None:
        if not self.enabled:
            return
        with self.lock:
            self.reload_generation += 1
            self.cookiejar = None
            self.loaded = False
            self.loaded_at = None
            self.last_error = ""
            self.next_load_action = "reloaded"

    def auto_reload(self) -> bool:
        if not self.enabled:
            return False
        with self.lock:
            now = time.monotonic()
            if (
                self.last_auto_reload_at is not None
                and now - self.last_auto_reload_at < self.auto_reload_cooldown_seconds
            ):
                return False
            self.last_auto_reload_at = now
            self.reload_generation += 1
            self.cookiejar = None
            self.loaded = False
            self.loaded_at = None
            self.last_error = ""
            self.next_load_action = "auto reloaded"
            self._load_locked()
            return self.cookiejar is not None

    def cache_token(self) -> str:
        with self.lock:
            return str(self.reload_generation)

    def _load_locked(self) -> None:
        self.loaded = True
        self.loaded_at = time.time()
        self.last_error = ""
        action = self.next_load_action
        self.next_load_action = "loaded"
        try:
            opts = self.client.opts(use_cookies=False, quiet=True, no_warnings=True)
            opts["cookiesfrombrowser"] = self.browser_specification()
            with self.client.yt_dlp.YoutubeDL(opts) as ydl:
                self.cookiejar = ydl.cookiejar
            cookie_count = sum(1 for _cookie in self.cookiejar) if self.cookiejar is not None else 0
            logger.info("browser cookies %s source=%s cookies=%s", action, self.cookies_from_browser, cookie_count)
        except Exception as exc:
            logger.warning("browser cookie load failed source=%s reason=%s", self.cookies_from_browser, exception_reason(exc))
            logger.debug("browser cookie load failed", exc_info=True)
            self.cookiejar = None
            self.last_error = str(exc)

    def browser_specification(self) -> tuple[str, str | None, str | None, str | None]:
        if self.cookies_from_browser == "firefox_data_dir":
            raise ValueError("cookies_from_browser mode firefox_data_dir requires --data-dir or DASHBOX_DATA_DIR")
        return parse_cookies_from_browser(self.cookies_from_browser)

    def status(self) -> dict[str, Any]:
        with self.lock:
            return {
                "enabled": bool(self.cookies_from_browser),
                "source": self.display_source,
                "loaded": self.loaded,
                "loaded_at": self.loaded_at,
                "cookie_count": sum(1 for _cookie in self.cookiejar) if self.cookiejar is not None else 0,
                "last_error": self.last_error,
                "last_auto_reload_at": self.last_auto_reload_at,
                "auto_reload_cooldown_seconds": self.auto_reload_cooldown_seconds,
                "reload_generation": self.reload_generation,
            }
