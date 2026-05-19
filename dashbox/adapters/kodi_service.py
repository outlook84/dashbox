from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace
from typing import Any
from urllib.parse import urlsplit

from ..config import (
    Config,
    CodecPreference,
    SearchProvider,
    Source,
    UrlItem,
    Subscription,
    SubscriptionType,
    YtdlpSearchPrefixMode,
    enabled_codec_order,
    parse_audio_codec_preferences,
    parse_max_video_fps,
    parse_max_video_height,
    parse_video_codec_preferences,
)
from .. import i18n
from ..core import client_selection
from ..core.client_model import ClientAction, ClientInputStream, ClientItem, ClientPage, ClientPlay, item_from_media_node, with_item_overrides
from ..core.client_service import ClientService
from ..core.navigation_resolver import resolve_config_item
from ..models import NodeKind
from ..media.dash_proxy import DashProxyStore
from ..media.playable_cache import PlayableInfoCache
from ..media.scope import PlaybackScope
from . import kodi


KODI_ROOT_SOURCE_ID = "root"


class KodiService(ClientService):
    def __init__(
        self,
        config: Config,
        subscription: Subscription,
        dash_store: DashProxyStore | None = None,
        *,
        http_client_provider: Callable[[], Any] | None = None,
        playable_cache: PlayableInfoCache | None = None,
    ) -> None:
        if subscription.type != SubscriptionType.KODI or subscription.kodi is None:
            raise ValueError("Kodi subscription is required")
        effective_config = config.with_kodi_overrides(subscription.kodi)
        super().__init__(
            effective_config,
            subscription.id,
            (Source(KODI_ROOT_SOURCE_ID, "", subscription.kodi.sources),),
            dash_store,
            http_client_provider=http_client_provider,
            playable_cache=playable_cache,
        )
        self.kodi_sub_id = subscription.id
        self.kodi_config = subscription.kodi

    def page_response(self, page: ClientPage, base_url: str = "") -> dict[str, Any]:
        return kodi.page_to_dict(page, self.config, base_url)

    def play_response(self, play: ClientPlay) -> dict[str, Any]:
        return kodi.play_to_dict(with_kodi_inputstream(play))

    async def root_page(self, base_url: str = "") -> ClientPage:
        items = (
            *tuple(await self.config_items_to_client_items(KODI_ROOT_SOURCE_ID, self.kodi_config.sources, base_url)),
            ClientItem(id="", title=kodi_search_title(self.config), kind="search", is_folder=True),
        )
        return self.with_kodi_playable_items(ClientPage(items=items, total_items=len(items)))

    async def search_page(
        self,
        key: str,
        base_url: str = "",
        *,
        locale: str = "",
    ) -> ClientPage:
        page = await super().search_page(key, base_url, locale=locale)
        return self.with_kodi_playable_items(page)

    async def item_page(
        self,
        item_id: str,
        base_url: str = "",
        *,
        refresh: bool = False,
        locale: str = "",
    ) -> ClientPage:
        url_item = self.config_tree.url_item_by_id(item_id)
        if url_item:
            return await self.kodi_page_from_config_url_item(item_id, url_item, base_url, refresh=refresh)
        if item_id.startswith(("http://", "https://")):
            return await self.kodi_category_page(item_id, base_url, refresh=refresh)
        page = await super().item_page(item_id, base_url, refresh=refresh, locale=locale)
        return self.with_kodi_playable_items(page)

    async def url_item_client_item(self, item_id: str, item: UrlItem, base_url: str = "") -> ClientItem:
        resolved = await resolve_config_item(self, item_id, item)
        client_item = item_from_media_node(resolved.node, is_folder=True if resolved.directory else None)
        client_item = with_item_overrides(
            client_item,
            item_id=item_id,
            title=item.title,
            thumbnail=item.pic,
            subtitle=item.remarks,
        )
        if resolved.directory:
            return client_item
        play_url = client_item.play_url or resolved.node.play_url
        if not play_url and client_item.node_kind == NodeKind.LEAF_VOD.value:
            play_url = resolved.source_url
        return self.with_kodi_playable_item(client_item, play_url=play_url)

    async def kodi_page_from_config_url_item(
        self,
        item_id: str,
        item: UrlItem,
        base_url: str = "",
        *,
        refresh: bool = False,
    ) -> ClientPage:
        url = await self.normalize_config_url(item.url)
        if self.node_kind_from_config_url(url) == NodeKind.AGGREGATE_VOD:
            page = await self.detail_page(url, base_url)
        else:
            page = await self.kodi_category_page(url, base_url, refresh=refresh)
        title = item.title or page.title
        return ClientPage(
            id=item_id,
            title=title,
            content_type=page.content_type,
            items=page.items,
            total_items=page.total_items,
            cache_to_disc=page.cache_to_disc,
            update_listing=page.update_listing,
            refreshable=page.refreshable,
            refresh=page.refresh,
        )

    async def kodi_category_page(self, url: str, base_url: str = "", *, refresh: bool = False) -> ClientPage:
        result = await self.directory_snapshot_result(url, refresh=refresh)
        page = self.client_page_from_resolved_category(result.snapshot.category, page_id=url, refreshable=True)
        if result.refresh.requested:
            page = ClientPage(
                id=page.id,
                title=page.title,
                content_type=page.content_type,
                items=page.items,
                total_items=page.total_items,
                cache_to_disc=page.cache_to_disc,
                update_listing=page.update_listing,
                refreshable=page.refreshable,
                refresh=result.refresh.to_dict(),
            )
        return self.with_kodi_playable_items(page)

    async def play(self, play_id: str, base_url: str = "", playback_preferences: Any | None = None) -> dict[str, Any]:
        return self.play_response(
            await self.play_item(
                play_id,
                base_url,
                scope=self.playback_scope(playback_preferences),
            )
        )

    async def detail_page(
        self,
        item_id: str,
        base_url: str = "",
        *,
        locale: str = "",
    ) -> ClientPage:
        playlist_detail_id = client_selection.decode_selection_id(item_id)
        if playlist_detail_id:
            snapshot = await self.directory_snapshot(playlist_detail_id["playlist_url"])
            page = self.client_page_from_resolved_category(snapshot.category)
            page = self.client_playlist_detail_page(
                page,
                snapshot.category.playlist_url or playlist_detail_id["playlist_url"],
                playlist_detail_id["selected_url"],
                playlist_detail_id.get("selected_key", ""),
            )
        else:
            page = await super().detail_page(item_id, base_url, locale=locale)
        return self.with_kodi_playable_items(page)

    def with_kodi_playable_items(self, page: ClientPage) -> ClientPage:
        return ClientPage(
            id=page.id,
            title=page.title,
            content_type=page.content_type,
            items=tuple(self.with_kodi_playable_item(item) for item in page.items),
            total_items=page.total_items,
            cache_to_disc=page.cache_to_disc,
            update_listing=page.update_listing,
            refreshable=page.refreshable,
            refresh=page.refresh,
        )

    def with_kodi_playable_item(self, item: ClientItem, *, play_url: str = "") -> ClientItem:
        if item.is_folder or item.kind in {"folder", "search", "error"}:
            return item
        if item.episodes:
            return item
        if item.selected_url == client_selection.SELECTION_DIRECTORY_SELECTED_URL:
            return replace(
                item,
                is_playable=True,
                actions=(*item.actions, ClientAction("play", id=item.id, endpoint="play-directory")),
            )
        playable = play_url or item.play_url or item.selected_url
        if not playable and item.node_kind == NodeKind.LEAF_VOD.value:
            playable = url_id(item.id)
        if not playable and item.node_kind not in {NodeKind.AGGREGATE_VOD.value, NodeKind.PLAYLIST_DIRECTORY.value}:
            playable = url_id(item.id)
        if not playable or playable == client_selection.SELECTION_DIRECTORY_SELECTED_URL:
            if item.node_kind in {NodeKind.AGGREGATE_VOD.value, NodeKind.PLAYLIST_DIRECTORY.value}:
                return replace(
                    item,
                    is_folder=True,
                    actions=(*item.actions, ClientAction("open", id=item.id, endpoint="items")),
                )
            return item
        if (
            item.is_playable
            and item.play_url == playable
            and any(action.kind == "play" and action.endpoint == "play" and action.id == playable for action in item.actions)
        ):
            return item
        return replace(
            item,
            is_folder=False,
            is_playable=True,
            play_url=playable,
            actions=(*item.actions, ClientAction("play", id=playable, endpoint="play")),
        )

    def playback_scope(self, playback_preferences: Any | None = None) -> PlaybackScope:
        prefs = playback_preferences if isinstance(playback_preferences, dict) else {}
        video_codec_preferences = parse_optional_video_codec_preferences(prefs.get("video_codec_preferences"))
        audio_codec_preferences = parse_optional_audio_codec_preferences(prefs.get("audio_codec_preferences"))
        max_video_height = parse_optional_max_video_height(prefs.get("max_video_height"))
        max_video_fps = parse_optional_max_video_fps(prefs.get("max_video_fps"))
        subtitle_languages = parse_subtitle_languages(prefs.get("subtitle_languages"))
        youtube_subtitles = parse_bool_pref(prefs.get("youtube_subtitles"))
        return PlaybackScope(
            protocol="kodi",
            sub_id=self.kodi_sub_id,
            policy_hash=self.playback_policy_hash(
                video_codec_preferences,
                audio_codec_preferences,
                max_video_height,
                max_video_fps,
                subtitle_languages,
                youtube_subtitles,
            ),
            video_codec_order=tuple(str(codec) for codec in enabled_codec_order(video_codec_preferences)),
            audio_codec_order=tuple(str(codec) for codec in enabled_codec_order(audio_codec_preferences)),
            max_video_height=max_video_height,
            max_video_fps=max_video_fps,
            proxy_dash_media_url=self.config.proxy_dash_media_url,
            subtitle_languages=subtitle_languages,
            youtube_subtitles=youtube_subtitles,
            all_manual_subtitles=True,
        )

    def playback_policy_hash(
        self,
        video_codec_preferences: tuple[CodecPreference, ...],
        audio_codec_preferences: tuple[CodecPreference, ...],
        max_video_height: int,
        max_video_fps: int,
        subtitle_languages: tuple[str, ...],
        youtube_subtitles: bool,
    ) -> str:
        value = "\0".join((
            *codec_preference_hash_parts("video_codec_preferences", video_codec_preferences),
            *codec_preference_hash_parts("audio_codec_preferences", audio_codec_preferences),
            f"max_video_height={max_video_height}",
            f"max_video_fps={max_video_fps}",
            f"proxy_dash_media_url={self.config.proxy_dash_media_url}",
            "subtitle_languages",
            *subtitle_languages,
            f"youtube_subtitles={youtube_subtitles}",
            "all_manual_subtitles=True",
        ))
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def parse_optional_video_codec_preferences(value: Any) -> tuple[CodecPreference, ...]:
    if value is None:
        return ()
    return parse_video_codec_preferences(value)


def parse_optional_audio_codec_preferences(value: Any) -> tuple[CodecPreference, ...]:
    if value is None:
        return ()
    return parse_audio_codec_preferences(value)


def codec_preference_hash_parts(label: str, preferences: tuple[CodecPreference, ...]) -> tuple[str, ...]:
    return (label, *(f"{preference.codec.value}={preference.enabled}" for preference in preferences))


def parse_optional_max_video_height(value: Any) -> int:
    if value is None:
        return 0
    return parse_max_video_height(value, "playback.max_video_height")


def parse_optional_max_video_fps(value: Any) -> int:
    if value is None:
        return 0
    return parse_max_video_fps(value, "playback.max_video_fps")


def parse_subtitle_languages(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        values = value.split(",")
    elif isinstance(value, list | tuple):
        values = value
    else:
        return ()
    out: list[str] = []
    for item in values:
        lang = str(item).strip()
        if lang and lang not in out:
            out.append(lang)
    return tuple(out)


def parse_bool_pref(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def url_id(value: str) -> str:
    return value if value.startswith(("http://", "https://")) else ""


def kodi_search_title(config: Config) -> str:
    if config.default_search_provider == SearchProvider.BILIBILI:
        return i18n.site_search_title(i18n.text("site.bilibili"), "")
    if config.ytdlp_search_prefix.mode == YtdlpSearchPrefixMode.YOUTUBE:
        return i18n.site_search_title(i18n.text("site.youtube"), "")
    if config.ytdlp_search_prefix.mode == YtdlpSearchPrefixMode.BILIBILI:
        return i18n.site_search_title(i18n.text("site.bilibili"), "")
    if config.ytdlp_search_prefix.mode == YtdlpSearchPrefixMode.SOUNDCLOUD:
        return i18n.site_search_title("SoundCloud", "")
    if config.ytdlp_search_prefix.value:
        return i18n.site_search_title(config.ytdlp_search_prefix.value, "")
    return i18n.site_search_title("yt-dlp", "")


def with_kodi_inputstream(play: ClientPlay) -> ClientPlay:
    if play.inputstream is not None and play.inputstream.addon:
        return play
    manifest_type = kodi_manifest_type(play.url, play.mime_type)
    if not manifest_type:
        return play
    return replace(
        play,
        inputstream=ClientInputStream(
            addon="inputstream.adaptive",
            manifest_type=manifest_type,
            manifest_headers=play.headers,
            stream_headers=play.headers,
        ),
    )


def kodi_manifest_type(url: str, mime_type: str = "") -> str:
    mime = mime_type.lower()
    if "dash+xml" in mime:
        return "mpd"
    if "mpegurl" in mime or "vnd.apple.mpegurl" in mime:
        return "hls"
    value = url.lower()
    if value.startswith("data:application/dash+xml"):
        return "mpd"
    path = urlsplit(value).path
    if path.endswith(".mpd"):
        return "mpd"
    if path.endswith((".m3u8", ".m3u")):
        return "hls"
    return ""
