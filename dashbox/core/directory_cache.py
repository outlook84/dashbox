from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")

DIRECTORY_SNAPSHOT_CACHE_TTL_SECONDS = 300
DIRECTORY_SNAPSHOT_CACHE_PRUNE_THRESHOLD = 512


@dataclass(frozen=True)
class CachedDirectory(Generic[T]):
    value: T
    expires_at: float


class DirectorySnapshotCache(Generic[T]):
    def __init__(
        self,
        *,
        ttl_seconds: int = DIRECTORY_SNAPSHOT_CACHE_TTL_SECONDS,
        prune_threshold: int = DIRECTORY_SNAPSHOT_CACHE_PRUNE_THRESHOLD,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.prune_threshold = prune_threshold
        self._items: OrderedDict[str, CachedDirectory[T]] = OrderedDict()
        self._tasks: dict[str, asyncio.Task[T]] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(
        self,
        key: str,
        loader: Callable[[], Awaitable[T]],
    ) -> T:
        async with self._lock:
            cached = self._fresh_locked(key, time.monotonic())
            if cached is not None:
                return cached.value
        return await self.reload(key, loader)

    async def reload(
        self,
        key: str,
        loader: Callable[[], Awaitable[T]],
    ) -> T:
        async with self._lock:
            task = self._tasks.get(key)
            if task is None:
                task = asyncio.create_task(loader())
                self._tasks[key] = task
                task.add_done_callback(lambda done, cache_key=key: self._finish_task(cache_key, done))
        value = await asyncio.shield(task)
        await self.store(key, value)
        return value

    async def fresh(self, key: str) -> T | None:
        async with self._lock:
            cached = self._fresh_locked(key, time.monotonic())
            return cached.value if cached is not None else None

    async def store(self, key: str, value: T) -> None:
        async with self._lock:
            self._items[key] = CachedDirectory(
                value=value,
                expires_at=time.monotonic() + self.ttl_seconds,
            )
            self._items.move_to_end(key)
            self.prune_locked(time.monotonic())

    def _fresh_locked(self, key: str, now: float) -> CachedDirectory[T] | None:
        cached = self._items.get(key)
        if cached is None:
            return None
        if cached.expires_at <= now:
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        return cached

    def _finish_task(self, key: str, task: asyncio.Task[T]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._store_finished_task(key, task))

    async def _store_finished_task(self, key: str, task: asyncio.Task[T]) -> None:
        value: T | None = None
        try:
            value = task.result()
        except BaseException:
            pass
        async with self._lock:
            if self._tasks.get(key) is task:
                self._tasks.pop(key, None)
        if value is not None:
            await self.store(key, value)

    def prune_locked(self, now: float) -> None:
        expired = [
            key
            for key, cached in self._items.items()
            if cached.expires_at <= now
        ]
        for key in expired:
            self._items.pop(key, None)
        while len(self._items) >= self.prune_threshold and self._items:
            self._items.popitem(last=False)
