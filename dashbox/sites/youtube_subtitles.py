from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs, urlparse


logger = logging.getLogger("dashbox.sites.youtube")

INCLUDE_TRANSLATED_AUTOMATIC_FALLBACK = False
SUBTITLE_FORMAT_PRIORITY = ("srt", "vtt")


def is_subtitle_redirect_target(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    hostname = parsed.hostname or ""
    return (
        parsed.scheme in {"http", "https"}
        and (hostname == "youtube.com" or hostname.endswith(".youtube.com"))
        and parsed.path == "/api/timedtext"
    )


def client_subtitles_from_info(
    info: dict[str, Any],
    *,
    subtitle_languages: tuple[str, ...] = (),
    subtitles_enabled: bool = False,
    all_manual: bool = False,
) -> tuple[dict[str, str], ...]:
    languages = youtube_subtitle_language_order(subtitle_languages)
    manual_langs = subtitle_language_keys(info.get("subtitles"))
    auto_langs = subtitle_language_keys(info.get("automatic_captions"))
    if not subtitles_enabled:
        log_subtitle_selection(
            "disabled",
            (),
            subtitles_enabled=subtitles_enabled,
            all_manual=all_manual,
            requested=subtitle_languages,
            expanded=languages,
            manual_langs=manual_langs,
            auto_langs=auto_langs,
        )
        return ()
    manual = selected_subtitles(
        info.get("subtitles"),
        subtitle_languages=languages,
        all_languages=all_manual or not languages,
    )
    if all_manual and manual:
        selected = unique_subtitles(manual)
        log_subtitle_selection(
            "manual-all",
            selected,
            subtitles_enabled=subtitles_enabled,
            all_manual=all_manual,
            requested=subtitle_languages,
            expanded=languages,
            manual_langs=manual_langs,
            auto_langs=auto_langs,
        )
        return selected
    if manual:
        log_subtitle_selection(
            "manual",
            manual,
            subtitles_enabled=subtitles_enabled,
            all_manual=all_manual,
            requested=subtitle_languages,
            expanded=languages,
            manual_langs=manual_langs,
            auto_langs=auto_langs,
        )
        return manual
    if subtitles_enabled:
        selected = selected_automatic_original_caption(info, languages)
        log_subtitle_selection(
            "automatic-original" if selected else "none",
            selected,
            subtitles_enabled=subtitles_enabled,
            all_manual=all_manual,
            requested=subtitle_languages,
            expanded=languages,
            manual_langs=manual_langs,
            auto_langs=auto_langs,
        )
        return selected
    return ()


def selected_automatic_original_caption(
    info: dict[str, Any],
    languages: tuple[str, ...],
) -> tuple[dict[str, str], ...]:
    captions = original_automatic_captions(info.get("automatic_captions"))
    preferred = selected_subtitles(
        captions,
        subtitle_languages=languages or ("en-orig", "en"),
        all_languages=False,
    )
    if preferred:
        return preferred
    return selected_subtitles(
        captions,
        subtitle_languages=languages or ("en-orig", "en"),
        all_languages=True,
    )


def selected_subtitles(
    subtitles: Any,
    *,
    subtitle_languages: tuple[str, ...] = (),
    all_languages: bool = False,
) -> tuple[dict[str, str], ...]:
    if not isinstance(subtitles, dict):
        return ()
    out: list[dict[str, str]] = []
    if all_languages:
        seen_languages: set[str] = set()
        ordered_languages = [
            *subtitle_languages,
            *(str(lang) for lang in subtitles if str(lang) not in subtitle_languages),
        ]
        for lang in ordered_languages:
            if lang in seen_languages:
                continue
            seen_languages.add(lang)
            items = subtitles.get(lang)
            subtitle = subtitle_for_language(lang, items)
            if subtitle:
                out.append(subtitle)
        return tuple(out)
    for lang in subtitle_languages:
        subtitle = subtitle_for_language(lang, subtitles.get(lang))
        if subtitle:
            return (subtitle,)
    return ()


def subtitle_for_language(lang: str, items: Any) -> dict[str, str] | None:
    if not isinstance(items, list):
        return None
    best: tuple[int, dict[str, str]] | None = None
    for item in items:
        if not isinstance(item, dict):
            continue
        if not item.get("url"):
            continue
        format_value, _format_source = subtitle_item_format(item)
        if format_value not in SUBTITLE_FORMAT_PRIORITY:
            continue
        subtitle = {
            "name": str(item.get("name") or lang),
            "language": str(lang),
            "url": str(item["url"]),
            "format": format_value,
        }
        priority = SUBTITLE_FORMAT_PRIORITY.index(format_value)
        if best is None or priority < best[0]:
            best = (priority, subtitle)
    return best[1] if best else None


def subtitle_item_format(item: dict[str, Any]) -> tuple[str, str]:
    query_format = subtitle_url_format(str(item.get("url") or ""))
    if query_format:
        return query_format, "url"
    for key in ("ext", "format"):
        format_value = normalize_subtitle_format(str(item.get(key) or ""))
        if format_value:
            return format_value, key
    mime_format = normalize_subtitle_format(str(item.get("mimetype") or item.get("mime_type") or ""))
    return mime_format, "mime" if mime_format else ""


def subtitle_url_format(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("fmt", "format"):
        for value in query.get(key, ()):
            format_value = normalize_subtitle_format(value)
            if format_value:
                return format_value
    path = parsed.path.lower()
    for ext in SUBTITLE_FORMAT_PRIORITY:
        if path.endswith(f".{ext}"):
            return ext
    return ""


def normalize_subtitle_format(value: str) -> str:
    lower = value.strip().lower().lstrip(".")
    return {
        "application/x-subrip": "srt",
        "application/subrip": "srt",
        "text/srt": "srt",
        "text/vtt": "vtt",
        "text/webvtt": "vtt",
        "text/x-ssa": "ass",
        "application/ttml+xml": "ttml",
    }.get(lower, lower)


def log_subtitle_selection(
    source: str,
    items: tuple[dict[str, str], ...],
    *,
    subtitles_enabled: bool,
    all_manual: bool,
    requested: tuple[str, ...],
    expanded: tuple[str, ...],
    manual_langs: tuple[str, ...],
    auto_langs: tuple[str, ...],
) -> None:
    logger.debug(
        "youtube subtitles result source=%s count=%s enabled=%s all_manual=%s requested=%s expanded=%s manual_langs=%s auto_langs=%s items=%s",
        source,
        len(items),
        subtitles_enabled,
        all_manual,
        requested,
        expanded,
        manual_langs,
        auto_langs,
        subtitle_debug_items(items),
    )


def subtitle_language_keys(value: Any) -> tuple[str, ...]:
    if not isinstance(value, dict):
        return ()
    return tuple(str(key) for key in value.keys())


def subtitle_debug_items(items: tuple[dict[str, str], ...]) -> tuple[dict[str, str], ...]:
    return tuple(subtitle_debug_item(item) for item in items)


def subtitle_debug_item(item: dict[str, str] | None) -> dict[str, str]:
    if not item:
        return {}
    return {
        "language": item.get("language", ""),
        "format": item.get("format", ""),
        "name": item.get("name", ""),
    }


def unique_subtitles(subtitles: tuple[dict[str, str], ...]) -> tuple[dict[str, str], ...]:
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for subtitle in subtitles:
        key = subtitle.get("url", "")
        if not key or key in seen:
            continue
        out.append(subtitle)
        seen.add(key)
    return tuple(out)


def original_automatic_captions(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, Any] = {}
    for lang, items in value.items():
        if not isinstance(items, list):
            continue
        filtered = [item for item in items if is_original_automatic_caption_item(item)]
        if filtered:
            out[str(lang)] = filtered
    return out


def is_original_automatic_caption_item(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    url = str(item.get("url") or "")
    if not url:
        return False
    query = parse_qs(urlparse(url).query)
    return INCLUDE_TRANSLATED_AUTOMATIC_FALLBACK or "tlang" not in query


def youtube_subtitle_language_order(languages: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for lang in languages:
        for candidate in youtube_subtitle_language_aliases(lang):
            if candidate not in out:
                out.append(candidate)
    for fallback in ("en-orig", "en"):
        if fallback not in out:
            out.append(fallback)
    return tuple(out)


def youtube_subtitle_language_aliases(lang: str) -> tuple[str, ...]:
    value = lang.strip()
    lower = value.lower().replace("_", "-")
    if lower in {"zh", "zh-cn", "zh-hans", "chinese", "chi", "zho"}:
        return ("zh-Hans", "zh-CN", "zh", "zh-Hant", "zh-TW")
    if lower in {"zh-tw", "zh-hk", "zh-mo", "zh-hant"}:
        return (value, "zh-Hant", "zh-TW", "zh-HK", "zh-Hans", "zh")
    if lower in {"en", "en-us", "en-gb", "english"}:
        if lower == "en":
            return ("en", "en-orig")
        return (value, "en", "en-orig")
    if not value:
        return ()
    return (value,)
