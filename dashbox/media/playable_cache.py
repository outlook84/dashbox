from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event, Lock
from typing import Any


logger = logging.getLogger("dashbox.playable_cache")

PLAYABLE_INFO_CACHE_TTL_SECONDS = 300
PLAYABLE_INFO_NEGATIVE_CACHE_TTL_SECONDS = 10
PLAYABLE_INFO_CACHE_PRUNE_THRESHOLD = 512
PLAYABLE_INFO_CACHE_DEFAULT_WAIT_TIMEOUT_SECONDS = 60.0


@dataclass
class _CacheItem:
    expires_at: float
    value: dict[str, Any] | None = None
    error: BaseException | None = None


class PlayableInfoCache:
    def __init__(
        self,
        ttl_seconds: float = PLAYABLE_INFO_CACHE_TTL_SECONDS,
        negative_ttl_seconds: float = PLAYABLE_INFO_NEGATIVE_CACHE_TTL_SECONDS,
        prune_threshold: int = PLAYABLE_INFO_CACHE_PRUNE_THRESHOLD,
        wait_timeout: float = PLAYABLE_INFO_CACHE_DEFAULT_WAIT_TIMEOUT_SECONDS,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.negative_ttl_seconds = negative_ttl_seconds
        self.prune_threshold = prune_threshold
        self.wait_timeout = wait_timeout
        self._items: dict[str, _CacheItem] = {}
        self._inflight: dict[str, Event] = {}
        self._lock = Lock()

    def get_or_create(
        self,
        key: str,
        loader: Callable[[], dict[str, Any]],
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        while True:
            with self._lock:
                now = time.monotonic()
                if force_refresh:
                    self._items.pop(key, None)
                else:
                    cached = self._items.get(key)
                    if cached and cached.expires_at > now:
                        if cached.error is not None:
                            raise cached.error
                        if cached.value is not None:
                            return cached.value
                    if cached:
                        self._items.pop(key, None)

                event = self._inflight.get(key)
                if event is None:
                    event = Event()
                    self._inflight[key] = event
                    break

            wait_started_at = time.monotonic()
            signaled = event.wait(timeout=self.wait_timeout)
            elapsed = time.monotonic() - wait_started_at
            if not signaled:
                logger.warning(
                    "playable cache follower timed out waiting key=%s elapsed=%.1fs timeout=%.1fs",
                    key,
                    elapsed,
                    self.wait_timeout,
                )
                raise TimeoutError(f"playable extraction is still running after {self.wait_timeout:.0f}s")
            if elapsed >= 10.0:
                logger.info("playable cache follower waited key=%s elapsed=%.1fs", key, elapsed)
            force_refresh = False

        try:
            value = loader()
        except Exception as exc:
            with self._lock:
                if self.negative_ttl_seconds > 0:
                    self._items[key] = _CacheItem(time.monotonic() + self.negative_ttl_seconds, error=exc)
                    self._prune_locked(time.monotonic())
                self._finish_inflight_locked(key, event)
            raise

        with self._lock:
            self._items[key] = _CacheItem(time.monotonic() + self.ttl_seconds, value=value)
            self._prune_locked(time.monotonic())
            self._finish_inflight_locked(key, event)
        return value

    def get_fresh(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            now = time.monotonic()
            cached = self._items.get(key)
            if not cached:
                return None
            if cached.expires_at <= now:
                self._items.pop(key, None)
                return None
            if cached.error is not None:
                raise cached.error
            return cached.value

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)

    def _finish_inflight_locked(self, key: str, event: Event) -> None:
        if self._inflight.get(key) is event:
            self._inflight.pop(key, None)
        event.set()

    def _prune_locked(self, now: float) -> None:
        if len(self._items) < self.prune_threshold:
            return
        expired = [key for key, item in self._items.items() if item.expires_at <= now]
        for key in expired:
            self._items.pop(key, None)
        while len(self._items) >= self.prune_threshold and self._items:
            oldest_key = min(self._items, key=lambda item_key: self._items[item_key].expires_at)
            self._items.pop(oldest_key, None)
