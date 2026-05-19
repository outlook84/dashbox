from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from ..config import Config
from ..sites import registry
from ..sites.types import MetadataStrategy, SiteMetadataPlan
from ..media.ytdlp_client import YtdlpClient

logger = logging.getLogger("dashbox.metadata")

LIGHT_METADATA_REUSE_TTL_SECONDS = 900
LIGHT_METADATA_REUSE_PRUNE_THRESHOLD = 2048


class MetadataResolver:
    """Short-term reuse for light metadata outside the directory freshness boundary.

    Directory pages use DirectorySnapshotCache as their visible freshness boundary.
    When a directory snapshot is rebuilt, callers pass force_refresh=True so the
    completed values here are bypassed. These caches still reduce repeated probes
    for config browsing, single-item detail pages, and concurrent callers.
    """

    def __init__(
        self,
        config: Config,
        ytdlp: YtdlpClient,
        *,
        run_blocking: Callable[..., Awaitable[Any]],
        fetch_display_metadata: Callable[[str], Awaitable[dict[str, Any]]],
        fetch_site_api_metadata: Callable[[str], Awaitable[dict[str, Any]]],
    ) -> None:
        self.config = config
        self.ytdlp = ytdlp
        self.run_blocking = run_blocking
        self.fetch_display_metadata_callback = fetch_display_metadata
        self.fetch_site_api_metadata_callback = fetch_site_api_metadata
        self.display_cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self.display_tasks: dict[str, asyncio.Task[dict[str, Any]]] = {}
        self.light_cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self.light_tasks: dict[str, asyncio.Task[dict[str, Any]]] = {}
        self.playlist_light_cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self.playlist_light_tasks: dict[str, asyncio.Task[dict[str, Any]]] = {}
        self.lock = asyncio.Lock()

    async def display_metadata(self, raw_id: str, *, force_refresh: bool = False) -> dict[str, Any]:
        return await self.cached_metadata(
            raw_id,
            self.display_cache,
            self.display_tasks,
            self.fetch_display_metadata,
            "display metadata",
            force_refresh=force_refresh,
        )

    def cached_display_metadata(self, raw_id: str) -> dict[str, Any]:
        return self.cached_metadata_value(raw_id, self.display_cache)

    def cached_playlist_light_metadata(self, raw_id: str) -> dict[str, Any]:
        return self.cached_metadata_value(raw_id, self.playlist_light_cache)

    @staticmethod
    def cached_metadata_value(raw_id: str, cache: OrderedDict[str, tuple[float, dict[str, Any]]]) -> dict[str, Any]:
        cached = cache.get(raw_id)
        if not cached:
            return {}
        now = time.monotonic()
        if now - cached[0] > LIGHT_METADATA_REUSE_TTL_SECONDS:
            cache.pop(raw_id, None)
            return {}
        cache[raw_id] = (now, cached[1])
        cache.move_to_end(raw_id)
        return cached[1]

    async def metadata_for_plan(
        self,
        raw_id: str,
        plan: SiteMetadataPlan,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        if plan.strategy == MetadataStrategy.PLAYLIST_YTDLP:
            return await self.playlist_light_metadata_for_plan(raw_id, plan, force_refresh=force_refresh)
        if plan.strategy == MetadataStrategy.SITE_API:
            return await self.site_api_metadata_for_plan(raw_id, plan, force_refresh=force_refresh)
        if plan.strategy == MetadataStrategy.SINGLE_YTDLP:
            return await self.light_metadata_for_plan(raw_id, plan, force_refresh=force_refresh)
        if plan.strategy == MetadataStrategy.DISPLAY:
            return await self.display_metadata(raw_id, force_refresh=force_refresh)
        return {}

    async def light_metadata_for_plan(
        self,
        raw_id: str,
        plan: SiteMetadataPlan,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        return await self.cached_metadata(
            self.plan_cache_key(raw_id, plan),
            self.light_cache,
            self.light_tasks,
            lambda _key: self.fetch_light_metadata_for_plan(raw_id, plan, force_refresh=force_refresh),
            "light metadata",
            force_refresh=force_refresh,
        )

    async def playlist_light_metadata_for_plan(
        self,
        raw_id: str,
        plan: SiteMetadataPlan,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        return await self.cached_metadata(
            self.plan_cache_key(raw_id, plan),
            self.playlist_light_cache,
            self.playlist_light_tasks,
            lambda _key: self.fetch_playlist_light_metadata_for_plan(raw_id, plan),
            "playlist light metadata",
            force_refresh=force_refresh,
        )

    @staticmethod
    def plan_cache_key(raw_id: str, plan: SiteMetadataPlan) -> str:
        ytdlp = plan.ytdlp
        return "\0".join((
            raw_id,
            plan.strategy.value,
            plan.canonical_url or "",
            ytdlp.extract_url if ytdlp else "",
            str(ytdlp.noplaylist) if ytdlp else "",
            str(ytdlp.extract_flat) if ytdlp else "",
            ytdlp.playlist_items or "" if ytdlp else "",
            str(ytdlp.process) if ytdlp else "",
        ))

    async def fetch_display_metadata(self, raw_id: str) -> dict[str, Any]:
        return await self.fetch_display_metadata_callback(raw_id)

    async def site_api_metadata_for_plan(
        self,
        raw_id: str,
        plan: SiteMetadataPlan,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        return await self.cached_metadata(
            self.plan_cache_key(raw_id, plan),
            self.playlist_light_cache,
            self.playlist_light_tasks,
            lambda _key: self.fetch_site_api_metadata(raw_id),
            "site api metadata",
            force_refresh=force_refresh,
        )

    async def fetch_site_api_metadata(self, raw_id: str) -> dict[str, Any]:
        try:
            return await self.fetch_site_api_metadata_callback(raw_id)
        except Exception as exc:
            logger.debug("site api metadata failed url=%s error=%s", raw_id, exc)
            return {}

    async def cached_metadata(
        self,
        raw_id: str,
        cache: OrderedDict[str, tuple[float, dict[str, Any]]],
        tasks: dict[str, asyncio.Task[dict[str, Any]]],
        fetch: Callable[[str], Awaitable[dict[str, Any]]],
        label: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        async with self.lock:
            cached = cache.get(raw_id)
            now = time.monotonic()
            if not force_refresh and cached and now - cached[0] <= LIGHT_METADATA_REUSE_TTL_SECONDS:
                logger.debug("%s cache hit url=%s", label, raw_id)
                cache[raw_id] = (now, cached[1])
                cache.move_to_end(raw_id)
                return cached[1]
            task = tasks.get(raw_id)
            if not task:
                task = asyncio.create_task(fetch(raw_id))
                tasks[raw_id] = task

        try:
            value = await task
        finally:
            if task.done():
                async with self.lock:
                    if tasks.get(raw_id) is task:
                        tasks.pop(raw_id, None)

        if value:
            value.setdefault("webpage_url", raw_id)
            async with self.lock:
                if len(cache) >= LIGHT_METADATA_REUSE_PRUNE_THRESHOLD:
                    self.prune_metadata_cache(cache, time.monotonic())
                cache[raw_id] = (time.monotonic(), value)
                cache.move_to_end(raw_id)
        return value

    async def fetch_light_metadata_for_plan(
        self,
        raw_id: str,
        plan: SiteMetadataPlan,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        value = await self.display_metadata(raw_id, force_refresh=force_refresh)
        if value:
            return value
        if plan.ytdlp is None:
            return {}
        return await self.run_blocking(self.ytdlp_metadata_for_plan, raw_id, plan)

    async def fetch_playlist_light_metadata_for_plan(self, raw_id: str, plan: SiteMetadataPlan) -> dict[str, Any]:
        if plan.ytdlp is None:
            return {}
        return await self.run_blocking(self.ytdlp_metadata_for_plan, raw_id, plan)

    def prune_metadata_cache(self, cache: OrderedDict[str, tuple[float, dict[str, Any]]], now: float) -> None:
        expired = [
            key
            for key, (stored_at, _value) in cache.items()
            if now - stored_at > LIGHT_METADATA_REUSE_TTL_SECONDS
        ]
        for key in expired:
            cache.pop(key, None)
        while len(cache) >= LIGHT_METADATA_REUSE_PRUNE_THRESHOLD and cache:
            cache.popitem(last=False)

    def ytdlp_metadata_for_plan(self, raw_id: str, plan: SiteMetadataPlan) -> dict[str, Any]:
        if plan.ytdlp is None:
            return {}
        opts = self.ytdlp.opts_for_url(
            plan.ytdlp.extract_url,
            quiet=True,
            no_warnings=True,
            noplaylist=plan.ytdlp.noplaylist,
            skip_download=True,
            socket_timeout=min(self.config.upstream_timeout, 8),
            extract_flat=plan.ytdlp.extract_flat,
            playlist_items=plan.ytdlp.playlist_items,
        )
        opts = {key: value for key, value in opts.items() if value is not None}
        try:
            with self.ytdlp.youtube_dl(opts) as ydl:
                try:
                    info = ydl.extract_info(
                        plan.ytdlp.extract_url,
                        download=False,
                        process=plan.ytdlp.process,
                    )
                except TypeError:
                    info = ydl.extract_info(plan.ytdlp.extract_url, download=False)
        except Exception as exc:
            logger.debug("yt-dlp plan metadata failed url=%s error=%s", raw_id, exc)
            adapter = registry.resolve(raw_id)
            reason = registry.call(adapter, "extraction_error_reason", raw_id, exc) or registry.call(
                adapter,
                "extraction_error_reason",
                plan.ytdlp.extract_url,
                exc,
            )
            if reason:
                return {
                    "webpage_url": raw_id,
                    "title": reason,
                    "dashbox_unavailable_reason": reason,
                }
            return {}
        if not isinstance(info, dict):
            return {}
        adapter = registry.resolve(raw_id)
        return registry.call(adapter, "metadata_from_ytdlp_info", info, raw_id)
