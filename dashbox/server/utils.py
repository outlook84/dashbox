from __future__ import annotations

import base64
import logging
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from .. import __version__
from .. import i18n
from ..config import Config
from ..media.ytdlp_client import ytdlp_version


logger = logging.getLogger("dashbox")


def json_response(value: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=value, status_code=status_code)


def base_url(config: Config, request: Request) -> str:
    if config.public_base_url:
        return config.public_base_url.rstrip("/")
    return str(request.base_url).rstrip("/")


def scoped_identity_key(key: str, base: str) -> str:
    scope = base.rstrip("/").lower().encode("utf-8")
    suffix = base64.urlsafe_b64encode(scope).decode("ascii").rstrip("=")
    return f"{key}_u{suffix}"


def set_tvbox_icon_base_url(base: str) -> None:
    from ..adapters import tvbox

    tvbox.set_icon_base_url(base)


def log_js_environment(state: Any) -> None:
    runtimes = sorted(state.service.ytdlp.js_runtimes)
    if runtimes:
        logger.info("yt-dlp JavaScript runtimes detected at startup: %s", ", ".join(runtimes))
    else:
        logger.info("yt-dlp JavaScript runtimes not found at startup")


def log_startup_versions(state: Any) -> None:
    version = ytdlp_version(state.service.ytdlp.yt_dlp) or "unknown"
    logger.info("dashbox version=%s yt-dlp version=%s", __version__, version)


def request_locale(request: Request) -> str:
    explicit = str(request.query_params.get("locale") or request.headers.get("x-dashbox-locale") or "").strip()
    if explicit:
        return i18n.normalize_locale(explicit)
    accept_language = str(request.headers.get("accept-language") or "")
    for part in accept_language.split(","):
        locale = part.split(";", 1)[0].strip()
        if i18n.normalize_locale(locale) == locale:
            return locale
    return i18n.DEFAULT_LOCALE
