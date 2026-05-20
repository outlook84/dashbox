# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import uuid
from urllib.parse import parse_qs, quote, urlencode

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

from resources.lib.client import DashboxClient, DashboxError
from resources.lib.routing import display_items


ADDON = xbmcaddon.Addon()
PLUGIN_URL = sys.argv[0]
HANDLE = int(sys.argv[1])
DIRECTORY_SELECTED_URL = "__dashbox_directory__"
ACCESS_CODE_RE = re.compile(r"^[0-9]{4,12}$")
VIDEO_CODEC_ORDER = ("h264", "hevc", "vp9", "av01")
VIDEO_CODEC_SLOT_KEYS = ("video_codec_1", "video_codec_2", "video_codec_3", "video_codec_4")
VIDEO_CODEC_BY_SLOT_VALUE = {
    "1": "h264",
    "2": "hevc",
    "3": "vp9",
    "4": "av01",
}
AUDIO_CODEC_ORDER = ("aac", "opus", "eac3", "ac3", "flac", "other")
AUDIO_CODEC_SLOT_KEYS = (
    "audio_codec_1",
    "audio_codec_2",
    "audio_codec_3",
    "audio_codec_4",
    "audio_codec_5",
    "audio_codec_6",
)
AUDIO_CODEC_BY_SLOT_VALUE = {
    "1": "aac",
    "2": "opus",
    "3": "eac3",
    "4": "ac3",
    "5": "flac",
    "6": "other",
}
DANMAKU_FONT_SIZE = 32


def log(message, level=xbmc.LOGINFO):
    xbmc.log("plugin.video.dashbox: {}".format(message), level)


def plugin_url(**params):
    return PLUGIN_URL + "?" + urlencode(params)


def settings_value(key):
    return ADDON.getSetting(key).strip()


def bool_setting_default_true(key):
    value = settings_value(key).lower()
    if value in ("false", "0", "no", "off"):
        return False
    return True


def set_setting(key, value):
    ADDON.setSetting(key, value)


def connection_settings():
    gateway = settings_value("gateway")
    sub_id = settings_value("sub_id")
    token = settings_value("access_token")
    if not gateway or not sub_id:
        raise DashboxError(localized(30012))
    return gateway, sub_id, token


def client():
    try:
        gateway, sub_id, token = connection_settings()
    except DashboxError:
        ADDON.openSettings()
        gateway, sub_id, token = connection_settings()
    return DashboxClient(gateway, sub_id, token)


def validate_connection_settings():
    gateway = settings_value("gateway")
    sub_id = settings_value("sub_id")
    if not gateway or not sub_id:
        raise DashboxError(localized(30012))


def clear_token(api):
    set_setting("access_token", "")
    api.access_token = ""


def clear_access_code():
    set_setting("access_code", "")


def save_token(api, token):
    set_setting("access_token", token)
    api.access_token = token


def save_credentials(api, token, access_code):
    save_token(api, token)
    if access_code:
        set_setting("access_code", access_code)


def ensure_authenticated(api):
    token = settings_value("access_token")
    if token:
        api.access_token = token
        return True
    access_code = settings_value("access_code")
    try:
        auth = api.auth(access_code)
    except DashboxError as exc:
        if getattr(exc, "status_code", 0) in {400, 401}:
            if access_code:
                clear_access_code()
            return False
        raise
    token = str(auth.get("access_token") or "")
    if token:
        save_token(api, token)
        return True
    return False


def route():
    params = parse_qs(sys.argv[2][1:])
    action = first(params, "action") or "home"
    if action == "settings":
        ADDON.openSettings()
        validate_connection_settings()
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return
    api = client()
    if action == "authenticate":
        authenticate(api)
        return
    if not ensure_authenticated(api):
        render_auth_page()
        return
    if action == "open":
        with_auth_failure(
            lambda: render_page(
                api.items(first(params, "id"), refresh=first(params, "refresh") == "1"),
                include_refresh=True,
            ),
            api,
        )
    elif action == "detail":
        with_auth_failure(lambda: render_page(api.detail(first(params, "id"))), api)
    elif action == "search":
        key = first(params, "id")
        if not key:
            heading = first(params, "heading") or localized(30014)
            key = xbmcgui.Dialog().input(heading, type=xbmcgui.INPUT_ALPHANUM)
            if key:
                xbmc.executebuiltin(
                    "AlarmClock(dashbox_search,Container.Update({}\\,replace),00:00:01,silent)".format(
                        plugin_url(action="search", id=key)
                    )
                )
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
            return
        with_auth_failure(lambda: render_page(api.search(key)), api)
    elif action == "play":
        with_auth_failure(lambda: resolve_play(api, first(params, "id")), api, render_on_unauthorized=False)
    elif action == "play_directory":
        with_auth_failure(lambda: play_directory(api, first(params, "id")), api, render_on_unauthorized=False)
    elif action == "start_queue":
        start_queue(first(params, "token"))
    else:
        with_auth_failure(lambda: render_page(api.home()), api)


def first(params, key):
    values = params.get(key) or []
    return values[0] if values else ""


def with_auth_failure(callback, api, render_on_unauthorized=True):
    try:
        return callback()
    except DashboxError as exc:
        if getattr(exc, "status_code", 0) != 401:
            raise
        clear_token(api)
        if ensure_authenticated(api):
            try:
                return callback()
            except DashboxError as retry_exc:
                if getattr(retry_exc, "status_code", 0) != 401:
                    raise
                clear_token(api)
        if render_on_unauthorized:
            render_auth_page()
        else:
            xbmcgui.Dialog().notification("Dashbox", localized(30019), xbmcgui.NOTIFICATION_ERROR, 5000)
            xbmc.executebuiltin("Container.Refresh")
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return None


def authenticate(api):
    code = xbmcgui.Dialog().numeric(0, localized(30017), "", True)
    if not code:
        render_auth_page()
        return
    if not ACCESS_CODE_RE.fullmatch(code):
        xbmcgui.Dialog().notification("Dashbox", localized(30018), xbmcgui.NOTIFICATION_ERROR, 5000)
        render_auth_page()
        return
    try:
        auth = api.auth(code)
    except DashboxError as exc:
        if getattr(exc, "status_code", 0) in {400, 401}:
            xbmcgui.Dialog().notification("Dashbox", localized(30019), xbmcgui.NOTIFICATION_ERROR, 5000)
            render_auth_page()
            return
        raise
    token = str(auth.get("access_token") or "")
    if not token:
        xbmcgui.Dialog().notification("Dashbox", localized(30019), xbmcgui.NOTIFICATION_ERROR, 5000)
        render_auth_page()
        return
    save_credentials(api, token, code)
    xbmc.executebuiltin("Container.Refresh")
    xbmcplugin.endOfDirectory(HANDLE, succeeded=False)


def render_auth_page():
    render_page(
        {
            "id": "__dashbox_auth_page__",
            "content_type": "videos",
            "cache_to_disc": False,
            "items": [
                {
                    "id": "__dashbox_authenticate__",
                    "title": localized(30016),
                    "kind": "settings",
                    "is_folder": False,
                    "is_playable": False,
                    "plugin_action": "authenticate",
                },
                {
                    "id": "__dashbox_settings__",
                    "title": localized(30010),
                    "kind": "settings",
                    "is_folder": False,
                    "is_playable": False,
                    "plugin_action": "settings",
                },
            ],
        }
    )


def render_page(page, *, include_refresh=False):
    xbmcplugin.setContent(HANDLE, page.get("content_type") or "videos")
    entries = []
    include_controls = not page.get("id")
    server_labels = page.get("labels") if isinstance(page.get("labels"), dict) else {}
    labels = {
        "settings": localized(30010),
        "play_directory": server_labels.get("play_directory") or "",
        "refresh_directory": server_labels.get("refresh_directory") or "",
        "current_directory": server_labels.get("current_directory") or "",
        "refresh_rejected": server_labels.get("refresh_rejected") or "",
    }
    for item in display_items(page, include_controls=include_controls, include_refresh=include_refresh, labels=labels):
        entries.append((item_url(item), list_item(item), bool(item.get("is_folder"))))
    xbmcplugin.addDirectoryItems(HANDLE, entries, totalItems=len(entries))
    xbmcplugin.endOfDirectory(
        HANDLE,
        succeeded=True,
        updateListing=bool(page.get("update_listing")),
        cacheToDisc=bool(page.get("cache_to_disc")),
    )


def item_url(item):
    item_id = str(item.get("id") or "")
    plugin_action = str(item.get("plugin_action") or "")
    if plugin_action:
        return plugin_url(action=plugin_action)
    kind = item.get("kind")
    if kind == "refresh":
        return plugin_url(action="open", id=item_id, refresh="1")
    if kind == "search":
        if item_id and item.get("is_folder"):
            return plugin_url(action="open", id=item_id)
        title = str(item.get("title") or "")
        if title:
            return plugin_url(action="search", id=item_id, heading=title)
        return plugin_url(action="search", id=item_id)
    if item.get("selected_url") == DIRECTORY_SELECTED_URL:
        return plugin_url(action="play_directory", id=item_id)
    if item.get("is_playable"):
        return plugin_url(action="play", id=item.get("play_url") or item_id)
    if item.get("is_folder"):
        return plugin_url(action="open", id=item_id)
    return plugin_url(action="detail", id=item_id)


def list_item(item):
    title = str(item.get("title") or item.get("id") or "")
    li = xbmcgui.ListItem(label=title)
    art = compact_dict(item.get("art") or {})
    if art:
        li.setArt(art)
    subtitle = str(item.get("subtitle") or "")
    set_video_info(li, video_info_with_subtitle(item.get("info") or {}, subtitle), title)
    if subtitle:
        li.setLabel2(subtitle)
    if item.get("is_playable"):
        li.setProperty("IsPlayable", "true")
    return li


def video_info_with_subtitle(info, subtitle):
    if not subtitle:
        return info
    out = dict(info)
    if not out.get("plot_outline"):
        out["plot_outline"] = subtitle
    if not out.get("plot"):
        out["plot"] = subtitle
    return out


def resolve_play(api, play_id):
    play = api.play(play_id, playback_preferences())
    li = xbmcgui.ListItem(label=str(play.get("title") or play_id), path=playback_path(play))
    li.setProperty("IsPlayable", "true")
    li.setContentLookup(False if play.get("content_lookup") is False else True)
    set_mime_type(li, play.get("mime_type"))
    art = compact_dict(play.get("art") or {})
    if art:
        li.setArt(art)
    set_video_info(li, play.get("info") or {}, str(play.get("title") or play_id))
    subtitles = [str(item.get("url")) for item in play.get("subtitles") or [] if item.get("url")]
    if subtitles:
        li.setSubtitles(subtitles)
    apply_headers(li, play.get("headers") or {})
    apply_inputstream(li, play.get("inputstream") or {})
    xbmcplugin.setResolvedUrl(HANDLE, True, listitem=li)


def play_directory(api, detail_id):
    page = api.detail(detail_id)
    items = [
        item
        for item in display_items(page)
        if item.get("selected_url") != DIRECTORY_SELECTED_URL
        and item.get("is_playable")
        and str(item.get("play_url") or item.get("id") or "")
    ]
    if not items:
        xbmcgui.Dialog().notification("Dashbox", localized(30013), xbmcgui.NOTIFICATION_ERROR, 5000)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return
    token = save_queue(items)
    xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
    xbmc.executebuiltin("RunPlugin({})".format(plugin_url(action="start_queue", token=token)))


def start_queue(token):
    items = load_queue(token)
    if not items:
        xbmcgui.Dialog().notification("Dashbox", localized(30013), xbmcgui.NOTIFICATION_ERROR, 5000)
        return
    playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
    playlist.clear()
    for item in items:
        li = list_item(item)
        li.setProperty("ForceResolvePlugin", "true")
        playlist.add(url=plugin_url(action="play", id=item.get("play_url") or item.get("id")), listitem=li)
    xbmc.Player().play(playlist, startpos=0)


def save_queue(items):
    token = uuid.uuid4().hex
    with open(queue_path(token), "w", encoding="utf-8") as handle:
        json.dump(items, handle, ensure_ascii=False)
    return token


def load_queue(token):
    path = queue_path(token)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            value = json.load(handle)
    except Exception:
        return []
    try:
        os.unlink(path)
    except OSError:
        pass
    return value if isinstance(value, list) else []


def queue_path(token):
    safe = "".join(char for char in str(token or "") if char.isalnum() or char in "-_")
    return os.path.join(tempfile.gettempdir(), "dashbox-kodi-queue-{}.json".format(safe))


def set_video_info(li, info, fallback_title):
    tag = li.getVideoInfoTag()
    title = str(info.get("title") or fallback_title)
    if title:
        tag.setTitle(title)
    if info.get("plot"):
        tag.setPlot(str(info.get("plot")))
    if info.get("plot_outline"):
        tag.setPlotOutline(str(info.get("plot_outline")))
    if int_value(info.get("duration")):
        tag.setDuration(int_value(info.get("duration")))
    if int_value(info.get("year")):
        tag.setYear(int_value(info.get("year")))
    if info.get("media_type"):
        tag.setMediaType(str(info.get("media_type")))


def apply_headers(li, headers):
    if not headers:
        return
    encoded = encode_headers(headers)
    li.setProperty("inputstream.adaptive.manifest_headers", encoded)
    li.setProperty("inputstream.adaptive.stream_headers", encoded)


def playback_path(play):
    url = str(play.get("url") or "")
    headers = play.get("headers") or {}
    inputstream = play.get("inputstream") or {}
    if not headers or inputstream.get("addon"):
        return url
    separator = "&" if "|" in url else "|"
    return url + separator + encode_headers(headers)


def encode_headers(headers):
    return "&".join("{}={}".format(quote(str(k)), quote(str(v))) for k, v in headers.items())


def set_mime_type(li, mime_type):
    if not mime_type:
        return
    if hasattr(li, "setMimeType"):
        li.setMimeType(str(mime_type))
    else:
        li.setProperty("MimeType", str(mime_type))


def apply_inputstream(li, inputstream):
    addon = str(inputstream.get("addon") or "")
    if addon:
        li.setProperty("inputstream", addon)
    if inputstream.get("manifest_type"):
        li.setProperty("inputstream.adaptive.manifest_type", str(inputstream.get("manifest_type")))
    manifest_headers = inputstream.get("manifest_headers") or {}
    if manifest_headers:
        li.setProperty("inputstream.adaptive.manifest_headers", encode_headers(manifest_headers))
    stream_headers = inputstream.get("stream_headers") or {}
    if stream_headers:
        li.setProperty("inputstream.adaptive.stream_headers", encode_headers(stream_headers))


def playback_preferences():
    prefs = {}
    prefs["video_codec_preferences"] = codec_slot_preferences(
        VIDEO_CODEC_SLOT_KEYS,
        VIDEO_CODEC_BY_SLOT_VALUE,
        VIDEO_CODEC_ORDER,
        localized(30101),
    )
    prefs["audio_codec_preferences"] = codec_slot_preferences(
        AUDIO_CODEC_SLOT_KEYS,
        AUDIO_CODEC_BY_SLOT_VALUE,
        AUDIO_CODEC_ORDER,
        localized(30102),
    )
    height = int_value(settings_value("max_video_height"))
    fps = int_value(settings_value("max_video_fps"))
    if height:
        prefs["max_video_height"] = height
    if fps:
        prefs["max_video_fps"] = fps
    prefs["danmaku_enabled"] = bool_setting_default_true("danmaku_enabled")
    danmaku_font_size = int_value(settings_value("danmaku_font_size"))
    prefs["danmaku_font_size"] = danmaku_font_size if danmaku_font_size else DANMAKU_FONT_SIZE
    prefs["youtube_subtitles"] = bool_setting_default_false("youtube_subtitles")
    subtitle_languages = kodi_subtitle_languages()
    if subtitle_languages:
        prefs["subtitle_languages"] = subtitle_languages
    return prefs


def bool_setting_default_false(key):
    value = settings_value(key).lower()
    return value in ("true", "1", "yes", "on")


def kodi_subtitle_languages():
    languages = []
    add_language(languages, xbmc.getLanguage(xbmc.ISO_639_1, region=True))
    add_language(languages, xbmc.getLanguage(xbmc.ISO_639_1))
    return languages


def add_language(languages, value):
    value = str(value or "").strip()
    if value and value not in languages:
        languages.append(value)


def codec_slot_preferences(slot_keys, slot_value_map, codec_order, label):
    raw_values = [settings_value(key) for key in slot_keys]
    if not any(raw_values):
        return [{"codec": codec, "enabled": True} for codec in codec_order]

    ordered = []
    seen = set()
    for raw_value in raw_values:
        codec = slot_value_map.get(raw_value)
        if codec and codec not in seen:
            ordered.append(codec)
            seen.add(codec)
    if not ordered:
        raise DashboxError("{}: {}".format(label, localized(30150)))
    preferences = [{"codec": codec, "enabled": True} for codec in ordered]
    for codec in codec_order:
        if codec not in seen:
            preferences.append({"codec": codec, "enabled": False})
    return preferences


def compact_dict(value):
    return {str(k): str(v) for k, v in value.items() if v}


def int_value(value):
    try:
        return int(value)
    except Exception:
        return 0


def localized(message_id):
    value = ADDON.getLocalizedString(message_id)
    return value or str(message_id)


try:
    route()
except DashboxError as exc:
    log(str(exc), xbmc.LOGERROR)
    xbmcgui.Dialog().notification("Dashbox", str(exc), xbmcgui.NOTIFICATION_ERROR, 5000)
    xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
except Exception as exc:
    log(str(exc), xbmc.LOGERROR)
    xbmcgui.Dialog().notification("Dashbox", localized(30013), xbmcgui.NOTIFICATION_ERROR, 5000)
    xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
