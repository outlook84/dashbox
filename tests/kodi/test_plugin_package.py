import hashlib
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from io import BytesIO
from pathlib import Path

from dashbox.adapters import kodi_repository


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "dashbox" / "kodi" / "plugin.video.dashbox"


def addon_version() -> str:
    return (PLUGIN / "VERSION").read_text(encoding="utf-8").strip()


def test_kodi_settings_xml_is_well_formed() -> None:
    tree = ET.parse(PLUGIN / "resources" / "settings.xml")
    root = tree.getroot()

    assert root.tag == "settings"
    assert root.find(".//setting[@id='gateway']") is not None
    assert root.find(".//setting[@id='sub_id']") is not None


def test_kodi_access_credentials_settings_are_internal_and_hidden() -> None:
    root = ET.parse(PLUGIN / "resources" / "settings.xml").getroot()
    for setting_id in ("access_code", "access_token"):
        setting = root.find(f".//setting[@id='{setting_id}']")

        assert setting is not None
        assert setting.findtext("level") == "4"
        assert setting.findtext("control/hidden") == "true"


def test_kodi_max_playback_caps_use_tvbox_supported_options() -> None:
    root = ET.parse(PLUGIN / "resources" / "settings.xml").getroot()

    expected = {
        "max_video_height": ["0", "480", "720", "1080", "1440", "2160", "4320"],
        "max_video_fps": ["0", "24", "30", "60", "120"],
        "danmaku_font_size": ["24", "28", "32", "36", "42"],
    }
    for setting_id, values in expected.items():
        setting = root.find(f".//setting[@id='{setting_id}']")
        assert setting is not None
        assert setting.attrib["type"] == "integer"
        assert setting.find("control").attrib == {"type": "spinner", "format": "integer"}
        options = setting.findall("constraints/options/option")
        assert [option.text for option in options] == values
        assert all(option.attrib["label"].startswith("301") for option in options)


def test_kodi_language_files_are_present() -> None:
    assert (PLUGIN / "resources" / "language" / "resource.language.en_gb" / "strings.po").exists()
    assert (PLUGIN / "resources" / "language" / "resource.language.zh_cn" / "strings.po").exists()


def test_kodi_addon_requires_inputstream_adaptive() -> None:
    root = ET.parse(PLUGIN / "addon.xml").getroot()

    assert root.find(".//import[@addon='inputstream.adaptive']") is not None


def test_kodi_repository_uses_visible_version_file() -> None:
    addons = ET.fromstring(kodi_repository.addons_xml(PLUGIN))

    assert kodi_repository.addon_version(PLUGIN) == addon_version()
    assert addons.find("addon").attrib["version"] == addon_version()


def test_kodi_repository_addons_xml_changes_with_base_url() -> None:
    first = kodi_repository.addons_xml(PLUGIN, base_url="http://dashbox.local:18990")
    second = kodi_repository.addons_xml(PLUGIN, base_url="https://dashbox.example.test")

    assert first != second
    fingerprint = kodi_repository.repository_base_fingerprint("http://dashbox.local:18990").encode("utf-8")
    assert fingerprint in first
    assert kodi_repository.addons_xml_md5(
        PLUGIN,
        base_url="http://dashbox.local:18990",
    ) == hashlib.md5(first).hexdigest()


def test_kodi_packaging_ignores_addon_xml_template_version(tmp_path: Path) -> None:
    plugin_dir = tmp_path / "plugin.video.dashbox"
    plugin_dir.mkdir()
    (plugin_dir / "VERSION").write_text("9.8.7\n", encoding="utf-8")
    (plugin_dir / "addon.xml").write_text(
        '<addon id="plugin.video.dashbox" name="Dashbox" version="1.2.3" />',
        encoding="utf-8",
    )

    addons = ET.fromstring(kodi_repository.addons_xml(plugin_dir))
    package = kodi_repository.package_zip(plugin_dir)

    with zipfile.ZipFile(BytesIO(package)) as archive:
        addon_xml = archive.read("plugin.video.dashbox/addon.xml")

    assert kodi_repository.addon_version(plugin_dir) == "9.8.7"
    assert addons.find("addon").attrib["version"] == "9.8.7"
    assert ET.fromstring(addon_xml).attrib["version"] == "9.8.7"


def test_kodi_package_script_creates_zip_parent_directory(tmp_path: Path) -> None:
    zip_path = tmp_path / "missing" / f"plugin.video.dashbox-{addon_version()}.zip"

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "package_kodi_plugin.py"),
            str(PLUGIN),
            str(zip_path),
        ],
        cwd=ROOT,
        check=True,
    )

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        addon_xml = archive.read("plugin.video.dashbox/addon.xml")

    assert {name.split("/", 1)[0] for name in names if name} == {"plugin.video.dashbox"}
    assert "plugin.video.dashbox/addon.xml" in names
    assert ET.fromstring(addon_xml).attrib["version"] == addon_version()


def test_kodi_package_script_can_set_default_gateway(tmp_path: Path) -> None:
    zip_path = tmp_path / f"plugin.video.dashbox-{addon_version()}.zip"

    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "package_kodi_plugin.py"),
            str(PLUGIN),
            str(zip_path),
            "http://dashbox.local:18990/",
        ],
        cwd=ROOT,
        check=True,
    )

    with zipfile.ZipFile(zip_path) as archive:
        settings_xml = archive.read("plugin.video.dashbox/resources/settings.xml")

    settings = ET.fromstring(settings_xml)
    assert settings.find(".//setting[@id='gateway']/default").text == "http://dashbox.local:18990"


def test_kodi_repository_build_is_cached(tmp_path: Path, monkeypatch) -> None:
    plugin_dir = tmp_path / "plugin.video.dashbox"
    plugin_dir.mkdir()
    (plugin_dir / "VERSION").write_text("1.2.4\n", encoding="utf-8")
    (plugin_dir / "addon.xml").write_text(
        '<addon id="plugin.video.dashbox" name="Dashbox" version="1.2.3" />',
        encoding="utf-8",
    )
    calls = []

    def fake_package_zip(path: Path) -> bytes:
        calls.append(path)
        return b"zip"

    kodi_repository.build.cache_clear()
    monkeypatch.setattr(kodi_repository, "package_zip", fake_package_zip)

    first = kodi_repository.build(plugin_dir)
    second = kodi_repository.build(plugin_dir)

    assert first is second
    assert first.package_filename == "plugin.video.dashbox-1.2.4.zip"
    assert calls == [plugin_dir]
