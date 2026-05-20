from __future__ import annotations

import asyncio
import functools
import json
import logging
from collections.abc import Callable
from typing import Any

from ..config import Config
from ..config.runtime import RuntimeConfigValues, default_runtime_config
from ..media import playback
from ..media.dash_proxy import DashProxyStore
from ..utils import text
from . import search_urls
from .display_metadata_runtime import DisplayMetadataRuntime
from .metadata_resolver import MetadataResolver
from ..models import NodeKind
from .site_runtime import SiteRuntimeRegistry
from ..media.playable_cache import PlayableInfoCache
from ..media.playback import PlaybackSelector
from ..media.segment_base import SegmentBaseProber
from ..media.ytdlp_client import YtdlpClient
from ..sites import registry
from ..sites.types import MetadataStrategy, SiteMetadataPlan

logger = logging.getLogger("dashbox.media")

class MediaService:
    def __init__(
        self,
        config: Config,
        dash_store: DashProxyStore | None = None,
        *,
        ytdlp_search_limit: int | None = None,
        playlist_limit: int | None = None,
        bilibili_list_limit: int | None = None,
        bilibili_search_limit: int | None = None,
        runtime_config: RuntimeConfigValues | None = None,
        http_client_provider: Callable[[], Any] | None = None,
        playable_cache: PlayableInfoCache | None = None,
    ) -> None:
        self.config = config
        self.runtime_config = runtime_config or default_runtime_config(config)
        self.ytdlp_search_limit = config.effective_ytdlp_search_limit if ytdlp_search_limit is None else ytdlp_search_limit
        self.playlist_limit = config.effective_playlist_limit if playlist_limit is None else playlist_limit
        self.bilibili_list_limit = config.effective_bilibili_list_limit if bilibili_list_limit is None else bilibili_list_limit
        self.bilibili_search_limit = config.effective_bilibili_search_limit if bilibili_search_limit is None else bilibili_search_limit
        self._segment_probe_sem = asyncio.Semaphore(max(1, min(config.ytdlp_concurrency, 4)))
        self.segment_base_prober = SegmentBaseProber(
            http_client_provider,
            self._segment_probe_sem,
            user_agent=config.effective_user_agent,
            upstream_timeout=config.upstream_timeout,
        )
        self.playback = PlaybackSelector(dash_store, self.segment_base_prober)
        self.ytdlp = YtdlpClient(
            config,
            self.runtime_config,
            ytdlp_search_limit=self.ytdlp_search_limit,
            playlist_limit=self.playlist_limit,
        )
        self.playable_cache = playable_cache or PlayableInfoCache()
        self.flat_playlist_info_tasks: dict[str, asyncio.Task[dict[str, Any]]] = {}
        self.flat_playlist_info_lock = asyncio.Lock()
        self._blocking_sem = asyncio.Semaphore(max(1, config.ytdlp_concurrency))
        self.site_runtime = SiteRuntimeRegistry(
            config,
            self.ytdlp,
            bilibili_list_limit=self.bilibili_list_limit,
            bilibili_search_limit=self.bilibili_search_limit,
            http_client_provider=http_client_provider,
        )
        self.display_runtime = DisplayMetadataRuntime(
            config,
            download_impersonated=self.download_webpage_with_ytdlp_impersonation_async,
            http_client_provider=http_client_provider,
        )
        self.metadata = MetadataResolver(
            config,
            self.ytdlp,
            run_blocking=self.run_blocking,
            fetch_display_metadata=self.fetch_display_metadata,
            fetch_site_api_metadata=self.site_api_category_info,
        )

    def detect_js_runtimes(self) -> dict[str, dict[str, Any]]:
        return self.ytdlp.detect_js_runtimes()

    @staticmethod
    def command_available(command: str) -> bool:
        return YtdlpClient.command_available(command)

    @classmethod
    def node_is_supported(cls) -> bool:
        return YtdlpClient.node_is_supported()

    def playable_info(self, raw_id: str, extract_url: str = "", *, force_refresh: bool = False) -> dict[str, Any]:
        self._ensure_no_running_loop_for_blocking_call("playable_info")
        return self.playable_cache.get_or_create(
            self.playable_cache_key(raw_id),
            lambda: self.extract_playable_info(raw_id, extract_url),
            force_refresh=force_refresh,
        )

    async def playable_info_async(self, raw_id: str, extract_url: str = "", *, force_refresh: bool = False) -> dict[str, Any]:
        if not force_refresh:
            cached = self.playable_cache.get_fresh(self.playable_cache_key(raw_id))
            if cached is not None:
                return cached
        extract_url = await self.playable_extract_url(raw_id, extract_url)
        if force_refresh:
            return await self.run_blocking(self.playable_info, raw_id, extract_url, force_refresh=True)
        return await self.run_blocking(self.playable_info, raw_id, extract_url)

    def extract_playable_info(self, raw_id: str, extract_url: str = "") -> dict[str, Any]:
        self._ensure_no_running_loop_for_blocking_call("extract_playable_info")
        extract_url = self._playable_extract_url_for_blocking_call(raw_id, extract_url)
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                return self.extract(extract_url, download=False, playlist=False, require_playable=True)
            except Exception as exc:
                last_error = exc
                if attempt == 0:
                    logger.debug("playable extraction failed, retrying once url=%s error=%s", extract_url, exc)
        if last_error is not None:
            raise last_error
        raise ValueError("playable extraction failed")

    async def playable_extract_url(self, raw_id: str, extract_url: str = "") -> str:
        return await self.site_runtime.playable_extract_url(raw_id, extract_url)

    def _playable_extract_url_for_blocking_call(self, raw_id: str, extract_url: str = "") -> str:
        self._ensure_no_running_loop_for_blocking_call("_playable_extract_url_for_blocking_call")
        return self.site_runtime.blocking_playable_extract_url(raw_id, extract_url)

    @staticmethod
    def _ensure_no_running_loop_for_blocking_call(name: str) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise RuntimeError(f"{name} is a blocking internal API; call the async playback API from a running event loop")

    def invalidate_playable_info(self, raw_id: str) -> None:
        self.playable_cache.invalidate(self.playable_cache_key(raw_id))

    def playable_cache_key(self, raw_id: str) -> str:
        return "\0".join((
            raw_id,
            self.config.effective_user_agent,
            self.ytdlp.browser_cookies.cookies_from_browser,
            self.ytdlp.browser_cookies.cache_token(),
            self.ytdlp.version(),
        ))

    def extract(
        self,
        url: str,
        *,
        download: bool,
        playlist: bool,
        flat: bool = False,
        require_playable: bool = False,
        flat_playlist_items: str = "",
    ) -> dict[str, Any]:
        extract_once_kwargs = {
            "download": download,
            "playlist": playlist,
            "flat": flat,
        }
        if flat_playlist_items:
            extract_once_kwargs["flat_playlist_items"] = flat_playlist_items
        try:
            info = self.extract_once(
                url,
                use_cookies=True,
                **extract_once_kwargs,
            )
            if require_playable and not playback.has_playable_media(info):
                raise ValueError("yt-dlp returned no playable media formats")
        except Exception as exc:
            if not self.ytdlp.browser_cookies.cookies_from_browser:
                raise
            logger.debug("yt-dlp extract failed with browser cookies, retrying without cookies url=%s error=%s", url, exc)
            info = self.extract_once(
                url,
                use_cookies=False,
                **extract_once_kwargs,
            )
            if require_playable and not playback.has_playable_media(info):
                raise ValueError("yt-dlp returned no playable media formats")
        return info

    def extract_once(
        self,
        url: str,
        *,
        download: bool,
        playlist: bool,
        flat: bool = False,
        use_cookies: bool = True,
        flat_playlist_items: str = "",
    ) -> dict[str, Any]:
        return self.ytdlp.extract_once(
            url,
            download=download,
            playlist=playlist,
            flat=flat,
            use_cookies=use_cookies,
            is_search_extract_url=search_urls.is_search_extract_url(url),
            flat_playlist_items=flat_playlist_items or (self.flat_playlist_items(url) if flat else ""),
        )

    def flat_playlist_items(self, url: str) -> str:
        return self.ytdlp.flat_playlist_items(url)

    def ytdlp_opts(self, *, use_cookies: bool = True, **opts: Any) -> dict[str, Any]:
        return self.ytdlp.opts(use_cookies=use_cookies, **opts)

    def reload_browser_cookies(self, *, load: bool = False) -> dict[str, Any]:
        self.ytdlp.browser_cookies.reload()
        if load:
            self.ytdlp.browser_cookies.get_cookiejar()
        return self.ytdlp.browser_cookies.status()

    async def reload_browser_cookies_async(self, *, load: bool = False) -> dict[str, Any]:
        if load:
            return await self.run_blocking(self.reload_browser_cookies, load=True)
        return self.reload_browser_cookies(load=False)

    def browser_cookie_status(self) -> dict[str, Any]:
        return self.ytdlp.browser_cookies.status()

    def enrich_flat_playlist_info(self, info: dict[str, Any]) -> None:
        self.ytdlp.enrich_flat_playlist_info(info)

    def download_webpage_with_ytdlp_impersonation(self, url: str) -> str:
        return self.ytdlp.download_webpage_with_impersonation(url)

    async def download_webpage_with_ytdlp_impersonation_async(self, url: str) -> str:
        return await self.run_blocking(self.download_webpage_with_ytdlp_impersonation, url)

    async def normalize_config_url(self, url: str) -> str:
        normalized = registry.normalize_config_url(url)
        return await self.site_runtime.normalize_config_url(normalized)

    async def site_config_node_from_url_item_with_directory(
        self,
        url: str,
        node_id: str,
        title: str = "",
        thumbnail: str = "",
        remarks: str = "",
    ) -> tuple[Any | None, bool]:
        runtime_node, runtime_directory = await self.site_runtime.config_node_from_url_item_with_directory(
            url,
            node_id,
            self.node_kind_from_config_url(url),
        )
        if runtime_node:
            return runtime_node, runtime_directory
        site_node = self.site_config_node_from_url_item(url, node_id, title, thumbnail, remarks)
        if site_node:
            return site_node, True
        return None, False

    async def site_category_nodes(self, url: str) -> tuple[list[Any], str] | None:
        return await self.site_runtime.category_nodes_with_title(url)

    async def site_search_nodes(self, key: str) -> list[Any]:
        return await self.site_runtime.search_nodes(key)

    async def site_detail_node(self, url: str) -> Any | None:
        return await self.site_runtime.detail_node(url)

    async def fetch_display_metadata(self, raw_id: str) -> dict[str, Any]:
        site_meta = await self.site_runtime.display_metadata(raw_id)
        if site_meta is not None:
            return site_meta
        return await self.display_runtime.fetch(raw_id)

    async def site_api_category_info(self, url: str) -> dict[str, Any]:
        return await self.site_api_info(url, "site_api_category_info")

    async def site_api_detail_info(self, url: str) -> dict[str, Any]:
        return await self.site_api_info(url, "site_api_detail_info")

    async def site_api_info(self, url: str, method_name: str) -> dict[str, Any]:
        plan = self.metadata_plan_from_config_url(url)
        if plan.strategy != MetadataStrategy.SITE_API:
            return {}
        adapter = registry.resolve(url)
        site_api = getattr(adapter, method_name, None)
        if site_api is None:
            return {}
        return await self.run_blocking(
            site_api,
            url,
            download_webpage=self.download_webpage_with_ytdlp_impersonation,
            limit=self.playlist_limit,
            concurrency=self.site_api_concurrency(url),
        )

    def site_api_concurrency(self, url: str) -> int:
        return registry.call_for_url(url, "site_api_concurrency", url, self.config.ytdlp_concurrency)

    @staticmethod
    def site_api_config_item_is_directory_entry(url: str) -> bool:
        return registry.call_for_url(url, "site_api_config_item_is_directory_entry", url)

    @staticmethod
    def site_api_detail_is_aggregate_vod(url: str, info: dict[str, Any]) -> bool:
        return registry.call_for_url(url, "site_api_detail_is_aggregate_vod", url, info)

    def site_danmaku_url_from_info(self, info: dict[str, Any], base_url: str) -> str:
        return self.site_runtime.danmaku_url_from_info(info, base_url)

    async def run_blocking(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        call = functools.partial(func, *args, **kwargs)
        async with self._blocking_sem:
            return await asyncio.to_thread(call)

    async def extract_flat_playlist_info_async(
        self,
        url: str,
        *,
        extract_url: str = "",
        flat_playlist_items: str = "",
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        key = self.flat_playlist_info_task_key(url, extract_url, flat_playlist_items)
        if force_refresh:
            return await self.extract_flat_playlist_info(url, extract_url, flat_playlist_items)
        async with self.flat_playlist_info_lock:
            task = self.flat_playlist_info_tasks.get(key)
            if not task:
                task = asyncio.create_task(self.extract_flat_playlist_info(url, extract_url, flat_playlist_items))
                self.flat_playlist_info_tasks[key] = task
                task.add_done_callback(lambda done, cache_key=key: self.finish_flat_playlist_info_task(cache_key, done))

        return await asyncio.shield(task)

    async def extract_flat_playlist_info(
        self,
        url: str,
        extract_url: str = "",
        flat_playlist_items: str = "",
    ) -> dict[str, Any]:
        kwargs = {"download": False, "playlist": True, "flat": True}
        if flat_playlist_items:
            kwargs["flat_playlist_items"] = flat_playlist_items
        return await self.run_blocking(self.extract, extract_url or url, **kwargs)

    def finish_flat_playlist_info_task(self, key: str, task: asyncio.Task[dict[str, Any]]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.remove_finished_flat_playlist_info_task(key, task))

    async def remove_finished_flat_playlist_info_task(self, key: str, task: asyncio.Task[dict[str, Any]]) -> None:
        async with self.flat_playlist_info_lock:
            if self.flat_playlist_info_tasks.get(key) is task:
                self.flat_playlist_info_tasks.pop(key, None)

    def flat_playlist_info_task_key(
        self,
        url: str,
        extract_url: str = "",
        flat_playlist_items: str = "",
    ) -> str:
        effective_extract_url = extract_url or url
        return "\0".join((
            url,
            effective_extract_url,
            flat_playlist_items,
            self.config.effective_user_agent,
            self.ytdlp.browser_cookies.cookies_from_browser,
            self.ytdlp.browser_cookies.cache_token(),
            self.ytdlp.version(),
        ))

    @staticmethod
    def clean_title(value: str) -> str:
        return text.display_title(value)

    @staticmethod
    def is_playlist(info: dict[str, Any]) -> bool:
        entries = info.get("entries")
        return isinstance(entries, list) and len(entries) > 0

    def node_kind_from_playlist_info(self, info: dict[str, Any], url: str) -> NodeKind:
        if not self.is_playlist(info):
            return NodeKind.LEAF_VOD
        node_kind = registry.call_for_url(url, "node_kind_from_playlist_info", info, url)
        return node_kind or NodeKind.PLAYLIST_DIRECTORY

    @staticmethod
    def playlist_collection_synthetic_urls(url: str, existing_urls: list[str], info: dict[str, Any]) -> list[str]:
        return registry.call_for_url(url, "playlist_collection_synthetic_urls", url, existing_urls, info)

    def node_kind_from_url_metadata(self, url: str, info: dict[str, Any] | None = None) -> NodeKind:
        return registry.call_default(
            "node_kind_from_metadata",
            self.node_kind_from_config_url(url),
            info,
            known_leaf=self.url_is_known_leaf(url),
        )

    @staticmethod
    def metadata_has_display_value(info: dict[str, Any]) -> bool:
        return registry.call_default("metadata_has_display_value", info)

    @staticmethod
    def metadata_needs_html_supplement(info: dict[str, Any]) -> bool:
        return registry.call_default("metadata_needs_html_supplement", info)

    @staticmethod
    def merge_metadata(primary: dict[str, Any], supplement: dict[str, Any]) -> dict[str, Any]:
        return registry.call_default("merge_metadata", primary, supplement)

    @staticmethod
    def fallback_config_node(
        node_id: str,
        url: str,
        *,
        title: str = "",
        thumbnail: str = "",
        remarks: str = "",
        kind: NodeKind = NodeKind.LEAF_VOD,
    ) -> Any:
        return registry.call_default(
            "fallback_config_node",
            node_id,
            url,
            title=title,
            thumbnail=thumbnail,
            remarks=remarks,
            kind=kind,
        )

    @staticmethod
    def metadata_plan_from_config_url(url: str) -> SiteMetadataPlan:
        return registry.resolve(url).metadata_plan_for_config_url(url)

    @staticmethod
    def node_kind_from_config_url(url: str) -> NodeKind:
        return MediaService.metadata_plan_from_config_url(url).node_kind

    def config_url_supports_playlist_light_metadata(self, url: str) -> bool:
        plan = self.metadata_plan_from_config_url(url)
        return plan.strategy in {MetadataStrategy.PLAYLIST_YTDLP, MetadataStrategy.SITE_API}

    def generic_config_url_supports_playlist_probe(self, url: str) -> bool:
        plan = self.metadata_plan_from_config_url(url)
        return registry.call_default(
            "config_url_supports_playlist_probe",
            url,
            config_kind=plan.node_kind,
            known_leaf=self.url_is_known_leaf(url),
        )

    @staticmethod
    def generic_playlist_probe_plan(url: str) -> SiteMetadataPlan:
        return registry.call_default("metadata_plan_for_playlist_probe", url)

    @staticmethod
    def url_is_known_leaf(url: str) -> bool:
        adapter = registry.resolve(url)
        if registry.is_generic(adapter):
            return False
        plan = adapter.metadata_plan_for_config_url(url)
        return plan.node_kind == NodeKind.LEAF_VOD or plan.strategy == MetadataStrategy.SINGLE_YTDLP

    @staticmethod
    def playlist_metadata_is_folder(info: dict[str, Any], url: str) -> bool:
        return registry.call_default("playlist_metadata_is_folder", info) and not MediaService.url_is_known_leaf(url)

    @staticmethod
    def site_light_collection_child_urls(url: str, meta: dict[str, Any] | None = None) -> list[str]:
        return registry.call_for_url(url, "light_collection_child_urls", url, meta)

    @staticmethod
    def site_light_collection_uses_static_metadata(url: str) -> bool:
        return registry.call_for_url(url, "light_collection_uses_static_metadata", url)

    @staticmethod
    def category_extract_url(url: str) -> str:
        return registry.call_for_url(url, "category_extract_url", url)

    @staticmethod
    def category_flat_playlist_items(url: str) -> str:
        return registry.call_for_url(url, "category_flat_playlist_items", url)

    @staticmethod
    def category_supports_collection_probe(url: str) -> bool:
        return registry.call_for_url(url, "category_supports_collection_probe", url)

    @staticmethod
    def category_fallback_child_urls(url: str) -> list[str]:
        return registry.call_for_url(url, "category_fallback_child_urls", url)

    @staticmethod
    def url_is_search_directory(url: str) -> bool:
        return registry.call_for_url(url, "url_is_search_directory", url)

    @staticmethod
    def site_config_node_from_url_item(
        url: str,
        node_id: str,
        title: str = "",
        thumbnail: str = "",
        remarks: str = "",
    ) -> Any:
        return registry.call_for_url(url, "config_node_from_url_item", url, node_id, title, thumbnail, remarks)

    @staticmethod
    def site_search_node_from_url_item(
        url: str,
        node_id: str,
        title: str = "",
        remarks: str = "",
    ) -> Any:
        return registry.call_for_url(url, "search_node_from_url_item", url, node_id, title, remarks)

    @staticmethod
    def site_collection_title(info: dict[str, Any], fallback_url: str) -> str:
        return registry.call_for_url(fallback_url, "collection_title", info, fallback_url)

    @staticmethod
    def playlist_item_supports_full_detail(url: str) -> bool:
        return registry.call_for_url(url, "playlist_item_supports_full_detail", url)

    @staticmethod
    def playlist_items_allow_full_selected_detail(url: str) -> bool:
        return registry.call_for_url(url, "playlist_items_allow_full_selected_detail", url)

    @staticmethod
    def single_video_uses_full_detail(url: str) -> bool:
        return registry.call_for_url(url, "single_video_uses_full_detail", url)

    @staticmethod
    def single_video_uses_light_detail(url: str) -> bool:
        return registry.call_for_url(url, "single_video_uses_light_detail", url)

    @staticmethod
    def single_video_detail_url(url: str) -> str:
        return registry.call_for_url(url, "single_video_detail_url", url)

    @staticmethod
    def single_video_prewarm_args(url: str) -> tuple[str, str] | None:
        return registry.call_for_url(url, "single_video_prewarm_args", url)

    @staticmethod
    def single_video_extract_url(url: str) -> str:
        return registry.call_for_url(url, "single_video_extract_url", url)

def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
