from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class FailureState:
    count: int = 0
    blocked_until: float = 0.0


class FailureLimiter:
    def __init__(self, *, limit: int = 5, cooldown_seconds: int = 30) -> None:
        self.limit = limit
        self.cooldown_seconds = cooldown_seconds
        self._states: dict[str, FailureState] = {}

    def is_limited(self, key: str, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        state = self._states.get(key)
        if not state:
            return False
        if state.blocked_until <= current:
            if state.blocked_until:
                self._states.pop(key, None)
            return False
        return True

    def record_failure(self, key: str, now: float | None = None) -> bool:
        current = time.time() if now is None else now
        state = self._states.setdefault(key, FailureState())
        if state.blocked_until and state.blocked_until <= current:
            state.count = 0
            state.blocked_until = 0.0
        state.count += 1
        if state.count >= self.limit:
            state.blocked_until = current + self.cooldown_seconds
            return True
        return False

    def clear(self, key: str) -> None:
        self._states.pop(key, None)
