from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from .model import (
    BrowserCookiesConfig,
    CodecPreference,
    Config,
    ConfigItem,
    KodiSubscriptionConfig,
    Source,
    Subscription,
    TvboxSubscriptionConfig,
    UrlItem,
    YtdlpSearchPrefixConfig,
)

def config_to_json_data(config: Config) -> dict[str, Any]:
    return {
        "proxy_media_idle_ttl_seconds": config.proxy_media_idle_ttl_seconds,
        "proxy_dash_media_url": config.proxy_dash_media_url,
        "ytdlp_concurrency": config.ytdlp_concurrency,
        "log_level": config.log_level.value,
        "user_agent": config.user_agent,
        "cookies_from_browser": browser_cookies_config_to_json_data(config.cookies_from_browser),
        "subs": [subscription_to_json_data(sub) for sub in config.subs],
    }


def config_defaults_to_json_data() -> dict[str, Any]:
    config = Config()
    return {
        "default_search_provider": config.default_search_provider.value,
        "ytdlp_search_prefix": ytdlp_search_prefix_to_json_data(config.ytdlp_search_prefix),
        "ytdlp_search_limit": config.ytdlp_search_limit,
        "bilibili_search_limit": config.bilibili_search_limit,
        "playlist_limit": config.playlist_limit,
        "bilibili_list_limit": config.bilibili_list_limit,
        "proxy_media_idle_ttl_seconds": config.proxy_media_idle_ttl_seconds,
        "ytdlp_concurrency": config.ytdlp_concurrency,
    }


def minimal_config_file_data() -> dict[str, Any]:
    return {"subs": []}


def browser_cookies_config_to_json_data(config: BrowserCookiesConfig) -> dict[str, Any]:
    data: dict[str, Any] = {"mode": config.mode.value}
    if config.value:
        data["value"] = config.value
    return data


def subscription_to_json_data(sub: Subscription) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": sub.id,
        "type": sub.type.value,
        "auth_mode": sub.auth_mode.value,
    }
    if sub.access_code_hash:
        data["access_code_hash"] = sub.access_code_hash
    if sub.tvbox is not None:
        data["tvbox"] = tvbox_subscription_to_json_data(sub.tvbox)
    if sub.kodi is not None:
        data["kodi"] = kodi_subscription_to_json_data(sub.kodi)
    return data


def tvbox_subscription_to_json_data(config: TvboxSubscriptionConfig) -> dict[str, Any]:
    data: dict[str, Any] = {
        "site_key": config.site_key,
        "site_name": config.site_name,
        "locale": config.locale.value,
        "sources": [source_to_json_data(source) for source in config.sources],
        "video_codec_preferences": codec_preferences_to_json_data(config.video_codec_preferences),
        "audio_codec_preferences": codec_preferences_to_json_data(config.audio_codec_preferences),
        "max_video_height": config.max_video_height,
        "max_video_fps": config.max_video_fps,
        "youtube_subtitles": config.youtube_subtitles,
        "vod_style": config.vod_style.value,
    }
    add_optional_subscription_overrides(data, config)
    return data


def codec_preferences_to_json_data(preferences: tuple[CodecPreference, ...]) -> list[dict[str, Any]]:
    return [{"codec": preference.codec.value, "enabled": preference.enabled} for preference in preferences]


def kodi_subscription_to_json_data(config: KodiSubscriptionConfig) -> dict[str, Any]:
    data: dict[str, Any] = {
        "sources": [item_to_json_data(item) for item in config.sources],
    }
    if config.root is not None:
        data["root"] = config.root
    add_optional_subscription_overrides(data, config)
    return data


def add_optional_subscription_overrides(data: dict[str, Any], config: Any) -> None:
    if config.search_provider is not None:
        data["search_provider"] = config.search_provider.value
    if config.ytdlp_search_prefix is not None:
        data["ytdlp_search_prefix"] = ytdlp_search_prefix_to_json_data(config.ytdlp_search_prefix)
    for key in ("ytdlp_search_limit", "bilibili_search_limit", "playlist_limit", "bilibili_list_limit"):
        value = getattr(config, key)
        if value is not None:
            data[key] = value


def ytdlp_search_prefix_to_json_data(config: YtdlpSearchPrefixConfig) -> dict[str, Any]:
    data: dict[str, Any] = {"mode": config.mode.value}
    if config.value:
        data["value"] = config.value
    return data


def source_to_json_data(source: Source) -> dict[str, Any]:
    return {
        "id": source.id,
        "name": source.name,
        "items": [item_to_json_data(item) for item in source.items],
    }


def item_to_json_data(item: ConfigItem) -> dict[str, Any]:
    if isinstance(item, UrlItem):
        data: dict[str, Any] = {"url": item.url}
        if item.title:
            data["title"] = item.title
    else:
        data = {
            "name": item.name,
            "items": [item_to_json_data(child) for child in item.items],
        }
    if item.pic:
        data["pic"] = item.pic
    if item.remarks:
        data["remarks"] = item.remarks
    if item.id:
        data["id"] = item.id
    return data


def write_config_file(path: str | Path, data: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    backup = target.with_name(target.name + ".bak")
    tmp = target.with_name(f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(content, encoding="utf-8")
        if target.exists():
            backup.write_bytes(target.read_bytes())
        tmp.replace(target)
    finally:
        if tmp.exists():
            tmp.unlink()

