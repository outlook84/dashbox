from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .model import BrowserCookiesMode, Config

DASHBOX_DATA_DIR_ENV = "DASHBOX_DATA_DIR"
FIREFOX_DATA_DIR_PROFILE_DIRNAME = "firefox-profile"


@dataclass(frozen=True)
class RuntimeConfigValues:
    cookies_from_browser: str = ""
    cookies_from_browser_display: str = ""
    data_dir: Path | None = None


def default_runtime_config(config: Config) -> RuntimeConfigValues:
    if config.cookies_from_browser.mode is BrowserCookiesMode.FIREFOX_DATA_DIR:
        return RuntimeConfigValues(
            cookies_from_browser=config.configured_cookies_from_browser,
            cookies_from_browser_display="firefox:<data-dir>/firefox-profile",
        )
    value = config.configured_cookies_from_browser
    return RuntimeConfigValues(cookies_from_browser=value, cookies_from_browser_display=value)


def resolve_runtime_data_dir(data_dir: Path | None) -> Path | None:
    if data_dir is not None:
        return data_dir.resolve()
    value = os.environ.get(DASHBOX_DATA_DIR_ENV, "").strip()
    if not value:
        return None
    return Path(value).resolve()


def bind_runtime_config(config: Config, data_dir: Path | None) -> RuntimeConfigValues:
    resolved_data_dir = resolve_runtime_data_dir(data_dir)
    cookies_from_browser, cookies_from_browser_display = resolve_runtime_browser_cookies(config, resolved_data_dir)
    return RuntimeConfigValues(
        cookies_from_browser=cookies_from_browser,
        cookies_from_browser_display=cookies_from_browser_display,
        data_dir=resolved_data_dir,
    )


def resolve_runtime_browser_cookies(config: Config, data_dir: Path | None) -> tuple[str, str]:
    resolved_data_dir = resolve_runtime_data_dir(data_dir)
    if config.cookies_from_browser.mode is not BrowserCookiesMode.FIREFOX_DATA_DIR:
        value = config.configured_cookies_from_browser
        return value, value
    if resolved_data_dir is None:
        raise ValueError("cookies_from_browser mode firefox_data_dir requires --data-dir or DASHBOX_DATA_DIR")
    profile_dir = (resolved_data_dir / FIREFOX_DATA_DIR_PROFILE_DIRNAME).resolve()
    return f"firefox:{profile_dir}", "firefox:<data-dir>/firefox-profile"
