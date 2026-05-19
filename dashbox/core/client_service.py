from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any

from ..auth.cooldown_limiter import CooldownLimiter
from ..config import Config, SearchProvider, Source
from ..config import FolderItem, UrlItem
from .. import i18n
from ..utils.errors import exception_reason
from ..media import playback_result
from ..media.dash_proxy import DashProxyStore
from ..media.playable_cache import PlayableInfoCache
from ..media.scope import PlaybackScope
from ..sites import registry
from . import client_selection
from . import media_mapper
from . import search_urls
from .client_model import ClientAction, ClientEpisode, ClientItem, ClientPage, ClientPlay, ClientSubtitle, item_from_media_node, with_item_overrides
from .config_tree import ConfigTree
from .directory_cache import DirectorySnapshotCache
from .media_service import MediaService
from ..models import MediaNode
from ..models import NodeKind
from .navigation_resolver import ResolvedCategory, ResolvedDetail, normalize_resolver_url, resolve_config_item, resolve_url_category, resolve_url_detail

logger = logging.getLogger("dashbox.media")


@dataclass(frozen=True)
class DirectorySnapshot:
    category: ResolvedCategory
    stored_at: float


@dataclass(frozen=True)
class DirectoryRefreshStatus:
    requested: bool = False
    refreshed: bool = False
    rejected: bool = False
    cooldown_remaining: int = 0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested": self.requested,
            "refreshed": self.refreshed,
            "rejected": self.rejected,
            "cooldown_remaining": self.cooldown_remaining,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class DirectorySnapshotResult:
    snapshot: DirectorySnapshot
    refresh: DirectoryRefreshStatus


class ClientService(MediaService):
    def __init__(
        self,
        config: Config,
        sub_id: str,
        sources: Sequence[Source] | Any,
        dash_store: DashProxyStore | None = None,
        *,
        http_client_provider: Callable[[], Any] | None = None,
        playable_cache: PlayableInfoCache | None = None,
    ) -> None:
        super().__init__(
            config,
            dash_store,
            http_client_provider=http_client_provider,
            playable_cache=playable_cache,
        )
        self.client_sub_id = sub_id
        self.background_tasks: set[asyncio.Task[Any]] = set()
        self.config_tree = ConfigTree(sub_id, sources)
        self.directory_cache: DirectorySnapshotCache[DirectorySnapshot] = DirectorySnapshotCache()
        self.directory_refresh_cooldown = CooldownLimiter(
            short_window_seconds=5,
            long_window_seconds=300,
            long_limit=10,
        )

    def home_page(self) -> ClientPage:
        items = tuple(
            ClientItem(
                id=source.id,
                title=source.name,
                kind="folder",
                is_folder=True,
                actions=(ClientAction("open", id=source.id, endpoint="items"),),
            )
            for source in self.config_tree.sources
        )
        return ClientPage(items=items, total_items=len(items))

    async def item_page(
        self,
        item_id: str,
        base_url: str = "",
        *,
        refresh: bool = False,
        locale: str = "",
    ) -> ClientPage:
        source = self.config_tree.source_by_id(item_id)
        if source:
            return ClientPage(
                id=item_id,
                title=source.name,
                items=tuple(await self.config_items_to_client_items(item_id, source.items, base_url)),
                total_items=len(source.items),
            )
        folder_item = self.config_tree.folder_item_by_id(item_id)
        if folder_item:
            return ClientPage(
                id=item_id,
                title=folder_item.name,
                items=tuple(await self.config_items_to_client_items(item_id, folder_item.items, base_url)),
                total_items=len(folder_item.items),
            )
        return ClientPage(id=item_id)

    async def search_page(
        self,
        key: str,
        base_url: str = "",
        *,
        locale: str = "",
    ) -> ClientPage:
        key = key.strip()
        if not key:
            return ClientPage()
        if key.startswith(("http://", "https://")):
            item = item_from_media_node(MediaNode(key, key, remarks="URL"))
            return ClientPage(items=(item,), total_items=1)
        if self.config.default_search_provider == SearchProvider.BILIBILI:
            nodes = await self.site_search_nodes(key)
            items = tuple(item_from_media_node(node) for node in nodes)
            return ClientPage(items=items, total_items=len(items))
        return await self.run_blocking(self.search_page_blocking, key, base_url)

    async def detail_page(
        self,
        item_id: str,
        base_url: str = "",
        *,
        locale: str = "",
    ) -> ClientPage:
        item_id = await self.normalize_config_url(item_id)
        site_detail_node = await self.site_detail_node(item_id)
        if site_detail_node:
            item = item_from_media_node(site_detail_node)
            return ClientPage(id=item_id, items=(item,), total_items=1)
        return self.client_page_from_resolved_detail(
            await resolve_url_detail(self, item_id),
            page_id=item_id,
        )

    async def single_video_detail_page(self, raw_id: str, base_url: str = "") -> ClientPage:
        clean_id = client_selection.without_episode_index(raw_id)
        if self.single_video_uses_full_detail(clean_id):
            return await self.single_video_full_detail_page(clean_id, base_url)
        detail_url = self.single_video_detail_url(clean_id)
        if not self.single_video_uses_light_detail(clean_id):
            self.start_single_video_playable_prewarm(clean_id)
            plan = self.metadata_plan_from_config_url(clean_id)
            if plan.ytdlp is not None:
                meta = await self.metadata.metadata_for_plan(clean_id, plan)
                if meta:
                    return self.client_page_from_metadata(clean_id, meta)
            return self.client_page_from_metadata(clean_id, {"webpage_url": clean_id, "title": clean_id})
        clean_id = detail_url
        prewarm = self.single_video_prewarm_args(clean_id)
        if prewarm:
            self.start_single_video_playable_prewarm(*prewarm)
        plan = self.metadata_plan_from_config_url(clean_id)
        meta = await self.metadata.metadata_for_plan(clean_id, plan)
        if meta:
            return self.client_page_from_metadata(clean_id, meta)
        return self.client_page_from_metadata(clean_id, {"webpage_url": clean_id, "title": clean_id})

    async def single_video_full_detail_page(self, clean_id: str, base_url: str = "") -> ClientPage:
        site_detail_node = await self.site_detail_node(clean_id)
        if site_detail_node:
            item = item_from_media_node(site_detail_node)
            return ClientPage(id=clean_id, items=(item,), total_items=1)
        extract_url = self.single_video_extract_url(clean_id)
        try:
            info = await self.playable_info_async(clean_id, extract_url)
        except Exception as exc:
            logger.warning("single video detail extraction failed url=%s reason=%s", clean_id, exception_reason(exc))
            logger.debug("single video detail extraction failed", exc_info=True)
            plan = self.metadata_plan_from_config_url(clean_id)
            meta = await self.metadata.metadata_for_plan(plan.canonical_url or clean_id, plan)
            if meta:
                return self.client_page_from_metadata(clean_id, meta)
            return ClientPage(
                id=clean_id,
                items=(ClientItem(id=clean_id, title=clean_id, kind="error", subtitle_key="unavailable"),),
                total_items=1,
            )
        node = media_mapper.node_from_info(info)
        playable = media_mapper.playable_url_from_info(info, clean_id) or clean_id
        item = replace(
            item_from_media_node(node),
            is_playable=True,
            play_url=playable,
            actions=(ClientAction("play", id=playable, endpoint="play"),),
        )
        return ClientPage(id=clean_id, items=(item,), total_items=1)

    async def playlist_item_full_detail_page(self, clean_id: str, base_url: str = "") -> ClientPage:
        if self.single_video_uses_full_detail(clean_id):
            return await self.single_video_full_detail_page(clean_id, base_url)
        detail_url = self.single_video_detail_url(clean_id)
        if self.single_video_uses_light_detail(clean_id):
            clean_id = detail_url
            prewarm = self.single_video_prewarm_args(clean_id)
            if prewarm:
                self.start_single_video_playable_prewarm(*prewarm)
            plan = self.metadata_plan_from_config_url(clean_id)
            meta = await self.metadata.metadata_for_plan(clean_id, plan)
            if meta:
                return self.client_page_from_metadata(clean_id, meta)
        return self.client_page_from_metadata(clean_id, {"webpage_url": clean_id, "title": clean_id})

    async def url_item_detail_page(
        self,
        item: UrlItem,
        base_url: str = "",
        *,
        locale: str = "",
    ) -> ClientPage:
        item_url = await self.normalize_config_url(item.url)
        if self.generic_config_url_supports_playlist_probe(item_url):
            playlist_meta = self.metadata.cached_playlist_light_metadata(item_url)
            display_meta = self.metadata.cached_display_metadata(item_url)
            if playlist_meta and self.node_kind_from_url_metadata(item_url, playlist_meta) == NodeKind.PLAYLIST_DIRECTORY:
                page = await self.detail_page(item_url, base_url, locale=locale)
            elif self.metadata_has_display_value(display_meta):
                page = self.client_page_from_metadata(item_url, display_meta)
            else:
                resolved = await resolve_config_item(self, item_url, item)
                if resolved.directory:
                    page = await self.detail_page(item_url, base_url, locale=locale)
                else:
                    page = self.client_page_from_resolved_detail(
                        ResolvedDetail([resolved.node], leaf_playable_url=item_url),
                        page_id=item_url,
                    )
        else:
            if self.url_is_known_leaf(item_url):
                page = await self.single_video_detail_page(item_url, base_url)
            else:
                page = await self.detail_page(item_url, base_url, locale=locale)
        return self.with_url_item_detail_overrides(page, item)

    def search_page_blocking(self, key: str, base_url: str = "") -> ClientPage:
        key = key.strip()
        if not key:
            return ClientPage()
        if key.startswith(("http://", "https://")):
            item = item_from_media_node(MediaNode(key, key, remarks="URL"))
            return ClientPage(items=(item,), total_items=1)
        info = self.extract(search_urls.search_url_for_key(self.config, key), download=False, playlist=True, flat=True)
        entries = info.get("entries") or []
        nodes = [
            media_mapper.node_from_info(entry, base_url, self.config.image_proxy_mode)
            for entry in entries
            if isinstance(entry, dict)
        ]
        items = tuple(item_from_media_node(node) for node in nodes)
        return ClientPage(items=items, total_items=len(items))

    async def config_items_to_client_items(
        self,
        parent_id: str,
        items: Any,
        base_url: str = "",
    ) -> list[ClientItem]:
        out: list[ClientItem | asyncio.Task[ClientItem]] = []
        for item in items:
            item_id = self.config_tree.item_id(parent_id, item)
            if isinstance(item, FolderItem):
                out.append(self.folder_item_client_item(item_id, item))
            elif isinstance(item, UrlItem):
                out.append(asyncio.create_task(self.url_item_client_item(item_id, item, base_url)))
        return [
            await item if isinstance(item, asyncio.Task) else item
            for item in out
        ]

    @staticmethod
    def folder_item_client_item(item_id: str, item: FolderItem) -> ClientItem:
        return ClientItem(
            id=item_id,
            title=item.name,
            kind="folder",
            subtitle=item.remarks,
            subtitle_key="" if item.remarks else "item_count",
            item_count=0 if item.remarks else len(item.items),
            is_folder=True,
            actions=(ClientAction("open", id=item_id, endpoint="items"),),
        )

    async def url_item_client_item(self, item_id: str, item: UrlItem, base_url: str = "") -> ClientItem:
        resolved = await resolve_config_item(self, item_id, item)
        client_item = item_from_media_node(resolved.node, is_folder=True if resolved.directory else None)
        return with_item_overrides(
            client_item,
            item_id=item_id,
            title=item.title,
            thumbnail=item.pic,
            subtitle=item.remarks,
        )

    async def directory_snapshot(self, url: str, *, refresh: bool = False) -> DirectorySnapshot:
        return (await self.directory_snapshot_result(url, refresh=refresh)).snapshot

    async def directory_snapshot_result(self, url: str, *, refresh: bool = False) -> DirectorySnapshotResult:
        normalized_url = await normalize_resolver_url(self, url)
        key = self.directory_snapshot_cache_key(normalized_url)
        status = DirectoryRefreshStatus(requested=refresh)
        cached_before_reload: DirectorySnapshot | None = None
        if refresh:
            decision = self.directory_refresh_cooldown.try_acquire(key)
            if not decision.allowed:
                status = DirectoryRefreshStatus(
                    requested=True,
                    refreshed=False,
                    rejected=True,
                    cooldown_remaining=max(1, math.ceil(decision.remaining_seconds)),
                    reason=decision.reason,
                )
                cached = await self.directory_cache.fresh(key)
                if cached is not None:
                    return DirectorySnapshotResult(cached, status)
        else:
            cached = await self.directory_cache.fresh(key)
            if cached is not None:
                return DirectorySnapshotResult(cached, status)
        if refresh:
            cached_before_reload = await self.directory_cache.fresh(key)
        snapshot = await self.directory_cache.reload(
            key,
            lambda: self.load_directory_snapshot(
                normalized_url,
                force_refresh=True,
                fallback=cached_before_reload,
            ),
        )
        if status.requested and not status.rejected:
            status = DirectoryRefreshStatus(
                requested=True,
                refreshed=snapshot is not cached_before_reload,
                rejected=False,
            )
        return DirectorySnapshotResult(snapshot, status)

    async def load_directory_snapshot(
        self,
        url: str,
        *,
        force_refresh: bool = False,
        fallback: DirectorySnapshot | None = None,
    ) -> DirectorySnapshot:
        category = await resolve_url_category(self, url, force_refresh=force_refresh)
        if fallback is not None and not category.nodes and category.unavailable_url:
            return fallback
        return DirectorySnapshot(category=category, stored_at=time.monotonic())

    def directory_snapshot_cache_key(self, normalized_url: str) -> str:
        return "\0".join((
            self.client_sub_id,
            normalized_url,
            str(self.config.effective_playlist_limit),
            str(self.config.effective_bilibili_list_limit),
            self.config.effective_user_agent,
            self.config.effective_cookies_from_browser,
            self.ytdlp.browser_cookies.cache_token(),
            self.ytdlp.version(),
        ))

    def client_page_from_resolved_category(
        self,
        category: ResolvedCategory,
        *,
        page_id: str = "",
        refresh: Any | None = None,
        refreshable: bool = False,
    ) -> ClientPage:
        directory_ids = set(category.directory_node_ids)
        items = [
            item_from_media_node(node, is_folder=True if node.id in directory_ids else None)
            for node in category.nodes
        ]
        if category.add_playlist_detail_ids and category.playlist_url:
            items = self.with_selection_ids(items, category.playlist_url)
        if category.add_play_directory and category.playlist_url:
            items = self.with_play_directory_item(items, category.playlist_url)
        if category.add_indexes:
            items = [
                replace(item, index=index)
                for index, item in enumerate(items, 1)
            ]
        return ClientPage(
            id=page_id,
            title=category.name,
            items=tuple(items),
            total_items=len(items),
            refreshable=refreshable,
            refresh=refresh,
        )

    def client_page_from_resolved_detail(
        self,
        detail: ResolvedDetail,
        *,
        page_id: str = "",
    ) -> ClientPage:
        if not detail.nodes and detail.unavailable_url:
            return ClientPage(
                id=page_id,
                items=(
                    ClientItem(
                        id=detail.unavailable_url,
                        title=detail.unavailable_url,
                        kind="error",
                        subtitle_key="unavailable",
                    ),
                ),
                total_items=1,
            )
        page = self.client_page_from_resolved_category(detail, page_id=page_id)
        if detail.leaf_playable_url and page.items:
            items = list(page.items)
            items[0] = replace(
                items[0],
                is_playable=True,
                play_url=detail.leaf_playable_url,
                actions=(
                    *items[0].actions,
                    ClientAction("play", id=detail.leaf_playable_url, endpoint="play"),
                ),
            )
            page = replace(page, items=tuple(items))
        return page

    def client_playlist_detail_page(
        self,
        page: ClientPage,
        collection_url: str,
        selected_url: str,
        selected_key: str = "",
    ) -> ClientPage:
        directory_entry = selected_url == client_selection.SELECTION_DIRECTORY_SELECTED_URL
        selected = page.items[0] if directory_entry and page.items else self.selected_playlist_item(page.items, selected_url, selected_key)
        if selected is None and not directory_entry:
            return ClientPage(
                id=collection_url,
                items=(ClientItem(
                    id=selected_url or collection_url,
                    title=selected_url or collection_url,
                    kind="error",
                    subtitle_key="unavailable",
                ),),
                total_items=1,
            )
        episodes = tuple(
            ClientEpisode(
                title=str(item.playlist_title or item.title or i18n.episode_title(index)),
                url=item.selected_url,
            )
            for index, item in enumerate(page.items, 1)
            if item.selected_url and item.selected_url != client_selection.SELECTION_DIRECTORY_SELECTED_URL
        )
        if directory_entry:
            playable_items = [
                item
                for item in page.items
                if item.selected_url and item.selected_url != client_selection.SELECTION_DIRECTORY_SELECTED_URL
            ]
            summaries = [item.summary for item in playable_items if item.summary]
            shared_summary = summaries[0] if summaries and all(summary == summaries[0] for summary in summaries) else ""
            item = ClientItem(
                id=selected.id if selected else selected_url or collection_url,
                title=selected.title if selected else collection_url,
                kind="playlist",
                subtitle=(selected.playlist_title or selected.title) if selected else "",
                subtitle_key="" if selected else "item_count",
                item_count=0 if selected else len(episodes),
                summary=shared_summary,
                art=selected.art if selected else ClientItem(id="", title="").art,
                playlist_url=collection_url,
                selected_url=client_selection.SELECTION_DIRECTORY_SELECTED_URL,
                episodes=episodes,
            )
        else:
            assert selected is not None
            item = replace(
                selected,
                id=selected.id or selected_url or collection_url,
                title=selected.title or collection_url,
                subtitle=selected.playlist_title or selected.title,
                subtitle_key="" if selected.playlist_title or selected.title else "item_count",
                item_count=selected.item_count if selected.playlist_title or selected.title else len(episodes),
                playlist_url=collection_url,
                selected_url=selected.selected_url or selected_url,
                selected_key=selected_key or selected.selected_key,
                episodes=episodes,
            )
        return ClientPage(id=collection_url, title=page.title, items=(item,), total_items=1)

    @staticmethod
    def selected_playlist_item(items: tuple[ClientItem, ...], selected_url: str, selected_key: str = "") -> ClientItem | None:
        if selected_key:
            for item in items:
                if item.selected_key == selected_key:
                    return item
        selected_clean = client_selection.without_episode_index(selected_url)
        for item in items:
            url = item.selected_url
            if url == selected_url or client_selection.without_episode_index(url) == selected_clean:
                return item
        return None

    def client_page_from_metadata(self, raw_id: str, meta: dict[str, Any]) -> ClientPage:
        info = {
            "webpage_url": raw_id,
            **meta,
        }
        unavailable_reason = str(info.get("dashbox_unavailable_reason") or "")
        if unavailable_reason:
            item = ClientItem(
                id=raw_id,
                title=str(info.get("title") or raw_id),
                kind="error",
                subtitle=unavailable_reason,
            )
        else:
            item = replace(
                item_from_media_node(media_mapper.node_from_info(info)),
                is_playable=True,
                play_url=raw_id,
                actions=(ClientAction("play", id=raw_id, endpoint="play"),),
            )
        return ClientPage(id=raw_id, items=(item,), total_items=1)

    @staticmethod
    def with_url_item_detail_overrides(page: ClientPage, item: UrlItem) -> ClientPage:
        if not page.items:
            return page
        items = list(page.items)
        items[0] = with_item_overrides(
            items[0],
            title=item.title,
            thumbnail=item.pic,
            subtitle=item.remarks,
        )
        return replace(page, items=tuple(items))

    async def play_item(
        self,
        play_id: str,
        base_url: str = "",
        *,
        scope: PlaybackScope,
        playback_preferences: Any | None = None,
    ) -> ClientPlay:
        clean_id = client_selection.without_episode_index(play_id)
        extract_url = await self.playable_extract_url(clean_id)
        try:
            info = await self.playable_info_async(clean_id, extract_url)
            return await self.client_play_from_info(info, clean_id, base_url, scope)
        except ValueError:
            self.invalidate_playable_info(clean_id)
            info = await self.playable_info_async(clean_id, extract_url, force_refresh=True)
            return await self.client_play_from_info(info, clean_id, base_url, scope)

    async def client_play_from_info(
        self,
        info: dict[str, Any],
        raw_id: str,
        base_url: str = "",
        scope: PlaybackScope | None = None,
    ) -> ClientPlay:
        selected = await self.playback.select_playable(info, base_url, raw_id, scope)
        return ClientPlay(
            url=selected.url,
            title=str(info.get("title") or ""),
            mime_type=client_mime_type(selected.format),
            headers=playback_result.headers_from_info(info, selected),
            subtitles=client_subtitles_from_info(info, raw_id, scope),
            danmaku_url=self.site_danmaku_url_from_info(info, base_url),
        )

    def start_single_video_playable_prewarm(self, clean_id: str, extract_url: str = "") -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        task = loop.create_task(self.prewarm_single_video_playable(clean_id, extract_url))
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)
        task.add_done_callback(lambda done: self.log_single_video_prewarm_result(done, clean_id))

    async def prewarm_single_video_playable(self, clean_id: str, extract_url: str = "") -> None:
        await self.playable_info_async(clean_id, extract_url)

    @staticmethod
    def log_single_video_prewarm_result(task: asyncio.Task[None], clean_id: str) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception as exc:
            logger.warning("single video playable prewarm failed url=%s reason=%s", clean_id, exception_reason(exc))
            logger.debug("single video playable prewarm failed", exc_info=True)

    @staticmethod
    def with_selection_ids(items: list[ClientItem], collection_url: str) -> list[ClientItem]:
        out: list[ClientItem] = []
        key_counts: dict[str, int] = {}
        for item in items:
            if not item.selected_url:
                out.append(item)
                continue
            base_key = item.selected_key or client_selection.selection_key_from_values(item.id, item.selected_url)
            key = client_selection.selection_occurrence_key(base_key, key_counts)
            out.append(replace(
                item,
                id=client_selection.encode_selection_id(collection_url, item.selected_url, key),
                playlist_url=collection_url,
                selected_key=key,
            ))
        return out

    @staticmethod
    def with_play_directory_item(items: list[ClientItem], collection_url: str) -> list[ClientItem]:
        playable_items = [item for item in items if item.selected_url]
        if not playable_items:
            return items
        summaries = [item.summary for item in playable_items if item.summary]
        shared_summary = summaries[0] if summaries and all(summary == summaries[0] for summary in summaries) else ""
        return [
            ClientItem(
                id=client_selection.encode_selection_id(
                    collection_url,
                    client_selection.SELECTION_DIRECTORY_SELECTED_URL,
                ),
                title="",
                kind="playlist",
                summary=shared_summary,
                playlist_url=collection_url,
                selected_url=client_selection.SELECTION_DIRECTORY_SELECTED_URL,
                subtitle_key="item_count",
                item_count=len(playable_items),
                actions=(ClientAction("detail", id=collection_url, endpoint="detail"),),
            ),
            *items,
        ]


def client_subtitles_from_info(
    info: dict[str, Any],
    raw_id: str = "",
    scope: PlaybackScope | None = None,
) -> tuple[ClientSubtitle, ...]:
    scope = scope or PlaybackScope(protocol="", sub_id="")
    adapter = registry.resolve_info(info, raw_id)
    selector = getattr(adapter, "client_subtitles_from_info", None)
    if selector is None:
        values = default_client_subtitles_from_info(info)
    else:
        values = selector(
            info,
            subtitle_languages=scope.subtitle_languages,
            subtitles_enabled=scope.youtube_subtitles,
            all_manual=scope.all_manual_subtitles,
        )
    out: list[ClientSubtitle] = []
    for item in values:
        if not isinstance(item, dict) or not item.get("url"):
            continue
        out.append(ClientSubtitle(
            name=str(item.get("name") or item.get("language") or ""),
            language=str(item.get("language") or item.get("name") or ""),
            url=str(item["url"]),
            format=str(item.get("format") or item.get("ext") or ""),
        ))
    return tuple(out)


def default_client_subtitles_from_info(info: dict[str, Any]) -> tuple[dict[str, str], ...]:
    subtitles = info.get("subtitles") or {}
    if not isinstance(subtitles, dict):
        return ()
    out: list[dict[str, str]] = []
    for lang, items in subtitles.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict) or not item.get("url"):
                continue
            out.append({
                "name": str(lang),
                "language": str(lang),
                "url": str(item["url"]),
                "format": str(item.get("ext") or item.get("format") or ""),
            })
            break
    return tuple(out)


def client_mime_type(format_name: str) -> str:
    value = format_name.lower()
    if value in {"m3u8", "hls", "m3u8_native"}:
        return "application/x-mpegURL"
    if value in {"mpd", "dash"}:
        return "application/dash+xml"
    return ""
