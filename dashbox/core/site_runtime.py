from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, cast

from ..config import Config
from ..media.ytdlp_client import YtdlpClient
from ..sites import registry
from ..models import NodeKind


class UrlSiteRuntime(Protocol):
    name: str

    def supports_url(self, url: str) -> bool: ...

    async def playable_extract_url(self, raw_id: str, extract_url: str = "") -> str: ...

    def blocking_playable_extract_url(self, raw_id: str, extract_url: str = "") -> str: ...

    async def normalize_config_url(self, url: str) -> str: ...

    async def config_node_from_url_item_with_directory(
        self,
        url: str,
        node_id: str,
        config_kind: NodeKind,
    ) -> tuple[Any | None, bool]: ...

    async def category_nodes_with_title(self, url: str) -> tuple[list[Any], str] | None: ...

    async def detail_node(self, url: str) -> Any | None: ...

    async def display_metadata(self, raw_id: str) -> dict[str, Any] | None: ...

    def danmaku_url_from_info(self, info: dict[str, Any], base_url: str) -> str: ...


class SiteRuntimeRegistry:
    def __init__(
        self,
        config: Config,
        ytdlp: YtdlpClient,
        *,
        bilibili_list_limit: int | None = None,
        bilibili_search_limit: int | None = None,
        http_client_provider: Callable[[], Any] | None = None,
    ) -> None:
        self.url_runtimes: tuple[UrlSiteRuntime, ...] = tuple(
            self._create_runtime(
                factory,
                config,
                ytdlp,
                bilibili_list_limit=bilibili_list_limit,
                bilibili_search_limit=bilibili_search_limit,
                http_client_provider=http_client_provider,
            )
            for factory in registry.runtime_factories()
        )
        for runtime in self.url_runtimes:
            setattr(self, runtime.name, runtime)

    @staticmethod
    def _create_runtime(
        factory: registry.RuntimeFactory,
        config: Config,
        ytdlp: YtdlpClient,
        *,
        bilibili_list_limit: int | None,
        bilibili_search_limit: int | None,
        http_client_provider: Callable[[], Any] | None,
    ) -> UrlSiteRuntime:
        if (
            getattr(factory, "__module__", "") == "dashbox.sites.bilibili.runtime"
            and getattr(factory, "__name__", "") == "BilibiliRuntime"
        ):
            bilibili_factory = cast(Any, factory)
            return bilibili_factory(
                config,
                ytdlp,
                bilibili_list_limit=bilibili_list_limit,
                bilibili_search_limit=bilibili_search_limit,
                http_client_provider=http_client_provider,
            )
        return factory(config, ytdlp, http_client_provider=http_client_provider)

    def runtime_for_url(self, url: str) -> UrlSiteRuntime | None:
        return next((runtime for runtime in self.url_runtimes if runtime.supports_url(url)), None)

    def runtimes_for_url(self, url: str) -> tuple[UrlSiteRuntime, ...]:
        return tuple(runtime for runtime in self.url_runtimes if runtime.supports_url(url))

    async def playable_extract_url(self, raw_id: str, extract_url: str = "") -> str:
        if extract_url:
            return extract_url
        runtime = self.runtime_for_url(raw_id)
        return await runtime.playable_extract_url(raw_id) if runtime else ""

    def blocking_playable_extract_url(self, raw_id: str, extract_url: str = "") -> str:
        if extract_url:
            return extract_url
        runtime = self.runtime_for_url(raw_id)
        return runtime.blocking_playable_extract_url(raw_id) if runtime else raw_id

    async def normalize_config_url(self, url: str) -> str:
        for runtime in self.runtimes_for_url(url):
            normalized = await runtime.normalize_config_url(url)
            if normalized != url:
                return normalized
        return url

    async def config_node_from_url_item_with_directory(
        self,
        url: str,
        node_id: str,
        config_kind: NodeKind,
    ) -> tuple[Any | None, bool]:
        runtime = self.runtime_for_url(url)
        if runtime is None:
            return None, False
        return await runtime.config_node_from_url_item_with_directory(url, node_id, config_kind)

    async def category_nodes_with_title(self, url: str) -> tuple[list[Any], str] | None:
        runtime = self.runtime_for_url(url)
        return await runtime.category_nodes_with_title(url) if runtime else None

    async def search_nodes(self, key: str) -> list[Any]:
        nodes: list[Any] = []
        for runtime in self.url_runtimes:
            search = getattr(runtime, "search_nodes", None)
            if search is not None:
                nodes.extend(await search(key))
        return nodes

    async def detail_node(self, url: str) -> Any | None:
        runtime = self.runtime_for_url(url)
        return await runtime.detail_node(url) if runtime else None

    async def display_metadata(self, raw_id: str) -> dict[str, Any] | None:
        runtime = self.runtime_for_url(raw_id)
        return await runtime.display_metadata(raw_id) if runtime else None

    def danmaku_url_from_info(self, info: dict[str, Any], base_url: str) -> str:
        raw_url = str(info.get("webpage_url") or info.get("original_url") or info.get("url") or "")
        runtime = self.runtime_for_url(raw_url)
        if runtime:
            return runtime.danmaku_url_from_info(info, base_url)
        for runtime in self.url_runtimes:
            danmaku_url = runtime.danmaku_url_from_info(info, base_url)
            if danmaku_url:
                return danmaku_url
        return ""
