from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..utils.dicts import compact_dict
from .playback_policy import video_height


@dataclass(frozen=True)
class Sub:
    name: str
    url: str
    ext: str = ""
    format: str = ""

    def to_dict(self) -> dict[str, Any]:
        return compact_dict(name=self.name, url=self.url, ext=self.ext, format=self.format)


@dataclass(frozen=True)
class PlaybackSelection:
    url: str
    transport: str
    format: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    debug_source: str = ""
    debug_selection: str = ""
    raw_format: dict[str, Any] = field(default_factory=dict)


def playback_selection_from_format(fmt: dict[str, Any], *, transport: str, debug_source: str = "") -> PlaybackSelection:
    url = fmt.get("url")
    if not isinstance(url, str) or not url:
        raise ValueError("playback format has no url")
    return PlaybackSelection(
        url=url,
        transport=transport,
        format=str(fmt.get("protocol") or fmt.get("ext") or transport),
        headers=validated_headers(fmt.get("http_headers")),
        debug_source=debug_source,
        raw_format=dict(fmt),
    )


def format_debug_summary(fmt: dict[str, Any]) -> str:
    video_codec = str(fmt.get("vcodec") or "").strip()
    audio_codec = str(fmt.get("acodec") or "").strip()
    codec = video_codec if video_codec and video_codec != "none" else audio_codec
    height = video_height(fmt)
    width = fmt.get("width")
    resolution = f"{width}x{height}" if width and height else (f"{height}p" if height else "?")
    format_id = fmt.get("format_id") or fmt.get("format") or fmt.get("format_note") or fmt.get("format")
    transport = fmt.get("protocol") or fmt.get("ext") or fmt.get("format") or ""
    return "format_id={} codec={} resolution={} transport={}".format(
        format_id or "?",
        codec or "?",
        resolution,
        transport or "?",
    )


def validated_headers(value: Any) -> dict[str, str]:
    headers: dict[str, str] = {}
    if isinstance(value, dict):
        for key, header_value in value.items():
            if isinstance(key, str) and isinstance(header_value, str):
                headers[key] = header_value
    return headers


def headers_from_info(info: dict[str, Any], selected: PlaybackSelection) -> dict[str, str]:
    headers: dict[str, str] = {}
    for source in (validated_headers(info.get("http_headers")), selected.headers):
        headers.update(source)
    return headers


def subtitles_from_info(info: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    subtitles = info.get("subtitles") or {}
    if not isinstance(subtitles, dict):
        return out
    for lang, items in subtitles.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            out.append(Sub(name=str(lang), url=str(item["url"]), ext=str(item.get("ext") or "")).to_dict())
            break
    return out
