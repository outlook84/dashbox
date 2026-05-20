from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from .. import i18n
from ..config import CodecPreference, Config, ImageProxyMode, Subscription, SubscriptionType, TvboxLocale, UrlItem, enabled_codec_order
from ..config.runtime import RuntimeConfigValues
from ..core import client_selection
from ..core import image_policy
from ..core.client_model import ClientItem, ClientPage, ClientPlay
from ..core.client_service import ClientService
from ..core.navigation_resolver import ResolvedCategory
from ..media.dash_proxy import DashProxyStore
from ..media.playable_cache import PlayableInfoCache
from ..media.scope import PlaybackScope
from ..utils.dicts import compact_dict
from . import tvbox
from . import tvbox_text
from .tvbox_models import Page


class TvboxService(ClientService):
    def __init__(
        self,
        config: Config,
        subscription: Subscription,
        dash_store: DashProxyStore | None = None,
        *,
        runtime_config: RuntimeConfigValues | None = None,
        http_client_provider: Callable[[], Any] | None = None,
        playable_cache: PlayableInfoCache | None = None,
    ) -> None:
        if subscription.type != SubscriptionType.TVBOX:
            raise ValueError("TVBox subscription is required")
        resolved = next((sub for sub in config.subs if sub.id == subscription.id), None)
        if resolved is None or resolved.tvbox is None:
            raise ValueError("TVBox subscription is required")
        super().__init__(
            config,
            resolved.id,
            resolved.tvbox.sources,
            dash_store,
            search_default_provider=resolved.tvbox.effective_search_provider,
            ytdlp_search_prefix=resolved.tvbox.effective_ytdlp_search_prefix,
            ytdlp_search_prefix_mode=resolved.tvbox.ytdlp_search_prefix.mode,
            ytdlp_search_prefix_value=resolved.tvbox.ytdlp_search_prefix.value,
            ytdlp_search_limit=resolved.tvbox.effective_ytdlp_search_limit,
            search_bilibili_limit=resolved.tvbox.effective_bilibili_search_limit,
            search_playlist_limit=resolved.tvbox.effective_playlist_limit,
            search_bilibili_list_limit=resolved.tvbox.effective_bilibili_list_limit,
            runtime_config=runtime_config,
            http_client_provider=http_client_provider,
            playable_cache=playable_cache,
        )
        self.tvbox_sub_id = resolved.id
        self.tvbox_config = resolved.tvbox

    def home(self) -> dict[str, Any]:
        with i18n.use_locale(self.tvbox_config.locale):
            style = self.default_vod_style()
            page = self.home_page()
            classes = self.tvbox_classes_from_home_page(page, style)
            filters = {
                item["type_id"]: [self.order_filter()]
                for item in classes
                if item.get("type_id")
            }
            return {"class": classes, "filters": filters, "list": []}

    @staticmethod
    def tvbox_classes_from_home_page(page: ClientPage, style: str) -> list[dict[str, Any]]:
        classes = [
            {
                "type_id": item.id,
                "type_name": item.title,
                "type_flag": tvbox.type_flag_for_vod_style(style),
                **tvbox.vod_style_fields(style),
            }
            for item in page.items
        ]
        if classes:
            return classes
        return [{
            "type_id": "demo",
            "type_name": i18n.tvbox_demo(),
            "type_flag": tvbox.type_flag_for_vod_style(style),
            **tvbox.vod_style_fields(style),
        }]

    async def category(self, tid: str, base_url: str = "", *, refresh: bool = False) -> dict[str, Any]:
        with i18n.use_locale(self.tvbox_config.locale):
            source = self.config_tree.source_by_id(tid)
            if source:
                return self.category_page_from_client_page(await self.item_page(tid, base_url, refresh=refresh), base_url)
            folder_item = self.config_tree.folder_item_by_id(tid)
            if folder_item:
                return self.category_page_from_client_page(await self.item_page(tid, base_url, refresh=refresh), base_url)
            url_item = self.config_tree.url_item_by_id(tid)
            if url_item:
                category = await self.url_category(url_item.url, base_url, refresh=refresh)
                page = self.category_page(category["vods"], url_item.title or category["name"], self.default_vod_style())
                self.apply_category_metadata(page, category)
                return page
            tid = await self.normalize_config_url(tid)
            if tid.startswith(("http://", "https://")):
                category = await self.url_category(tid, base_url, refresh=refresh)
                page = self.category_page(category["vods"], category["name"], self.default_vod_style())
                self.apply_category_metadata(page, category)
                return page
            if tid == "demo":
                return self.category_page_from_client_page(
                    ClientPage(
                        title=i18n.tvbox_demo(),
                        items=(ClientItem(
                            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                            i18n.tvbox_demo_youtube_video(),
                            subtitle=i18n.tvbox_demo_remarks(),
                        ),),
                        total_items=1,
                    ),
                    base_url,
                )
            return self.category_page([], "", self.default_vod_style())

    def category_page_from_client_page(self, page: ClientPage, base_url: str = "") -> dict[str, Any]:
        result = self.category_page(
            [self.vod_from_client_item(item, base_url) for item in page.items],
            page.title,
            self.default_vod_style(),
        )
        result["dashbox_refreshable"] = page.refreshable
        if page.refresh is not None:
            result["dashbox_refresh"] = page.refresh
        return result

    @staticmethod
    def category_page(vods: list[dict[str, Any]], name: str = "", style: str = tvbox.DEFAULT_VOD_STYLE) -> dict[str, Any]:
        page = Page(vods).to_dict()
        if name:
            page["dashbox_category_name"] = name
        return tvbox.decorate_page_style(page, style)

    @staticmethod
    def apply_category_metadata(page: dict[str, Any], category: dict[str, Any]) -> None:
        if "dashbox_refreshable" in category:
            page["dashbox_refreshable"] = category["dashbox_refreshable"]
        refresh = category.get("dashbox_refresh")
        if isinstance(refresh, dict):
            page["dashbox_refresh"] = refresh

    def default_vod_style(self) -> str:
        return tvbox.normalize_vod_style(self.tvbox_config.vod_style)

    def image_base_url(self, base_url: str) -> str:
        return base_url if self.config.image_proxy_mode != ImageProxyMode.OFF else ""

    def vod_from_client_item(self, item: ClientItem, base_url: str = "") -> dict[str, Any]:
        if item.art.thumb:
            item = replace(
                item,
                art=replace(
                    item.art,
                    thumb=image_policy.proxied_thumbnail_url(
                        item.art.thumb,
                        self.image_base_url(base_url),
                        self.config.image_proxy_mode,
                    ),
                ),
            )
        return tvbox.vod_from_client_item(item)

    async def url_category(self, url: str, base_url: str = "", *, refresh: bool = False) -> dict[str, Any]:
        result = await self.directory_snapshot_result(url, refresh=refresh)
        category = self.tvbox_category_from_resolved(result.snapshot.category, base_url)
        if result.refresh.requested:
            category["dashbox_refresh"] = result.refresh.to_dict()
        return category

    def tvbox_category_from_resolved(self, category: ResolvedCategory, base_url: str = "") -> dict[str, Any]:
        page = self.client_page_from_resolved_category(category, refreshable=True)
        vods = [self.vod_from_client_item(item, base_url) for item in page.items]
        if category.add_playlist_detail_ids and category.playlist_url and not category.allow_full_selected_detail:
            vods = tvbox.with_playlist_metadata_detail(vods)
        if not vods and category.unavailable_url:
            vods = [tvbox.unavailable_vod(category.unavailable_url)]
        return {"vods": vods, "name": category.name, "dashbox_refreshable": page.refreshable}

    async def search(self, key: str, base_url: str = "") -> dict[str, Any]:
        with i18n.use_locale(self.tvbox_config.locale):
            page = await self.search_page(key, base_url)
            return tvbox.decorate_page_style(
                Page([self.vod_from_client_item(item, base_url) for item in page.items]).to_dict(),
                self.default_vod_style(),
            )

    async def detail(self, raw_id: str, base_url: str = "") -> dict[str, Any]:
        with i18n.use_locale(self.tvbox_config.locale):
            raw_id = await self.normalize_config_url(raw_id)
            playlist_detail_id = client_selection.decode_selection_id(raw_id)
            if playlist_detail_id:
                return await self.playlist_item_detail(
                    playlist_detail_id["playlist_url"],
                    playlist_detail_id["selected_url"],
                    playlist_detail_id.get("selected_key", ""),
                    base_url,
                )
            url_item = self.config_tree.url_item_by_id(raw_id)
            if url_item:
                return await self.url_item_detail(url_item, base_url)
            if self.url_is_known_leaf(raw_id):
                return await self.single_video_detail(raw_id, base_url)
            return self.tvbox_detail_from_client_page(await self.detail_page(raw_id, base_url), base_url)

    def tvbox_detail_from_client_page(self, page: ClientPage, base_url: str = "") -> dict[str, Any]:
        vods = [self.vod_from_client_item(item, base_url) for item in page.items]
        if not vods:
            return compact_dict(list=[])
        return compact_dict(list=vods)

    async def url_item_detail(self, item: UrlItem, base_url: str = "") -> dict[str, Any]:
        value = self.tvbox_detail_from_client_page(
            await self.url_item_detail_page(item, base_url),
            base_url,
        )
        vods = value.get("list")
        if isinstance(vods, list) and vods and isinstance(vods[0], dict):
            if item.title and vods[0].get("vod_play_url"):
                vods[0]["vod_play_url"] = tvbox.rewrite_first_episode_title(vods[0]["vod_play_url"], item.title)
        return value

    @staticmethod
    def order_filter() -> dict[str, Any]:
        return {
            "key": "order",
            "name": i18n.tvbox_order(),
            "init": "source",
            "value": [
                {"n": i18n.tvbox_order_source(), "v": "source"},
                {"n": i18n.tvbox_order_reverse(), "v": "reverse"},
            ],
        }

    async def single_video_detail(self, raw_id: str, base_url: str = "") -> dict[str, Any]:
        return self.tvbox_detail_from_client_page(await self.single_video_detail_page(raw_id, base_url), base_url)

    async def single_video_full_detail(self, clean_id: str, base_url: str = "") -> dict[str, Any]:
        return self.tvbox_detail_from_client_page(await self.single_video_full_detail_page(clean_id, base_url), base_url)

    async def play(self, play_value: str, base_url: str = "") -> dict[str, Any]:
        raw_id = tvbox_text.restore_play_value(play_value)
        return self.tvbox_play_from_client_play(
            await self.play_item(raw_id, base_url, scope=self.playback_scope())
        )

    @staticmethod
    def tvbox_play_from_client_play(play: ClientPlay) -> dict[str, Any]:
        subtitles = [
            {
                "name": subtitle.name,
                "lang": subtitle.language,
                "url": subtitle.url,
                "ext": subtitle.format,
                "format": tvbox_subtitle_format(subtitle.format),
            }
            for subtitle in play.subtitles
        ]
        return compact_dict(
            parse=0,
            url=play.url,
            header=dict(play.headers),
            subs=subtitles,
            danmaku=play.danmaku_url,
        )

    def playback_scope(self) -> PlaybackScope:
        return PlaybackScope(
            protocol="tvbox",
            sub_id=self.tvbox_sub_id,
            policy_hash=self.playback_policy_hash(),
            video_codec_order=tuple(str(codec) for codec in enabled_codec_order(self.tvbox_config.video_codec_preferences)),
            audio_codec_order=tuple(str(codec) for codec in enabled_codec_order(self.tvbox_config.audio_codec_preferences)),
            max_video_height=self.tvbox_config.max_video_height,
            max_video_fps=self.tvbox_config.max_video_fps,
            proxy_dash_media_url=self.config.proxy_dash_media_url,
            subtitle_languages=tvbox_subtitle_languages(self.tvbox_config.locale),
            youtube_subtitles=self.tvbox_config.youtube_subtitles,
        )

    def playback_policy_hash(self) -> str:
        value = "\0".join((
            *codec_preference_hash_parts("video_codec_preferences", self.tvbox_config.video_codec_preferences),
            *codec_preference_hash_parts("audio_codec_preferences", self.tvbox_config.audio_codec_preferences),
            f"max_video_height={self.tvbox_config.max_video_height}",
            f"max_video_fps={self.tvbox_config.max_video_fps}",
            f"proxy_dash_media_url={self.config.proxy_dash_media_url}",
            f"locale={self.tvbox_config.locale}",
            f"youtube_subtitles={self.tvbox_config.youtube_subtitles}",
        ))
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

    async def playlist_item_detail(
        self,
        playlist_url: str,
        selected_url: str,
        selected_key: str = "",
        base_url: str = "",
    ) -> dict[str, Any]:
        with i18n.use_locale(self.tvbox_config.locale):
            snapshot = await self.directory_snapshot(playlist_url)
            category = snapshot.category
            detail_playlist_url = category.playlist_url or playlist_url
            page = self.client_page_from_resolved_category(category)
            if not category.nodes and category.unavailable_url:
                return compact_dict(list=[tvbox.unavailable_vod(category.unavailable_url or selected_url or playlist_url)])
            if (
                selected_url != client_selection.SELECTION_DIRECTORY_SELECTED_URL
                and self.selected_playlist_item(page.items, selected_url, selected_key) is None
            ):
                return await self.detail(selected_url, base_url)
            return await self.playlist_item_detail_page_with_metadata(
                page,
                detail_playlist_url,
                selected_url,
                selected_key,
                base_url,
                allow_full_selected_detail=category.allow_full_selected_detail or self.playlist_item_supports_full_detail(selected_url),
            )

    async def playlist_item_detail_page_with_metadata(
        self,
        page: ClientPage,
        playlist_url: str,
        selected_url: str,
        selected_key: str = "",
        base_url: str = "",
        *,
        allow_full_selected_detail: bool = True,
    ) -> dict[str, Any]:
        detail_page = self.client_playlist_detail_page(page, playlist_url, selected_url, selected_key)
        detail = self.tvbox_detail_from_client_page(detail_page, base_url)
        if selected_url == client_selection.SELECTION_DIRECTORY_SELECTED_URL:
            return detail
        clean_selected = client_selection.without_episode_index(selected_url)
        if not allow_full_selected_detail:
            self.start_playlist_item_playable_prewarm(clean_selected)
            return detail
        if not self.playlist_item_supports_full_detail(clean_selected):
            self.start_playlist_item_playable_prewarm(clean_selected)
            return detail
        full_detail = await self.playlist_item_full_detail(clean_selected, base_url)
        full_vods = full_detail.get("list")
        detail_vods = detail.get("list")
        if not (
            isinstance(full_vods, list)
            and full_vods
            and isinstance(full_vods[0], dict)
            and isinstance(detail_vods, list)
            and detail_vods
            and isinstance(detail_vods[0], dict)
        ):
            return detail
        if full_vods[0].get("vod_name") == clean_selected and not full_vods[0].get("vod_content"):
            return detail
        merged = dict(detail_vods[0])
        for key in ("vod_name", "vod_pic", "vod_content"):
            value = full_vods[0].get(key)
            if value:
                merged[key] = value
        detail_vods[0] = merged
        return detail

    async def playlist_item_full_detail(self, clean_id: str, base_url: str = "") -> dict[str, Any]:
        return self.tvbox_detail_from_client_page(await self.playlist_item_full_detail_page(clean_id, base_url), base_url)


    def start_playlist_item_playable_prewarm(self, clean_id: str) -> None:
        if clean_id.startswith(("http://", "https://")) and not self.playlist_item_supports_full_detail(clean_id):
            self.start_single_video_playable_prewarm(clean_id)


def tvbox_subtitle_languages(locale: TvboxLocale) -> tuple[str, ...]:
    if locale == TvboxLocale.ZH_CN:
        return (locale.value, "en")
    return (locale.value, "zh-CN")


def tvbox_subtitle_format(value: str) -> str:
    format_value = value.strip().lower()
    return {
        "srt": "application/x-subrip",
        "vtt": "text/vtt",
        "ssa": "text/x-ssa",
        "ass": "text/x-ssa",
        "ttml": "application/ttml+xml",
        "dfxp": "application/ttml+xml",
        "xml": "application/ttml+xml",
    }.get(format_value, value)


def codec_preference_hash_parts(label: str, preferences: tuple[CodecPreference, ...]) -> tuple[str, ...]:
    return (label, *(f"{preference.codec.value}={preference.enabled}" for preference in preferences))
