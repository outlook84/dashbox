from __future__ import annotations

from typing import Any

from .formats import has_audio_format, has_video_format
from .playback_candidates import is_single_url_playable_format
from .playback_policy import (
    best_format_by_video_codec_policy,
    formats_with_playback_policy,
    formats_with_video_caps,
    single_url_quality_key,
)


def select_hls_format(
    formats: list[dict[str, Any]],
    video_codec_order: tuple[str, ...] = (),
    max_video_height: int = 0,
    max_video_fps: int = 0,
    *,
    audio_codec_order: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    return select_single_url_format(
        formats,
        video_codec_order,
        max_video_height,
        max_video_fps,
        audio_codec_order=audio_codec_order,
        transport="hls",
    )


def select_progressive_format(
    formats: list[dict[str, Any]],
    video_codec_order: tuple[str, ...] = (),
    max_video_height: int = 0,
    max_video_fps: int = 0,
    *,
    audio_codec_order: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    return select_single_url_format(
        formats,
        video_codec_order,
        max_video_height,
        max_video_fps,
        audio_codec_order=audio_codec_order,
        transport="progressive",
    )


def select_single_url_format(
    formats: list[dict[str, Any]],
    video_codec_order: tuple[str, ...] = (),
    max_video_height: int = 0,
    max_video_fps: int = 0,
    *,
    audio_codec_order: tuple[str, ...] = (),
    transport: str | None = None,
) -> dict[str, Any] | None:
    candidates = [
        fmt for fmt in formats
        if fmt.get("url")
        and has_video_format(fmt)
        and has_audio_format(fmt)
        and is_single_url_playable_format(fmt, transport)
    ]
    capped_candidates = formats_with_video_caps(candidates, max_video_height, max_video_fps)
    if not capped_candidates:
        return None
    policy_candidates = formats_with_playback_policy(
        capped_candidates,
        video_codec_order,
        audio_codec_order,
    )
    if policy_candidates:
        best = max(
            policy_candidates,
            key=lambda fmt: single_url_quality_key(fmt, video_codec_order, audio_codec_order),
        )
        return best
    if audio_codec_order:
        return None
    best = best_format_by_video_codec_policy(
        capped_candidates,
        video_codec_order,
        max_video_height,
        max_video_fps,
    )
    if best:
        return best
    best = max(
        capped_candidates,
        key=lambda fmt: single_url_quality_key(fmt, video_codec_order, audio_codec_order),
    )
    return best
