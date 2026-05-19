from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class CooldownDecision:
    allowed: bool
    remaining_seconds: float = 0.0
    reason: str = ""


class CooldownLimiter:
    def __init__(
        self,
        *,
        short_window_seconds: int = 5,
        long_window_seconds: int = 300,
        long_limit: int = 10,
    ) -> None:
        self.short_window_seconds = short_window_seconds
        self.long_window_seconds = long_window_seconds
        self.long_limit = long_limit
        self._hits: dict[str, deque[float]] = {}

    def try_acquire(self, key: str, now: float | None = None) -> CooldownDecision:
        current = time.time() if now is None else now
        self.clear_expired(current)
        hits = self._hits.setdefault(key, deque())
        self._prune_hits(hits, current)

        if hits and current - hits[-1] < self.short_window_seconds:
            return CooldownDecision(
                allowed=False,
                remaining_seconds=self.short_window_seconds - (current - hits[-1]),
                reason="short_window",
            )
        if len(hits) >= self.long_limit:
            return CooldownDecision(
                allowed=False,
                remaining_seconds=self.long_window_seconds - (current - hits[0]),
                reason="long_window",
            )
        hits.append(current)
        return CooldownDecision(allowed=True)

    def clear_expired(self, now: float | None = None) -> None:
        current = time.time() if now is None else now
        expired = []
        for key, hits in self._hits.items():
            self._prune_hits(hits, current)
            if not hits:
                expired.append(key)
        for key in expired:
            self._hits.pop(key, None)

    def _prune_hits(self, hits: deque[float], current: float) -> None:
        while hits and current - hits[0] >= self.long_window_seconds:
            hits.popleft()
