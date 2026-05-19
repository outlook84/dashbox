from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .formats import has_audio_format, has_video_format, is_audio_only_format
from .playback_policy import (
    has_unknown_codec_direct_url,
    is_known_media_format,
    is_unknown_media_format,
)

ROLE_DIRECT_URL = "direct_url"
ROLE_MANIFEST = "manifest"
ROLE_HLS_SINGLE_URL = "hls_single_url"
ROLE_PROGRESSIVE_SINGLE_URL = "progressive_single_url"
ROLE_DASH_TRACK = "dash_track"
ROLE_KNOWN_DIRECT_FALLBACK = "known_direct_fallback"
ROLE_UNKNOWN_DIRECT_FALLBACK = "unknown_direct_fallback"
ROLE_VIDEO_ONLY_DIRECT_FALLBACK = "video_only_direct_fallback"


@dataclass(frozen=True)
class PlaybackCandidate:
    fmt: dict[str, Any]
    roles: frozenset[str]


def is_playable_media_format(fmt: dict[str, Any]) -> bool:
    if not fmt.get("url") and not fmt.get("manifest_url"):
        return False
    if fmt.get("vcodec") == "images":
        return False
    if fmt.get("ext") == "mhtml":
        return False
    if fmt.get("protocol") == "mhtml":
        return False
    return (
        has_video_format(fmt)
        or has_audio_format(fmt)
        or bool(fmt.get("manifest_url"))
        or has_unknown_codec_direct_url(fmt)
    )


def playable_format_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [fmt for fmt in value if isinstance(fmt, dict) and is_playable_media_format(fmt)]


def playable_formats_from_info(info: dict[str, Any]) -> list[dict[str, Any]]:
    formats = playable_format_dicts(info.get("formats"))
    if not is_top_level_direct_playable_format(info):
        return formats
    top_level_key = playable_format_key(info)
    if any(playable_format_key(fmt) == top_level_key for fmt in formats):
        return formats
    return [info, *formats]


def is_top_level_direct_playable_format(info: dict[str, Any]) -> bool:
    return bool(info.get("url")) and not info.get("manifest_url") and is_playable_media_format(info)


def playable_format_key(fmt: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(fmt.get("url") or ""),
        str(fmt.get("manifest_url") or ""),
        str(fmt.get("format_id") or ""),
        str(fmt.get("protocol") or ""),
        str(fmt.get("ext") or ""),
    )


def playback_candidates(formats: list[dict[str, Any]]) -> list[PlaybackCandidate]:
    return [
        PlaybackCandidate(fmt=fmt, roles=format_roles(fmt))
        for fmt in formats
    ]


def candidate_formats_with_role(
    candidates: list[PlaybackCandidate],
    role: str,
) -> list[dict[str, Any]]:
    return [candidate.fmt for candidate in candidates if role in candidate.roles]


def format_roles(fmt: dict[str, Any]) -> frozenset[str]:
    roles: set[str] = set()
    if fmt.get("url"):
        roles.add(ROLE_DIRECT_URL)
        if is_dash_track_candidate(fmt):
            roles.add(ROLE_DASH_TRACK)
        if is_known_direct_fallback_candidate(fmt):
            roles.add(ROLE_KNOWN_DIRECT_FALLBACK)
        if is_unknown_direct_fallback_candidate(fmt):
            roles.add(ROLE_UNKNOWN_DIRECT_FALLBACK)
        if is_video_only_direct_fallback_candidate(fmt):
            roles.add(ROLE_VIDEO_ONLY_DIRECT_FALLBACK)
        if is_hls_single_url_candidate(fmt):
            roles.add(ROLE_HLS_SINGLE_URL)
        if is_progressive_single_url_candidate(fmt):
            roles.add(ROLE_PROGRESSIVE_SINGLE_URL)
    if fmt.get("manifest_url"):
        roles.add(ROLE_MANIFEST)
    return frozenset(roles)


def is_dash_track_candidate(fmt: dict[str, Any]) -> bool:
    return is_known_media_format(fmt)


def is_known_direct_fallback_candidate(fmt: dict[str, Any]) -> bool:
    return (
        is_known_media_format(fmt)
        and is_true_direct_media_format(fmt)
        and is_complete_direct_media_format(fmt)
    )


def is_unknown_direct_fallback_candidate(fmt: dict[str, Any]) -> bool:
    return (
        is_unknown_media_format(fmt)
        and is_true_direct_media_format(fmt)
        and is_complete_direct_media_format(fmt)
    )


def is_video_only_direct_fallback_candidate(fmt: dict[str, Any]) -> bool:
    return (
        is_known_media_format(fmt)
        and is_true_direct_media_format(fmt)
        and has_video_format(fmt)
        and not has_audio_format(fmt)
    )


def is_hls_single_url_candidate(fmt: dict[str, Any]) -> bool:
    return is_muxed_single_url_candidate(fmt, "hls")


def is_progressive_single_url_candidate(fmt: dict[str, Any]) -> bool:
    return is_muxed_single_url_candidate(fmt, "progressive")


def is_muxed_single_url_candidate(fmt: dict[str, Any], transport: str) -> bool:
    return (
        has_video_format(fmt)
        and has_audio_format(fmt)
        and is_single_url_playable_format(fmt, transport)
    )


def is_true_direct_media_format(fmt: dict[str, Any]) -> bool:
    if fmt.get("manifest_url"):
        return False
    if isinstance(fmt.get("fragments"), list) and fmt.get("fragments"):
        return False
    return fmt.get("protocol") not in ("http_dash_segments",)


def is_complete_direct_media_format(fmt: dict[str, Any]) -> bool:
    if is_audio_only_format(fmt):
        return True
    if not has_video_format(fmt) and not has_audio_format(fmt):
        return True
    return has_video_format(fmt) and has_audio_format(fmt)


def is_single_url_playable_format(fmt: dict[str, Any], transport: str | None = None) -> bool:
    protocol = fmt.get("protocol")
    is_hls = protocol in ("m3u8", "m3u8_native")
    if transport == "hls":
        return is_hls
    if is_hls:
        return transport is None
    if transport == "progressive" and protocol not in (None, "http", "https"):
        return False
    if fmt.get("manifest_url"):
        return False
    if isinstance(fmt.get("fragments"), list) and fmt.get("fragments"):
        return False
    return protocol in (None, "http", "https")
