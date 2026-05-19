from __future__ import annotations

import time
import uuid
from threading import RLock
from typing import Any
from urllib.parse import urljoin

from .dash import (
    DashSegment,
    DashSession,
    DashTrack,
    dash_track_metadata,
    estimate_dash_duration,
    require_complete_dash_tracks,
    same_dash_structure,
)
from .scope import PlaybackScope


class DashProxyStore:
    def __init__(self, idle_ttl_seconds: int = 21600, max_age_seconds: int | None = None) -> None:
        self.idle_ttl_seconds = idle_ttl_seconds
        self.max_age_seconds = max_age_seconds
        self._sessions: dict[str, DashSession] = {}
        self._lock = RLock()

    def create(
        self,
        info: dict[str, Any],
        formats: list[dict[str, Any]],
        raw_id: str = "",
        *,
        scope: PlaybackScope | None = None,
    ) -> DashSession:
        session = self.session_from_formats(info, formats, raw_id, uuid.uuid4().hex, scope=scope)
        with self._lock:
            self._prune_locked()
            self._sessions[session.token] = session
        return session

    def refresh(self, token: str, info: dict[str, Any], formats: list[dict[str, Any]]) -> DashSession | None:
        with self._lock:
            current = self._sessions.get(token)
            if not current:
                return None
            raw_id = current.raw_id
            scope = current.scope
        refreshed = self.session_from_formats(info, formats, raw_id, token, scope=scope)
        with self._lock:
            current = self._sessions.get(token)
            if not current or not self.same_structure(current, refreshed):
                return None
            refreshed.created_at = current.created_at
            self._sessions[token] = refreshed
            return refreshed

    def session_from_formats(
        self,
        info: dict[str, Any],
        formats: list[dict[str, Any]],
        raw_id: str,
        token: str,
        *,
        scope: PlaybackScope | None = None,
    ) -> DashSession:
        tracks = [track for fmt in formats if (track := self.track_from_format(fmt))]
        require_complete_dash_tracks(tracks, len(formats), "DASH proxy")
        now = time.time()
        session = DashSession(
            token=token,
            raw_id=raw_id,
            title=str(info.get("title") or token),
            duration=int(info.get("duration") or estimate_dash_duration(tracks) or 0),
            tracks=tracks,
            created_at=now,
            last_accessed_at=now,
            scope=scope,
        )
        return session

    def get(self, token: str, *, touch: bool = True) -> DashSession | None:
        with self._lock:
            self._prune_locked()
            session = self._sessions.get(token)
            if session and touch:
                session.last_accessed_at = time.time()
            return session

    def touch(self, token: str) -> None:
        with self._lock:
            session = self._sessions.get(token)
            if session:
                session.last_accessed_at = time.time()

    def prune(self) -> None:
        with self._lock:
            self._prune_locked()

    def _prune_locked(self) -> None:
        now = time.time()
        expired = [
            token
            for token, session in self._sessions.items()
            if now - session.last_accessed_at > self.idle_ttl_seconds
            or (self.max_age_seconds is not None and now - session.created_at > self.max_age_seconds)
        ]
        for token in expired:
            self._sessions.pop(token, None)

    @staticmethod
    def same_structure(left: DashSession, right: DashSession) -> bool:
        return same_dash_structure(left, right)

    @staticmethod
    def track_from_format(fmt: dict[str, Any]) -> DashTrack | None:
        fragments = resolve_fragments(fmt)
        if not fragments:
            return None
        metadata = dash_track_metadata(fmt)
        if not metadata:
            return None
        return DashTrack(**metadata, segments=fragments)


def resolve_fragments(fmt: dict[str, Any]) -> list[DashSegment]:
    raw = fmt.get("fragments")
    if not isinstance(raw, list):
        return []
    # yt-dlp's YouTube "dashy" fragments are byte ranges of a whole file
    # encoded as URL query parameters. They are downloader chunks, not DASH
    # media segments, and wrapping them in SegmentList produces a manifest
    # ExoPlayer accepts but cannot decode correctly.
    if fmt.get("protocol") == "http_dash_segments" and all(
        isinstance(item, dict) and isinstance(item.get("url"), str) and "range=" in item["url"]
        for item in raw[:3]
    ):
        return []
    base_url = str(fmt.get("fragment_base_url") or fmt.get("url") or "")
    segments: list[DashSegment] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if not url and item.get("path") and base_url:
            url = urljoin(base_url, str(item["path"]))
        if not isinstance(url, str) or not url:
            continue
        duration = item.get("duration")
        segments.append(DashSegment(url=url, duration=float(duration) if duration else None))
    return segments

