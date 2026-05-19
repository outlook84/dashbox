from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from typing import Any

from ..config import UrlItem
from ..utils.errors import exception_reason
from ..sites.types import MetadataStrategy
from . import media_mapper
from ..models import MediaNode
from ..models import NodeKind

logger = logging.getLogger("dashbox.media")


@dataclass(frozen=True)
class ResolvedConfigItem:
    node: MediaNode
    directory: bool = False
    source_url: str = ""


@dataclass(frozen=True)
class ResolvedNodeList:
    nodes: list[MediaNode]
    name: str = ""
    playlist_url: str = ""
    add_play_directory: bool = False
    add_playlist_detail_ids: bool = False
    add_indexes: bool = False
    unavailable_url: str = ""
    directory_node_ids: tuple[str, ...] = ()
    leaf_playable_url: str = ""
    allow_full_selected_detail: bool = False


ResolvedCategory = ResolvedNodeList
ResolvedDetail = ResolvedNodeList


async def normalize_resolver_url(service: Any, url: str) -> str:
    return await service.normalize_config_url(url)


async def resolve_config_item(service: Any, item_id: str, item: UrlItem) -> ResolvedConfigItem:
    url = await normalize_resolver_url(service, item.url)
    config_kind = service.node_kind_from_config_url(url)

    site_config_node, site_config_directory = await service.site_config_node_from_url_item_with_directory(
        url,
        item_id,
        item.title,
        item.pic,
        item.remarks,
    )
    if site_config_node:
        return ResolvedConfigItem(
            with_node_kind(site_config_node, config_kind),
            directory=site_config_directory,
            source_url=url,
        )

    plan = service.metadata_plan_from_config_url(url)
    if service.url_is_known_leaf(url):
        meta_url = plan.canonical_url or url
        meta = await service.metadata.metadata_for_plan(meta_url, plan)
        if meta:
            return ResolvedConfigItem(with_node_kind(media_mapper.node_from_info(meta), NodeKind.LEAF_VOD), source_url=url)

    search_node = service.site_search_node_from_url_item(url, item_id, item.title, item.remarks)
    if search_node:
        return ResolvedConfigItem(with_node_kind(search_node, config_kind), source_url=url)

    if service.generic_config_url_supports_playlist_probe(url):
        meta = await service.metadata.metadata_for_plan(url, service.generic_playlist_probe_plan(url))
        if meta and service.node_kind_from_url_metadata(url, meta) == NodeKind.PLAYLIST_DIRECTORY:
            if service.metadata_needs_html_supplement(meta):
                meta = service.merge_metadata(meta, await service.metadata.display_metadata(url))
            return ResolvedConfigItem(
                with_node_kind(media_mapper.node_from_playlist_metadata(meta, item_id), NodeKind.PLAYLIST_DIRECTORY),
                directory=True,
                source_url=url,
            )
        if not meta or service.metadata_needs_html_supplement(meta):
            meta = service.merge_metadata(meta, await service.metadata.display_metadata(url))
        if service.metadata_has_display_value(meta):
            return ResolvedConfigItem(with_node_kind(media_mapper.node_from_info(meta), NodeKind.LEAF_VOD), source_url=url)
        return ResolvedConfigItem(
            with_node_kind(service.fallback_config_node(
                item_id,
                url,
                title=item.title,
                thumbnail=item.pic,
                remarks=item.remarks,
            ), NodeKind.LEAF_VOD),
            source_url=url,
        )

    if (
        plan.node_kind == NodeKind.PLAYLIST_DIRECTORY
        and plan.strategy == MetadataStrategy.SITE_API
        and service.site_api_config_item_is_directory_entry(url)
    ):
        info = await service.site_api_category_info(url)
        if info:
            return ResolvedConfigItem(
                with_node_kind(media_mapper.playlist_node_from_info(info, item_id), NodeKind.PLAYLIST_DIRECTORY),
                directory=True,
                source_url=url,
            )

    if service.config_url_supports_playlist_light_metadata(url):
        plan = service.metadata_plan_from_config_url(url)
        meta = await service.metadata.metadata_for_plan(url, plan)
        if meta:
            title = service.site_collection_title(meta, url)
            if title and not meta.get("title") and not meta.get("playlist_title"):
                meta = {**meta, "title": title}
            search_node = service.site_search_node_from_url_item(
                url,
                item_id,
                str(item.title or meta.get("title") or meta.get("playlist_title") or title or ""),
                item.remarks,
            )
            if search_node:
                node = search_node
            else:
                node = media_mapper.node_from_playlist_metadata(meta, item_id)
            return ResolvedConfigItem(
                with_node_kind(node, service.node_kind_from_url_metadata(url, meta)),
                directory=service.node_kind_from_url_metadata(url, meta) == NodeKind.PLAYLIST_DIRECTORY,
                source_url=url,
            )

    if service.node_kind_from_url_metadata(url) == NodeKind.PLAYLIST_DIRECTORY:
        search_node = service.site_search_node_from_url_item(url, item_id, item.title, item.remarks)
        node = search_node or service.fallback_config_node(
            item_id,
            url,
            title=item.title or service.site_collection_title({}, url),
            thumbnail=item.pic,
            remarks=item.remarks,
            kind=NodeKind.PLAYLIST_DIRECTORY,
        )
        return ResolvedConfigItem(with_node_kind(node, NodeKind.PLAYLIST_DIRECTORY), source_url=url)

    plan = service.metadata_plan_from_config_url(url)
    meta_url = plan.canonical_url or url
    meta = await service.metadata.metadata_for_plan(meta_url, plan)
    if meta:
        return ResolvedConfigItem(with_node_kind(media_mapper.node_from_info(meta), NodeKind.LEAF_VOD), source_url=url)

    return ResolvedConfigItem(
        with_node_kind(service.fallback_config_node(
            item_id,
            url,
            title=item.title,
            thumbnail=item.pic,
            remarks=item.remarks,
        ), NodeKind.LEAF_VOD),
        source_url=url,
    )


def with_node_kind(node: MediaNode, node_kind: NodeKind) -> MediaNode:
    if node.node_kind:
        return node
    return replace(node, node_kind=node_kind.value)


async def resolve_url_category(service: Any, url: str, *, force_refresh: bool = False) -> ResolvedCategory:
    url = await normalize_resolver_url(service, url)

    site_category = await service.site_category_nodes(url)
    if site_category is not None:
        site_nodes, title = site_category
        return ResolvedCategory(
            site_nodes,
            title or category_name_from_nodes(site_nodes, url),
            playlist_url=url,
            add_play_directory=True,
            add_playlist_detail_ids=True,
        )

    plan = service.metadata_plan_from_config_url(url)
    if plan.node_kind == NodeKind.PLAYLIST_DIRECTORY and plan.strategy == MetadataStrategy.SITE_API:
        try:
            site_info = await service.site_api_category_info(url)
        except Exception as exc:
            logger.warning("site category extraction failed url=%s reason=%s", url, exception_reason(exc))
            logger.debug("site category extraction failed", exc_info=True)
            return ResolvedCategory([], url, unavailable_url=url)
        if site_info:
            nodes = media_mapper.playlist_item_nodes_from_info(site_info)
            return ResolvedCategory(
                nodes,
                category_name_from_metadata(service, site_info, url),
                playlist_url=url,
                add_play_directory=True,
                add_playlist_detail_ids=True,
                unavailable_url="" if nodes else url,
            )

    meta = await metadata_playlist_light(service, url, force_refresh=force_refresh) if service.site_light_collection_child_urls(url) or service.site_light_collection_uses_static_metadata(url) else {}
    child_urls = service.site_light_collection_child_urls(url, meta)
    if child_urls:
        nodes, directory_node_ids = await light_collection_nodes(service, child_urls, force_refresh=force_refresh)
        return ResolvedCategory(
            nodes,
            category_name_from_metadata(service, meta, url),
            add_indexes=True,
            unavailable_url="" if nodes else url,
            directory_node_ids=directory_node_ids,
        )

    info = await extract_flat_playlist(
        service,
        url,
        "url category extraction",
        extract_url=service.category_extract_url(url),
        flat_playlist_items=service.category_flat_playlist_items(url),
        force_refresh=force_refresh,
    )
    if info is None:
        if service.category_supports_collection_probe(url):
            fallback_nodes, directory_node_ids = await light_collection_nodes(
                service,
                service.category_fallback_child_urls(url),
                force_refresh=force_refresh,
            )
            if fallback_nodes:
                return ResolvedCategory(fallback_nodes, url, add_indexes=True, directory_node_ids=directory_node_ids)
        return ResolvedCategory([], url, unavailable_url=url)

    if service.url_is_search_directory(url):
        nodes = media_mapper.search_nodes_from_info(info)
        return ResolvedCategory(
            nodes,
            category_name_from_metadata(service, info, url),
            unavailable_url="" if nodes else url,
        )

    node_kind = service.node_kind_from_playlist_info(info, url)
    if node_kind == NodeKind.COLLECTION_DIRECTORY:
        nodes = media_mapper.collection_nodes_from_info(info)
        nodes.extend(media_mapper.synthetic_collection_nodes(service.playlist_collection_synthetic_urls(
            url,
            [node.id for node in nodes],
            info,
        ), info))
        return ResolvedCategory(
            nodes,
            category_name_from_metadata(service, info, url),
            add_indexes=True,
            directory_node_ids=tuple(node.id for node in nodes),
        )

    if service.category_supports_collection_probe(url):
        fallback_nodes, directory_node_ids = await light_collection_nodes(
            service,
            service.category_fallback_child_urls(url),
            force_refresh=force_refresh,
        )
        if fallback_nodes:
            return ResolvedCategory(
                fallback_nodes,
                category_name_from_metadata(service, info, url),
                add_indexes=True,
                directory_node_ids=directory_node_ids,
            )

    if node_kind == NodeKind.PLAYLIST_DIRECTORY:
        nodes = media_mapper.playlist_item_nodes_from_info(info)
        if nodes:
            return ResolvedCategory(
                nodes,
                category_name_from_metadata(service, info, url),
                playlist_url=url,
                add_play_directory=True,
                add_playlist_detail_ids=True,
                allow_full_selected_detail=service.playlist_items_allow_full_selected_detail(url),
            )

    if node_kind == NodeKind.AGGREGATE_VOD:
        return ResolvedCategory([media_mapper.aggregate_playlist_node_from_info(info, url)], category_name_from_metadata(service, info, url))

    return ResolvedCategory([service.fallback_config_node(url, url)], category_name_from_metadata(service, info, url))


async def resolve_url_detail(service: Any, raw_id: str) -> ResolvedDetail:
    raw_id = await normalize_resolver_url(service, raw_id)

    plan = service.metadata_plan_from_config_url(raw_id)
    if plan.node_kind == NodeKind.PLAYLIST_DIRECTORY and plan.strategy == MetadataStrategy.SITE_API:
        try:
            site_info = await service.site_api_detail_info(raw_id)
        except Exception as exc:
            logger.warning("site detail extraction failed url=%s reason=%s", raw_id, exception_reason(exc))
            logger.debug("site detail extraction failed", exc_info=True)
            return ResolvedDetail([], unavailable_url=raw_id)
        if service.site_api_detail_is_aggregate_vod(raw_id, site_info):
            return ResolvedDetail([media_mapper.aggregate_playlist_node_from_info(site_info, raw_id)])
        nodes = media_mapper.playlist_item_nodes_from_info(site_info)
        return ResolvedDetail(
            nodes,
            playlist_url=raw_id,
            add_play_directory=True,
            add_playlist_detail_ids=True,
            unavailable_url="" if nodes else raw_id,
        )

    info = await extract_flat_playlist(
        service,
        raw_id,
        "detail extraction",
        extract_url=service.category_extract_url(raw_id),
    )
    if info is None:
        return ResolvedDetail([], unavailable_url=raw_id)

    if service.url_is_search_directory(raw_id):
        return ResolvedDetail(media_mapper.search_nodes_from_info(info), unavailable_url=raw_id)

    if service.is_playlist(info):
        node_kind = service.node_kind_from_playlist_info(info, raw_id)
        if node_kind == NodeKind.COLLECTION_DIRECTORY:
            nodes = media_mapper.collection_nodes_from_info(info)
            return ResolvedDetail(nodes, directory_node_ids=tuple(node.id for node in nodes))
        if node_kind == NodeKind.AGGREGATE_VOD:
            return ResolvedDetail([media_mapper.aggregate_playlist_node_from_info(info, raw_id)])
        nodes = media_mapper.playlist_item_nodes_from_info(info)
        return ResolvedDetail(
            nodes,
            playlist_url=raw_id,
            add_play_directory=True,
            add_playlist_detail_ids=True,
            unavailable_url="" if nodes else raw_id,
        )

    detail_plan = service.metadata_plan_from_config_url(raw_id)
    light_meta = await service.metadata.metadata_for_plan(detail_plan.canonical_url or raw_id, detail_plan)
    meta = {**info, **light_meta} if light_meta else info
    playable = media_mapper.playable_url_from_info(info, raw_id)
    return ResolvedDetail([media_mapper.node_from_info(meta)], leaf_playable_url=playable)


def category_name_from_metadata(service: Any, info: dict[str, Any], fallback: str) -> str:
    return service.site_collection_title(info, fallback)


def category_name_from_nodes(nodes: list[MediaNode], fallback: str) -> str:
    return next((node.title for node in nodes if node.title), fallback)


async def extract_flat_playlist(
    service: Any,
    url: str,
    log_label: str,
    *,
    extract_url: str = "",
    flat_playlist_items: str = "",
    force_refresh: bool = False,
) -> dict[str, Any] | None:
    try:
        return await service.extract_flat_playlist_info_async(
            url,
            extract_url=extract_url,
            flat_playlist_items=flat_playlist_items,
            force_refresh=force_refresh,
        )
    except Exception as exc:
        logger.warning("%s failed url=%s reason=%s", log_label, url, exception_reason(exc))
        logger.debug("%s failed", log_label, exc_info=True)
        return None


async def metadata_playlist_light(service: Any, url: str, *, force_refresh: bool = False) -> dict[str, Any]:
    plan = service.metadata_plan_from_config_url(url)
    return await service.metadata.metadata_for_plan(url, plan, force_refresh=force_refresh)


async def light_collection_nodes(service: Any, urls: list[str], *, force_refresh: bool = False) -> tuple[list[MediaNode], tuple[str, ...]]:
    nodes = []
    directory_ids = []
    values = await asyncio.gather(*(metadata_playlist_light(service, url, force_refresh=force_refresh) for url in urls))
    for url, meta in zip(urls, values):
        if not meta:
            continue
        node = media_mapper.node_from_playlist_metadata(meta, url)
        if service.node_kind_from_url_metadata(url, meta) == NodeKind.PLAYLIST_DIRECTORY:
            directory_ids.append(node.id)
        nodes.append(node)
    return nodes, tuple(directory_ids)
