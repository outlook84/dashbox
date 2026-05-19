from __future__ import annotations

from dataclasses import dataclass
import html
from typing import Any

from .formats import has_video_format, media_content_type, mime_from_ext
from .scope import PlaybackScope


@dataclass
class DashSegment:
    url: str
    duration: float | None = None


@dataclass
class DashTrack:
    id: str
    content_type: str
    mime_type: str
    codecs: str
    bandwidth: int
    segments: list[DashSegment]
    width: int | None = None
    height: int | None = None
    fps: int | None = None
    audio_sampling_rate: int | None = None
    headers: dict[str, str] | None = None


@dataclass
class DashSegmentBaseTrack:
    id: str
    content_type: str
    mime_type: str
    codecs: str
    bandwidth: int
    url: str
    init_range: str
    index_range: str
    width: int | None = None
    height: int | None = None
    fps: int | None = None
    audio_sampling_rate: int | None = None
    headers: dict[str, str] | None = None


@dataclass
class DashSession:
    token: str
    raw_id: str
    title: str
    duration: int
    tracks: list[DashTrack]
    created_at: float
    last_accessed_at: float
    scope: PlaybackScope | None = None


def dash_track_metadata(fmt: dict[str, Any]) -> dict[str, Any] | None:
    content_type = media_content_type(fmt)
    if not content_type:
        return None
    vcodec = fmt.get("vcodec")
    acodec = fmt.get("acodec")
    mime_type = str(fmt.get("mime_type") or mime_from_ext(fmt.get("ext"), has_video_format(fmt)))
    codecs = str(vcodec if has_video_format(fmt) else acodec or "")
    bandwidth = int(float(fmt.get("tbr") or fmt.get("abr") or fmt.get("vbr") or 0) * 1000)
    if bandwidth <= 0:
        bandwidth = 1
    return {
        "id": str(fmt.get("format_id") or content_type),
        "content_type": content_type,
        "mime_type": mime_type,
        "codecs": codecs,
        "bandwidth": bandwidth,
        "width": int(fmt["width"]) if fmt.get("width") else None,
        "height": int(fmt["height"]) if fmt.get("height") else None,
        "fps": int(float(fmt["fps"])) if fmt.get("fps") else None,
        "audio_sampling_rate": int(fmt["asr"]) if fmt.get("asr") else None,
        "headers": fmt.get("http_headers") if isinstance(fmt.get("http_headers"), dict) else None,
    }


def require_complete_dash_tracks(tracks: list[Any], expected_count: int, label: str) -> None:
    if len(tracks) != expected_count:
        raise ValueError(f"{label} needs every selected DASH track")
    if len(tracks) < 2:
        raise ValueError(f"{label} needs at least two DASH tracks")
    if not any(track.content_type == "video" for track in tracks):
        raise ValueError(f"{label} needs at least one video track")
    if not any(track.content_type == "audio" for track in tracks):
        raise ValueError(f"{label} needs at least one audio track")


def same_dash_structure(left: DashSession, right: DashSession) -> bool:
    if len(left.tracks) != len(right.tracks):
        return False
    for left_track, right_track in zip(left.tracks, right.tracks):
        if (
            left_track.content_type != right_track.content_type
            or left_track.mime_type != right_track.mime_type
            or left_track.codecs != right_track.codecs
            or len(left_track.segments) != len(right_track.segments)
        ):
            return False
    return True


def estimate_dash_duration(tracks: list[DashTrack]) -> int:
    durations = [
        sum(segment.duration or 0 for segment in track.segments)
        for track in tracks
        if any(segment.duration for segment in track.segments)
    ]
    return int(max(durations)) if durations else 0


def build_mpd(session: DashSession, base_url: str) -> str:
    period_duration = f"PT{max(session.duration, 0)}S"
    adaptation_sets = "\n".join(build_adaptation_set(session, idx, track) for idx, track in enumerate(session.tracks))
    return (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        "<MPD xmlns='urn:mpeg:dash:schema:mpd:2011' type='static' "
        f"mediaPresentationDuration='{period_duration}' minBufferTime='PT1.5S' "
        "profiles='urn:mpeg:dash:profile:isoff-main:2011'>\n"
        f"<BaseURL>{html.escape(base_url.rstrip('/') + '/')}</BaseURL>\n"
        f"<Period duration='{period_duration}' start='PT0S'>\n"
        f"{adaptation_sets}\n"
        "</Period>\n"
        "</MPD>\n"
    )


def build_adaptation_set(session: DashSession, track_index: int, track: DashTrack) -> str:
    attrs = [
        f"id='{html.escape(track.id)}'",
        f"bandwidth='{track.bandwidth}'",
        f"codecs='{html.escape(track.codecs)}'",
        f"mimeType='{html.escape(track.mime_type)}'",
    ]
    if track.width:
        attrs.append(f"width='{track.width}'")
    if track.height:
        attrs.append(f"height='{track.height}'")
    if track.fps:
        attrs.append(f"frameRate='{track.fps}'")
    if track.audio_sampling_rate:
        attrs.append(f"audioSamplingRate='{track.audio_sampling_rate}'")
    media_start = 1 if len(track.segments) > 1 and track.segments[0].duration is None else 0
    initialization = f"<Initialization sourceURL='{session.token}/{track_index}/0'/>\n" if media_start else ""
    segments = "\n".join(
        f"<SegmentURL media='{session.token}/{track_index}/{segment_index}'/>"
        for segment_index in range(media_start, len(track.segments))
    )
    duration = default_segment_duration(track)
    duration_attr = f" duration='{duration}'" if duration else ""
    return (
        f"<AdaptationSet contentType='{track.content_type}' segmentAlignment='true'>\n"
        f"<Representation {' '.join(attrs)}>\n"
        f"<SegmentList timescale='1000'{duration_attr}>\n"
        f"{initialization}"
        f"{segments}\n"
        "</SegmentList>\n"
        "</Representation>\n"
        "</AdaptationSet>"
    )


def default_segment_duration(track: DashTrack) -> int:
    durations = [segment.duration for segment in track.segments if segment.duration]
    if not durations:
        return 0
    return max(1, int((sum(durations) / len(durations)) * 1000))
