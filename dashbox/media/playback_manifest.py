from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .playback_policy import format_within_video_caps, is_unknown_media_format
from .playback_result import PlaybackSelection, validated_headers


@dataclass(frozen=True)
class ManifestSelectionState:
    info: dict[str, Any]
    allowed_formats: list[dict[str, Any]]
    all_formats: list[dict[str, Any]]

    @property
    def top_level_url(self) -> str:
        manifest_url = self.info.get("manifest_url")
        return manifest_url if isinstance(manifest_url, str) else ""

    @property
    def is_top_level_only(self) -> bool:
        return bool(self.top_level_url) and not self.all_formats

    def related_formats(self, manifest_url: str) -> list[dict[str, Any]]:
        return [
            fmt for fmt in self.all_formats
            if fmt.get("manifest_url") == manifest_url
        ]

    def allowed_related_formats(self, manifest_url: str) -> list[dict[str, Any]]:
        return [
            fmt for fmt in self.allowed_formats
            if fmt.get("manifest_url") == manifest_url
        ]

    def url_allowed_by_playback_policy(self, manifest_url: str) -> bool:
        if self.is_top_level_only and manifest_url == self.top_level_url:
            return True
        related_formats = self.related_formats(manifest_url)
        if not related_formats:
            return False
        return len(self.allowed_related_formats(manifest_url)) == len(related_formats)


@dataclass(frozen=True)
class ManifestCandidate:
    manifest_url: str
    raw_format: dict[str, Any] | None = None


def select_manifest(
    state: ManifestSelectionState,
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> ManifestCandidate | None:
    return select_manifest_matching(state, max_video_height, max_video_fps)


def select_unknown_manifest(
    state: ManifestSelectionState,
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> ManifestCandidate | None:
    return select_manifest_matching(
        state,
        max_video_height,
        max_video_fps,
        predicate=lambda fmt: is_unknown_media_format(fmt) and format_within_video_caps(fmt, max_video_height, max_video_fps),
    )


def select_manifest_matching(
    state: ManifestSelectionState,
    max_video_height: int = 0,
    max_video_fps: int = 0,
    *,
    predicate: Callable[[dict[str, Any]], bool] | None = None,
) -> ManifestCandidate | None:
    manifest_url = state.top_level_url
    if (
        max_video_height <= 0
        and max_video_fps <= 0
        and manifest_url
        and state.url_allowed_by_playback_policy(manifest_url)
    ):
        return ManifestCandidate(manifest_url=manifest_url)
    for fmt in reversed(state.allowed_formats):
        manifest_url = fmt.get("manifest_url")
        if (
            isinstance(manifest_url, str)
            and manifest_url
            and (predicate is None or predicate(fmt))
            and state.url_allowed_by_playback_policy(manifest_url)
            and manifest_url_within_video_caps(
                manifest_url,
                state.all_formats,
                max_video_height,
                max_video_fps,
            )
        ):
            return ManifestCandidate(manifest_url=manifest_url, raw_format=fmt)
    return None


def manifest_result_from_candidate(
    state: ManifestSelectionState,
    candidate: ManifestCandidate | None,
) -> PlaybackSelection | None:
    if candidate is None:
        return None
    if candidate.raw_format is None:
        return top_level_manifest_result(state.info, candidate.manifest_url)
    return format_manifest_result(candidate.raw_format, candidate.manifest_url)


def top_level_manifest_result(info: dict[str, Any], manifest_url: str) -> PlaybackSelection:
    return PlaybackSelection(
        url=manifest_url,
        transport="manifest",
        format="manifest",
        headers=validated_headers(info.get("http_headers")),
    )


def format_manifest_result(fmt: dict[str, Any], manifest_url: str) -> PlaybackSelection:
    return PlaybackSelection(
        url=manifest_url,
        transport="manifest",
        format=str(fmt.get("protocol") or "manifest"),
        headers=validated_headers(fmt.get("http_headers")),
        raw_format=dict(fmt),
    )


def manifest_url_within_video_caps(
    manifest_url: str,
    formats: list[dict[str, Any]],
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> bool:
    if max_video_height <= 0 and max_video_fps <= 0:
        return True
    related = [fmt for fmt in formats if fmt.get("manifest_url") == manifest_url]
    if not related:
        return False
    return all(format_within_video_caps(fmt, max_video_height, max_video_fps) for fmt in related)
