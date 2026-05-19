from __future__ import annotations

from typing import Any

from .formats import has_audio_format, has_video_format, is_audio_only_format
from .playback_policy import (
    best_audio_format,
    best_video_format_by_codec_policy,
    format_quality_key,
    formats_with_playback_policy,
)


def dash_candidate_sets(
    formats: list[dict[str, Any]],
    video_codec_order: tuple[str, ...] = (),
    audio_codec_order: tuple[str, ...] = (),
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> list[list[dict[str, Any]]]:
    allowed_formats = formats_with_playback_policy(
        formats,
        video_codec_order,
        audio_codec_order,
        max_video_height,
        max_video_fps,
    )
    candidates: list[list[dict[str, Any]]] = []
    seen: set[tuple[int, ...]] = set()

    def append(value: list[dict[str, Any]]) -> None:
        if not is_complete_dash_candidate_set(value):
            return
        key = tuple(id(fmt) for fmt in value)
        if key in seen:
            return
        seen.add(key)
        candidates.append(value)

    append(select_formats_by_video_codec_policy(
        allowed_formats,
        video_codec_order,
        audio_codec_order,
        max_video_height,
        max_video_fps,
    ))
    append(select_formats_by_generic_dash_policy(allowed_formats, audio_codec_order))
    append(complete_fragmented_candidate_set(allowed_formats))
    return candidates


def is_complete_dash_candidate_set(formats: list[dict[str, Any]]) -> bool:
    if len(formats) < 2:
        return False
    return any(has_video_format(fmt) for fmt in formats) and any(is_audio_only_format(fmt) for fmt in formats)


def complete_fragmented_candidate_set(formats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [
        fmt for fmt in formats
        if isinstance(fmt.get("fragments"), list) and fmt.get("fragments")
    ]
    return out if is_complete_dash_candidate_set(out) else []


def select_formats_by_video_codec_policy(
    formats: list[dict[str, Any]],
    video_codec_order: tuple[str, ...] = (),
    audio_codec_order: tuple[str, ...] = (),
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> list[dict[str, Any]]:
    if not formats or not video_codec_order:
        return []
    video = best_video_format_by_codec_policy(formats, video_codec_order, max_video_height, max_video_fps)
    if not video:
        return []
    if has_audio_format(video):
        return [video]
    audio = best_audio_format(formats, audio_codec_order)
    return [video, audio] if audio else [video]


def select_formats_by_generic_dash_policy(
    formats: list[dict[str, Any]],
    audio_codec_order: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    video = best_video_format_by_generic_quality(formats)
    if not video:
        return []
    if has_audio_format(video):
        return [video]
    audio = best_audio_format(formats, audio_codec_order)
    return [video, audio] if audio else [video]


def best_video_format_by_generic_quality(formats: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [
        fmt for fmt in formats
        if fmt.get("url")
        and has_video_format(fmt)
        and not has_audio_format(fmt)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda fmt: format_quality_key(fmt, ()))
