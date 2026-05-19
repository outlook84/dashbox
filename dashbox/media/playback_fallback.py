from __future__ import annotations

from dataclasses import replace
from typing import Any

from .formats import has_video_format
from .playback_candidates import (
    is_complete_direct_media_format,
    is_playable_media_format,
    is_true_direct_media_format,
)
from .playback_catalog import PlaybackFormats
from .playback_manifest import ManifestSelectionState, manifest_result_from_candidate, select_unknown_manifest
from .playback_policy import (
    best_audio_format,
    best_format_by_video_codec_policy,
    format_within_video_caps,
    formats_with_video_caps,
    is_unknown_media_format,
)
from .playback_result import PlaybackSelection, playback_selection_from_format

ALLOW_UNKNOWN_MEDIA_METADATA_FALLBACK = True


def select_unknown_media_fallback(
    info: dict[str, Any],
    playback_formats: PlaybackFormats,
    video_codec_order: tuple[str, ...] = (),
    audio_codec_order: tuple[str, ...] = (),
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> PlaybackSelection | None:
    if not ALLOW_UNKNOWN_MEDIA_METADATA_FALLBACK:
        return None
    manifest_state = ManifestSelectionState(
        info=info,
        allowed_formats=playback_formats.manifest_formats(),
        all_formats=playback_formats.all_manifest_formats(),
    )
    manifest_candidate = select_unknown_manifest(
        manifest_state,
        max_video_height,
        max_video_fps,
    )
    manifest = manifest_result_from_candidate(manifest_state, manifest_candidate)
    if manifest:
        return replace(manifest, debug_source="unknown_manifest_fallback")
    selected = select_unknown_direct_url(
        playback_formats.direct_fallback_formats(known=False),
        max_video_height,
        max_video_fps,
    )
    if not selected:
        return None
    return playback_selection_from_format(
        selected,
        transport="single_url",
        debug_source="unknown_direct_fallback",
    )


def select_known_media_fallback(
    playback_formats: PlaybackFormats,
    video_codec_order: tuple[str, ...] = (),
    audio_codec_order: tuple[str, ...] = (),
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> PlaybackSelection | None:
    fallback_formats = playback_formats.direct_fallback_formats(known=True)
    if not fallback_formats:
        return None
    best = select_fallback_format_by_playback_policy(
        fallback_formats,
        video_codec_order,
        audio_codec_order,
        max_video_height,
        max_video_fps,
    )
    return playback_selection_from_format(
        best,
        transport="single_url",
        debug_source="fallback_format",
    )


def select_video_only_direct_fallback(
    playback_formats: PlaybackFormats,
    video_codec_order: tuple[str, ...] = (),
    audio_codec_order: tuple[str, ...] = (),
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> PlaybackSelection | None:
    fallback_formats = playback_formats.video_only_direct_fallback_formats()
    if not fallback_formats:
        return None
    best = select_fallback_format_by_playback_policy(
        fallback_formats,
        video_codec_order,
        audio_codec_order,
        max_video_height,
        max_video_fps,
    )
    return playback_selection_from_format(
        best,
        transport="single_url",
        debug_source="video_only_direct_fallback",
    )


def select_fallback_format_by_playback_policy(
    fallback_formats: list[dict[str, Any]],
    video_codec_order: tuple[str, ...] = (),
    audio_codec_order: tuple[str, ...] = (),
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> dict[str, Any]:
    allowed_fallback_formats = formats_with_video_caps(
        fallback_formats,
        max_video_height,
        max_video_fps,
    )
    audio = best_audio_format(fallback_formats, audio_codec_order) if not any(has_video_format(fmt) for fmt in fallback_formats) else None
    if not allowed_fallback_formats and audio:
        return audio
    if not allowed_fallback_formats:
        raise ValueError("no playable format found within video caps")
    return (
        best_format_by_video_codec_policy(fallback_formats, video_codec_order, max_video_height, max_video_fps)
        or best_format_by_video_codec_policy(allowed_fallback_formats, video_codec_order, max_video_height, max_video_fps)
        or audio
        or allowed_fallback_formats[-1]
    )


def select_unknown_direct_url(
    formats: list[dict[str, Any]],
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> dict[str, Any] | None:
    for fmt in reversed(formats):
        url = fmt.get("url")
        if (
            isinstance(url, str)
            and url
            and is_playable_media_format(fmt)
            and is_unknown_media_format(fmt)
            and is_true_direct_media_format(fmt)
            and is_complete_direct_media_format(fmt)
            and format_within_video_caps(fmt, max_video_height, max_video_fps)
        ):
            return fmt
    return None
