import importlib.util
import sys
import types
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "dashbox" / "kodi" / "plugin.video.dashbox" / "default.py"


class FakeAddon:
    settings = {
        "gateway": "http://dashbox.test",
        "sub_id": "main",
        "access_code": "",
        "access_token": "token",
    }
    opened_settings = False

    def getSetting(self, key):
        return self.settings.get(key, "")

    def setSetting(self, key, value):
        self.settings[key] = value

    def getLocalizedString(self, message_id):
        return str(message_id)

    def openSettings(self):
        self.opened_settings = True


class FakeVideoInfoTag:
    def __init__(self):
        self.title = ""
        self.plot = ""
        self.plot_outline = ""

    def setTitle(self, value):
        self.title = value
        return None

    def setPlot(self, value):
        self.plot = value
        return None

    def setPlotOutline(self, value):
        self.plot_outline = value
        return None

    def setDuration(self, _value):
        return None

    def setYear(self, _value):
        return None

    def setMediaType(self, _value):
        return None


class FakeListItem:
    def __init__(self, label="", path=""):
        self.label = label
        self.path = path
        self.properties = {}
        self.video_info_tag = FakeVideoInfoTag()
        self.label2 = ""

    def setProperty(self, key, value):
        self.properties[key] = value

    def setLabel2(self, value):
        self.label2 = value

    def setContentLookup(self, value):
        self.content_lookup = value

    def setMimeType(self, value):
        self.mime_type = value

    def setArt(self, value):
        self.art = value

    def setSubtitles(self, value):
        self.subtitles = value

    def getVideoInfoTag(self):
        return self.video_info_tag


class FakeDialog:
    numeric_value = ""
    numeric_calls = []
    input_value = ""
    input_calls = []

    def input(self, *args, **kwargs):
        self.input_calls.append((args, kwargs))
        return self.input_value

    def numeric(self, *args, **kwargs):
        self.numeric_calls.append((args, kwargs))
        return self.numeric_value

    def notification(self, *_args, **_kwargs):
        return None


class FakeDashboxError(Exception):
    def __init__(self, message="", status_code=0):
        super().__init__(message)
        self.status_code = status_code


class FakeClient:
    auth_response = {"access_token": "token"}
    auth_error_status = 0
    auth_calls = []
    home_response = {"items": [{"id": "main", "title": "Main", "is_folder": True}]}
    home_error_status = 0
    home_failures_before_success = 0
    home_calls = 0
    items_response = {"id": "folder", "items": []}
    items_calls = []
    detail_response = {}
    detail_calls = []
    search_response = {"items": []}
    search_calls = []
    play_calls = []
    display_calls = []

    def __init__(self, _gateway, _sub_id, _token):
        self.access_token = _token

    def auth(self, access_code):
        FakeClient.auth_calls.append(access_code)
        if FakeClient.auth_error_status:
            raise FakeDashboxError("auth failed", FakeClient.auth_error_status)
        return dict(FakeClient.auth_response)

    def home(self):
        FakeClient.home_calls += 1
        if FakeClient.home_failures_before_success:
            FakeClient.home_failures_before_success -= 1
            raise FakeDashboxError("unauthorized", 401)
        if FakeClient.home_error_status:
            raise FakeDashboxError("unauthorized", FakeClient.home_error_status)
        return dict(FakeClient.home_response)

    def play(self, _play_id, _preferences):
        FakeClient.play_calls.append((_play_id, _preferences))
        return dict(FakeClient.play_response)

    def detail(self, item_id):
        FakeClient.detail_calls.append(item_id)
        return dict(FakeClient.detail_response)

    def search(self, key):
        FakeClient.search_calls.append(key)
        return dict(FakeClient.search_response)

    def items(self, item_id, refresh=False):
        FakeClient.items_calls.append((item_id, refresh))
        return dict(FakeClient.items_response)


def load_plugin(monkeypatch, play_response):
    resolved = {}
    reset_fakes()
    FakeClient.play_response = play_response
    monkeypatch.setattr(sys, "argv", ["plugin://plugin.video.dashbox", "1", "?action=play&id=video"])
    monkeypatch.setitem(sys.modules, "xbmc", fake_xbmc_module())
    monkeypatch.setitem(sys.modules, "xbmcaddon", fake_xbmcaddon_module())
    monkeypatch.setitem(sys.modules, "xbmcgui", fake_xbmcgui_module())
    monkeypatch.setitem(sys.modules, "xbmcplugin", fake_xbmcplugin_module(resolved))
    install_resource_stubs(monkeypatch)

    module_name = "dashbox_kodi_plugin_default_" + str(len(sys.modules))
    spec = importlib.util.spec_from_file_location(module_name, DEFAULT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return resolved["listitem"], module


def load_plugin_with_action(
    monkeypatch,
    query,
    *,
    play_response=None,
    detail_response=None,
    items_response=None,
    search_response=None,
    addon_settings=None,
    auth_error_status=0,
    home_error_status=0,
    home_failures_before_success=0,
    numeric_value="",
    input_value="",
):
    resolved = {}
    events = []
    reset_fakes()
    if addon_settings:
        FakeAddon.settings.update(addon_settings)
    FakeClient.auth_error_status = auth_error_status
    FakeClient.home_error_status = home_error_status
    FakeClient.home_failures_before_success = home_failures_before_success
    FakeDialog.numeric_value = numeric_value
    FakeDialog.input_value = input_value
    FakeClient.play_response = play_response or {}
    FakeClient.detail_response = detail_response or {}
    FakeClient.items_response = items_response or {"id": "folder", "items": []}
    FakeClient.search_response = search_response or {"items": []}
    FakeClient.detail_calls = []
    xbmc_module = fake_xbmc_module()
    xbmc_module.events = events
    monkeypatch.setattr(sys, "argv", ["plugin://plugin.video.dashbox", "1", query])
    monkeypatch.setitem(sys.modules, "xbmc", xbmc_module)
    monkeypatch.setitem(sys.modules, "xbmcaddon", fake_xbmcaddon_module())
    monkeypatch.setitem(sys.modules, "xbmcgui", fake_xbmcgui_module())
    monkeypatch.setitem(sys.modules, "xbmcplugin", fake_xbmcplugin_module(resolved, events=events))
    install_resource_stubs(monkeypatch)

    module_name = "dashbox_kodi_plugin_default_" + str(len(sys.modules))
    spec = importlib.util.spec_from_file_location(module_name, DEFAULT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, xbmc_module, resolved


def reset_fakes():
    FakeAddon.settings = {
        "gateway": "http://dashbox.test",
        "sub_id": "main",
        "access_code": "",
        "access_token": "token",
    }
    FakeAddon.opened_settings = False
    FakeDialog.numeric_value = ""
    FakeDialog.numeric_calls = []
    FakeDialog.input_value = ""
    FakeDialog.input_calls = []
    FakeClient.auth_response = {"access_token": "token"}
    FakeClient.auth_error_status = 0
    FakeClient.auth_calls = []
    FakeClient.home_response = {"items": [{"id": "main", "title": "Main", "is_folder": True}]}
    FakeClient.home_error_status = 0
    FakeClient.home_failures_before_success = 0
    FakeClient.home_calls = 0
    FakeClient.items_response = {"id": "folder", "items": []}
    FakeClient.items_calls = []
    FakeClient.detail_response = {}
    FakeClient.detail_calls = []
    FakeClient.search_response = {"items": []}
    FakeClient.search_calls = []
    FakeClient.play_calls = []
    FakeClient.display_calls = []


def codec_preferences(enabled_order, all_codecs):
    enabled = set(enabled_order)
    return [
        {"codec": codec, "enabled": codec in enabled}
        for codec in (*enabled_order, *(codec for codec in all_codecs if codec not in enabled))
    ]


def install_resource_stubs(monkeypatch):
    resources = types.ModuleType("resources")
    lib = types.ModuleType("resources.lib")
    client = types.ModuleType("resources.lib.client")
    routing = types.ModuleType("resources.lib.routing")
    client.DashboxClient = FakeClient
    client.DashboxError = FakeDashboxError
    routing.display_items = fake_display_items
    monkeypatch.setitem(sys.modules, "resources", resources)
    monkeypatch.setitem(sys.modules, "resources.lib", lib)
    monkeypatch.setitem(sys.modules, "resources.lib.client", client)
    monkeypatch.setitem(sys.modules, "resources.lib.routing", routing)


def fake_display_items(page, **kwargs):
    FakeClient.display_calls.append((page, kwargs))
    items = page.get("items") or []
    if len(items) != 1:
        return items
    parent = items[0]
    episodes = parent.get("episodes") or []
    if not episodes:
        if kwargs.get("include_controls"):
            labels = kwargs.get("labels") or {}
            return items + [{
                "id": "__dashbox_settings__",
                "title": labels.get("settings") or "Settings",
                "is_folder": False,
                "is_playable": False,
                "plugin_action": "settings",
            }]
        return items
    directory = {
        "id": str(parent.get("id") or ""),
        "title": "Play all",
        "is_playable": True,
        "selected_url": "__dashbox_directory__",
        "play_url": "",
    }
    episode_items = [
        {
            "id": episode.get("url"),
            "title": episode.get("title"),
            "art": parent.get("art") or {},
            "info": {**(parent.get("info") or {}), "title": episode.get("title")},
            "is_playable": bool(episode.get("url")),
            "play_url": episode.get("url"),
        }
        for episode in episodes
    ]
    return [directory, *episode_items]


def fake_xbmc_module():
    module = types.ModuleType("xbmc")
    module.LOGINFO = 1
    module.LOGERROR = 4
    module.PLAYLIST_VIDEO = 1
    module.ISO_639_1 = 0
    module.created_playlists = []
    module.player_calls = []
    module.builtin_calls = []
    module.log = lambda *_args, **_kwargs: None
    module.executebuiltin = lambda command, *_args, **_kwargs: module.builtin_calls.append(command)
    module.getLanguage = lambda *_args, **_kwargs: "zh-CN" if _kwargs.get("region") else "zh"
    module.PlayList = lambda playlist_id: FakePlayList(module, playlist_id)
    module.Player = lambda: FakePlayer(module)
    return module


class FakePlayList:
    def __init__(self, module, playlist_id):
        self.module = module
        self.playlist_id = playlist_id
        self.items = []
        self.cleared = False
        module.created_playlists.append(self)

    def clear(self):
        self.cleared = True
        self.items = []

    def add(self, url, listitem=None, index=-1):
        value = (url, listitem, index)
        if index >= 0:
            self.items.insert(index, value)
        else:
            self.items.append(value)


class FakePlayer:
    def __init__(self, module):
        self.module = module

    def play(self, item=None, listitem=None, windowed=False, startpos=-1):
        self.module.events.append("player.play")
        self.module.player_calls.append({
            "item": item,
            "listitem": listitem,
            "windowed": windowed,
            "startpos": startpos,
        })


def fake_xbmcaddon_module():
    module = types.ModuleType("xbmcaddon")
    module.Addon = FakeAddon
    return module


def fake_xbmcgui_module():
    module = types.ModuleType("xbmcgui")
    module.INPUT_ALPHANUM = 0
    module.NOTIFICATION_ERROR = "error"
    module.ListItem = FakeListItem
    module.Dialog = FakeDialog
    return module


def fake_xbmcplugin_module(resolved, events=None):
    module = types.ModuleType("xbmcplugin")
    module.setResolvedUrl = lambda _handle, _succeeded, listitem: resolved.update({"listitem": listitem})
    module.setContent = lambda *_args, **_kwargs: None
    module.addDirectoryItems = lambda _handle, entries, **_kwargs: resolved.update({"directory_items": entries})
    module.endOfDirectory = lambda *_args, **_kwargs: (events.append("endOfDirectory") if events is not None else None)
    return module


def test_resolve_play_appends_headers_to_native_http_path(monkeypatch):
    listitem, _module = load_plugin(
        monkeypatch,
        {
            "url": "https://media.example.test/video.mp4",
            "headers": {"User-Agent": "Kodi Test", "Referer": "https://page.example.test/watch"},
        },
    )

    assert listitem.path == (
        "https://media.example.test/video.mp4|"
        "User-Agent=Kodi%20Test&Referer=https%3A//page.example.test/watch"
    )
    assert listitem.properties["inputstream.adaptive.manifest_headers"] == (
        "User-Agent=Kodi%20Test&Referer=https%3A//page.example.test/watch"
    )


def test_resolve_play_keeps_inputstream_path_bare(monkeypatch):
    listitem, _module = load_plugin(
        monkeypatch,
        {
            "url": "https://media.example.test/manifest.mpd",
            "headers": {"User-Agent": "Kodi Test"},
            "inputstream": {"addon": "inputstream.adaptive", "manifest_type": "mpd"},
        },
    )

    assert listitem.path == "https://media.example.test/manifest.mpd"


def test_resolve_play_sends_codec_slot_preferences(monkeypatch):
    load_plugin_with_action(
        monkeypatch,
        "?action=play&id=video",
        play_response={"url": "https://media.example.test/video.mp4"},
        addon_settings={
            "video_codec_1": "2",
            "video_codec_2": "1",
            "video_codec_3": "2",
            "video_codec_4": "0",
            "audio_codec_1": "3",
            "audio_codec_2": "1",
            "audio_codec_3": "2",
            "audio_codec_4": "3",
            "audio_codec_5": "0",
            "audio_codec_6": "0",
        },
    )

    assert FakeClient.play_calls == [
        (
            "video",
            {
                "video_codec_preferences": codec_preferences(["hevc", "h264"], ["h264", "hevc", "vp9", "av01"]),
                "audio_codec_preferences": codec_preferences(
                    ["eac3", "aac", "opus"],
                    ["aac", "opus", "eac3", "ac3", "flac", "other"],
                ),
                "danmaku_enabled": True,
                "danmaku_font_size": 32,
                "youtube_subtitles": False,
                "subtitle_languages": ["zh-CN", "zh"],
            },
        )
    ]


def test_resolve_play_reports_all_disabled_codec_preferences(monkeypatch):
    load_plugin_with_action(
        monkeypatch,
        "?action=play&id=video",
        play_response={"url": "https://media.example.test/video.mp4"},
        addon_settings={
            "video_codec_1": "0",
            "video_codec_2": "0",
            "video_codec_3": "0",
            "video_codec_4": "0",
        },
    )

    assert FakeClient.play_calls == []


def test_resolve_play_sends_danmaku_font_size(monkeypatch):
    load_plugin_with_action(
        monkeypatch,
        "?action=play&id=video",
        play_response={"url": "https://media.example.test/video.mp4"},
        addon_settings={"danmaku_font_size": "36"},
    )

    assert FakeClient.play_calls[-1][1]["danmaku_font_size"] == 36


def test_resolve_play_sends_disabled_danmaku_signal(monkeypatch):
    load_plugin_with_action(
        monkeypatch,
        "?action=play&id=video",
        play_response={"url": "https://media.example.test/video.mp4"},
        addon_settings={"danmaku_enabled": "false"},
    )

    assert FakeClient.play_calls[-1][1]["danmaku_enabled"] is False


def test_resolve_play_sends_youtube_subtitles_signal(monkeypatch):
    load_plugin_with_action(
        monkeypatch,
        "?action=play&id=video",
        play_response={"url": "https://media.example.test/video.mp4"},
        addon_settings={"youtube_subtitles": "true"},
    )

    assert FakeClient.play_calls[-1][1]["youtube_subtitles"] is True


def test_play_directory_defers_queue_start(monkeypatch):
    _module, xbmc_module, _resolved = load_plugin_with_action(
        monkeypatch,
        "?action=play_directory&id=directory-id",
        detail_response={
            "items": [
                {
                    "title": "Multi P",
                    "art": {"thumb": "https://example.test/thumb.jpg"},
                    "info": {"title": "Multi P"},
                    "episodes": [
                        {"title": "P01 上", "url": "https://media.example.test/bv1?p=1"},
                        {"title": "P02 下", "url": "https://media.example.test/bv1?p=2"},
                    ],
                }
            ]
        },
    )

    assert FakeClient.detail_calls == ["directory-id"]
    assert xbmc_module.created_playlists == []
    assert xbmc_module.player_calls == []
    assert xbmc_module.events == ["endOfDirectory"]
    assert len(xbmc_module.builtin_calls) == 1
    command = xbmc_module.builtin_calls[0]
    assert command.startswith("RunPlugin(plugin://plugin.video.dashbox?")
    token = parse_qs(urlsplit(command.removeprefix("RunPlugin(").removesuffix(")")).query)["token"][0]

    _module, queue_xbmc_module, _resolved = load_plugin_with_action(
        monkeypatch,
        "?action=start_queue&token={}".format(token),
    )

    playlist = queue_xbmc_module.created_playlists[0]
    assert playlist.playlist_id == xbmc_module.PLAYLIST_VIDEO
    assert playlist.cleared is True
    assert [item[0] for item in playlist.items] == [
        "plugin://plugin.video.dashbox?action=play&id=https%3A%2F%2Fmedia.example.test%2Fbv1%3Fp%3D1",
        "plugin://plugin.video.dashbox?action=play&id=https%3A%2F%2Fmedia.example.test%2Fbv1%3Fp%3D2",
    ]
    assert [item[1].label for item in playlist.items] == ["P01 上", "P02 下"]
    assert all(item[1].properties["IsPlayable"] == "true" for item in playlist.items)
    assert all(item[1].properties["ForceResolvePlugin"] == "true" for item in playlist.items)
    assert queue_xbmc_module.events == ["player.play"]
    assert queue_xbmc_module.player_calls == [{
        "item": playlist,
        "listitem": None,
        "windowed": False,
        "startpos": 0,
    }]


def test_home_without_token_shows_auth_page_when_anonymous_auth_fails(monkeypatch):
    _module, _xbmc_module, resolved = load_plugin_with_action(
        monkeypatch,
        "",
        addon_settings={"access_token": ""},
        auth_error_status=400,
    )

    entries = resolved["directory_items"]
    assert FakeClient.auth_calls == [""]
    assert [entry[1].label for entry in entries] == ["30016", "30010"]
    assert "action=authenticate" in entries[0][0]
    assert "action=settings" in entries[1][0]


def test_home_with_expired_token_clears_token_and_shows_auth_page(monkeypatch):
    _module, _xbmc_module, resolved = load_plugin_with_action(
        monkeypatch,
        "",
        auth_error_status=400,
        home_failures_before_success=1,
    )

    entries = resolved["directory_items"]
    assert FakeAddon.settings["access_token"] == ""
    assert FakeClient.auth_calls == [""]
    assert [entry[1].label for entry in entries] == ["30016", "30010"]


def test_home_with_expired_token_uses_saved_access_code_and_retries(monkeypatch):
    _module, _xbmc_module, resolved = load_plugin_with_action(
        monkeypatch,
        "",
        addon_settings={"access_code": "012345"},
        home_failures_before_success=1,
    )

    entries = resolved["directory_items"]
    assert FakeClient.home_calls == 2
    assert FakeClient.auth_calls == ["012345"]
    assert FakeAddon.settings["access_token"] == "token"
    assert [entry[1].label for entry in entries] == ["Main", "30010"]


def test_home_with_expired_token_clears_invalid_saved_access_code(monkeypatch):
    _module, _xbmc_module, resolved = load_plugin_with_action(
        monkeypatch,
        "",
        addon_settings={"access_code": "012345"},
        auth_error_status=401,
        home_failures_before_success=1,
    )

    entries = resolved["directory_items"]
    assert FakeClient.home_calls == 1
    assert FakeClient.auth_calls == ["012345"]
    assert FakeAddon.settings["access_token"] == ""
    assert FakeAddon.settings["access_code"] == ""
    assert [entry[1].label for entry in entries] == ["30016", "30010"]


def test_authenticate_uses_hidden_numeric_dialog_and_saves_token(monkeypatch):
    _module, xbmc_module, _resolved = load_plugin_with_action(
        monkeypatch,
        "?action=authenticate",
        addon_settings={"access_token": ""},
        numeric_value="012345",
    )

    assert FakeDialog.numeric_calls == [((0, "30017", "", True), {})]
    assert FakeClient.auth_calls == ["012345"]
    assert FakeAddon.settings["access_token"] == "token"
    assert FakeAddon.settings["access_code"] == "012345"
    assert xbmc_module.builtin_calls == ["Container.Refresh"]
    assert xbmc_module.events == ["endOfDirectory"]


def test_open_directory_passes_refresh_flag_and_requests_refresh_control(monkeypatch):
    load_plugin_with_action(
        monkeypatch,
        "?action=open&id=folder&refresh=1",
        items_response={"id": "folder", "items": [{"id": "video", "title": "Video", "is_playable": True}]},
    )

    assert FakeClient.items_calls == [("folder", True)]
    assert FakeClient.display_calls[0][1]["include_refresh"] is True


def test_refresh_item_url_reopens_directory_with_refresh(monkeypatch):
    module, _xbmc_module, _resolved = load_plugin_with_action(monkeypatch, "")

    url = module.item_url({"id": "folder", "kind": "refresh"})
    params = parse_qs(urlsplit(url).query)

    assert params["action"] == ["open"]
    assert params["id"] == ["folder"]
    assert params["refresh"] == ["1"]


def test_search_folder_item_url_opens_directory_without_prompt(monkeypatch):
    module, _xbmc_module, _resolved = load_plugin_with_action(monkeypatch, "")

    url = module.item_url({"id": "mock-search://youtube/lofi", "kind": "search", "is_folder": True})
    params = parse_qs(urlsplit(url).query)

    assert params["action"] == ["open"]
    assert params["id"] == ["mock-search://youtube/lofi"]


def test_search_action_with_key_calls_search_without_prompt(monkeypatch):
    load_plugin_with_action(
        monkeypatch,
        "?action=search&id=lofi",
        search_response={"items": [{"id": "video", "title": "Video", "is_playable": True}]},
    )

    assert FakeClient.search_calls == ["lofi"]
    assert FakeDialog.input_calls == []


def test_search_action_without_key_redirects_prompt_to_stable_results_url(monkeypatch):
    _module, xbmc_module, _resolved = load_plugin_with_action(
        monkeypatch,
        "?action=search",
        input_value="lofi beats",
    )

    assert FakeDialog.input_calls
    assert FakeClient.search_calls == []
    assert xbmc_module.builtin_calls == [
        "AlarmClock(dashbox_search,Container.Update(plugin://plugin.video.dashbox?action=search&id=lofi+beats\\,replace),00:00:01,silent)"
    ]
    assert xbmc_module.events == ["endOfDirectory"]


def test_search_action_without_key_uses_heading_from_url(monkeypatch):
    load_plugin_with_action(
        monkeypatch,
        "?action=search&heading=Bilibili+%E6%90%9C%E7%B4%A2",
        input_value="lofi",
    )

    assert FakeDialog.input_calls[0] == (("Bilibili 搜索",), {"type": 0})


def test_empty_search_item_url_prompts_for_input(monkeypatch):
    module, _xbmc_module, _resolved = load_plugin_with_action(monkeypatch, "")

    url = module.item_url({"id": "", "title": "Bilibili 搜索", "kind": "search"})
    params = parse_qs(urlsplit(url).query)

    assert params["action"] == ["search"]
    assert params["heading"] == ["Bilibili 搜索"]
    assert "id" not in params


def test_list_item_maps_subtitle_to_label2_and_video_info(monkeypatch):
    module, _xbmc_module, _resolved = load_plugin_with_action(monkeypatch, "")

    item = module.list_item({
        "id": "refresh",
        "title": "Refresh list",
        "subtitle": "Current directory",
        "info": {"title": "Refresh list"},
    })

    assert item.label2 == "Current directory"
    assert item.video_info_tag.plot_outline == "Current directory"
    assert item.video_info_tag.plot == "Current directory"
