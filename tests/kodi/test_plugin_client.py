import importlib.util
import sys
import types
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLIENT_PATH = ROOT / "dashbox" / "kodi" / "plugin.video.dashbox" / "resources" / "lib" / "client.py"
ADDON_XML = ROOT / "dashbox" / "kodi" / "plugin.video.dashbox" / "addon.xml"


spec = importlib.util.spec_from_file_location("dashbox_kodi_plugin_client", CLIENT_PATH)
assert spec is not None and spec.loader is not None
client_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client_module)


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return b'{"ok": true}'


def test_client_sends_addon_and_api_versions(monkeypatch) -> None:
    captured = {}
    addon_version = ET.parse(ADDON_XML).getroot().attrib["version"]

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(client_module, "urlopen", fake_urlopen)
    monkeypatch.setitem(sys.modules, "xbmcaddon", fake_xbmcaddon_module(addon_version))
    monkeypatch.setitem(sys.modules, "xbmc", fake_xbmc_module("en-US"))

    api = client_module.DashboxClient("http://dashbox.test", "main", "token")
    api.home()

    request = captured["request"]
    assert request.headers["X-dashbox-kodi-addon-version"] == addon_version
    assert request.headers["X-dashbox-kodi-api-version"] == "2"
    assert request.headers["X-dashbox-locale"] == "en-US"
    assert captured["timeout"] == 60


def test_kodi_locale_maps_chinese_region(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "xbmc", fake_xbmc_module("zh_CN"))

    assert client_module.kodi_locale() == "zh-CN"


def test_addon_version_falls_back_empty_outside_kodi(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "xbmcaddon", raising=False)

    assert client_module.addon_version() == ""


def fake_xbmcaddon_module(version: str):
    module = types.ModuleType("xbmcaddon")

    class FakeAddon:
        def getAddonInfo(self, key):
            return version if key == "version" else ""

    module.Addon = FakeAddon
    return module


def fake_xbmc_module(language: str):
    module = types.ModuleType("xbmc")
    module.ISO_639_1 = 0

    def get_language(_format, region=False):
        return language

    module.getLanguage = get_language
    return module
