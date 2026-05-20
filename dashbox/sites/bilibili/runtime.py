from __future__ import annotations

import urllib.request
from collections.abc import Callable
from typing import Any

from ...config import Config
from ...media.ytdlp_client import BrowserCookieProvider, YtdlpClient
from ...models import NodeKind
from . import site as bilibili


class BilibiliCookieProvider:
    def __init__(self, browser_cookies: BrowserCookieProvider) -> None:
        self.browser_cookies = browser_cookies

    @property
    def cookiejar(self) -> Any | None:
        return self.browser_cookies.cookiejar

    @cookiejar.setter
    def cookiejar(self, value: Any | None) -> None:
        self.browser_cookies.cookiejar = value

    @property
    def loaded(self) -> bool:
        return self.browser_cookies.loaded

    @loaded.setter
    def loaded(self, value: bool) -> None:
        self.browser_cookies.loaded = value

    def cookie_header(self, url: str) -> str:
        cookiejar = self.get_cookiejar()
        if not cookiejar:
            return ""
        request = urllib.request.Request(url)
        cookiejar.add_cookie_header(request)
        return request.get_header("Cookie") or ""

    def get_cookiejar(self) -> Any | None:
        return self.browser_cookies.get_cookiejar()

    def reload(self) -> None:
        self.browser_cookies.reload()

    def auto_reload(self) -> bool:
        return self.browser_cookies.auto_reload()


class BilibiliRuntime:
    name = "bilibili"

    def __init__(
        self,
        config: Config,
        ytdlp: YtdlpClient,
        *,
        bilibili_list_limit: int | None = None,
        bilibili_search_limit: int | None = None,
        http_client_provider: Callable[[], Any] | None = None,
    ) -> None:
        self.cookies = BilibiliCookieProvider(ytdlp.browser_cookies)
        list_limit = config.effective_bilibili_list_limit if bilibili_list_limit is None else bilibili_list_limit
        search_limit = config.effective_bilibili_search_limit if bilibili_search_limit is None else bilibili_search_limit
        self.site = bilibili.BilibiliSite(
            config.effective_user_agent,
            config.upstream_timeout,
            list_limit,
            search_limit,
            self.cookies.cookie_header,
            self.cookies.reload,
            self.cookies.auto_reload,
            http_client_provider=http_client_provider,
        )
        self.search_limit = search_limit

    def supports_url(self, url: str) -> bool:
        return bilibili.matches_url(url)

    async def playable_extract_url(self, raw_id: str, extract_url: str = "") -> str:
        return extract_url or await self.site.resolve_extract_url(raw_id)

    def blocking_playable_extract_url(self, raw_id: str, extract_url: str = "") -> str:
        return extract_url or self.site._extract_url_for_blocking_call(raw_id)

    def cookie_header(self, url: str) -> str:
        return self.cookies.cookie_header(url)

    def cookiejar(self) -> Any | None:
        return self.cookies.get_cookiejar()

    def reload_cookiejar(self) -> None:
        self.cookies.reload()

    async def normalize_config_url(self, url: str) -> str:
        return await self.site.normalize_config_url(url)

    async def config_node_from_url_item_with_directory(
        self,
        url: str,
        node_id: str,
        config_kind: NodeKind,
    ) -> tuple[Any | None, bool]:
        light_node = await self.site.category_light_node(url, node_id)
        if light_node:
            return light_node, True
        node = await self.site.category_node(url, node_id)
        if node:
            return node, config_kind == NodeKind.PLAYLIST_DIRECTORY
        return None, False

    async def category_nodes_with_title(self, url: str) -> tuple[list[Any], str] | None:
        nodes = await self.site.category_nodes(url)
        if nodes is None:
            return None
        title_node = await self.site.category_node(url, url)
        return nodes, title_node.title if title_node else ""

    async def search_nodes(self, key: str) -> list[Any]:
        return await self.site.search_nodes(key, limit=self.search_limit)

    async def detail_node(self, url: str) -> Any | None:
        return await self.site.detail_node(url)

    async def display_metadata(self, raw_id: str) -> dict[str, Any] | None:
        if bilibili.supports_video_api_metadata(raw_id):
            info = await self.site.video_metadata(raw_id)
            if info:
                return {
                    "webpage_url": raw_id,
                    "title": info.get("title"),
                    "thumbnail": info.get("pic"),
                    "duration": info.get("duration"),
                    "description": info.get("desc"),
                }
        if bilibili.is_single_playable_url(raw_id):
            return {}
        return None

    def danmaku_url_from_info(self, info: dict[str, Any], base_url: str) -> str:
        return self.site.danmaku_url_from_info(info, base_url)
