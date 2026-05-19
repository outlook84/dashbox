from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Awaitable
from typing import Any, Callable, Iterator

from .formats import has_audio_format, has_video_format, is_audio_only_format
from .playback_catalog import PlaybackFormats
from .playback_fallback import (
    select_known_media_fallback,
    select_unknown_media_fallback,
    select_video_only_direct_fallback,
)
from .playback_manifest import (
    ManifestSelectionState,
    ManifestCandidate,
    manifest_result_from_candidate,
    select_manifest,
)
from .playback_materialize import materialize_single_url
from .playback_policy import playback_format_policy_key
from .playback_result import PlaybackSelection
from .playback_single_url import select_hls_format, select_progressive_format
from .playback_transport import candidate_transport_score

PRIMARY_BUCKET = 2
KNOWN_FALLBACK_BUCKET = 1
UNKNOWN_FALLBACK_BUCKET = 0
VIDEO_ONLY_FALLBACK_BUCKET = -1

QualityKey = tuple[int, float, int, int, int, float, int, str]
DashMaterializer = Callable[[list[list[dict[str, Any]]], PlaybackSelection | None], Awaitable[PlaybackSelection | None]]
SelectionMaterializer = Callable[[], Awaitable[PlaybackSelection | None]]


@dataclass(frozen=True)
class PlaybackCandidateSelection:
    candidate_transport: str
    quality_key: QualityKey
    debug_reason: str
    priority_bucket: int
    _materialize: SelectionMaterializer | None = None

    async def materialize(self) -> PlaybackSelection | None:
        if self._materialize is None:
            return None
        return await self._materialize()


def iter_playback_candidate_selections(
    info: dict[str, Any],
    playback_formats: PlaybackFormats,
    dash_candidate_sets: list[list[dict[str, Any]]],
    candidate_transport_order: tuple[str, ...],
    materialize_dash: DashMaterializer,
    video_codec_order: tuple[str, ...] = (),
    audio_codec_order: tuple[str, ...] = (),
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> Iterator[PlaybackCandidateSelection]:
    candidates = [
        *single_url_candidates(
            playback_formats,
            video_codec_order,
            audio_codec_order,
            max_video_height,
            max_video_fps,
        ),
        *dash_candidates(
            info,
            playback_formats,
            dash_candidate_sets,
            materialize_dash,
            video_codec_order,
            audio_codec_order,
            max_video_height,
            max_video_fps,
        ),
        *fallback_candidates(
            info,
            playback_formats,
            video_codec_order,
            audio_codec_order,
            max_video_height,
            max_video_fps,
        ),
    ]
    yield from sorted(
        candidates,
        key=lambda candidate: playback_candidate_sort_key(candidate, candidate_transport_order),
        reverse=True,
    )


def single_url_candidates(
    playback_formats: PlaybackFormats,
    video_codec_order: tuple[str, ...] = (),
    audio_codec_order: tuple[str, ...] = (),
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> list[PlaybackCandidateSelection]:
    candidates: list[PlaybackCandidateSelection] = []
    hls = select_hls_format(
        playback_formats.single_url_formats("hls"),
        video_codec_order,
        max_video_height,
        max_video_fps,
        audio_codec_order=audio_codec_order,
    )
    if hls:
        candidates.append(
            PlaybackCandidateSelection(
                candidate_transport="hls",
                quality_key=playback_format_policy_key(hls, video_codec_order, audio_codec_order),
                debug_reason="hls_single_url",
                priority_bucket=PRIMARY_BUCKET,
                _materialize=lambda hls=hls: async_materialize_single_url(hls),
            )
        )

    progressive = select_progressive_format(
        playback_formats.single_url_formats("progressive"),
        video_codec_order,
        max_video_height,
        max_video_fps,
        audio_codec_order=audio_codec_order,
    )
    if progressive:
        candidates.append(
            PlaybackCandidateSelection(
                candidate_transport="progressive",
                quality_key=playback_format_policy_key(progressive, video_codec_order, audio_codec_order),
                debug_reason="progressive_single_url",
                priority_bucket=PRIMARY_BUCKET,
                _materialize=lambda progressive=progressive: async_materialize_single_url(progressive),
            )
        )
    return candidates


def dash_candidates(
    info: dict[str, Any],
    playback_formats: PlaybackFormats,
    dash_candidate_sets: list[list[dict[str, Any]]],
    materialize_dash: DashMaterializer,
    video_codec_order: tuple[str, ...] = (),
    audio_codec_order: tuple[str, ...] = (),
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> list[PlaybackCandidateSelection]:
    all_manifest_formats = playback_formats.all_manifest_formats()
    manifest_state = ManifestSelectionState(
        info=info,
        allowed_formats=playback_formats.manifest_formats(known_only=True),
        all_formats=all_manifest_formats,
    )
    manifest_candidate = select_manifest(
        manifest_state,
        max_video_height,
        max_video_fps,
    )
    if not dash_candidate_sets and not manifest_candidate:
        return []
    representative = dash_candidate_representative(
        dash_candidate_sets,
        manifest_candidate,
        video_codec_order,
        audio_codec_order,
    )
    return [
        PlaybackCandidateSelection(
            candidate_transport="dash",
            quality_key=playback_format_policy_key(representative or {}, video_codec_order, audio_codec_order),
            debug_reason="dash",
            priority_bucket=PRIMARY_BUCKET,
            _materialize=lambda dash_candidate_sets=dash_candidate_sets, manifest_candidate=manifest_candidate: materialize_dash(
                dash_candidate_sets,
                manifest_result_from_candidate(manifest_state, manifest_candidate),
            ),
        )
    ]


def fallback_candidates(
    info: dict[str, Any],
    playback_formats: PlaybackFormats,
    video_codec_order: tuple[str, ...] = (),
    audio_codec_order: tuple[str, ...] = (),
    max_video_height: int = 0,
    max_video_fps: int = 0,
) -> list[PlaybackCandidateSelection]:
    return [
        PlaybackCandidateSelection(
            candidate_transport="known_fallback",
            quality_key=playback_format_policy_key({}, video_codec_order, audio_codec_order),
            debug_reason="known_direct_fallback",
            priority_bucket=KNOWN_FALLBACK_BUCKET,
            _materialize=lambda: async_select_known_media_fallback(
                playback_formats,
                video_codec_order,
                audio_codec_order,
                max_video_height,
                max_video_fps,
            ),
        ),
        PlaybackCandidateSelection(
            candidate_transport="unknown_fallback",
            quality_key=playback_format_policy_key({}, video_codec_order, audio_codec_order),
            debug_reason="unknown_direct_fallback",
            priority_bucket=UNKNOWN_FALLBACK_BUCKET,
            _materialize=lambda: async_select_unknown_media_fallback(
                info,
                playback_formats,
                video_codec_order,
                audio_codec_order,
                max_video_height,
                max_video_fps,
            ),
        ),
        PlaybackCandidateSelection(
            candidate_transport="video_only_fallback",
            quality_key=playback_format_policy_key({}, video_codec_order, audio_codec_order),
            debug_reason="video_only_direct_fallback",
            priority_bucket=VIDEO_ONLY_FALLBACK_BUCKET,
            _materialize=lambda: async_select_video_only_direct_fallback(
                playback_formats,
                video_codec_order,
                audio_codec_order,
                max_video_height,
                max_video_fps,
            ),
        ),
    ]


def playback_candidate_sort_key(
    candidate: PlaybackCandidateSelection,
    candidate_transport_order: tuple[str, ...],
) -> tuple[int, int, float, int, int, int, int, str]:
    quality = candidate.quality_key
    return (
        candidate.priority_bucket,
        quality[0],
        quality[1],
        quality[2],
        quality[3],
        quality[4],
        candidate_transport_score(candidate.candidate_transport, candidate_transport_order),
        quality[7],
    )


async def async_materialize_single_url(selected: dict[str, Any]) -> PlaybackSelection:
    return materialize_single_url(selected)


async def async_select_known_media_fallback(
    playback_formats: PlaybackFormats,
    video_codec_order: tuple[str, ...],
    audio_codec_order: tuple[str, ...],
    max_video_height: int,
    max_video_fps: int,
) -> PlaybackSelection | None:
    return select_known_media_fallback(
        playback_formats,
        video_codec_order,
        audio_codec_order,
        max_video_height,
        max_video_fps,
    )


async def async_select_unknown_media_fallback(
    info: dict[str, Any],
    playback_formats: PlaybackFormats,
    video_codec_order: tuple[str, ...],
    audio_codec_order: tuple[str, ...],
    max_video_height: int,
    max_video_fps: int,
) -> PlaybackSelection | None:
    return select_unknown_media_fallback(
        info,
        playback_formats,
        video_codec_order,
        audio_codec_order,
        max_video_height,
        max_video_fps,
    )


async def async_select_video_only_direct_fallback(
    playback_formats: PlaybackFormats,
    video_codec_order: tuple[str, ...],
    audio_codec_order: tuple[str, ...],
    max_video_height: int,
    max_video_fps: int,
) -> PlaybackSelection | None:
    return select_video_only_direct_fallback(
        playback_formats,
        video_codec_order,
        audio_codec_order,
        max_video_height,
        max_video_fps,
    )


def dash_candidate_representative(
    dash_candidate_sets: list[list[dict[str, Any]]],
    manifest_candidate: ManifestCandidate | None,
    video_codec_order: tuple[str, ...] = (),
    audio_codec_order: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    representative_candidates = [
        merged_dash_candidate_representative(candidate_set, video_codec_order, audio_codec_order)
        for candidate_set in dash_candidate_sets
    ]
    representative_candidates = [fmt for fmt in representative_candidates if fmt]
    if representative_candidates:
        return max(
            representative_candidates,
            key=lambda fmt: playback_format_policy_key(fmt, video_codec_order, audio_codec_order),
        )
    return manifest_candidate.raw_format if manifest_candidate else None


def merged_dash_candidate_representative(
    candidate_set: list[dict[str, Any]],
    video_codec_order: tuple[str, ...] = (),
    audio_codec_order: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    video_formats = [fmt for fmt in candidate_set if has_video_format(fmt)]
    audio_formats = [fmt for fmt in candidate_set if is_audio_only_format(fmt)]
    if not video_formats:
        return max(
            audio_formats,
            key=lambda fmt: playback_format_policy_key(fmt, video_codec_order, audio_codec_order),
            default=None,
        )
    video = max(
        video_formats,
        key=lambda fmt: playback_format_policy_key(fmt, video_codec_order, audio_codec_order),
    )
    if has_audio_format(video):
        return video
    audio = max(
        audio_formats,
        key=lambda fmt: playback_format_policy_key(fmt, video_codec_order, audio_codec_order),
        default=None,
    )
    if not audio:
        return video
    merged = dict(video)
    merged["acodec"] = audio.get("acodec")
    merged["abr"] = audio.get("abr")
    merged["asr"] = audio.get("asr")
    merged["audio_format_id"] = audio.get("format_id")
    merged["tbr"] = float(video.get("tbr") or video.get("vbr") or 0) + float(audio.get("abr") or audio.get("tbr") or 0)
    return merged
