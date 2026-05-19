from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any

from .dash_proxy import DashProxyStore
from .playback_candidates import playable_formats_from_info
from .playback_catalog import PlaybackFormats
from .playback_dash_selection import dash_candidate_sets
from .playback_materialize import (
    materialize_direct_dash,
    materialize_standard_dash,
)
from .playback_selection_candidates import iter_playback_candidate_selections
from .playback_result import PlaybackSelection, format_debug_summary
from .playback_transport import candidate_transport_order_for_scope, should_proxy_dash_media_url
from .scope import PlaybackScope
from .segment_base import SegmentBaseProber, dash_candidate_debug_summary

logger = logging.getLogger("dashbox.media")

DEFAULT_SEGMENT_BASE_PROBER = object()


@dataclass(frozen=True)
class PlaybackContext:
    candidate_transport_order: tuple[str, ...]
    proxy_dash_media_url: bool
    video_codec_order: tuple[str, ...]
    audio_codec_order: tuple[str, ...]
    max_video_height: int
    max_video_fps: int
    dash_store_present: bool


class PlaybackSelector:
    def __init__(
        self,
        dash_store: DashProxyStore | None = None,
        segment_base_prober: SegmentBaseProber | None | object = DEFAULT_SEGMENT_BASE_PROBER,
    ) -> None:
        self.dash_store = dash_store
        if segment_base_prober is DEFAULT_SEGMENT_BASE_PROBER:
            self.segment_base_prober = SegmentBaseProber()
        else:
            self.segment_base_prober = segment_base_prober

    async def select_playable(
        self,
        info: dict[str, Any],
        base_url: str = "",
        raw_id: str = "",
        scope: PlaybackScope | None = None,
    ) -> PlaybackSelection:
        context = self.playback_context(scope)
        playback_formats = PlaybackFormats(
            info,
            context.video_codec_order,
            context.audio_codec_order,
            context.max_video_height,
            context.max_video_fps,
        )
        dash_candidates = dash_candidate_sets(
            playback_formats.dash_track_formats(),
            context.video_codec_order,
            context.audio_codec_order,
            context.max_video_height,
            context.max_video_fps,
        )
        for candidate in iter_playback_candidate_selections(
            info,
            playback_formats,
            dash_candidates,
            context.candidate_transport_order,
            lambda candidate_sets, manifest: self.materialize_dash_candidate(
                info,
                candidate_sets,
                manifest,
                base_url,
                raw_id,
                scope,
                context,
            ),
            context.video_codec_order,
            context.audio_codec_order,
            context.max_video_height,
            context.max_video_fps,
        ):
            selected = await candidate.materialize()
            if selected:
                if candidate.debug_reason in {"known_direct_fallback", "unknown_direct_fallback"}:
                    logger.debug(
                        "playback path=%s selected=%s",
                        selected.debug_source or candidate.debug_reason,
                        format_debug_summary(selected.raw_format),
                    )
                return selected
        raise ValueError("no playable format found")

    def playback_context(self, scope: PlaybackScope | None) -> PlaybackContext:
        return PlaybackContext(
            candidate_transport_order=candidate_transport_order_for_scope(scope),
            proxy_dash_media_url=should_proxy_dash_media_url(scope),
            video_codec_order=scope.video_codec_order if scope else (),
            audio_codec_order=scope.audio_codec_order if scope else (),
            max_video_height=scope.max_video_height if scope else 0,
            max_video_fps=scope.max_video_fps if scope else 0,
            dash_store_present=self.dash_store is not None,
        )

    async def materialize_dash_candidate(
        self,
        info: dict[str, Any],
        dash_candidates: list[list[dict[str, Any]]],
        manifest: PlaybackSelection | None,
        base_url: str,
        raw_id: str,
        scope: PlaybackScope | None,
        context: PlaybackContext,
    ) -> PlaybackSelection | None:
        if not context.proxy_dash_media_url:
            selected = await materialize_direct_dash(info, dash_candidates, manifest, self.segment_base_prober)
            if selected:
                return selected
        if context.dash_store_present and base_url:
            local_dash = self.select_local_dash(info, dash_candidates, base_url, raw_id, scope)
            if local_dash:
                local_dash = replace(local_dash, debug_source="dash_proxy")
                logger.debug("playback path=dash_proxy selected=%s", local_dash.debug_selection)
                return local_dash
        return await materialize_standard_dash(info, dash_candidates, manifest, self.segment_base_prober)

    def select_local_dash(
        self,
        info: dict[str, Any],
        dash_candidates: list[list[dict[str, Any]]],
        base_url: str,
        raw_id: str,
        scope: PlaybackScope | None,
    ) -> PlaybackSelection | None:
        if not self.dash_store:
            return None
        for candidates in dash_candidates:
            try:
                session = self.dash_store.create(info, candidates, raw_id, scope=scope)
                return PlaybackSelection(
                    url=f"{base_url.rstrip('/')}/media/{session.token}/manifest.mpd",
                    transport="dash",
                    format="dash",
                    debug_selection=dash_candidate_debug_summary(candidates),
                )
            except ValueError:
                pass
        return None


def dash_candidate_sets_from_info(
    info: dict[str, Any],
    scope: PlaybackScope | None = None,
) -> list[list[dict[str, Any]]]:
    video_codec_order = scope.video_codec_order if scope else ()
    audio_codec_order = scope.audio_codec_order if scope else ()
    max_video_height = scope.max_video_height if scope else 0
    max_video_fps = scope.max_video_fps if scope else 0
    playback_formats = PlaybackFormats(
        info,
        video_codec_order,
        audio_codec_order,
        max_video_height,
        max_video_fps,
    )
    return dash_candidate_sets(
        playback_formats.dash_track_formats(),
        video_codec_order,
        audio_codec_order,
        max_video_height,
        max_video_fps,
    )


def has_playable_media(info: dict[str, Any]) -> bool:
    return bool(playable_formats_from_info(info))
