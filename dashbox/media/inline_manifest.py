from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from threading import RLock

from .scope import PlaybackScope


@dataclass
class InlineManifestSession:
    token: str
    content: str
    media_type: str
    created_at: float
    last_accessed_at: float
    scope: PlaybackScope | None = None


class InlineManifestStore:
    def __init__(self, idle_ttl_seconds: int = 21600, max_age_seconds: int | None = None) -> None:
        self.idle_ttl_seconds = idle_ttl_seconds
        self.max_age_seconds = max_age_seconds
        self._sessions: dict[str, InlineManifestSession] = {}
        self._lock = RLock()

    def create(self, content: str, media_type: str, *, scope: PlaybackScope | None = None) -> InlineManifestSession:
        now = time.time()
        session = InlineManifestSession(
            token=uuid.uuid4().hex,
            content=content,
            media_type=media_type,
            created_at=now,
            last_accessed_at=now,
            scope=scope,
        )
        with self._lock:
            self._prune_locked()
            self._sessions[session.token] = session
        return session

    def get(self, token: str, *, touch: bool = True) -> InlineManifestSession | None:
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
