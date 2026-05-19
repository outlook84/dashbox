from __future__ import annotations

from typing import Any

from ..auth.access_code import (
    ADMIN_ACCESS_CODE_MAX_LENGTH,
    ADMIN_ACCESS_CODE_MIN_LENGTH,
    SUBSCRIPTION_ACCESS_CODE_MAX_LENGTH,
    SUBSCRIPTION_ACCESS_CODE_MIN_LENGTH,
)
from .model import (
    AudioCodec,
    AuthMode,
    BrowserCookiesMode,
    LogLevel,
    MAX_LIST_LIMIT,
    MAX_PROXY_MEDIA_IDLE_TTL_SECONDS,
    MAX_SEARCH_LIMIT,
    MAX_YTDLP_CONCURRENCY,
    SUPPORTED_MAX_VIDEO_FPS,
    SUPPORTED_MAX_VIDEO_HEIGHTS,
    SearchProvider,
    SubscriptionType,
    TvboxLocale,
    VideoCodec,
    VodStyle,
    YtdlpSearchPrefixMode,
)
from .serialize import config_defaults_to_json_data

ADMIN_SCHEMA_VERSION = 1
CONFIG_ITEM_TYPES = ("url", "folder")


def admin_schema_data() -> dict[str, Any]:
    return {
        "schema_version": ADMIN_SCHEMA_VERSION,
        "search_provider": enum_values(SearchProvider),
        "vod_style": enum_values(VodStyle),
        "tvbox_locale": enum_values(TvboxLocale),
        "video_codec": enum_values(VideoCodec),
        "audio_codec": enum_values(AudioCodec),
        "subscription_type": enum_values(SubscriptionType),
        "auth_mode": enum_values(AuthMode),
        "log_level": enum_values(LogLevel),
        "cookies_from_browser_mode": enum_values(BrowserCookiesMode),
        "ytdlp_search_prefix_mode": enum_values(YtdlpSearchPrefixMode),
        "item_type": list(CONFIG_ITEM_TYPES),
        "max_video_height": list(SUPPORTED_MAX_VIDEO_HEIGHTS),
        "max_video_fps": list(SUPPORTED_MAX_VIDEO_FPS),
        "limits": {
            "max_search_limit": MAX_SEARCH_LIMIT,
            "max_list_limit": MAX_LIST_LIMIT,
            "max_ytdlp_concurrency": MAX_YTDLP_CONCURRENCY,
            "max_proxy_media_idle_ttl_seconds": MAX_PROXY_MEDIA_IDLE_TTL_SECONDS,
            "admin_access_code_min_length": ADMIN_ACCESS_CODE_MIN_LENGTH,
            "admin_access_code_max_length": ADMIN_ACCESS_CODE_MAX_LENGTH,
            "subscription_access_code_min_length": SUBSCRIPTION_ACCESS_CODE_MIN_LENGTH,
            "subscription_access_code_max_length": SUBSCRIPTION_ACCESS_CODE_MAX_LENGTH,
        },
        "defaults": config_defaults_to_json_data(),
    }


def enum_values(enum_type: Any) -> list[str]:
    return [item.value for item in enum_type]
