from __future__ import annotations

from functools import cached_property
from typing import Any

from .playback_candidates import (
    ROLE_DASH_TRACK,
    ROLE_HLS_SINGLE_URL,
    ROLE_KNOWN_DIRECT_FALLBACK,
    ROLE_MANIFEST,
    ROLE_PROGRESSIVE_SINGLE_URL,
    ROLE_UNKNOWN_DIRECT_FALLBACK,
    ROLE_VIDEO_ONLY_DIRECT_FALLBACK,
    candidate_formats_with_role,
    playable_formats_from_info,
    playback_candidates,
)
from .playback_policy import (
    formats_with_playback_policy,
    formats_with_video_caps,
    known_media_formats,
    normalize_video_codec,
)


class PlaybackFormats:
    def __init__(
        self,
        info: dict[str, Any],
        video_codec_order: tuple[str, ...],
        audio_codec_order: tuple[str, ...],
        max_video_height: int,
        max_video_fps: int,
    ) -> None:
        self.video_codec_order = video_codec_order
        self.audio_codec_order = audio_codec_order
        self.max_video_height = max_video_height
        self.max_video_fps = max_video_fps
        self.formats = playable_formats_from_info(info)
        self.format_candidates = playback_candidates(self.formats)

    @cached_property
    def _merged_manifest_formats(self) -> list[dict[str, Any]]:
        return candidate_formats_with_role(self.format_candidates, ROLE_MANIFEST)

    def single_url_formats(self, transport: str) -> list[dict[str, Any]]:
        role_by_transport = {
            "hls": ROLE_HLS_SINGLE_URL,
            "progressive": ROLE_PROGRESSIVE_SINGLE_URL,
        }
        role = role_by_transport.get(transport)
        if role is None:
            return []
        return formats_with_video_caps(
            self.known_allowed_formats_with_role(role),
            self.max_video_height,
            self.max_video_fps,
        )

    def manifest_formats(self, *, known_only: bool = False) -> list[dict[str, Any]]:
        formats = formats_with_video_caps(
            self._merged_manifest_formats,
            self.max_video_height,
            self.max_video_fps,
        )
        if known_only:
            formats = known_media_formats(
                formats,
                self.max_video_height,
                self.max_video_fps,
            )
        return self.allowed_formats(formats)

    def all_manifest_formats(self) -> list[dict[str, Any]]:
        return self._merged_manifest_formats

    def dash_track_formats(self) -> list[dict[str, Any]]:
        return self.known_allowed_formats_with_role(ROLE_DASH_TRACK)

    def direct_fallback_formats(self, *, known: bool) -> list[dict[str, Any]]:
        role = ROLE_KNOWN_DIRECT_FALLBACK if known else ROLE_UNKNOWN_DIRECT_FALLBACK
        fallback_formats = candidate_formats_with_role(
            self.format_candidates,
            role,
        )
        if known:
            fallback_formats = known_media_formats(
                fallback_formats,
                self.max_video_height,
                self.max_video_fps,
            )
        return self.allowed_formats(fallback_formats)

    def video_only_direct_fallback_formats(self) -> list[dict[str, Any]]:
        fallback_formats = candidate_formats_with_role(
            self.format_candidates,
            ROLE_VIDEO_ONLY_DIRECT_FALLBACK,
        )
        return [
            fmt for fmt in known_media_formats(
                fallback_formats,
                self.max_video_height,
                self.max_video_fps,
            )
            if self._known_video_codec_allowed(fmt)
        ]

    def _known_video_codec_allowed(self, fmt: dict[str, Any]) -> bool:
        if not self.video_codec_order:
            return True
        codec = normalize_video_codec(fmt.get("vcodec"))
        return not codec or codec in self.video_codec_order

    def known_allowed_formats_with_role(self, role: str) -> list[dict[str, Any]]:
        return self.allowed_formats(
            known_media_formats(
                candidate_formats_with_role(self.format_candidates, role),
                self.max_video_height,
                self.max_video_fps,
            )
        )

    def allowed_formats(self, formats: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return formats_with_playback_policy(
            formats,
            self.video_codec_order,
            self.audio_codec_order,
            self.max_video_height,
            self.max_video_fps,
        )
