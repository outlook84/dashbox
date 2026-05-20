from __future__ import annotations

import asyncio
import secrets
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..admin import AdminAuthState
from ..adapters import kodi_repository
from ..adapters.kodi_service import KodiService
from ..adapters.tvbox_service import TvboxService
from ..auth.failure_limiter import FailureLimiter
from ..config import Config, Subscription, SubscriptionType
from ..config.runtime import bind_runtime_config
from ..core.image_proxy import ImageCache, ImageFetchManager, ImagePrefetchIndex
from ..core.media_service import MediaService
from ..media.dash_proxy import DashProxyStore
from ..media.inline_manifest import InlineManifestStore
from ..media.playable_cache import PlayableInfoCache
from ..media.scope import PlaybackScope
from .cli import apply_runtime_log_level


class AppState:
    def __init__(
        self,
        config: Config,
        *,
        config_path: str | Path | None = None,
        data_dir: str | Path | None = None,
    ) -> None:
        self.config_path = Path(config_path) if config_path else None
        self.data_dir = Path(data_dir) if data_dir else None
        self.http_client = AppHttpClient(config)
        self.stream_http_client = AppStreamHttpClient()
        self.dash_store = DashProxyStore(idle_ttl_seconds=config.proxy_media_idle_ttl_seconds)
        self.inline_manifest_store = InlineManifestStore(idle_ttl_seconds=config.proxy_media_idle_ttl_seconds)
        self.playable_cache = PlayableInfoCache(wait_timeout=playable_cache_wait_timeout(config))
        self.image_cache = ImageCache()
        self.image_fetcher = ImageFetchManager()
        self.image_prefetch = ImagePrefetchIndex()
        self.token_secret = secrets.token_bytes(32)
        self.auth_failures = FailureLimiter()
        self.admin = AdminAuthState(self.data_dir or (self.config_path.parent if self.config_path else None))
        self.kodi_repo = kodi_repository.build()
        self.configure(config)

    def configure(self, config: Config) -> None:
        self.config = config
        self.runtime_config = bind_runtime_config(config, self.data_dir)
        self.dash_store.idle_ttl_seconds = config.proxy_media_idle_ttl_seconds
        self.inline_manifest_store.idle_ttl_seconds = config.proxy_media_idle_ttl_seconds
        self.playable_cache.wait_timeout = playable_cache_wait_timeout(config)
        self.service = MediaService(
            config,
            self.dash_store,
            runtime_config=self.runtime_config,
            http_client_provider=self.http_client.client,
            playable_cache=self.playable_cache,
        )
        self.subscriptions = SubscriptionRegistry(config.subs)
        self.tvbox_services = {
            sub.id: TvboxService(
                config,
                sub,
                self.dash_store,
                runtime_config=self.runtime_config,
                http_client_provider=self.http_client.client,
                playable_cache=self.playable_cache,
            )
            for sub in config.subs
            if sub.type == SubscriptionType.TVBOX
        }
        self.kodi_services = {
            sub.id: KodiService(
                config,
                sub,
                self.dash_store,
                runtime_config=self.runtime_config,
                http_client_provider=self.http_client.client,
                playable_cache=self.playable_cache,
            )
            for sub in config.subs
            if sub.type == SubscriptionType.KODI
        }
        apply_runtime_log_level(config.log_level)

    async def reload_config(self, config: Config) -> None:
        self.cancel_background_tasks()
        self.configure(config)

    def cancel_background_tasks(self) -> None:
        services = [
            getattr(self, "service", None),
            *getattr(self, "tvbox_services", {}).values(),
            *getattr(self, "kodi_services", {}).values(),
        ]
        for service in services:
            tasks = getattr(service, "background_tasks", None)
            if not tasks:
                continue
            for task in tuple(tasks):
                if isinstance(task, asyncio.Task):
                    task.cancel()

    def tvbox_service(self, sub_id: str) -> TvboxService:
        self.subscriptions.tvbox_sub_by_id(sub_id)
        service = self.tvbox_services.get(sub_id)
        if service is None:
            raise HTTPException(status_code=404, detail="subscription not found")
        return service

    def kodi_service(self, sub_id: str) -> KodiService:
        self.subscriptions.kodi_sub_by_id(sub_id)
        service = self.kodi_services.get(sub_id)
        if service is None:
            raise HTTPException(status_code=404, detail="subscription not found")
        return service

    def service_for_scope(self, scope: PlaybackScope | None) -> MediaService:
        if scope and scope.protocol == "tvbox":
            return self.tvbox_service(scope.sub_id)
        if scope and scope.protocol == "kodi":
            return self.kodi_service(scope.sub_id)
        return self.service


class SubscriptionRegistry:
    def __init__(self, subs: tuple[Subscription, ...]) -> None:
        self._subs = {sub.id: sub for sub in subs}

    def sub_by_id(self, sub_id: str) -> Subscription:
        sub = self._subs.get(sub_id)
        if sub is None:
            raise HTTPException(status_code=404, detail="subscription not found")
        return sub

    def tvbox_sub_by_id(self, sub_id: str) -> Subscription:
        sub = self.sub_by_id(sub_id)
        if sub.type != SubscriptionType.TVBOX or sub.tvbox is None:
            raise HTTPException(status_code=404, detail="subscription not found")
        return sub

    def kodi_sub_by_id(self, sub_id: str) -> Subscription:
        sub = self.sub_by_id(sub_id)
        if sub.type != SubscriptionType.KODI or sub.kodi is None:
            raise HTTPException(status_code=404, detail="subscription not found")
        return sub

class AppHttpClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._client: Any | None = None

    async def aopen(self) -> None:
        if self._client is None or self._client.is_closed:
            import httpx

            self._client = httpx.AsyncClient(
                timeout=self.config.upstream_timeout,
                follow_redirects=True,
                http2=True,
            )

    def client(self) -> Any:
        if self._client is None or self._client.is_closed:
            raise RuntimeError("shared HTTP client is not open")
        return self._client

    async def aclose(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            await client.aclose()


def playable_cache_wait_timeout(config: Config) -> float:
    return min(120.0, max(30.0, float(config.upstream_timeout) * 2.0))


class AppStreamHttpClient:
    def __init__(self) -> None:
        self._client: Any | None = None

    async def aopen(self) -> None:
        if self._client is None or self._client.is_closed:
            import httpx

            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                limits=httpx.Limits(
                    max_connections=64,
                    max_keepalive_connections=16,
                    keepalive_expiry=20.0,
                ),
            )

    def client(self) -> Any:
        if self._client is None or self._client.is_closed:
            raise RuntimeError("stream HTTP client is not open")
        return self._client

    async def aclose(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            await client.aclose()
