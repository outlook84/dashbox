from __future__ import annotations

import asyncio
import base64
import html
import logging
import struct
from collections.abc import Callable
from typing import Any

from ..config import DEFAULT_USER_AGENT
from ..utils.errors import exception_reason
from ..sites import registry
from .dash import DashSegmentBaseTrack, dash_track_metadata, require_complete_dash_tracks
from .formats import has_video_format, is_audio_only_format
from .playback_result import PlaybackSelection

SEGMENT_BASE_PROBE_BYTES = 2 * 1024 * 1024
logger = logging.getLogger("dashbox.media")


class SegmentBaseProber:
    def __init__(
        self,
        http_client_provider: Callable[[], Any] | None = None,
        semaphore: asyncio.Semaphore | None = None,
        max_bytes: int = SEGMENT_BASE_PROBE_BYTES,
        user_agent: str = DEFAULT_USER_AGENT,
        upstream_timeout: int | float = 15.0,
    ) -> None:
        self.http_client_provider = http_client_provider
        self.semaphore = semaphore or asyncio.Semaphore(4)
        self.max_bytes = max_bytes
        self.user_agent = user_agent
        self.upstream_timeout = upstream_timeout

    async def probe_ranges(self, fmt: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, str]:
        if fmt.get("ext") not in ("mp4", "m4a", "webm") and fmt.get("container") not in ("mp4_dash", "m4a_dash", "webm_dash"):
            return {}
        url = fmt.get("url")
        if not isinstance(url, str) or not url:
            return {}
        probe_headers = dict(headers or headers_from_format(fmt))
        probe_headers.setdefault("User-Agent", self.user_agent)
        data = await self.fetch_initial_bytes(url, probe_headers, self.max_bytes)
        if not data:
            return {}
        if fmt.get("ext") == "webm" or fmt.get("container") == "webm_dash":
            return probe_webm_segment_base_ranges(data)
        return probe_mp4_segment_base_ranges(data)

    async def fetch_initial_bytes(self, url: str, headers: dict[str, str], size: int) -> bytes:
        request_headers = dict(headers)
        request_headers["Range"] = f"bytes=0-{size - 1}"
        data = await self._fetch_initial_bytes_once(url, request_headers, size)
        if data:
            return data
        ranged_url = with_query_param(url, "range", f"0-{size - 1}")
        return await self._fetch_initial_bytes_once(ranged_url, headers, size)

    async def _fetch_initial_bytes_once(self, url: str, headers: dict[str, str], size: int) -> bytes:
        try:
            async with self.semaphore:
                if self.http_client_provider is not None:
                    client = self.http_client_provider()
                    return await self._fetch_with_client(client, url, headers, size)
                import httpx

                async with httpx.AsyncClient(
                    timeout=self.upstream_timeout,
                    follow_redirects=True,
                    headers={"User-Agent": self.user_agent},
                ) as client:
                    return await self._fetch_with_client(client, url, headers, size)
        except Exception as exc:
            logger.debug("segment base probe failed url=%s reason=%s", url, exception_reason(exc))
            return b""

    async def _fetch_with_client(self, client: Any, url: str, headers: dict[str, str], size: int) -> bytes:
        async with client.stream("GET", url, headers=headers) as response:
            if response.status_code not in (200, 206):
                return b""
            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                if not chunk:
                    continue
                remaining = size - len(chunks)
                if remaining <= 0:
                    break
                chunks += chunk[:remaining]
                if len(chunks) >= size:
                    break
            return bytes(chunks)


async def select_segment_base_dash(
    info: dict[str, Any],
    dash_candidates: list[list[dict[str, Any]]],
    *,
    probe: bool,
    prober: SegmentBaseProber | None = None,
) -> PlaybackSelection | None:
    for candidates in dash_candidates:
        try:
            user_agent = prober.user_agent if prober is not None else DEFAULT_USER_AGENT
            mpd = await build_mpd_async(info, candidates, prober=prober) if probe else build_mpd(info, candidates)
            return PlaybackSelection(
                url="data:application/dash+xml;base64," + mpd,
                transport="dash",
                format="dash",
                headers=headers_for_formats(info, candidates, user_agent=user_agent),
                debug_selection=dash_candidate_debug_summary(candidates),
            )
        except ValueError:
            pass
    return None


async def build_mpd_async(info: dict[str, Any], formats: list[dict[str, Any]], *, prober: SegmentBaseProber | None = None) -> str:
    user_agent = prober.user_agent if prober is not None else DEFAULT_USER_AGENT
    tracks = await segment_base_tracks_from_formats_async(
        formats,
        prober=prober,
        info=info,
        user_agent=user_agent,
    )
    return build_mpd_from_tracks(info, tracks)


def build_mpd(info: dict[str, Any], formats: list[dict[str, Any]]) -> str:
    tracks = segment_base_tracks_from_formats(formats)
    return build_mpd_from_tracks(info, tracks)


def build_mpd_from_tracks(info: dict[str, Any], tracks: list[DashSegmentBaseTrack]) -> str:
    duration = int(info.get("duration") or 0)
    sets = [build_segment_base_adaptation_set(track) for track in tracks]
    xml = (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<MPD xmlns='urn:mpeg:dash:schema:mpd:2011' type='static' "
        f"mediaPresentationDuration='PT{duration}S' minBufferTime='PT1.5S' "
        "profiles='urn:mpeg:dash:profile:isoff-on-demand:2011'>"
        f"<Period duration='PT{duration}S' start='PT0S'>"
        + "".join(sets)
        + "</Period></MPD>"
    )
    return base64.b64encode(xml.encode("utf-8")).decode("ascii")


def segment_base_tracks_from_formats(formats: list[dict[str, Any]]) -> list[DashSegmentBaseTrack]:
    tracks = [track for fmt in formats if (track := segment_base_track_from_format(fmt))]
    require_complete_dash_tracks(tracks, len(formats), "SegmentBase MPD")
    return tracks


async def segment_base_tracks_from_formats_async(
    formats: list[dict[str, Any]],
    *,
    prober: SegmentBaseProber | None = None,
    info: dict[str, Any] | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> list[DashSegmentBaseTrack]:
    tracks = await asyncio.gather(
        *(segment_base_track_from_format_async(fmt, prober=prober, info=info, user_agent=user_agent) for fmt in formats)
    )
    complete_tracks = [track for track in tracks if track]
    require_complete_dash_tracks(complete_tracks, len(formats), "SegmentBase MPD")
    return complete_tracks


def segment_base_track_from_format(fmt: dict[str, Any]) -> DashSegmentBaseTrack | None:
    url = fmt.get("url")
    if not isinstance(url, str) or not url:
        return None
    metadata = dash_track_metadata(fmt)
    if not metadata:
        return None
    init_range = fmt.get("init_range") or {}
    index_range = fmt.get("index_range") or {}
    init = range_text(init_range)
    index = range_text(index_range)
    if not init or not index:
        return None
    return DashSegmentBaseTrack(**metadata, url=url, init_range=init, index_range=index)


async def segment_base_track_from_format_async(
    fmt: dict[str, Any],
    *,
    prober: SegmentBaseProber | None = None,
    info: dict[str, Any] | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> DashSegmentBaseTrack | None:
    url = fmt.get("url")
    if not isinstance(url, str) or not url:
        return None
    metadata = dash_track_metadata(fmt)
    if not metadata:
        return None
    init_range = fmt.get("init_range") or {}
    index_range = fmt.get("index_range") or {}
    init = range_text(init_range)
    index = range_text(index_range)
    if (not init or not index) and prober is not None:
        init, index = await probe_missing_segment_ranges(
            fmt,
            prober=prober,
            info=info,
            user_agent=user_agent,
        )
    if not init or not index:
        return None
    return DashSegmentBaseTrack(**metadata, url=url, init_range=init, index_range=index)


async def probe_missing_segment_ranges(
    fmt: dict[str, Any],
    *,
    prober: SegmentBaseProber,
    info: dict[str, Any] | None = None,
    user_agent: str = DEFAULT_USER_AGENT,
) -> tuple[str, str]:
    headers = headers_for_format(info or {}, fmt, user_agent=user_agent)
    ranges = await prober.probe_ranges(fmt, headers)
    return ranges.get("init", ""), ranges.get("index", "")


def build_segment_base_adaptation_set(track: DashSegmentBaseTrack) -> str:
    attrs = []
    if track.width:
        attrs.append(f"width='{track.width}'")
    if track.height:
        attrs.append(f"height='{track.height}'")
    if track.fps:
        attrs.append(f"frameRate='{track.fps}'")
    if track.audio_sampling_rate:
        attrs.append(f"audioSamplingRate='{track.audio_sampling_rate}'")
    return (
        "<AdaptationSet>"
        f"<ContentComponent contentType='{track.content_type}'/>"
        f"<Representation id='{html.escape(track.id)}' "
        f"bandwidth='{track.bandwidth}' "
        f"codecs='{html.escape(track.codecs)}' mimeType='{html.escape(track.mime_type)}' {' '.join(attrs)}>"
        f"<BaseURL>{html.escape(track.url)}</BaseURL>"
        f"<SegmentBase indexRange='{track.index_range}'><Initialization range='{track.init_range}'/></SegmentBase>"
        "</Representation></AdaptationSet>"
    )


def probe_mp4_segment_base_ranges(data: bytes) -> dict[str, str]:
    boxes = parse_mp4_boxes(data)
    if not boxes:
        return {}
    init_end = -1
    index_range = ""
    for box_type, start, end in boxes:
        if box_type in ("ftyp", "moov"):
            init_end = max(init_end, end - 1)
        if box_type == "sidx" and not index_range:
            index_range = f"{start}-{end - 1}"
    if init_end < 0 or not index_range:
        return {}
    return {"init": f"0-{init_end}", "index": index_range}


def probe_webm_segment_base_ranges(data: bytes) -> dict[str, str]:
    if len(data) < 4 or struct.unpack(">I", data[0:4])[0] != 0x1A45DFA3:
        return {}
    header_size_length, first_header_size_value = webm_decode_vint(data[4])
    header_size_end = 4 + header_size_length
    if header_size_end > len(data):
        return {}
    header_size_bytes = bytearray([first_header_size_value])
    header_size_bytes += data[5:header_size_end]
    header_size = int.from_bytes(header_size_bytes, byteorder="big", signed=False)
    offset = header_size_end + header_size
    while offset < len(data):
        element_id_length, _element_id_value = webm_decode_vint(data[offset])
        element_id = int.from_bytes(data[offset:offset + element_id_length], byteorder="big", signed=False)
        size_offset = offset + element_id_length
        if size_offset >= len(data):
            return {}
        size_length, first_size_value = webm_decode_vint(data[size_offset])
        size_end = size_offset + size_length
        if size_end > len(data):
            return {}
        size_bytes = bytearray([first_size_value])
        size_bytes += data[size_offset + 1:size_end]
        element_size = int.from_bytes(size_bytes, byteorder="big", signed=False)
        if element_id == 0x1C53BB6B:
            index_end = offset + element_id_length + size_length + element_size - 1
            return {
                "init": f"0-{offset - 1}",
                "index": f"{offset}-{index_end}",
            }
        if element_id == 0x18538067:
            offset += element_id_length + size_length
        else:
            offset += element_id_length + size_length + element_size
    return {}


def webm_decode_vint(byte: int) -> tuple[int, int]:
    if byte >= 128:
        return 1, byte & 0b01111111
    if byte >= 64:
        return 2, byte & 0b00111111
    if byte >= 32:
        return 3, byte & 0b00011111
    if byte >= 16:
        return 4, byte & 0b00001111
    if byte >= 8:
        return 5, byte & 0b00000111
    if byte >= 4:
        return 6, byte & 0b00000011
    if byte >= 2:
        return 7, byte & 0b00000001
    return 8, 0


def range_text(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    start = value.get("start")
    end = value.get("end")
    if start is None or end is None:
        return ""
    return f"{int(start)}-{int(end)}"


def dash_candidate_debug_summary(candidates: list[dict[str, Any]]) -> str:
    video = [format_debug_summary(fmt) for fmt in candidates if has_video_format(fmt)]
    audio = [format_debug_summary(fmt) for fmt in candidates if is_audio_only_format(fmt)]
    parts = []
    if video:
        parts.append("video=[" + "; ".join(video) + "]")
    if audio:
        parts.append("audio=[" + "; ".join(audio) + "]")
    return " ".join(parts) if parts else "?"


def format_debug_summary(fmt: dict[str, Any]) -> str:
    video_codec = str(fmt.get("vcodec") or "").strip()
    audio_codec = str(fmt.get("acodec") or "").strip()
    codec = video_codec if video_codec and video_codec != "none" else audio_codec
    height = video_height(fmt)
    width = fmt.get("width")
    resolution = f"{width}x{height}" if width and height else (f"{height}p" if height else "?")
    format_id = fmt.get("format_id") or fmt.get("format") or fmt.get("format_note") or fmt.get("format")
    transport = fmt.get("protocol") or fmt.get("ext") or fmt.get("format") or ""
    return "format_id={} codec={} resolution={} transport={}".format(
        format_id or "?",
        codec or "?",
        resolution,
        transport or "?",
    )


def video_height(fmt: dict[str, Any]) -> int | None:
    value = fmt.get("height")
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def headers_for_formats(
    info: dict[str, Any],
    formats: list[dict[str, Any]],
    *,
    user_agent: str = DEFAULT_USER_AGENT,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    for source in [info.get("http_headers"), *(fmt.get("http_headers") for fmt in formats)]:
        if isinstance(source, dict):
            for key, value in source.items():
                if isinstance(key, str) and isinstance(value, str):
                    headers[key] = value
    urls = [str(fmt.get("url") or "") for fmt in formats]
    for key, value in registry.headers_for_format_urls(urls).items():
        headers.setdefault(key, value)
    headers.setdefault("User-Agent", user_agent)
    return headers


def headers_for_format(
    info: dict[str, Any],
    fmt: dict[str, Any],
    *,
    user_agent: str = DEFAULT_USER_AGENT,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    for source in (info.get("http_headers"), fmt.get("http_headers")):
        if isinstance(source, dict):
            for key, value in source.items():
                if isinstance(key, str) and isinstance(value, str):
                    headers[key] = value
    url = fmt.get("url")
    urls = [url] if isinstance(url, str) else []
    for key, value in registry.headers_for_format_urls(urls).items():
        headers.setdefault(key, value)
    headers.setdefault("User-Agent", user_agent)
    return headers


def headers_from_format(fmt: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    source = fmt.get("http_headers")
    if isinstance(source, dict):
        for key, value in source.items():
            if isinstance(key, str) and isinstance(value, str):
                headers[key] = value
    return headers


def parse_mp4_boxes(data: bytes) -> list[tuple[str, int, int]]:
    boxes: list[tuple[str, int, int]] = []
    offset = 0
    length = len(data)
    while offset + 8 <= length:
        size = int.from_bytes(data[offset:offset + 4], "big")
        box_type = data[offset + 4:offset + 8].decode("ascii", errors="ignore")
        header = 8
        if size == 1:
            if offset + 16 > length:
                break
            size = int.from_bytes(data[offset + 8:offset + 16], "big")
            header = 16
        elif size == 0:
            size = length - offset
        if size < header or offset + size > length:
            break
        boxes.append((box_type, offset, offset + size))
        offset += size
    return boxes


def with_query_param(url: str, key: str, value: str) -> str:
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query[key] = value
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
