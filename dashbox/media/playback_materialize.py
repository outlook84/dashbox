from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from .playback_result import PlaybackSelection, format_debug_summary, playback_selection_from_format
from .segment_base import SegmentBaseProber, select_segment_base_dash

logger = logging.getLogger("dashbox.media")


def materialize_single_url(selected: dict[str, Any]) -> PlaybackSelection:
    selection = playback_selection_from_format(
        selected,
        transport="single_url",
        debug_source="single_url",
    )
    logger.debug("playback path=single_url selected=%s", format_debug_summary(selection.raw_format))
    return selection


async def materialize_direct_dash(
    info: dict[str, Any],
    dash_candidates: list[list[dict[str, Any]]],
    manifest: PlaybackSelection | None,
    prober: SegmentBaseProber | None = None,
) -> PlaybackSelection | None:
    return await materialize_segment_base_dash_with_manifest_fallback(
        info,
        dash_candidates,
        manifest,
        prober,
        source="segment_base_dash_direct",
        manifest_source="dash_manifest_direct",
    )


async def materialize_standard_dash(
    info: dict[str, Any],
    dash_candidates: list[list[dict[str, Any]]],
    manifest: PlaybackSelection | None,
    prober: SegmentBaseProber | None = None,
) -> PlaybackSelection | None:
    return await materialize_segment_base_dash_with_manifest_fallback(
        info,
        dash_candidates,
        manifest,
        prober,
        source="segment_base_dash",
        manifest_source="dash_manifest",
    )


async def materialize_segment_base_dash_with_manifest_fallback(
    info: dict[str, Any],
    dash_candidates: list[list[dict[str, Any]]],
    manifest: PlaybackSelection | None,
    prober: SegmentBaseProber | None,
    *,
    source: str,
    manifest_source: str,
) -> PlaybackSelection | None:
    selected = await materialize_segment_base_dash(
        info,
        dash_candidates,
        prober,
        source=source,
        probe=True,
    )
    if selected:
        return selected
    if manifest:
        selection = replace(manifest, debug_source=manifest_source)
        logger.debug("playback path=%s selected=%s", manifest_source, format_debug_summary(selection.raw_format))
        return selection
    return await materialize_segment_base_dash(
        info,
        dash_candidates,
        prober,
        source=source,
        probe=False,
    )


async def materialize_segment_base_dash(
    info: dict[str, Any],
    dash_candidates: list[list[dict[str, Any]]],
    prober: SegmentBaseProber | None,
    *,
    source: str,
    probe: bool,
) -> PlaybackSelection | None:
    selected = await select_segment_base_dash(info, dash_candidates, probe=probe, prober=prober)
    if not selected:
        return None
    selected = replace(selected, debug_source=source)
    logger.debug(
        "playback path=%s probe=%s selected=%s",
        source,
        str(probe).lower(),
        selected.debug_selection,
    )
    return selected
