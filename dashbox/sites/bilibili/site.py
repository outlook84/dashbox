from __future__ import annotations

# This module is both the site implementation and the compatibility export
# surface for helper functions split into sibling modules.
# ruff: noqa: F401

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from ... import i18n
from ...config import DEFAULT_BILIBILI_LIST_LIMIT, DEFAULT_USER_AGENT
from ...models import MediaNode
from ...models import NodeKind
from ..hosts import with_query_param
from .auth import (
    parse_cookie_header,
    cookie_header_from_dict,
    wbi_image_key,
    wbi_mixin_key_from_nav,
    encode_wbi_params,
    add_wbi2_params,
    wbi_signature_is_invalid,
)
from .nodes import (
    node_from_pages,
    playable_playlist_node_from_pages,
    single_node_from_video_metadata,
    single_node_from_bangumi_metadata,
    single_node_from_cheese_metadata,
    page_episode,
    node_from_medialist,
    light_playlist_node,
    aggregate_nodes_from_medialist,
    node_from_medialist_entry,
    aggregate_node_from_medialist_entry,
    playable_playlist_node_from_medialist,
    medialist_episode,
    medialist_entry_page_count,
    medialist_entry_is_single_page,
    medialist_entry_has_page_count_hint,
    entry_bvid,
    search_node_from_entry,
    node_from_bangumi_season,
    aggregate_nodes_from_bangumi_season,
    node_from_bangumi_episode,
    aggregate_node_from_bangumi_episode,
    playable_playlist_node_from_bangumi_season,
    node_from_cheese_season,
    aggregate_nodes_from_cheese_season,
    aggregate_node_from_cheese_episode,
    node_from_cheese_episode,
    playable_playlist_node_from_cheese_season,
    cheese_episode,
    cheese_episode_title,
    cheese_content_from_metadata,
    node_from_audio_album,
    aggregate_nodes_from_audio_album,
    aggregate_node_from_audio_entry,
    node_from_audio_entry,
    playable_playlist_node_from_audio_album,
    audio_episode,
    bangumi_episode,
    bangumi_episode_title,
    bangumi_duration_seconds,
)
from .urls import (
    CollectionKind,
    CollectionRoute,
    COLLECTION_ROUTE_KINDS,
    is_info,
    _collection_routes,
    is_video_playlist,
    playlist_info_node_kind,
    node_kind_from_playlist_info,
    playlist_item_supports_full_detail,
    single_video_uses_full_detail,
    single_video_extract_url,
    config_node_kind,
    matches_url,
    metadata_plan_for_config_url,
    _video_playlist_episode_url,
    aggregate_playlist_episode,
    _video_playlist_episode_title,
    is_search_url,
    search_keyword_from_url,
    search_title_from_url,
    normalize_extract_url,
    video_metadata_from_payload,
    player_page_from_url,
    player_cid_from_url,
    page_number_from_cid,
    supports_video_api_metadata,
    ytdlp_light_metadata_url,
    ytdlp_light_metadata_needs_processing,
    headers_for_format_urls,
    danmaku_url_from_info,
    danmaku_xml_upstream_url,
    is_video_url,
    is_live_url,
    is_short_url,
    _is_single_playable_path,
    is_single_playable_url,
    is_bangumi_season_url,
    is_bangumi_episode_url,
    is_bangumi_media_url,
    is_cheese_season_url,
    is_cheese_episode_url,
    is_watchlater_url,
    is_category_url,
    is_channel_url,
    is_audio_album_url,
    is_medialist_url,
    is_favorites_url,
    is_space_collection_url,
    is_space_series_url,
    is_space_video_url,
    is_space_audio_url,
    bvid_from_url,
    _is_bvid,
    aid_from_url,
    supported_short_url_target,
    is_supported_short_url_target,
    extraction_error_reason,
    bangumi_season_id_from_url,
    bangumi_episode_id_from_url,
    bangumi_media_id_from_url,
    cheese_season_id_from_url,
    cheese_episode_id_from_url,
    audio_album_id_from_url,
    category_ids_from_url,
    channel_route_from_url,
    _is_ascii_alpha,
    _is_ascii_alpha_or_underscore,
    _is_ascii_alnum,
    _is_ascii_alnum_or_underscore,
    prefixed_path_id,
    channel_config_from_payload,
    medialist_ids_from_url,
    favorites_id_from_url,
    space_collection_ids_from_url,
    space_series_ids_from_url,
    space_video_mid_from_url,
    space_audio_mid_from_url,
    space_audio_light_metadata as _default_space_audio_light_metadata,
)
from .utils import (
    clean_html_text,
    normalize_image_url,
    space_archive_collection_info,
    collection_count_fields,
    positive_int,
    dict_list,
    payload_value,
    payload_dict,
    gather_limited,
    parse_initial_state,
    initial_state_json_text,
    balanced_json_object_text,
    find_cid,
    cid_text,
    positive_int_text,
    find_cid_from_formats,
    cid_from_bilivideo_url,
    clean_title,
    clean_content,
)

logger = logging.getLogger("dashbox.bilibili")

BILIBILI_CATEGORY_RIDS = {
    "kichiku": {
        "mad": 26,
        "manual_vocaloid": 126,
        "guide": 22,
        "theatre": 216,
        "course": 127,
    },
}
WBI_MIXIN_KEY_ENC_TAB = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
)
WBI_MIXIN_KEY_TTL_SECONDS = 6 * 60 * 60


class BilibiliSite:
    def __init__(
        self,
        user_agent: str = "",
        upstream_timeout: int = 30,
        list_limit: int = DEFAULT_BILIBILI_LIST_LIMIT,
        search_limit: int = 30,
        cookie_header_provider: Callable[[str], str] | None = None,
        cookie_reload: Callable[[], None] | None = None,
        cookie_auto_reload: Callable[[], bool] | None = None,
        short_url_resolver: Callable[[str], Awaitable[str]] | None = None,
        http_client_provider: Callable[[], Any] | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.upstream_timeout = upstream_timeout
        self.list_limit = list_limit
        self.search_limit = search_limit
        self.cookie_header_provider = cookie_header_provider
        self.cookie_reload = cookie_reload
        self.cookie_auto_reload = cookie_auto_reload
        self.short_url_resolver = short_url_resolver
        self.http_client_provider = http_client_provider
        self._wbi_mixin_key = ""
        self._wbi_mixin_key_expires_at = 0.0
        self._buvid_cookies: dict[str, str] = {}

    @asynccontextmanager
    async def http_client(self, *, timeout: int | float | None = None, follow_redirects: bool = True):
        if self.http_client_provider is not None:
            yield self.http_client_provider()
            return

        import httpx

        async with httpx.AsyncClient(
            timeout=self.upstream_timeout if timeout is None else timeout,
            follow_redirects=follow_redirects,
        ) as client:
            yield client

    async def video_metadata(self, url: str) -> dict[str, Any]:
        bvid = bvid_from_url(url)
        aid = aid_from_url(url)
        if not bvid and not aid:
            return {}
        try:
            headers = self.headers("https://api.bilibili.com/x/web-interface/view", url)
            params = {"bvid": bvid} if bvid else {"aid": aid}
            async with self.http_client() as client:
                response = await client.get(
                    "https://api.bilibili.com/x/web-interface/view",
                    params=params,
                    headers=headers,
                )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.debug("bilibili metadata failed url=%s error=%s", url, exc)
            return {}
        return video_metadata_from_payload(payload, url)

    async def resolve_extract_url(self, url: str) -> str:
        if is_short_url(url):
            url = await self.resolve_short_url(url)
        extract_url = normalize_extract_url(url)
        cid = player_cid_from_url(url)
        if not cid or player_page_from_url(url) or extract_url == url:
            return extract_url
        info = await self.video_metadata(extract_url)
        page = page_number_from_cid(info, cid)
        return with_query_param(extract_url, "p", page) if page else url

    async def normalize_config_url(self, url: str) -> str:
        return await self.resolve_extract_url(url) if is_short_url(url) else url

    def _extract_url_for_blocking_call(self, url: str) -> str:
        if is_short_url(url):
            raise RuntimeError("Bilibili short URL resolution requires the async playback API")
        extract_url = normalize_extract_url(url)
        cid = player_cid_from_url(url)
        if cid and not player_page_from_url(url) and extract_url != url:
            raise RuntimeError("Bilibili player CID page resolution requires the async playback API or an explicit extract_url")
        return extract_url

    async def resolve_short_url(self, url: str) -> str:
        if self.short_url_resolver:
            return supported_short_url_target(url, await self.short_url_resolver(url))
        try:
            async with self.http_client(timeout=min(self.upstream_timeout, 8), follow_redirects=False) as client:
                response = await client.head(url, headers=self.headers(url, url), follow_redirects=False, timeout=min(self.upstream_timeout, 8))
                if response.status_code in (405, 501):
                    response = await client.get(url, headers=self.headers(url, url), follow_redirects=False, timeout=min(self.upstream_timeout, 8))
            return supported_short_url_target(url, response.headers.get("Location", ""))
        except Exception as exc:
            logger.debug("bilibili short url resolution failed url=%s error=%s", url, exc)
            return url

    async def medialist_metadata(self, url: str, allow_cookie_reload: bool = True) -> dict[str, Any]:
        ids = medialist_ids_from_url(url)
        if not ids:
            return {}
        try:
            headers = self.headers(url, url)
            async with self.http_client() as client:
                html_response = await client.get(url, headers=headers)
                html_text = html_response.text
                initial_state = parse_initial_state(html_text)
                playlist = initial_state.get("playlist") if isinstance(initial_state.get("playlist"), dict) else {}
                media_info = initial_state.get("mediaListInfo") if isinstance(initial_state.get("mediaListInfo"), dict) else {}
                total = positive_int(media_info.get("media_count") or media_info.get("count") or media_info.get("total"))
                query = {
                    "ps": 20,
                    "with_current": "false",
                    "type": playlist.get("type") or ids["type"],
                    "biz_id": playlist.get("id") or ids["biz_id"],
                }
                entries: list[dict[str, Any]] = []
                for _ in range(self.list_page_limit()):
                    response = await client.get(
                        "https://api.bilibili.com/x/v2/medialist/resource/list",
                        params=query,
                        headers=self.headers("https://api.bilibili.com/x/v2/medialist/resource/list", url),
                    )
                    response.raise_for_status()
                    payload = response.json()
                    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
                        if payload.get("code") == -403:
                            reloaded = await self.retry_after_cookie_reload(
                                allow_cookie_reload,
                                lambda: self.medialist_metadata(url, allow_cookie_reload=False),
                            )
                            if reloaded is not None:
                                return reloaded
                        logger.warning("bilibili medialist invalid url=%s code=%s message=%s", url, payload.get("code"), payload.get("message"))
                        return {}
                    page_data = payload["data"]
                    if not total:
                        total = positive_int(page_data.get("total") or page_data.get("count"))
                    media_list = dict_list(page_data.get("media_list"))
                    if _append_limited_entries(entries, media_list, self.list_limit):
                        break
                    if not page_data.get("has_more") or not media_list:
                        break
                    query["oid"] = media_list[-1].get("id")
            title = str(media_info.get("title") or initial_state.get("title") or ids["biz_id"])
            logger.debug("bilibili medialist title=%s entries=%s", title, len(entries))
            return {
                "title": title,
                "thumbnail": str(media_info.get("cover") or ""),
                "total": total,
                "entries": entries,
            }
        except Exception as exc:
            logger.debug("bilibili medialist failed url=%s error=%s", url, exc)
            return {}

    async def favorites_metadata(self, url: str, allow_cookie_reload: bool = True) -> dict[str, Any]:
        fid = favorites_id_from_url(url)
        if not fid:
            return {}
        try:
            entries: list[dict[str, Any]] = []
            info: dict[str, Any] = {}
            async with self.http_client() as client:
                for page_num in range(1, self.list_page_limit() + 1):
                    payload = await self._favorites_page_payload(
                        client,
                        url,
                        fid,
                        page_num=page_num,
                        page_size=20,
                    )
                    if payload.get("code") == -403:
                        reloaded = await self.retry_after_cookie_reload(
                            page_num == 1 and allow_cookie_reload,
                            lambda: self.favorites_metadata(url, allow_cookie_reload=False),
                        )
                        if reloaded is not None:
                            return reloaded
                        logger.warning("bilibili favorites requires login or permission url=%s", url)
                        return {}
                    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
                        logger.warning("bilibili favorites invalid url=%s code=%s message=%s", url, payload.get("code"), payload.get("message"))
                        return {}
                    page_data = payload["data"]
                    if page_num == 1 and isinstance(page_data.get("info"), dict):
                        info = page_data["info"]
                    media_list = dict_list(page_data.get("medias"))
                    if _append_limited_entries(entries, media_list, self.list_limit):
                        break
                    if not page_data.get("has_more") or not media_list:
                        break
            title = str(info.get("title") or fid)
            logger.debug("bilibili favorites title=%s entries=%s", title, len(entries))
            return {
                "title": title,
                "thumbnail": str(info.get("cover") or ""),
                "total": positive_int(info.get("media_count") or info.get("count") or info.get("total")),
                "entries": entries,
            }
        except Exception as exc:
            logger.debug("bilibili favorites failed url=%s error=%s", url, exc)
            return {}

    async def favorites_light_metadata(self, url: str, allow_cookie_reload: bool = True) -> dict[str, Any]:
        fid = favorites_id_from_url(url)
        if not fid:
            return {}
        try:
            async with self.http_client() as client:
                payload = await self._favorites_page_payload(
                    client,
                    url,
                    fid,
                    page_num=1,
                    page_size=1,
                )
            if payload.get("code") == -403:
                reloaded = await self.retry_after_cookie_reload(
                    allow_cookie_reload,
                    lambda: self.favorites_light_metadata(url, allow_cookie_reload=False),
                )
                if reloaded is not None:
                    return reloaded
                logger.warning("bilibili favorites light requires login or permission url=%s", url)
                return {}
            if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
                logger.warning("bilibili favorites light invalid url=%s code=%s message=%s", url, payload.get("code"), payload.get("message"))
                return {}
            page_data = payload["data"]
            info = page_data.get("info")
            if not isinstance(info, dict):
                return {}
            return {
                "title": str(info.get("title") or ""),
                "thumbnail": str(info.get("cover") or ""),
                "total": positive_int(info.get("media_count") or info.get("count") or info.get("total")),
            }
        except Exception as exc:
            logger.debug("bilibili favorites light failed url=%s error=%s", url, exc)
            return {}

    async def _favorites_page_payload(
        self,
        client: Any,
        url: str,
        fid: str,
        *,
        page_num: int,
        page_size: int,
    ) -> dict[str, Any]:
        api_url = "https://api.bilibili.com/x/v3/fav/resource/list"
        response = await client.get(
            api_url,
            params={"media_id": fid, "pn": page_num, "ps": page_size},
            headers=self.headers(api_url, url),
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def medialist_light_metadata(self, url: str) -> dict[str, Any]:
        ids = medialist_ids_from_url(url)
        if not ids:
            return {}
        try:
            headers = self.headers(url, url)
            async with self.http_client() as client:
                html_response = await client.get(url, headers=headers)
            initial_state = parse_initial_state(html_response.text)
            media_info = initial_state.get("mediaListInfo") if isinstance(initial_state.get("mediaListInfo"), dict) else {}
            return {
                "title": str(media_info.get("title") or initial_state.get("title") or ""),
                "thumbnail": str(media_info.get("cover") or ""),
                "total": positive_int(media_info.get("media_count") or media_info.get("count") or media_info.get("total")),
            }
        except Exception as exc:
            logger.debug("bilibili medialist light failed url=%s error=%s", url, exc)
            return {}

    async def space_collection_metadata(self, url: str) -> dict[str, Any]:
        ids = space_collection_ids_from_url(url)
        if not ids:
            return {}
        try:
            entries: list[dict[str, Any]] = []
            meta: dict[str, Any] = {}
            async with self.http_client() as client:
                for page_num in range(1, self.list_page_limit() + 1):
                    payload = await self._space_collection_page_payload(client, url, ids, page_num=page_num, page_size=30)
                    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
                        logger.warning("bilibili space collection invalid url=%s code=%s message=%s", url, payload.get("code"), payload.get("message"))
                        return {}
                    data = payload["data"]
                    if page_num == 1 and isinstance(data.get("meta"), dict):
                        meta = data["meta"]
                    page_entries = dict_list(data.get("archives"))
                    page = data.get("page")
                    if page_num == 1 and isinstance(page, dict):
                        meta["total"] = positive_int(page.get("total"))
                    if _append_limited_entries(entries, page_entries, self.list_limit):
                        break
                    total = positive_int(page.get("total")) if isinstance(page, dict) else 0
                    page_size = positive_int(page.get("page_size")) if isinstance(page, dict) else 30
                    if not page_entries or (total and page_num * page_size >= total):
                        break
            return space_archive_collection_info(ids["sid"], meta, entries)
        except Exception as exc:
            logger.debug("bilibili space collection failed url=%s error=%s", url, exc)
            return {}

    async def space_collection_light_metadata(self, url: str) -> dict[str, Any]:
        ids = space_collection_ids_from_url(url)
        if not ids:
            return {}
        try:
            async with self.http_client() as client:
                payload = await self._space_collection_page_payload(client, url, ids, page_num=1, page_size=1)
            if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
                logger.warning("bilibili space collection light invalid url=%s code=%s message=%s", url, payload.get("code"), payload.get("message"))
                return {}
            data = payload["data"]
            meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
            page = data.get("page")
            if isinstance(page, dict):
                meta["total"] = positive_int(page.get("total"))
            return space_archive_collection_info(ids["sid"], meta, {})
        except Exception as exc:
            logger.debug("bilibili space collection light failed url=%s error=%s", url, exc)
            return {}

    async def _space_collection_page_payload(
        self,
        client: Any,
        url: str,
        ids: dict[str, str],
        *,
        page_num: int,
        page_size: int,
    ) -> dict[str, Any]:
        api_url = "https://api.bilibili.com/x/polymer/web-space/seasons_archives_list"
        response = await client.get(
            api_url,
            params={
                "mid": ids["mid"],
                "season_id": ids["sid"],
                "page_num": page_num,
                "page_size": page_size,
            },
            headers=self.headers(api_url, url),
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def space_series_metadata(self, url: str) -> dict[str, Any]:
        ids = space_series_ids_from_url(url)
        if not ids:
            return {}
        try:
            entries: list[dict[str, Any]] = []
            meta: dict[str, Any] = {}
            async with self.http_client() as client:
                meta_payload = await self._space_series_meta_payload(client, url, ids)
                meta_data = payload_dict(meta_payload)
                if isinstance(meta_data.get("meta"), dict):
                    meta = meta_data["meta"]
                for page_num in range(1, self.list_page_limit() + 1):
                    payload = await self._space_series_archives_payload(client, url, ids, page_num=page_num, page_size=30)
                    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
                        logger.warning("bilibili space series invalid url=%s code=%s message=%s", url, payload.get("code"), payload.get("message"))
                        return {}
                    data = payload["data"]
                    page_entries = dict_list(data.get("archives"))
                    page = data.get("page")
                    if page_num == 1 and isinstance(page, dict):
                        meta["total"] = positive_int(page.get("total"))
                    if _append_limited_entries(entries, page_entries, self.list_limit):
                        break
                    total = positive_int(page.get("total")) if isinstance(page, dict) else 0
                    page_size = positive_int(page.get("size")) if isinstance(page, dict) else 30
                    if not page_entries or (total and page_num * page_size >= total):
                        break
            return space_archive_collection_info(ids["sid"], meta, entries)
        except Exception as exc:
            logger.debug("bilibili space series failed url=%s error=%s", url, exc)
            return {}

    async def space_series_light_metadata(self, url: str) -> dict[str, Any]:
        ids = space_series_ids_from_url(url)
        if not ids:
            return {}
        try:
            async with self.http_client() as client:
                meta_payload = await self._space_series_meta_payload(client, url, ids)
                data = payload_dict(meta_payload)
                meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
                archives_payload = await self._space_series_archives_payload(client, url, ids, page_num=1, page_size=1)
            archives_data = payload_dict(archives_payload)
            page = archives_data.get("page") if isinstance(archives_data, dict) else {}
            if isinstance(page, dict):
                meta["total"] = positive_int(page.get("total"))
            return space_archive_collection_info(ids["sid"], meta, {})
        except Exception as exc:
            logger.debug("bilibili space series light failed url=%s error=%s", url, exc)
            return {}

    async def _space_series_meta_payload(self, client: Any, url: str, ids: dict[str, str]) -> dict[str, Any]:
        meta_url = "https://api.bilibili.com/x/series/series"
        response = await client.get(
            meta_url,
            params={"series_id": ids["sid"]},
            headers=self.headers(meta_url, url),
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def _space_series_archives_payload(
        self,
        client: Any,
        url: str,
        ids: dict[str, str],
        *,
        page_num: int,
        page_size: int,
    ) -> dict[str, Any]:
        archives_url = "https://api.bilibili.com/x/series/archives"
        response = await client.get(
            archives_url,
            params={
                "mid": ids["mid"],
                "series_id": ids["sid"],
                "pn": page_num,
                "ps": page_size,
            },
            headers=self.headers(archives_url, url),
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def space_video_metadata(self, url: str) -> dict[str, Any]:
        mid = space_video_mid_from_url(url)
        if not mid:
            return {}
        try:
            entries: list[dict[str, Any]] = []
            total = 0
            user_info: dict[str, Any] = {}
            async with self.http_client() as client:
                user_info = await self._space_user_info(client, url, mid)
                cookies = await self.wbi_cookies(client)
                mixin_key = await self.wbi_mixin_key(client, cookies)
                for page_num in range(1, self.list_page_limit() + 1):
                    payload = await self._space_video_page_payload(
                        client,
                        url,
                        mid,
                        page_num=page_num,
                        page_size=30,
                        cookies=cookies,
                        mixin_key=mixin_key,
                    )
                    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
                        logger.warning("bilibili space video invalid url=%s code=%s message=%s", url, payload.get("code"), payload.get("message"))
                        return {}
                    data = payload["data"]
                    list_data = data.get("list") if isinstance(data.get("list"), dict) else {}
                    page_entries = dict_list(list_data.get("vlist"))
                    if page_num == 1:
                        total = self._space_video_total(data)
                    if _append_limited_entries(entries, page_entries, self.list_limit):
                        break
                    if not page_entries or len(page_entries) < 30 or (total and len(entries) >= total):
                        break
            return {
                **self._space_owner_metadata(mid, user_info, i18n.bilibili_video(), i18n.bilibili_video_title(mid)),
                "total": total,
                "entries": entries,
            }
        except Exception as exc:
            logger.debug("bilibili space video failed url=%s error=%s", url, exc)
            return {}

    async def space_video_light_metadata(self, url: str) -> dict[str, Any]:
        mid = space_video_mid_from_url(url)
        if not mid:
            return {}
        try:
            async with self.http_client() as client:
                user_info = await self._space_user_info(client, url, mid)
                cookies = await self.wbi_cookies(client)
                mixin_key = await self.wbi_mixin_key(client, cookies)
                payload = await self._space_video_page_payload(
                    client,
                    url,
                    mid,
                    page_num=1,
                    page_size=1,
                    cookies=cookies,
                    mixin_key=mixin_key,
                )
            if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
                logger.warning("bilibili space video light invalid url=%s code=%s message=%s", url, payload.get("code"), payload.get("message"))
                return {}
            return {
                **self._space_owner_metadata(mid, user_info, i18n.bilibili_video(), i18n.bilibili_video_title(mid)),
                "total": self._space_video_total(payload["data"]),
            }
        except Exception as exc:
            logger.debug("bilibili space video light failed url=%s error=%s", url, exc)
            return {}

    async def _space_user_info(self, client: Any, url: str, mid: str) -> dict[str, Any]:
        try:
            api_url = "https://api.bilibili.com/x/web-interface/card"
            response = await client.get(
                api_url,
                params={"mid": mid},
                headers=self.headers(api_url, url),
            )
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) and payload.get("code") == 0 else {}
            card = data.get("card") if isinstance(data, dict) and isinstance(data.get("card"), dict) else {}
            return card if isinstance(card, dict) else {}
        except Exception as exc:
            logger.debug("bilibili space user info failed url=%s mid=%s error=%s", url, mid, exc)
            return {}

    def _space_owner_metadata(
        self,
        mid: str,
        user_info: dict[str, Any],
        label: str,
        fallback_title: str,
    ) -> dict[str, Any]:
        name = str(user_info.get("name") or "").strip()
        return {
            "title": f"{name} - {label}" if name else fallback_title,
            "thumbnail": str(user_info.get("face") or ""),
            "description": str(user_info.get("sign") or ""),
        }

    async def _space_video_page_payload(
        self,
        client: Any,
        url: str,
        mid: str,
        *,
        page_num: int,
        page_size: int,
        cookies: dict[str, str],
        mixin_key: str,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "mid": mid,
            "ps": page_size,
            "tid": 0,
            "pn": page_num,
            "keyword": "",
            "order": "pubdate",
            "order_avoided": "true",
            "platform": "web",
        }
        return await self.wbi_get_json(
            client,
            "https://api.bilibili.com/x/space/wbi/arc/search",
            add_wbi2_params(params),
            cookies,
            mixin_key,
            referer=url,
        )

    def _space_video_total(self, data: dict[str, Any]) -> int:
        page = data.get("page")
        if isinstance(page, dict):
            return positive_int(page.get("count") or page.get("total"))
        list_data = data.get("list")
        if isinstance(list_data, dict):
            return positive_int(list_data.get("count") or list_data.get("total"))
        return 0

    async def space_audio_metadata(self, url: str) -> dict[str, Any]:
        mid = space_audio_mid_from_url(url)
        if not mid:
            return {}
        try:
            entries: list[dict[str, Any]] = []
            total = 0
            user_info: dict[str, Any] = {}
            async with self.http_client() as client:
                user_info = await self._space_user_info(client, url, mid)
                for page_num in range(1, self.list_page_limit() + 1):
                    payload = await self._space_audio_page_payload(client, url, mid, page_num=page_num, page_size=30)
                    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
                        logger.warning("bilibili space audio invalid url=%s code=%s message=%s", url, payload.get("code"), payload.get("message"))
                        return {}
                    data = payload["data"]
                    page_entries = dict_list(data.get("data"))
                    page_count = positive_int(data.get("pageCount"))
                    page_size = positive_int(data.get("pageSize")) or 30
                    total = positive_int(data.get("totalSize"))
                    if _append_limited_entries(entries, page_entries, self.list_limit):
                        break
                    if (
                        not page_entries
                        or (page_count and page_num >= page_count)
                        or (total and len(entries) >= total)
                        or (not page_count and len(page_entries) < page_size)
                    ):
                        break
            return {
                **self._space_owner_metadata(mid, user_info, i18n.bilibili_audio(), i18n.bilibili_audio_title(mid)),
                "entries": entries,
                "total": total or len(entries),
            }
        except Exception as exc:
            logger.debug("bilibili space audio failed url=%s error=%s", url, exc)
            return {}

    async def space_audio_light_metadata(self, url: str) -> dict[str, Any]:
        mid = space_audio_mid_from_url(url)
        if not mid:
            return {}
        try:
            async with self.http_client() as client:
                user_info = await self._space_user_info(client, url, mid)
                payload = await self._space_audio_page_payload(client, url, mid, page_num=1, page_size=1)
            if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
                logger.warning("bilibili space audio light invalid url=%s code=%s message=%s", url, payload.get("code"), payload.get("message"))
                return {}
            data = payload["data"]
            return {
                **self._space_owner_metadata(mid, user_info, i18n.bilibili_audio(), i18n.bilibili_audio_title(mid)),
                "total": positive_int(data.get("totalSize")),
            }
        except Exception as exc:
            logger.debug("bilibili space audio light failed url=%s error=%s", url, exc)
            return {}

    async def _space_audio_page_payload(
        self,
        client: Any,
        url: str,
        mid: str,
        *,
        page_num: int,
        page_size: int,
    ) -> dict[str, Any]:
        api_url = "https://api.bilibili.com/audio/music-service/web/song/upper"
        response = await client.get(
            api_url,
            params={"uid": mid, "pn": page_num, "ps": page_size, "order": 1},
            headers=self.headers(api_url, url),
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def list_page_limit(self) -> int:
        return max(1, (self.list_limit + 19) // 20)

    def channel_page_limit(self) -> int:
        return self.list_page_limit()

    async def bangumi_season_metadata(self, url: str) -> dict[str, Any]:
        season_id = bangumi_season_id_from_url(url)
        if not season_id:
            return {}
        return await self.bangumi_metadata({"season_id": season_id}, url)

    async def bangumi_episode_metadata(self, url: str) -> dict[str, Any]:
        episode_id = bangumi_episode_id_from_url(url)
        if not episode_id:
            return {}
        return await self.bangumi_metadata({"ep_id": episode_id}, url)

    async def bangumi_metadata(self, params: dict[str, Any], url: str) -> dict[str, Any]:
        try:
            async with self.http_client() as client:
                response = await client.get(
                    "https://api.bilibili.com/pgc/view/web/season",
                    params=params,
                    headers=self.headers("https://api.bilibili.com/pgc/view/web/season", url),
                )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.debug("bilibili bangumi metadata failed url=%s error=%s", url, exc)
            return {}
        if payload.get("code") != 0 or not isinstance(payload.get("result"), dict):
            logger.warning("bilibili bangumi metadata invalid url=%s code=%s message=%s", url, payload.get("code"), payload.get("message"))
            return {}
        data = payload["result"]
        episodes = dict_list(data.get("episodes"))
        data["episodes"] = episodes
        logger.debug("bilibili bangumi title=%s episodes=%s", data.get("title"), len(episodes))
        return data

    async def bangumi_media_metadata(self, url: str) -> dict[str, Any]:
        media_id = bangumi_media_id_from_url(url)
        if not media_id:
            return {}
        try:
            async with self.http_client() as client:
                response = await client.get(url, headers=self.headers(url, url))
            response.raise_for_status()
            initial_state = parse_initial_state(response.text)
            media_info = initial_state.get("mediaInfo") if isinstance(initial_state.get("mediaInfo"), dict) else {}
            season_id = str(media_info.get("season_id") or "")
            if not season_id:
                return {}
            data = await self.bangumi_season_metadata(f"https://www.bilibili.com/bangumi/play/ss{season_id}")
            if media_info.get("title"):
                data["title"] = str(media_info["title"])
            if media_info.get("evaluate") and not data.get("evaluate"):
                data["evaluate"] = str(media_info["evaluate"])
            return data
        except Exception as exc:
            logger.debug("bilibili bangumi media failed url=%s error=%s", url, exc)
            return {}

    async def cheese_season_metadata(self, url: str) -> dict[str, Any]:
        season_id = cheese_season_id_from_url(url)
        if not season_id:
            return {}
        return await self.cheese_metadata({"season_id": season_id}, url)

    async def cheese_episode_metadata(self, url: str) -> dict[str, Any]:
        episode_id = cheese_episode_id_from_url(url)
        if not episode_id:
            return {}
        return await self.cheese_metadata({"ep_id": episode_id}, url)

    async def cheese_metadata(self, params: dict[str, Any], url: str) -> dict[str, Any]:
        try:
            api_url = "https://api.bilibili.com/pugv/view/web/season"
            async with self.http_client() as client:
                response = await client.get(
                    api_url,
                    params=params,
                    headers=self.headers(api_url, url),
                )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.debug("bilibili cheese metadata failed url=%s error=%s", url, exc)
            return {}
        if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
            logger.warning("bilibili cheese metadata invalid url=%s code=%s message=%s", url, payload.get("code"), payload.get("message"))
            return {}
        data = payload["data"]
        episodes = [
            episode
            for episode in dict_list(data.get("episodes"))
            if episode.get("episode_can_view", True)
        ]
        data["episodes"] = episodes
        logger.debug("bilibili cheese title=%s episodes=%s", data.get("title"), len(episodes))
        return data

    async def watchlater_metadata(self, url: str, allow_cookie_reload: bool = True) -> dict[str, Any]:
        if not is_watchlater_url(url):
            return {}
        try:
            api_url = "https://api.bilibili.com/x/v2/history/toview/web"
            async with self.http_client() as client:
                response = await client.get(
                    api_url,
                    params={"jsonp": "jsonp"},
                    headers=self.headers(api_url, url),
                )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") == -101:
                reloaded = await self.retry_after_cookie_reload(
                    allow_cookie_reload,
                    lambda: self.watchlater_metadata(url, allow_cookie_reload=False),
                )
                if reloaded is not None:
                    return reloaded
                logger.warning("bilibili watchlater requires login url=%s", url)
                return {}
            if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
                logger.warning("bilibili watchlater invalid url=%s code=%s message=%s", url, payload.get("code"), payload.get("message"))
                return {}
            entries = dict_list(payload["data"].get("list"))
            total = positive_int(payload["data"].get("count") or payload["data"].get("total")) or len(entries)
            if self.list_limit:
                entries = entries[:self.list_limit]
            return {"title": i18n.bilibili_watch_later(), "total": total, "entries": entries}
        except Exception as exc:
            logger.debug("bilibili watchlater failed url=%s error=%s", url, exc)
            return {}

    async def watchlater_light_metadata(self, url: str, allow_cookie_reload: bool = True) -> dict[str, Any]:
        if not is_watchlater_url(url):
            return {}
        info = await self.watchlater_metadata(url, allow_cookie_reload=allow_cookie_reload)
        if not info:
            return {}
        return {"title": i18n.bilibili_watch_later(), "total": positive_int(info.get("total")) or len(info.get("entries") or [])}

    async def category_metadata(self, url: str) -> dict[str, Any]:
        ids = category_ids_from_url(url)
        if not ids:
            return {}
        rid = BILIBILI_CATEGORY_RIDS.get(ids["category"], {}).get(ids["subcategory"])
        if not rid:
            logger.debug("bilibili category unsupported url=%s", url)
            return {}
        try:
            api_url = "https://api.bilibili.com/x/web-interface/newlist"
            entries: list[dict[str, Any]] = []
            async with self.http_client() as client:
                for page_num in range(1, self.list_page_limit() + 1):
                    response = await client.get(
                        api_url,
                        params={"rid": rid, "type": 1, "ps": 20, "jsonp": "jsonp", "pn": page_num},
                        headers=self.headers(api_url, url),
                    )
                    response.raise_for_status()
                    payload = response.json()
                    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
                        logger.warning("bilibili category invalid url=%s code=%s message=%s", url, payload.get("code"), payload.get("message"))
                        return {}
                    page_entries = dict_list(payload["data"].get("archives"))
                    if _append_limited_entries(entries, page_entries, self.list_limit):
                        break
                    page = payload["data"].get("page")
                    count = positive_int(page.get("count")) if isinstance(page, dict) else 0
                    size = positive_int(page.get("size")) if isinstance(page, dict) else 20
                    if not page_entries or (count and page_num * size >= count):
                        break
            title = f"{ids['category']}: {ids['subcategory']}"
            return {"title": title, "entries": entries}
        except Exception as exc:
            logger.debug("bilibili category failed url=%s error=%s", url, exc)
            return {}

    async def channel_metadata(self, url: str) -> dict[str, Any]:
        route = channel_route_from_url(url)
        if not route:
            return {}
        try:
            config_url = "https://api.bilibili.com/x/kv-frontend/namespace/data"
            feed_url = "https://api.bilibili.com/x/web-interface/region/feed/rcmd"
            async with self.http_client() as client:
                config_response = await client.get(
                    config_url,
                    params={"appKey": "333.1339", "nscode": 10, "versionId": ""},
                    headers=self.headers(config_url, url),
                )
                config_response.raise_for_status()
                channel = channel_config_from_payload(config_response.json(), route)
                tid = positive_int(channel.get("tid"))
                if not tid:
                    logger.debug("bilibili channel unsupported url=%s", url)
                    return {}
                entries: list[dict[str, Any]] = []
                for page_num in range(1, self.channel_page_limit() + 1):
                    response = await client.get(
                        feed_url,
                        params={
                            "display_id": page_num,
                            "request_cnt": 20,
                            "from_region": tid,
                            "device": "web",
                            "plat": 30,
                        },
                        headers=self.headers(feed_url, url),
                    )
                    response.raise_for_status()
                    payload = response.json()
                    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
                        logger.warning("bilibili channel invalid url=%s code=%s message=%s", url, payload.get("code"), payload.get("message"))
                        return {}
                    page_entries = dict_list(payload["data"].get("archives"))
                    if _append_limited_entries(entries, page_entries, self.list_limit):
                        break
                    if not page_entries:
                        break
            return {
                "title": str(channel.get("name") or route),
                "entries": entries,
            }
        except Exception as exc:
            logger.debug("bilibili channel failed url=%s error=%s", url, exc)
            return {}

    async def audio_album_metadata(self, url: str) -> dict[str, Any]:
        album_id = audio_album_id_from_url(url)
        if not album_id:
            return {}
        try:
            base_url = "https://www.bilibili.com/audio/music-service-c/web"
            async with self.http_client() as client:
                page_size = min(self.list_limit or 100, 100)
                entries: list[dict[str, Any]] = []
                for page_num in range(1, 1_000_001):
                    songs_response = await client.get(
                        f"{base_url}/song/of-menu",
                        params={"sid": album_id, "pn": page_num, "ps": page_size},
                        headers=self.headers(f"{base_url}/song/of-menu", url),
                    )
                    songs_response.raise_for_status()
                    songs_payload = songs_response.json()
                    songs_data = payload_value(songs_payload)
                    if isinstance(songs_data, dict):
                        songs = songs_data.get("data")
                    else:
                        songs = songs_data
                    page_entries = dict_list(songs)
                    if _append_limited_entries(entries, page_entries, self.list_limit):
                        break
                    if not page_entries:
                        break
                    if isinstance(songs_data, dict):
                        current_page = positive_int(songs_data.get("curPage")) or page_num
                        page_count = positive_int(songs_data.get("pageCount"))
                        total_size = positive_int(songs_data.get("totalSize"))
                        response_page_size = positive_int(songs_data.get("pageSize")) or page_size
                        if (page_count and current_page >= page_count) or (total_size and len(entries) >= total_size):
                            break
                        if not page_count and len(page_entries) < response_page_size:
                            break
                info_response = await client.get(
                    f"{base_url}/menu/info",
                    params={"sid": album_id},
                    headers=self.headers(f"{base_url}/menu/info", url),
                )
                info_response.raise_for_status()
                info_payload = info_response.json()
        except Exception as exc:
            logger.debug("bilibili audio album failed url=%s error=%s", url, exc)
            return {}
        info = payload_dict(info_payload)
        return {
            "title": str(info.get("title") or album_id),
            "thumbnail": str(info.get("cover") or ""),
            "description": str(info.get("intro") or ""),
            "entries": entries,
        }

    async def search_nodes(self, keyword: str, *, limit: int = 30) -> list[MediaNode]:
        keyword = keyword.strip()
        if not keyword:
            return []
        limit = max(1, limit)
        try:
            async with self.http_client() as client:
                cookies = await self.wbi_cookies(client)
                mixin_key = await self.wbi_mixin_key(client, cookies)
                entries: list[dict[str, Any]] = []
                page_num = 1
                while len(entries) < limit:
                    page_size = min(50, max(1, limit - len(entries)))
                    payload = await self.wbi_get_json(
                        client,
                        "https://api.bilibili.com/x/web-interface/wbi/search/type",
                        {
                            "keyword": keyword,
                            "search_type": "video",
                            "page": page_num,
                            "page_size": page_size,
                            "duration": 0,
                        },
                        cookies,
                        mixin_key,
                        referer="https://www.bilibili.com",
                    )
                    if payload.get("code") != 0 or not isinstance(payload.get("data"), dict):
                        logger.warning("bilibili search invalid keyword=%s code=%s message=%s", keyword, payload.get("code"), payload.get("message"))
                        break
                    results = dict_list(payload["data"].get("result"))
                    entries.extend(results)
                    if len(entries) >= limit or not results or len(results) < page_size:
                        break
                    page_num += 1
                return [
                    node
                    for node in (search_node_from_entry(entry) for entry in entries[:limit])
                    if node
                ]
        except Exception as exc:
            logger.debug("bilibili search failed keyword=%s error=%s", keyword, exc)
            return []

    async def wbi_get_json(
        self,
        client: Any,
        api_url: str,
        params: dict[str, Any],
        cookies: dict[str, str],
        mixin_key: str,
        *,
        referer: str,
    ) -> dict[str, Any]:
        headers = self.wbi_headers(api_url, referer, cookies)
        last_payload: dict[str, Any] = {}
        for attempt in range(2):
            signed_params = encode_wbi_params(params, mixin_key)
            response = await client.get(api_url, params=signed_params, headers=headers)
            if response.status_code == 412 and attempt == 0:
                await asyncio.sleep(1)
                continue
            response.raise_for_status()
            payload = response.json()
            last_payload = payload if isinstance(payload, dict) else {}
            if wbi_signature_is_invalid(last_payload) and attempt == 0:
                mixin_key = await self.wbi_mixin_key(client, cookies, force_refresh=True)
                continue
            break
        return last_payload

    async def wbi_mixin_key(self, client: Any, cookies: dict[str, str], *, force_refresh: bool = False) -> str:
        if not force_refresh and self._wbi_mixin_key and time.time() < self._wbi_mixin_key_expires_at:
            return self._wbi_mixin_key
        api_url = "https://api.bilibili.com/x/web-interface/nav"
        response = await client.get(
            api_url,
            headers=self.wbi_headers(api_url, "https://www.bilibili.com", cookies),
        )
        response.raise_for_status()
        self._wbi_mixin_key = wbi_mixin_key_from_nav(response.json())
        self._wbi_mixin_key_expires_at = time.time() + WBI_MIXIN_KEY_TTL_SECONDS
        return self._wbi_mixin_key

    async def wbi_cookies(self, client: Any) -> dict[str, str]:
        cookies = parse_cookie_header(self.cookie_header_provider("https://api.bilibili.com") if self.cookie_header_provider else "")
        if cookies.get("buvid3") and cookies.get("buvid4"):
            return cookies
        if self._buvid_cookies.get("buvid3") and self._buvid_cookies.get("buvid4"):
            return {**cookies, **self._buvid_cookies}
        api_url = "https://api.bilibili.com/x/frontend/finger/spi"
        response = await client.get(api_url, headers=self.wbi_headers(api_url, "https://www.bilibili.com", cookies))
        response.raise_for_status()
        data = response.json().get("data") or {}
        self._buvid_cookies = {
            "buvid3": str(data.get("b_3") or ""),
            "buvid4": str(data.get("b_4") or ""),
        }
        return {**cookies, **self._buvid_cookies}

    def headers(self, target_url: str, referer: str) -> dict[str, str]:
        headers = {
            "User-Agent": self.user_agent or DEFAULT_USER_AGENT,
            "Referer": referer,
        }
        if self.cookie_header_provider:
            cookie = self.cookie_header_provider(target_url)
            if cookie:
                headers["Cookie"] = cookie
        return headers

    def wbi_headers(self, target_url: str, referer: str, cookies: dict[str, str]) -> dict[str, str]:
        headers = {
            "User-Agent": self.user_agent or DEFAULT_USER_AGENT,
            "Referer": referer,
        }
        cookie_header = cookie_header_from_dict(cookies)
        if cookie_header:
            headers["Cookie"] = cookie_header
        return headers

    def reload_cookies(self) -> bool:
        if not self.cookie_reload:
            return False
        self.cookie_reload()
        return True

    def auto_reload_cookies(self) -> bool:
        if self.cookie_auto_reload:
            return self.cookie_auto_reload()
        return self.reload_cookies()

    async def retry_after_cookie_reload(
        self,
        allow_cookie_reload: bool,
        retry: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any] | None:
        if not allow_cookie_reload or not self.auto_reload_cookies():
            return None
        return await retry()

    async def category_node(self, url: str, node_id: str) -> MediaNode | None:
        if is_video_url(url):
            video = await self.video_metadata(url)
            if len(video.get("pages") or []) > 1:
                return node_from_pages(video, node_id)
        if is_watchlater_url(url):
            info = await self.watchlater_light_metadata(url)
            return light_playlist_node(info or {"title": i18n.bilibili_watch_later()}, node_id, url, "", "bilibili_watch_later")
        return await self._collection_folder_node(url, node_id, include_watchlater=False)

    async def category_light_node(self, url: str, node_id: str) -> MediaNode | None:
        if is_search_url(url):
            return MediaNode(
                node_id,
                search_title_from_url(url),
                kind="search",
                remarks_key="search",
            )
        if is_watchlater_url(url):
            info = await self.watchlater_light_metadata(url)
            return light_playlist_node(info or {"title": i18n.bilibili_watch_later()}, node_id, url, "", "bilibili_watch_later")
        if is_favorites_url(url):
            info = await self.favorites_light_metadata(url)
            return light_playlist_node(info, node_id, url, "", "bilibili_favorites")
        if is_medialist_url(url):
            info = await self.medialist_light_metadata(url)
            return light_playlist_node(info, node_id, url, "", "playlist")
        if is_space_collection_url(url):
            info = await self.space_collection_light_metadata(url)
            return light_playlist_node(info, node_id, url, "", "bilibili_collection")
        if is_space_series_url(url):
            info = await self.space_series_light_metadata(url)
            return light_playlist_node(info, node_id, url, "", "bilibili_series")
        if is_space_video_url(url):
            info = await self.space_video_light_metadata(url)
            return light_playlist_node(info, node_id, url, "", "playlist")
        if is_space_audio_url(url):
            info = await self.space_audio_light_metadata(url)
            return light_playlist_node(info, node_id, url, "", "bilibili_audio")
        return None

    async def category_nodes(self, url: str) -> list[MediaNode] | None:
        if is_search_url(url):
            return await self.search_nodes(search_keyword_from_url(url), limit=self.search_limit)
        if not _collection_routes(url):
            return None
        return await self._collection_aggregate_nodes(url)

    async def _collection_folder_node(
        self,
        url: str,
        node_id: str,
        *,
        include_watchlater: bool = True,
    ) -> MediaNode | None:
        collection = await self._collection_metadata(url, include_watchlater=include_watchlater)
        if collection is None:
            return None
        kind, info = collection
        if not _collection_has_items(kind, info):
            return None
        return _collection_folder_node_from_info(kind, info, node_id)

    async def _collection_aggregate_nodes(self, url: str) -> list[MediaNode]:
        collection = await self._collection_metadata(url)
        if collection is None:
            return []
        kind, info = collection
        if not _collection_has_items(kind, info):
            return []
        if kind == "medialist":
            await self.enrich_medialist_entry_pages(info.get("entries") or [])
        return _collection_aggregate_nodes_from_info(kind, info)

    async def _collection_detail_node(self, url: str) -> MediaNode | None:
        collection = await self._collection_metadata(url)
        if collection is None:
            return None
        kind, info = collection
        if not _collection_has_items(kind, info):
            return None
        if kind == "medialist":
            await self.enrich_medialist_entry_pages(info.get("entries") or [])
        return _collection_detail_node_from_info(kind, info, url)

    async def _collection_metadata(
        self,
        url: str,
        *,
        include_watchlater: bool = True,
    ) -> tuple[CollectionKind, dict[str, Any]] | None:
        for kind, load in self._collection_metadata_loaders(url, include_watchlater=include_watchlater):
            info = await load()
            if _collection_has_items(kind, info):
                return kind, info
        return None

    def _collection_metadata_loaders(
        self,
        url: str,
        *,
        include_watchlater: bool = True,
    ) -> list[tuple[CollectionKind, Callable[[], Awaitable[dict[str, Any]]]]]:
        route_loaders: dict[CollectionRoute, Callable[[str], Awaitable[dict[str, Any]]]] = {
            "watchlater": self.watchlater_metadata,
            "favorites": self.favorites_metadata,
            "medialist": self.medialist_metadata,
            "space_collection": self.space_collection_metadata,
            "space_series": self.space_series_metadata,
            "space_video": self.space_video_metadata,
            "bangumi_season": self.bangumi_season_metadata,
            "bangumi_media": self.bangumi_media_metadata,
            "cheese": self.cheese_season_metadata,
            "category": self.category_metadata,
            "channel": self.channel_metadata,
            "space_audio": self.space_audio_metadata,
            "audio": self.audio_album_metadata,
        }
        loaders: list[tuple[CollectionKind, Callable[[], Awaitable[dict[str, Any]]]]] = []
        for route in _collection_routes(url, include_watchlater=include_watchlater):
            loaders.append((COLLECTION_ROUTE_KINDS[route], lambda route=route: route_loaders[route](url)))
        return loaders

    async def enrich_medialist_entry_pages(self, entries: Any) -> None:
        if not isinstance(entries, list):
            return
        targets = [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and entry_bvid(entry)
            and medialist_entry_page_count(entry) <= 1
            and not medialist_entry_has_page_count_hint(entry)
        ]
        if not targets:
            return

        async def enrich(entry: dict[str, Any]) -> None:
            video = await self.video_metadata(f"https://www.bilibili.com/video/{entry_bvid(entry)}")
            videos = positive_int(video.get("videos"))
            if videos:
                entry["videos"] = videos
            pages = dict_list(video.get("pages"))
            if pages:
                entry["pages"] = pages

        await gather_limited(8, *(enrich(entry) for entry in targets))

    async def detail_node(self, url: str) -> MediaNode | None:
        if is_video_url(url):
            video = await self.video_metadata(url)
            if len(video.get("pages") or []) > 1:
                return playable_playlist_node_from_pages(video, url)
            return single_node_from_video_metadata(url, video)
        if is_bangumi_episode_url(url):
            return single_node_from_bangumi_metadata(url, await self.bangumi_episode_metadata(url))
        if is_cheese_episode_url(url):
            return single_node_from_cheese_metadata(url, await self.cheese_episode_metadata(url))
        return await self._collection_detail_node(url)

    def danmaku_url_from_info(self, info: dict[str, Any], base_url: str) -> str:
        return danmaku_url_from_info(info, base_url)


space_audio_light_metadata = _default_space_audio_light_metadata


def _append_limited_entries(entries: list[dict[str, Any]], page_entries: list[dict[str, Any]], limit: int) -> bool:
    entries.extend(page_entries)
    if limit and len(entries) >= limit:
        del entries[limit:]
        return True
    return False


def _collection_has_items(kind: CollectionKind, info: dict[str, Any]) -> bool:
    if kind in {"medialist", "audio"}:
        return bool(info.get("entries"))
    if kind in {"bangumi", "cheese"}:
        return bool(info.get("episodes"))
    return False


def _collection_folder_node_from_info(kind: CollectionKind, info: dict[str, Any], node_id: str) -> MediaNode | None:
    if kind == "medialist":
        return node_from_medialist(info, node_id)
    if kind == "bangumi":
        return node_from_bangumi_season(info, node_id)
    if kind == "cheese":
        return node_from_cheese_season(info, node_id)
    if kind == "audio":
        return node_from_audio_album(info, node_id)
    return None


def _collection_aggregate_nodes_from_info(kind: CollectionKind, info: dict[str, Any]) -> list[MediaNode]:
    if kind == "medialist":
        return aggregate_nodes_from_medialist(info)
    if kind == "bangumi":
        return aggregate_nodes_from_bangumi_season(info)
    if kind == "cheese":
        return aggregate_nodes_from_cheese_season(info)
    if kind == "audio":
        return aggregate_nodes_from_audio_album(info)
    return []


def _collection_detail_node_from_info(kind: CollectionKind, info: dict[str, Any], url: str) -> MediaNode | None:
    if kind == "medialist":
        return playable_playlist_node_from_medialist(info, url)
    if kind == "bangumi":
        return playable_playlist_node_from_bangumi_season(info, url)
    if kind == "cheese":
        return playable_playlist_node_from_cheese_season(info, url)
    if kind == "audio":
        return playable_playlist_node_from_audio_album(info, url)
    return None


