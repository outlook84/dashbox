from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from yt_dlp.utils.networking import std_headers

@dataclass(frozen=True)
class UrlItem:
    url: str
    title: str = ""
    pic: str = ""
    remarks: str = ""
    id: str = ""


@dataclass(frozen=True)
class FolderItem:
    name: str
    items: tuple["ConfigItem", ...] = ()
    pic: str = ""
    remarks: str = ""
    id: str = ""


ConfigItem = UrlItem | FolderItem

DEFAULT_YTDLP_SEARCH_LIMIT = 30
DEFAULT_BILIBILI_SEARCH_LIMIT = 30
DEFAULT_PLAYLIST_LIMIT = 100
DEFAULT_BILIBILI_LIST_LIMIT = 100
DEFAULT_PROXY_MEDIA_IDLE_TTL_SECONDS = 21600
DEFAULT_USER_AGENT = std_headers["User-Agent"]
MAX_SEARCH_LIMIT = 200
MAX_LIST_LIMIT = 1000
MAX_UPSTREAM_TIMEOUT = 300
MAX_YTDLP_CONCURRENCY = 32
MAX_PROXY_MEDIA_IDLE_TTL_SECONDS = 7 * 24 * 60 * 60
CONFIG_FILE_TOP_LEVEL_KEYS = {
    "proxy_media_idle_ttl_seconds",
    "proxy_dash_media_url",
    "ytdlp_concurrency",
    "log_level",
    "user_agent",
    "cookies_from_browser",
}
SUPPORTED_MAX_VIDEO_HEIGHTS = (0, 480, 720, 1080, 1440, 2160, 4320)
SUPPORTED_MAX_VIDEO_FPS = (0, 24, 30, 60, 120)
IMAGE_PROXY_MODE_ENV = "DASHBOX_UNSAFE_IMAGE_PROXY_MODE"
UPSTREAM_TIMEOUT_ENV = "DASHBOX_UPSTREAM_TIMEOUT"
PUBLIC_BASE_URL_ENV = "DASHBOX_PUBLIC_BASE_URL"


class LogLevel(StrEnum):
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"
    DEBUG = "debug"


class SearchProvider(StrEnum):
    BILIBILI = "bilibili"
    YTDLP = "ytdlp"


class VodStyle(StrEnum):
    LIST = "list"
    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"


class TvboxLocale(StrEnum):
    ZH_CN = "zh-CN"
    EN_US = "en-US"


class VideoCodec(StrEnum):
    H264 = "h264"
    HEVC = "hevc"
    VP9 = "vp9"
    AV01 = "av01"


class AudioCodec(StrEnum):
    AAC = "aac"
    OPUS = "opus"
    EAC3 = "eac3"
    AC3 = "ac3"
    FLAC = "flac"
    OTHER = "other"


class YtdlpSearchPrefixMode(StrEnum):
    YOUTUBE = "youtube"
    BILIBILI = "bilibili"
    SOUNDCLOUD = "soundcloud"
    CUSTOM = "custom"


class BrowserCookiesMode(StrEnum):
    DISABLED = "disabled"
    FIREFOX = "firefox"
    FIREFOX_DATA_DIR = "firefox_data_dir"
    CHROME = "chrome"
    EDGE = "edge"
    CUSTOM = "custom"


class ImageProxyMode(StrEnum):
    OFF = "off"
    KNOWN = "known"
    ALL = "all"


class SubscriptionType(StrEnum):
    TVBOX = "tvbox"
    KODI = "kodi"


class AuthMode(StrEnum):
    ANONYMOUS = "anonymous"
    ACCESS_CODE = "access_code"


DEFAULT_TVBOX_LOCALE = TvboxLocale.ZH_CN
DEFAULT_VIDEO_CODEC_ORDER = (VideoCodec.H264, VideoCodec.HEVC, VideoCodec.VP9, VideoCodec.AV01)
DEFAULT_AUDIO_CODEC_ORDER = (
    AudioCodec.AAC,
    AudioCodec.OPUS,
    AudioCodec.EAC3,
    AudioCodec.AC3,
    AudioCodec.FLAC,
    AudioCodec.OTHER,
)


@dataclass(frozen=True)
class CodecPreference:
    codec: VideoCodec | AudioCodec
    enabled: bool = True


DEFAULT_VIDEO_CODEC_PREFERENCES = tuple(CodecPreference(codec, True) for codec in DEFAULT_VIDEO_CODEC_ORDER)
DEFAULT_AUDIO_CODEC_PREFERENCES = tuple(CodecPreference(codec, True) for codec in DEFAULT_AUDIO_CODEC_ORDER)

YTDLP_SEARCH_PREFIX_BY_MODE = {
    YtdlpSearchPrefixMode.YOUTUBE: "ytsearch",
    YtdlpSearchPrefixMode.BILIBILI: "bilisearch",
    YtdlpSearchPrefixMode.SOUNDCLOUD: "scsearch",
}


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    items: tuple[ConfigItem, ...] = ()

@dataclass(frozen=True)
class YtdlpSearchPrefixConfig:
    mode: YtdlpSearchPrefixMode = YtdlpSearchPrefixMode.YOUTUBE
    value: str = ""

    def to_ytdlp_value(self) -> str:
        if self.mode == YtdlpSearchPrefixMode.CUSTOM:
            return self.value
        return YTDLP_SEARCH_PREFIX_BY_MODE[self.mode]


@dataclass(frozen=True)
class BrowserCookiesConfig:
    mode: BrowserCookiesMode = BrowserCookiesMode.DISABLED
    value: str = ""

    def to_ytdlp_value(self) -> str:
        if self.mode == BrowserCookiesMode.DISABLED:
            return ""
        if self.mode == BrowserCookiesMode.CUSTOM:
            return self.value
        return self.mode.value


@dataclass(frozen=True)
class TvboxSubscriptionConfig:
    site_key: str = "dashbox"
    site_name: str = "Dashbox"
    locale: TvboxLocale = DEFAULT_TVBOX_LOCALE
    sources: tuple[Source, ...] = ()
    search_provider: SearchProvider | None = None
    ytdlp_search_prefix: YtdlpSearchPrefixConfig | None = None
    ytdlp_search_limit: int | None = None
    bilibili_search_limit: int | None = None
    playlist_limit: int | None = None
    bilibili_list_limit: int | None = None
    video_codec_preferences: tuple[CodecPreference, ...] = DEFAULT_VIDEO_CODEC_PREFERENCES
    audio_codec_preferences: tuple[CodecPreference, ...] = DEFAULT_AUDIO_CODEC_PREFERENCES
    max_video_height: int = 0
    max_video_fps: int = 0
    youtube_subtitles: bool = False
    vod_style: VodStyle = VodStyle.LIST

    def __post_init__(self) -> None:
        object.__setattr__(self, "locale", parse_tvbox_locale(self.locale))
        if self.search_provider is not None:
            object.__setattr__(self, "search_provider", parse_search_provider(self.search_provider, "tvbox.search_provider"))
        if self.ytdlp_search_prefix is not None:
            object.__setattr__(self, "ytdlp_search_prefix", parse_ytdlp_search_prefix(self.ytdlp_search_prefix))
        if self.ytdlp_search_limit is not None:
            object.__setattr__(
                self,
                "ytdlp_search_limit",
                parse_non_negative_int(self.ytdlp_search_limit, "tvbox.ytdlp_search_limit", maximum=MAX_SEARCH_LIMIT),
            )
        if self.bilibili_search_limit is not None:
            object.__setattr__(
                self,
                "bilibili_search_limit",
                parse_non_negative_int(self.bilibili_search_limit, "tvbox.bilibili_search_limit", maximum=MAX_SEARCH_LIMIT),
            )
        if self.playlist_limit is not None:
            object.__setattr__(
                self,
                "playlist_limit",
                parse_non_negative_int(self.playlist_limit, "tvbox.playlist_limit", maximum=MAX_LIST_LIMIT),
            )
        if self.bilibili_list_limit is not None:
            object.__setattr__(
                self,
                "bilibili_list_limit",
                parse_non_negative_int(self.bilibili_list_limit, "tvbox.bilibili_list_limit", maximum=MAX_LIST_LIMIT),
            )
        object.__setattr__(
            self,
            "video_codec_preferences",
            parse_video_codec_preferences(self.video_codec_preferences),
        )
        object.__setattr__(
            self,
            "audio_codec_preferences",
            parse_audio_codec_preferences(self.audio_codec_preferences),
        )
        object.__setattr__(
            self,
            "max_video_height",
            parse_max_video_height(self.max_video_height, "tvbox.max_video_height"),
        )
        object.__setattr__(
            self,
            "max_video_fps",
            parse_max_video_fps(self.max_video_fps, "tvbox.max_video_fps"),
        )
        object.__setattr__(
            self,
            "youtube_subtitles",
            parse_bool(self.youtube_subtitles, "tvbox.youtube_subtitles"),
        )
        object.__setattr__(self, "vod_style", parse_vod_style(self.vod_style, "tvbox.vod_style"))

    @property
    def effective_search_provider(self) -> SearchProvider:
        return self.search_provider or SearchProvider.YTDLP

    @property
    def effective_ytdlp_search_prefix(self) -> str:
        prefix = self.ytdlp_search_prefix or YtdlpSearchPrefixConfig()
        return prefix.to_ytdlp_value()

    @property
    def effective_ytdlp_search_limit(self) -> int:
        return DEFAULT_YTDLP_SEARCH_LIMIT if self.ytdlp_search_limit == 0 else int(self.ytdlp_search_limit or DEFAULT_YTDLP_SEARCH_LIMIT)

    @property
    def effective_bilibili_search_limit(self) -> int:
        return DEFAULT_BILIBILI_SEARCH_LIMIT if self.bilibili_search_limit == 0 else int(self.bilibili_search_limit or DEFAULT_BILIBILI_SEARCH_LIMIT)

    @property
    def effective_playlist_limit(self) -> int:
        return DEFAULT_PLAYLIST_LIMIT if self.playlist_limit == 0 else int(self.playlist_limit or DEFAULT_PLAYLIST_LIMIT)

    @property
    def effective_bilibili_list_limit(self) -> int:
        return DEFAULT_BILIBILI_LIST_LIMIT if self.bilibili_list_limit == 0 else int(self.bilibili_list_limit or DEFAULT_BILIBILI_LIST_LIMIT)


@dataclass(frozen=True)
class KodiSubscriptionConfig:
    root: dict[str, Any] | None = None
    sources: tuple[ConfigItem, ...] = ()
    search_provider: SearchProvider | None = None
    ytdlp_search_prefix: YtdlpSearchPrefixConfig | None = None
    ytdlp_search_limit: int | None = None
    bilibili_search_limit: int | None = None
    playlist_limit: int | None = None
    bilibili_list_limit: int | None = None

    def __post_init__(self) -> None:
        if self.search_provider is not None:
            object.__setattr__(self, "search_provider", parse_search_provider(self.search_provider, "kodi.search_provider"))
        if self.ytdlp_search_prefix is not None:
            object.__setattr__(self, "ytdlp_search_prefix", parse_ytdlp_search_prefix(self.ytdlp_search_prefix))
        if self.ytdlp_search_limit is not None:
            object.__setattr__(
                self,
                "ytdlp_search_limit",
                parse_non_negative_int(self.ytdlp_search_limit, "kodi.ytdlp_search_limit", maximum=MAX_SEARCH_LIMIT),
            )
        if self.bilibili_search_limit is not None:
            object.__setattr__(
                self,
                "bilibili_search_limit",
                parse_non_negative_int(self.bilibili_search_limit, "kodi.bilibili_search_limit", maximum=MAX_SEARCH_LIMIT),
            )
        if self.playlist_limit is not None:
            object.__setattr__(
                self,
                "playlist_limit",
                parse_non_negative_int(self.playlist_limit, "kodi.playlist_limit", maximum=MAX_LIST_LIMIT),
            )
        if self.bilibili_list_limit is not None:
            object.__setattr__(
                self,
                "bilibili_list_limit",
                parse_non_negative_int(self.bilibili_list_limit, "kodi.bilibili_list_limit", maximum=MAX_LIST_LIMIT),
            )

    @property
    def effective_search_provider(self) -> SearchProvider:
        return self.search_provider or SearchProvider.YTDLP

    @property
    def effective_ytdlp_search_prefix(self) -> str:
        prefix = self.ytdlp_search_prefix or YtdlpSearchPrefixConfig()
        return prefix.to_ytdlp_value()

    @property
    def effective_ytdlp_search_limit(self) -> int:
        return DEFAULT_YTDLP_SEARCH_LIMIT if self.ytdlp_search_limit == 0 else int(self.ytdlp_search_limit or DEFAULT_YTDLP_SEARCH_LIMIT)

    @property
    def effective_bilibili_search_limit(self) -> int:
        return DEFAULT_BILIBILI_SEARCH_LIMIT if self.bilibili_search_limit == 0 else int(self.bilibili_search_limit or DEFAULT_BILIBILI_SEARCH_LIMIT)

    @property
    def effective_playlist_limit(self) -> int:
        return DEFAULT_PLAYLIST_LIMIT if self.playlist_limit == 0 else int(self.playlist_limit or DEFAULT_PLAYLIST_LIMIT)

    @property
    def effective_bilibili_list_limit(self) -> int:
        return DEFAULT_BILIBILI_LIST_LIMIT if self.bilibili_list_limit == 0 else int(self.bilibili_list_limit or DEFAULT_BILIBILI_LIST_LIMIT)


@dataclass(frozen=True)
class Subscription:
    id: str
    type: SubscriptionType
    auth_mode: AuthMode = AuthMode.ANONYMOUS
    access_code_hash: str = ""
    tvbox: TvboxSubscriptionConfig | None = None
    kodi: KodiSubscriptionConfig | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", parse_subscription_type(self.type))
        object.__setattr__(self, "auth_mode", parse_auth_mode(self.auth_mode, self.id))


@dataclass(frozen=True)
class Config:
    public_base_url: str = ""
    default_search_provider: SearchProvider = SearchProvider.YTDLP
    ytdlp_search_prefix: YtdlpSearchPrefixConfig = YtdlpSearchPrefixConfig()
    ytdlp_search_limit: int = DEFAULT_YTDLP_SEARCH_LIMIT
    bilibili_search_limit: int = DEFAULT_BILIBILI_SEARCH_LIMIT
    playlist_limit: int = DEFAULT_PLAYLIST_LIMIT
    bilibili_list_limit: int = DEFAULT_BILIBILI_LIST_LIMIT
    upstream_timeout: int = 30
    proxy_media_idle_ttl_seconds: int = DEFAULT_PROXY_MEDIA_IDLE_TTL_SECONDS
    proxy_dash_media_url: bool = False
    image_proxy_mode: ImageProxyMode = ImageProxyMode.KNOWN
    ytdlp_concurrency: int = 8
    log_level: LogLevel = LogLevel.INFO
    user_agent: str = ""
    cookies_from_browser: BrowserCookiesConfig = BrowserCookiesConfig()
    subs: tuple[Subscription, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "log_level", parse_log_level(self.log_level))
        object.__setattr__(self, "default_search_provider", parse_search_provider(self.default_search_provider))
        object.__setattr__(self, "ytdlp_search_prefix", parse_ytdlp_search_prefix(self.ytdlp_search_prefix))
        object.__setattr__(
            self,
            "ytdlp_search_limit",
            parse_non_negative_int(self.ytdlp_search_limit, "ytdlp_search_limit", maximum=MAX_SEARCH_LIMIT),
        )
        object.__setattr__(
            self,
            "bilibili_search_limit",
            parse_non_negative_int(self.bilibili_search_limit, "bilibili_search_limit", maximum=MAX_SEARCH_LIMIT),
        )
        object.__setattr__(
            self,
            "playlist_limit",
            parse_non_negative_int(self.playlist_limit, "playlist_limit", maximum=MAX_LIST_LIMIT),
        )
        object.__setattr__(
            self,
            "bilibili_list_limit",
            parse_non_negative_int(self.bilibili_list_limit, "bilibili_list_limit", maximum=MAX_LIST_LIMIT),
        )
        object.__setattr__(
            self,
            "upstream_timeout",
            parse_positive_int(self.upstream_timeout, "upstream_timeout", maximum=MAX_UPSTREAM_TIMEOUT),
        )
        object.__setattr__(
            self,
            "proxy_media_idle_ttl_seconds",
            parse_positive_int(
                self.proxy_media_idle_ttl_seconds,
                "proxy_media_idle_ttl_seconds",
                maximum=MAX_PROXY_MEDIA_IDLE_TTL_SECONDS,
            ),
        )
        object.__setattr__(self, "proxy_dash_media_url", parse_bool(self.proxy_dash_media_url, "proxy_dash_media_url"))
        object.__setattr__(self, "image_proxy_mode", parse_image_proxy_mode(self.image_proxy_mode))
        object.__setattr__(
            self,
            "ytdlp_concurrency",
            parse_positive_int(self.ytdlp_concurrency, "ytdlp_concurrency", maximum=MAX_YTDLP_CONCURRENCY),
        )
        object.__setattr__(self, "cookies_from_browser", parse_browser_cookies_config(self.cookies_from_browser))
        object.__setattr__(self, "subs", tuple(self._resolve_subscription(sub) for sub in self.subs))

    @property
    def effective_user_agent(self) -> str:
        return self.user_agent or DEFAULT_USER_AGENT

    @property
    def configured_cookies_from_browser(self) -> str:
        return self.cookies_from_browser.to_ytdlp_value()

    @property
    def effective_search_provider(self) -> SearchProvider:
        return self.default_search_provider

    @property
    def effective_ytdlp_search_prefix(self) -> str:
        return self.ytdlp_search_prefix.to_ytdlp_value()

    @property
    def effective_ytdlp_search_limit(self) -> int:
        return DEFAULT_YTDLP_SEARCH_LIMIT if self.ytdlp_search_limit == 0 else self.ytdlp_search_limit

    @property
    def effective_bilibili_search_limit(self) -> int:
        return DEFAULT_BILIBILI_SEARCH_LIMIT if self.bilibili_search_limit == 0 else self.bilibili_search_limit

    @property
    def effective_playlist_limit(self) -> int:
        return DEFAULT_PLAYLIST_LIMIT if self.playlist_limit == 0 else self.playlist_limit

    @property
    def effective_bilibili_list_limit(self) -> int:
        return DEFAULT_BILIBILI_LIST_LIMIT if self.bilibili_list_limit == 0 else self.bilibili_list_limit

    def _resolve_subscription(self, sub: Subscription) -> Subscription:
        if sub.type == SubscriptionType.TVBOX and sub.tvbox is not None:
            return replace(sub, tvbox=self._resolve_tvbox_subscription(sub.tvbox))
        if sub.type == SubscriptionType.KODI and sub.kodi is not None:
            return replace(sub, kodi=self._resolve_kodi_subscription(sub.kodi))
        return sub

    def _resolve_tvbox_subscription(self, tvbox: TvboxSubscriptionConfig) -> TvboxSubscriptionConfig:
        values: dict[str, Any] = {}
        if tvbox.search_provider is None:
            values["search_provider"] = self.default_search_provider
        if tvbox.ytdlp_search_prefix is None:
            values["ytdlp_search_prefix"] = self.ytdlp_search_prefix
        for field in ("ytdlp_search_limit", "bilibili_search_limit", "playlist_limit", "bilibili_list_limit"):
            if getattr(tvbox, field) is None:
                values[field] = getattr(self, field)
        if not values:
            return tvbox
        return replace(tvbox, **values)

    def _resolve_kodi_subscription(self, kodi: KodiSubscriptionConfig) -> KodiSubscriptionConfig:
        values: dict[str, Any] = {}
        if kodi.search_provider is None:
            values["search_provider"] = self.default_search_provider
        if kodi.ytdlp_search_prefix is None:
            values["ytdlp_search_prefix"] = self.ytdlp_search_prefix
        for field in ("ytdlp_search_limit", "bilibili_search_limit", "playlist_limit", "bilibili_list_limit"):
            if getattr(kodi, field) is None:
                values[field] = getattr(self, field)
        if not values:
            return kodi
        return replace(kodi, **values)



# Imported after class definitions to avoid a module initialization cycle: the
# parsers construct these dataclasses, while __post_init__ validates values.
from .parse import (  # noqa: E402
    parse_audio_codec_preferences,
    parse_auth_mode,
    parse_bool,
    parse_browser_cookies_config,
    parse_image_proxy_mode,
    parse_log_level,
    parse_max_video_fps,
    parse_max_video_height,
    parse_non_negative_int,
    parse_positive_int,
    parse_search_provider,
    parse_subscription_type,
    parse_tvbox_locale,
    parse_video_codec_preferences,
    parse_vod_style,
    parse_ytdlp_search_prefix,
)
