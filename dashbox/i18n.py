from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar


DEFAULT_LOCALE = "zh-CN"
SUPPORTED_LOCALES = {"zh-CN", "en-US"}
_current_locale: ContextVar[str] = ContextVar("dashbox_locale", default=DEFAULT_LOCALE)

_MESSAGES = {
    "zh-CN": {
        "common.unnamed": "未命名",
        "common.unavailable": "不可用",
        "common.search": "搜索",
        "common.play": "播放",
        "common.playlist": "播放列表",
        "common.enter": "点击进入",
        "common.enter_detail": "点击进入详情",
        "common.items": "{count}项",
        "common.parts": "{count}P",
        "common.episode": "第{index}集",
        "common.lesson": "第{index}课",
        "common.song": "第{index}首",
        "tvbox.demo": "示例",
        "tvbox.demo_youtube_video": "示例 YouTube 视频",
        "tvbox.demo_remarks": "在 config.json 中配置 sources 后替换",
        "tvbox.current_directory": "当前目录",
        "tvbox.play_current_directory": "点击播放$$$当前目录",
        "tvbox.play_directory": "播放此列表",
        "tvbox.order": "排序",
        "tvbox.order_source": "源顺序",
        "tvbox.order_reverse": "反转",
        "tvbox.refresh_directory": "刷新此列表",
        "tvbox.refresh_rejected": "稍后重试",
        "tvbox.auth_title": "访问码",
        "tvbox.auth_empty": "未输入",
        "tvbox.auth_prompt": "请输入访问码",
        "tvbox.auth_backspace": "退格",
        "tvbox.auth_submit": "确认",
        "tvbox.auth_clear": "清空",
        "tvbox.auth_success_restart": "认证成功，请重启应用",
        "tvbox.auth_failed": "访问码错误",
        "site.youtube": "YouTube",
        "site.bilibili": "Bilibili",
        "site.pornhub": "Pornhub",
        "bilibili.watch_later": "稍后再看",
        "bilibili.favorites": "收藏夹",
        "bilibili.collection": "合集",
        "bilibili.series": "系列",
        "bilibili.audio": "音频",
        "bilibili.bangumi": "番剧",
        "bilibili.course": "课程",
        "bilibili.songlist": "歌单",
        "bilibili.live_not_started": "直播未开播",
    },
    "en-US": {
        "common.unnamed": "Untitled",
        "common.unavailable": "Unavailable",
        "common.search": "Search",
        "common.play": "Play",
        "common.playlist": "Playlist",
        "common.enter": "Open",
        "common.enter_detail": "Open details",
        "common.items": "{count} items",
        "common.parts": "{count}P",
        "common.episode": "Episode {index}",
        "common.lesson": "Lesson {index}",
        "common.song": "Track {index}",
        "tvbox.demo": "Demo",
        "tvbox.demo_youtube_video": "Demo YouTube Video",
        "tvbox.demo_remarks": "Configure sources in config.json to replace this",
        "tvbox.current_directory": "Current directory",
        "tvbox.play_current_directory": "Play$$$Current directory",
        "tvbox.play_directory": "Play all",
        "tvbox.order": "Order",
        "tvbox.order_source": "Source order",
        "tvbox.order_reverse": "Reverse",
        "tvbox.refresh_directory": "Refresh list",
        "tvbox.refresh_rejected": "Try again later",
        "tvbox.auth_title": "Access code",
        "tvbox.auth_empty": "Empty",
        "tvbox.auth_prompt": "Enter access code",
        "tvbox.auth_backspace": "Backspace",
        "tvbox.auth_submit": "Confirm",
        "tvbox.auth_clear": "Clear",
        "tvbox.auth_success_restart": "Authenticated. Restart the app",
        "tvbox.auth_failed": "Wrong access code",
        "site.youtube": "YouTube",
        "site.bilibili": "Bilibili",
        "site.pornhub": "Pornhub",
        "bilibili.watch_later": "Watch later",
        "bilibili.favorites": "Favorites",
        "bilibili.collection": "Collection",
        "bilibili.series": "Series",
        "bilibili.audio": "Audio",
        "bilibili.bangumi": "Bangumi",
        "bilibili.course": "Course",
        "bilibili.songlist": "Song list",
        "bilibili.live_not_started": "Live not started",
    },
}


def normalize_locale(locale: str = "") -> str:
    return locale if locale in SUPPORTED_LOCALES else DEFAULT_LOCALE


def current_locale() -> str:
    return normalize_locale(_current_locale.get())


@contextmanager
def use_locale(locale: str) -> Iterator[None]:
    token = _current_locale.set(normalize_locale(locale))
    try:
        yield
    finally:
        _current_locale.reset(token)


def text(key: str, locale: str = "", **values: object) -> str:
    selected = normalize_locale(locale) if locale else current_locale()
    template = _MESSAGES.get(selected, _MESSAGES[DEFAULT_LOCALE]).get(key)
    if template is None:
        template = _MESSAGES[DEFAULT_LOCALE].get(key, key)
    return template.format(**values) if values else template


def unnamed() -> str:
    return text("common.unnamed")


def unavailable() -> str:
    return text("common.unavailable")


def search() -> str:
    return text("common.search")


def play() -> str:
    return text("common.play")


def playlist() -> str:
    return text("common.playlist")


def enter() -> str:
    return text("common.enter")


def enter_detail() -> str:
    return text("common.enter_detail")


def item_count(count: int) -> str:
    return text("common.items", count=count)


def part_count(count: int) -> str:
    return text("common.parts", count=count)


def episode_title(index: int) -> str:
    return text("common.episode", index=index)


def lesson_title(index: int) -> str:
    return text("common.lesson", index=index)


def song_title(index: int) -> str:
    return text("common.song", index=index)


def tvbox_demo() -> str:
    return text("tvbox.demo")


def tvbox_demo_youtube_video() -> str:
    return text("tvbox.demo_youtube_video")


def tvbox_demo_remarks() -> str:
    return text("tvbox.demo_remarks")


def tvbox_current_directory() -> str:
    return text("tvbox.current_directory")


def tvbox_play_current_directory() -> str:
    return text("tvbox.play_current_directory")


def tvbox_play_directory() -> str:
    return text("tvbox.play_directory")


def tvbox_order() -> str:
    return text("tvbox.order")


def tvbox_order_source() -> str:
    return text("tvbox.order_source")


def tvbox_order_reverse() -> str:
    return text("tvbox.order_reverse")


def bilibili_watch_later() -> str:
    return text("bilibili.watch_later")


def bilibili_favorites() -> str:
    return text("bilibili.favorites")


def bilibili_collection() -> str:
    return text("bilibili.collection")


def bilibili_series() -> str:
    return text("bilibili.series")


def bilibili_audio() -> str:
    return text("bilibili.audio")


def bilibili_bangumi() -> str:
    return text("bilibili.bangumi")


def bilibili_course() -> str:
    return text("bilibili.course")


def bilibili_songlist() -> str:
    return text("bilibili.songlist")


def bilibili_live_not_started() -> str:
    return text("bilibili.live_not_started")


def bilibili_audio_title(mid: str) -> str:
    return f"{mid} - {bilibili_audio()}"


def site_search_title(site: str, keyword: str) -> str:
    return f"{site} {search()}: {keyword}" if keyword else f"{site} {search()}"


def youtube_search_title(keyword: str) -> str:
    return site_search_title(text("site.youtube"), keyword)


def bilibili_search_title(keyword: str) -> str:
    return site_search_title(text("site.bilibili"), keyword)


def pornhub_search_title(keyword: str) -> str:
    return site_search_title(text("site.pornhub"), keyword)


def spider_labels(locale: str = DEFAULT_LOCALE) -> dict[str, str]:
    return {
        "refreshDirectory": text("tvbox.refresh_directory", locale=locale),
        "refreshRejected": text("tvbox.refresh_rejected", locale=locale),
        "currentDirectory": text("tvbox.current_directory", locale=locale),
        "playCurrentDirectory": text("tvbox.play_current_directory", locale=locale),
        "play": text("common.play", locale=locale),
        "episode": text("common.episode", locale=locale),
        "items": text("common.items", locale=locale),
        "authTitle": text("tvbox.auth_title", locale=locale),
        "authEmpty": text("tvbox.auth_empty", locale=locale),
        "authPrompt": text("tvbox.auth_prompt", locale=locale),
        "authBackspace": text("tvbox.auth_backspace", locale=locale),
        "authSubmit": text("tvbox.auth_submit", locale=locale),
        "authClear": text("tvbox.auth_clear", locale=locale),
        "authSuccessRestart": text("tvbox.auth_success_restart", locale=locale),
        "authFailed": text("tvbox.auth_failed", locale=locale),
    }
