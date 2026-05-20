from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from ..auth.access_code import validate_access_code_hash_shape
from .ids import validate_config_id
from .validation import is_ytdlp_search_prefix, parse_cookies_from_browser, validate_ytdlp_search_prefix
from .model import (
    DEFAULT_AUDIO_CODEC_ORDER,
    DEFAULT_AUDIO_CODEC_PREFERENCES,
    DEFAULT_TVBOX_LOCALE,
    DEFAULT_VIDEO_CODEC_ORDER,
    DEFAULT_VIDEO_CODEC_PREFERENCES,
    MAX_LIST_LIMIT,
    MAX_SEARCH_LIMIT,
    SUPPORTED_MAX_VIDEO_FPS,
    SUPPORTED_MAX_VIDEO_HEIGHTS,
    AudioCodec,
    AuthMode,
    BrowserCookiesConfig,
    BrowserCookiesMode,
    CodecPreference,
    ConfigItem,
    FolderItem,
    ImageProxyMode,
    KodiSubscriptionConfig,
    LogLevel,
    SearchProvider,
    Source,
    Subscription,
    SubscriptionType,
    TvboxLocale,
    TvboxSubscriptionConfig,
    UrlItem,
    VideoCodec,
    VodStyle,
    YtdlpSearchPrefixConfig,
    YtdlpSearchPrefixMode,
)

def parse_subscriptions(value: Any) -> tuple[Subscription, ...]:
    if not isinstance(value, list):
        raise ValueError("subs must be an array")
    subs: list[Subscription] = []
    seen: set[str] = set()
    seen_tvbox_site_keys: dict[str, str] = {}
    for sub in value:
        if not isinstance(sub, dict):
            raise ValueError("subscription must be an object")
        sub_id = str(sub.get("id") or "").strip()
        raw_sub_type = sub.get("type")
        if not sub_id or not str(raw_sub_type or "").strip():
            raise ValueError("subscription id and type are required")
        if sub_id in seen:
            raise ValueError(f"duplicate subscription id: {sub_id}")
        seen.add(sub_id)
        if "access_code" in sub:
            raise ValueError(f"subscription {sub_id} access_code plaintext is not supported; use access_code_hash")
        if "auth_mode" not in sub:
            raise ValueError(f"subscription {sub_id} auth_mode is required")
        auth_mode = parse_auth_mode(sub.get("auth_mode"), sub_id)
        access_code_hash = parse_access_code_hash(sub.get("access_code_hash"), auth_mode, sub_id)
        has_tvbox = isinstance(sub.get("tvbox"), dict)
        has_kodi = isinstance(sub.get("kodi"), dict)
        sub_type = parse_subscription_type(raw_sub_type)
        if sub_type == SubscriptionType.TVBOX:
            if not has_tvbox or has_kodi:
                raise ValueError(f"subscription {sub_id} type tvbox requires only a tvbox payload")
            tvbox = parse_tvbox_subscription(sub["tvbox"])
            existing_site_key_sub_id = seen_tvbox_site_keys.get(tvbox.site_key)
            if existing_site_key_sub_id is not None:
                raise ValueError(
                    f"duplicate tvbox site_key: {tvbox.site_key} "
                    f"for subscriptions {existing_site_key_sub_id} and {sub_id}"
                )
            seen_tvbox_site_keys[tvbox.site_key] = sub_id
            subs.append(Subscription(
                id=sub_id,
                type=SubscriptionType.TVBOX,
                auth_mode=auth_mode,
                access_code_hash=access_code_hash,
                tvbox=tvbox,
            ))
            continue
        if sub_type == SubscriptionType.KODI:
            if not has_kodi or has_tvbox:
                raise ValueError(f"subscription {sub_id} type kodi requires only a kodi payload")
            subs.append(Subscription(
                id=sub_id,
                type=SubscriptionType.KODI,
                auth_mode=auth_mode,
                access_code_hash=access_code_hash,
                kodi=parse_kodi_subscription(sub["kodi"]),
            ))
            continue
    return tuple(subs)


def parse_subscription_type(value: Any) -> SubscriptionType:
    sub_type = str(value or "").strip().lower()
    try:
        return SubscriptionType(sub_type)
    except ValueError:
        supported = ", ".join(sorted(item.value for item in SubscriptionType))
        raise ValueError(f"unsupported subscription type: {sub_type}. Supported: {supported}") from None


def parse_auth_mode(value: Any, sub_id: str) -> AuthMode:
    mode = str(value or "").strip().lower()
    try:
        return AuthMode(mode)
    except ValueError:
        supported = ", ".join(sorted(item.value for item in AuthMode))
        raise ValueError(f"subscription {sub_id} unsupported auth_mode: {value}. Supported: {supported}") from None


def parse_access_code_hash(value: Any, auth_mode: AuthMode, sub_id: str) -> str:
    access_code_hash = str(value or "").strip()
    if auth_mode == AuthMode.ANONYMOUS:
        if access_code_hash:
            raise ValueError(f"subscription {sub_id} auth_mode anonymous must not set access_code_hash")
        return ""
    if not access_code_hash:
        raise ValueError(f"subscription {sub_id} auth_mode access_code requires access_code_hash")
    validate_access_code_hash_shape(access_code_hash)
    return access_code_hash


def parse_tvbox_subscription(value: Any) -> TvboxSubscriptionConfig:
    if not isinstance(value, dict):
        raise ValueError("tvbox subscription payload must be an object")
    site_key = str(value.get("site_key") or "").strip()
    if not site_key:
        raise ValueError("tvbox.site_key is required")
    return TvboxSubscriptionConfig(
        site_key=site_key,
        site_name=str(value.get("site_name") or "Dashbox").strip() or "Dashbox",
        locale=parse_tvbox_locale(value.get("locale", DEFAULT_TVBOX_LOCALE)),
        sources=parse_sources(value.get("sources") or []),
        search_provider=parse_optional_search_provider(value.get("search_provider"), "tvbox.search_provider")
        if "search_provider" in value
        else None,
        ytdlp_search_prefix=parse_ytdlp_search_prefix(value.get("ytdlp_search_prefix"))
        if "ytdlp_search_prefix" in value
        else None,
        ytdlp_search_limit=parse_optional_non_negative_int(
            value.get("ytdlp_search_limit"),
            "tvbox.ytdlp_search_limit",
            maximum=MAX_SEARCH_LIMIT,
        ),
        bilibili_search_limit=parse_optional_non_negative_int(
            value.get("bilibili_search_limit"),
            "tvbox.bilibili_search_limit",
            maximum=MAX_SEARCH_LIMIT,
        ),
        playlist_limit=parse_optional_non_negative_int(
            value.get("playlist_limit"),
            "tvbox.playlist_limit",
            maximum=MAX_LIST_LIMIT,
        ),
        bilibili_list_limit=parse_optional_non_negative_int(
            value.get("bilibili_list_limit"),
            "tvbox.bilibili_list_limit",
            maximum=MAX_LIST_LIMIT,
        ),
        video_codec_preferences=parse_video_codec_preferences(
            value.get("video_codec_preferences", DEFAULT_VIDEO_CODEC_PREFERENCES)
        ),
        audio_codec_preferences=parse_audio_codec_preferences(
            value.get("audio_codec_preferences", DEFAULT_AUDIO_CODEC_PREFERENCES)
        ),
        max_video_height=parse_max_video_height(
            value.get("max_video_height", 0),
            "tvbox.max_video_height",
        ),
        max_video_fps=parse_max_video_fps(
            value.get("max_video_fps", 0),
            "tvbox.max_video_fps",
        ),
        youtube_subtitles=parse_bool(
            value.get("youtube_subtitles", False),
            "tvbox.youtube_subtitles",
        ),
        vod_style=parse_vod_style(value.get("vod_style", VodStyle.LIST), "tvbox.vod_style"),
    )


def parse_kodi_subscription(value: Any) -> KodiSubscriptionConfig:
    if not isinstance(value, dict):
        raise ValueError("kodi subscription payload must be an object")
    return KodiSubscriptionConfig(
        root=value.get("root"),
        sources=parse_kodi_sources(value.get("sources") or []),
        search_provider=parse_optional_search_provider(value.get("search_provider"), "kodi.search_provider")
        if "search_provider" in value
        else None,
        ytdlp_search_prefix=parse_ytdlp_search_prefix(value.get("ytdlp_search_prefix"))
        if "ytdlp_search_prefix" in value
        else None,
        ytdlp_search_limit=parse_optional_non_negative_int(
            value.get("ytdlp_search_limit"),
            "kodi.ytdlp_search_limit",
            maximum=MAX_SEARCH_LIMIT,
        ),
        bilibili_search_limit=parse_optional_non_negative_int(
            value.get("bilibili_search_limit"),
            "kodi.bilibili_search_limit",
            maximum=MAX_SEARCH_LIMIT,
        ),
        playlist_limit=parse_optional_non_negative_int(
            value.get("playlist_limit"),
            "kodi.playlist_limit",
            maximum=MAX_LIST_LIMIT,
        ),
        bilibili_list_limit=parse_optional_non_negative_int(
            value.get("bilibili_list_limit"),
            "kodi.bilibili_list_limit",
            maximum=MAX_LIST_LIMIT,
        ),
    )


def parse_log_level(value: Any) -> LogLevel:
    log_level = str(value or "").strip().lower()
    try:
        return LogLevel(log_level)
    except ValueError:
        supported = ", ".join(sorted(item.value for item in LogLevel))
        raise ValueError(f"unsupported log_level: {value}. Supported: {supported}") from None


def parse_search_provider(value: Any, path: str = "default_search_provider") -> SearchProvider:
    provider = str(value or "").strip().lower()
    try:
        return SearchProvider(provider)
    except ValueError:
        supported = ", ".join(sorted(item.value for item in SearchProvider))
        raise ValueError(f"unsupported {path}: {value}. Supported: {supported}") from None


def parse_optional_search_provider(value: Any, path: str) -> SearchProvider | None:
    if value is None:
        return None
    return parse_search_provider(value, path)


def parse_non_negative_int(value: Any, path: str, *, maximum: int | None = None) -> int:
    return parse_int(value, path, minimum=0, maximum=maximum)


def parse_optional_non_negative_int(value: Any, path: str, *, maximum: int | None = None) -> int | None:
    if value is None:
        return None
    return parse_non_negative_int(value, path, maximum=maximum)


def parse_positive_int(value: Any, path: str, *, maximum: int | None = None) -> int:
    return parse_int(value, path, minimum=1, maximum=maximum)


def parse_bool(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"unsupported {path}: {value}. Expected boolean")
    return value


def parse_int(value: Any, path: str, *, minimum: int, maximum: int | None = None) -> int:
    expected = f"integer >= {minimum}" if maximum is None else f"integer between {minimum} and {maximum}"
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"unsupported {path}: {value}. Expected {expected}")
    if value < minimum or (maximum is not None and value > maximum):
        raise ValueError(f"unsupported {path}: {value}. Expected {expected}")
    return value


def parse_ytdlp_search_prefix(value: Any) -> YtdlpSearchPrefixConfig:
    if isinstance(value, YtdlpSearchPrefixConfig):
        return _validated_ytdlp_search_prefix_config(value)
    if not isinstance(value, dict):
        raise ValueError("ytdlp_search_prefix must be an object")
    mode = parse_ytdlp_search_prefix_mode(value.get("mode"))
    custom_value = str(value.get("value") or "").strip()
    return _validated_ytdlp_search_prefix_config(YtdlpSearchPrefixConfig(mode=mode, value=custom_value))


def parse_ytdlp_search_prefix_mode(value: Any) -> YtdlpSearchPrefixMode:
    mode = str(value or "").strip().lower()
    try:
        return YtdlpSearchPrefixMode(mode)
    except ValueError:
        supported = ", ".join(item.value for item in YtdlpSearchPrefixMode)
        raise ValueError(f"unsupported ytdlp_search_prefix mode: {value}. Supported: {supported}") from None


def _validated_ytdlp_search_prefix_config(value: YtdlpSearchPrefixConfig) -> YtdlpSearchPrefixConfig:
    mode = parse_ytdlp_search_prefix_mode(value.mode)
    custom_value = str(value.value or "").strip()
    if mode == YtdlpSearchPrefixMode.CUSTOM:
        if not custom_value:
            raise ValueError("ytdlp_search_prefix custom mode requires value")
        return YtdlpSearchPrefixConfig(mode=mode, value=validate_ytdlp_search_prefix(custom_value))
    if custom_value:
        raise ValueError("ytdlp_search_prefix value is only supported in custom mode")
    return YtdlpSearchPrefixConfig(mode=mode)


def parse_browser_cookies_config(value: Any) -> BrowserCookiesConfig:
    if isinstance(value, BrowserCookiesConfig):
        return _validated_browser_cookies_config(value)
    if not isinstance(value, dict):
        raise ValueError("cookies_from_browser must be an object")
    mode = parse_browser_cookies_mode(value.get("mode"))
    custom_value = str(value.get("value") or "").strip()
    return _validated_browser_cookies_config(BrowserCookiesConfig(mode=mode, value=custom_value))


def parse_browser_cookies_mode(value: Any) -> BrowserCookiesMode:
    mode = str(value or "").strip().lower()
    try:
        return BrowserCookiesMode(mode)
    except ValueError:
        supported = ", ".join(item.value for item in BrowserCookiesMode)
        raise ValueError(f"unsupported cookies_from_browser mode: {value}. Supported: {supported}") from None



def parse_image_proxy_mode(value: Any, path: str = "image_proxy_mode") -> ImageProxyMode:
    mode = str(value or "").strip().lower()
    try:
        return ImageProxyMode(mode)
    except ValueError:
        supported = ", ".join(item.value for item in ImageProxyMode)
        raise ValueError(f"unsupported {path}: {value}. Supported: {supported}") from None


def _validated_browser_cookies_config(value: BrowserCookiesConfig) -> BrowserCookiesConfig:
    mode = parse_browser_cookies_mode(value.mode)
    custom_value = str(value.value or "").strip()
    if mode == BrowserCookiesMode.CUSTOM:
        if not custom_value:
            raise ValueError("cookies_from_browser custom mode requires value")
        parse_cookies_from_browser(custom_value)
        return BrowserCookiesConfig(mode=mode, value=custom_value)
    if custom_value:
        raise ValueError("cookies_from_browser value is only supported in custom mode")
    out = BrowserCookiesConfig(mode=mode)
    if mode != BrowserCookiesMode.FIREFOX_DATA_DIR:
        effective = out.to_ytdlp_value()
        if effective:
            parse_cookies_from_browser(effective)
    return out


def parse_vod_style(value: Any, path: str) -> VodStyle:
    style = str(value or "").strip().lower()
    if not style:
        return VodStyle.LIST
    try:
        return VodStyle(style)
    except ValueError:
        supported = ", ".join(sorted(item.value for item in VodStyle))
        raise ValueError(f"unsupported {path}: {value}. Supported: {supported}") from None


def parse_tvbox_locale(value: Any) -> TvboxLocale:
    locale = str(value or DEFAULT_TVBOX_LOCALE).strip()
    try:
        return TvboxLocale(locale)
    except ValueError:
        supported = ", ".join(item.value for item in TvboxLocale)
        raise ValueError(f"unsupported tvbox locale: {value}. Supported: {supported}") from None


def parse_video_codec_preferences(value: Any) -> tuple[CodecPreference, ...]:
    return parse_codec_preferences(
        value,
        VideoCodec,
        DEFAULT_VIDEO_CODEC_ORDER,
        "video_codec_preferences",
    )


def parse_audio_codec_preferences(value: Any) -> tuple[CodecPreference, ...]:
    return parse_codec_preferences(
        value,
        AudioCodec,
        DEFAULT_AUDIO_CODEC_ORDER,
        "audio_codec_preferences",
    )


def parse_codec_preferences(
    value: Any,
    codec_type: type[VideoCodec] | type[AudioCodec],
    required_codecs: tuple[VideoCodec, ...] | tuple[AudioCodec, ...],
    path: str,
) -> tuple[CodecPreference, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{path} must be an array")

    out: list[CodecPreference] = []
    seen: set[VideoCodec | AudioCodec] = set()
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if isinstance(item, CodecPreference):
            codec_value = item.codec
            enabled = item.enabled
        elif isinstance(item, dict):
            codec_value = item.get("codec")
            if "enabled" not in item:
                raise ValueError(f"{item_path}.enabled is required")
            enabled = parse_bool(item.get("enabled"), f"{item_path}.enabled")
        else:
            raise ValueError(f"{item_path} must be an object")

        try:
            codec = codec_value if isinstance(codec_value, codec_type) else codec_type(str(codec_value or "").strip().lower())
        except ValueError:
            supported = ", ".join(codec.value for codec in required_codecs)
            raise ValueError(f"unsupported {item_path}.codec: {codec_value}. Supported: {supported}") from None

        if codec in seen:
            raise ValueError(f"duplicate {path} codec: {codec.value}")
        seen.add(codec)
        out.append(CodecPreference(codec=codec, enabled=bool(enabled)))

    required_set = set(required_codecs)
    if seen != required_set:
        missing = ", ".join(codec.value for codec in required_codecs if codec not in seen)
        extra = ", ".join(codec.value for codec in seen if codec not in required_set)
        details = []
        if missing:
            details.append(f"missing: {missing}")
        if extra:
            details.append(f"extra: {extra}")
        raise ValueError(f"{path} must contain every supported codec exactly once ({'; '.join(details)})")
    if not any(preference.enabled for preference in out):
        raise ValueError(f"{path} must enable at least one codec")
    return tuple(out)


def enabled_codec_order(preferences: tuple[CodecPreference, ...]) -> tuple[VideoCodec | AudioCodec, ...]:
    return tuple(preference.codec for preference in preferences if preference.enabled)


def parse_max_video_height(value: Any, path: str) -> int:
    supported = ", ".join(str(item) for item in SUPPORTED_MAX_VIDEO_HEIGHTS)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"unsupported {path}: {value}. Supported: {supported}")
    height = value
    if height not in SUPPORTED_MAX_VIDEO_HEIGHTS:
        raise ValueError(f"unsupported {path}: {value}. Supported: {supported}")
    return height


def parse_max_video_fps(value: Any, path: str) -> int:
    supported = ", ".join(str(item) for item in SUPPORTED_MAX_VIDEO_FPS)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"unsupported {path}: {value}. Supported: {supported}")
    fps = value
    if fps not in SUPPORTED_MAX_VIDEO_FPS:
        raise ValueError(f"unsupported {path}: {value}. Supported: {supported}")
    return fps


def parse_sources(value: Any) -> tuple[Source, ...]:
    if not isinstance(value, list):
        raise ValueError("sources must be an array")
    sources: list[Source] = []
    seen_source_ids: set[str] = set()
    for index, source in enumerate(value):
        source_path = f"sources[{index}]"
        if not isinstance(source, dict):
            raise ValueError(f"{source_path} must be an object")
        source_id = validate_config_id(source.get("id"), source_path)
        if source_id in seen_source_ids:
            raise ValueError(f"duplicate source id: {source_id}")
        seen_source_ids.add(source_id)
        name = str(source.get("name") or source_id).strip()
        if not name:
            raise ValueError(f"{source_path}.name is required")
        raw_items = source.get("items") or []
        if not isinstance(raw_items, list):
            raise ValueError(f"{source_path}.items must be an array")
        items = parse_items(raw_items, f"{source_path}.items")
        validate_source_item_ids(source_id, items, source_path)
        sources.append(Source(id=source_id, name=name, items=tuple(items)))
    return tuple(sources)


def validate_source_item_ids(source_id: str, items: tuple[ConfigItem, ...], source_path: str) -> None:
    validate_config_item_ids(items, f"{source_path}.items", f"source {source_id}")


def validate_config_item_ids(items: tuple[ConfigItem, ...], path: str, label: str) -> None:
    seen: set[str] = set()

    def walk(nodes: tuple[ConfigItem, ...], path: str) -> None:
        for index, item in enumerate(nodes):
            item_path = f"{path}[{index}]"
            if isinstance(item, UrlItem):
                item_id = validate_config_id(item.id, item_path)
            elif isinstance(item, FolderItem):
                item_id = validate_config_id(item.id, item_path)
            else:
                continue
            if item_id in seen:
                raise ValueError(f"duplicate item id in {label}: {item_id}")
            seen.add(item_id)
            if isinstance(item, FolderItem):
                walk(item.items, f"{item_path}.items")

    walk(items, path)


def parse_kodi_sources(value: Any) -> tuple[ConfigItem, ...]:
    if not isinstance(value, list):
        raise ValueError("kodi.sources must be an array")
    sources: list[ConfigItem] = []
    for index, source in enumerate(value):
        source_path = f"kodi.sources[{index}]"
        if not isinstance(source, dict):
            raise ValueError(f"{source_path} must be an object")
        sources.extend(parse_items([source], source_path))
    out = tuple(sources)
    validate_config_item_ids(out, "kodi.sources", "kodi root")
    return out


def parse_items(value: Any, path: str) -> tuple[ConfigItem, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be an array")
    items: list[ConfigItem] = []
    for index, item in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(item, dict):
            raise ValueError(f"{item_path} must be an object")
        has_url = "url" in item
        has_items = "items" in item
        if has_url and has_items:
            raise ValueError(f"{item_path} cannot have both url and items")
        if has_url:
            url = parse_config_item_url(item.get("url"), item_path)
            if "name" in item:
                raise ValueError(f"{item_path} url item cannot have name; use title")
            title = str(item.get("title") or "").strip()
            items.append(UrlItem(
                url=url,
                title=title,
                pic=str(item.get("pic") or ""),
                remarks=str(item.get("remarks") or ""),
                id=str(item.get("id") or "").strip(),
            ))
            continue
        if has_items:
            name = str(item.get("name") or "").strip()
            if not name:
                raise ValueError(f"{item_path} name is required")
            items.append(FolderItem(
                name=name,
                items=parse_items(item.get("items"), f"{item_path}.items"),
                pic=str(item.get("pic") or ""),
                remarks=str(item.get("remarks") or ""),
                id=str(item.get("id") or "").strip(),
            ))
            continue
        raise ValueError(f"{item_path} must have either url or items")
    return tuple(items)


def parse_config_item_url(value: Any, path: str) -> str:
    url = str(value or "").strip()
    if not url:
        raise ValueError(f"{path} url is required")
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    is_ytdlp_search_url = bool(scheme and not parts.netloc and is_ytdlp_search_prefix(scheme))
    if parts.netloc and not scheme:
        raise ValueError(f"{path} url must include http or https scheme")
    if scheme and scheme not in {"http", "https"} and not is_ytdlp_search_url:
        raise ValueError(f"{path} url scheme must be http or https")
    if scheme in {"http", "https"} and not parts.netloc:
        raise ValueError(f"{path} url must include a host")
    return url
