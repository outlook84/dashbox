from __future__ import annotations

import base64
import re
from typing import Any

from ..media import danmaku
from ..media.scope import PlaybackScope
from .auth import media_token_from_headers, session_id_from_manifest_url
from .state import AppState
from ..sites import youtube_subtitles


def localize_kodi_data_manifest(value: dict[str, Any], sub_id: str, base: str, state: AppState) -> None:
    url = str(value.get("url") or "")
    if not url.lower().startswith("data:application/dash+xml"):
        return
    try:
        header, payload = url.split(",", 1)
    except ValueError:
        return
    if ";base64" not in header.lower():
        return
    try:
        content = base64.b64decode(payload).decode("utf-8")
    except Exception:
        return
    session = state.inline_manifest_store.create(
        content,
        "application/dash+xml; charset=utf-8",
        scope=PlaybackScope(protocol="kodi", sub_id=sub_id),
    )
    value["url"] = f"{base.rstrip('/')}/media/{session.token}/manifest.mpd"


def attach_kodi_danmaku_subtitle(value: dict[str, Any], playback_preferences: Any | None = None) -> None:
    if not kodi_danmaku_enabled(playback_preferences):
        return
    subtitle = danmaku.kodi_danmaku_subtitle(
        str(value.get("danmaku") or value.get("danmaku_url") or ""),
        font_size=kodi_danmaku_font_size(playback_preferences),
    )
    if not subtitle:
        return
    subtitles = value.get("subtitles")
    if not isinstance(subtitles, list):
        subtitles = []
    if any(isinstance(item, dict) and item.get("url") == subtitle["url"] for item in subtitles):
        return
    value["subtitles"] = [*subtitles, subtitle]


def wrap_kodi_subtitle_urls(value: dict[str, Any], base: str) -> None:
    subtitles = value.get("subtitles")
    if not isinstance(subtitles, list):
        return
    for item in subtitles:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "")
        if not youtube_subtitles.is_subtitle_redirect_target(url) or not subtitle_url_needs_filename_wrapper(url):
            continue
        filename = kodi_subtitle_filename(item, url)
        if not filename:
            continue
        item["url"] = subtitle_redirect_url(base, filename, url)


def subtitle_url_needs_filename_wrapper(url: str) -> bool:
    from urllib.parse import urlsplit

    try:
        path = urlsplit(url).path
    except ValueError:
        return False
    filename = path.rsplit("/", 1)[-1]
    if not filename:
        return True
    return "." not in filename


def kodi_subtitle_filename(item: dict[str, Any], url: str) -> str:
    from urllib.parse import parse_qsl, urlsplit

    language = safe_subtitle_filename_part(str(item.get("language") or item.get("name") or "subtitle"))
    ext = safe_subtitle_filename_part(str(item.get("format") or "")).lower()
    if not ext:
        try:
            params = parse_qsl(urlsplit(url).query, keep_blank_values=True)
        except ValueError:
            params = []
        for key, value in params:
            if key.lower() in {"fmt", "format"}:
                candidate = safe_subtitle_filename_part(value).lower()
                if candidate:
                    ext = candidate
                    break
    if not ext:
        ext = "srt"
    if ext.startswith("."):
        ext = ext[1:]
    if not ext:
        ext = "srt"
    return f"{language or 'subtitle'}.{ext}"


def safe_subtitle_filename_part(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    cleaned = cleaned.strip(".-")
    return cleaned[:80]


def subtitle_redirect_url(base: str, filename: str, url: str) -> str:
    from urllib.parse import quote, urlencode

    return f"{base.rstrip('/')}/subtitle/{quote(filename)}?{urlencode({'url': url})}"


def kodi_danmaku_enabled(playback_preferences: Any | None) -> bool:
    if not isinstance(playback_preferences, dict):
        return True
    value = playback_preferences.get("danmaku_enabled")
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"false", "0", "no", "off"}
    return bool(value)


def kodi_danmaku_font_size(playback_preferences: Any | None) -> int:
    if not isinstance(playback_preferences, dict):
        return danmaku.DEFAULT_FONT_SIZE
    try:
        value = int(playback_preferences.get("danmaku_font_size") or 0)
    except (TypeError, ValueError):
        return danmaku.DEFAULT_FONT_SIZE
    if 8 <= value <= 200:
        return value
    return danmaku.DEFAULT_FONT_SIZE


def sync_inputstream_headers(value: dict[str, Any], state: AppState | None = None) -> None:
    inputstream = value.get("inputstream")
    if not isinstance(inputstream, dict):
        return
    headers = value.get("headers")
    if isinstance(headers, dict):
        inputstream["manifest_headers"] = dict(headers)
    session_id = session_id_from_manifest_url(str(value.get("url") or ""))
    session = state.dash_store.get(session_id, touch=False) if state is not None and session_id else None
    if session is None:
        if not isinstance(inputstream.get("stream_headers"), dict):
            inputstream["stream_headers"] = {}
        return
    token = media_token_from_headers(headers)
    if not token:
        return
    stream_headers = inputstream.get("stream_headers")
    if not isinstance(stream_headers, dict):
        stream_headers = {}
    stream_headers = {
        key: header_value
        for key, header_value in stream_headers.items()
        if key.lower() != "x-media-token"
    }
    inputstream["stream_headers"] = {**stream_headers, "X-Media-Token": token}
