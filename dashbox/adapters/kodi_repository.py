from __future__ import annotations

import functools
import hashlib
import io
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

ADDON_ID = "plugin.video.dashbox"
REPOSITORY_ADDON_ID = "repository.dashbox"
REPOSITORY_ADDON_VERSION = "0.1.1"
PLUGIN_DIR = Path(__file__).resolve().parents[1] / "kodi" / ADDON_ID


@dataclass(frozen=True)
class KodiRepositoryBuild:
    addon_id: str
    addon_version: str
    package_filename: str
    addons_xml: bytes
    addons_xml_md5: str
    package_zip: bytes


@functools.lru_cache(maxsize=4)
def build(plugin_dir: Path = PLUGIN_DIR) -> KodiRepositoryBuild:
    version = addon_version(plugin_dir)
    xml = addons_xml(plugin_dir)
    return KodiRepositoryBuild(
        addon_id=ADDON_ID,
        addon_version=version,
        package_filename=f"{ADDON_ID}-{version}.zip",
        addons_xml=xml,
        addons_xml_md5=hashlib.md5(xml).hexdigest(),
        package_zip=package_zip(plugin_dir),
    )


def addon_version(plugin_dir: Path = PLUGIN_DIR) -> str:
    return (plugin_dir / "VERSION").read_text(encoding="utf-8").strip()


def package_filename(plugin_dir: Path = PLUGIN_DIR) -> str:
    return f"{ADDON_ID}-{addon_version(plugin_dir)}.zip"


def addons_xml(plugin_dir: Path = PLUGIN_DIR) -> bytes:
    addon_root = ET.parse(plugin_dir / "addon.xml").getroot()
    addon_root.attrib["version"] = addon_version(plugin_dir)
    root = ET.Element("addons")
    root.append(addon_root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def addons_xml_md5(plugin_dir: Path = PLUGIN_DIR) -> str:
    return hashlib.md5(addons_xml(plugin_dir)).hexdigest()


def package_zip(plugin_dir: Path = PLUGIN_DIR, default_gateway: str = "") -> bytes:
    root_name = plugin_dir.name
    version = addon_version(plugin_dir)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(plugin_dir.rglob("*")):
            if path.is_dir() or "__pycache__" in path.parts:
                continue
            archive_name = Path(root_name) / path.relative_to(plugin_dir)
            relative_path = path.relative_to(plugin_dir).as_posix()
            if relative_path == "addon.xml":
                archive.writestr(str(archive_name), addon_xml_with_version(path, version))
            elif default_gateway and relative_path == "resources/settings.xml":
                archive.writestr(str(archive_name), settings_xml_with_default_gateway(path, default_gateway))
            else:
                archive.write(path, archive_name)
    return output.getvalue()


def addon_xml_with_version(addon_xml_path: Path, version: str) -> bytes:
    tree = ET.parse(addon_xml_path)
    tree.getroot().attrib["version"] = version
    output = io.BytesIO()
    tree.write(output, encoding="utf-8", xml_declaration=True)
    return output.getvalue()


def settings_xml_with_default_gateway(settings_path: Path, gateway: str) -> bytes:
    tree = ET.parse(settings_path)
    root = tree.getroot()
    gateway_setting = root.find(".//setting[@id='gateway']")
    if gateway_setting is None:
        raise ValueError("Kodi settings.xml is missing gateway setting")
    default = gateway_setting.find("default")
    if default is None:
        default = ET.SubElement(gateway_setting, "default")
    default.text = gateway.rstrip("/")
    output = io.BytesIO()
    tree.write(output, encoding="utf-8", xml_declaration=True)
    return output.getvalue()


def repository_package_filename(base_url: str = "") -> str:
    suffix = f"-u{repository_base_fingerprint(base_url)}" if base_url else ""
    return f"{REPOSITORY_ADDON_ID}-{REPOSITORY_ADDON_VERSION}{suffix}.zip"


def repository_base_fingerprint(base_url: str) -> str:
    repo_base = base_url.rstrip("/") + "/repo/"
    return hashlib.sha256(repo_base.encode("utf-8")).hexdigest()[:8]


def repository_package_zip(base_url: str) -> bytes:
    repo_base = base_url.rstrip("/") + "/repo"
    addon_xml = repository_addon_xml(repo_base)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr(f"{REPOSITORY_ADDON_ID}/", "")
        archive.writestr(f"{REPOSITORY_ADDON_ID}/addon.xml", addon_xml)
    return output.getvalue()


def repository_addon_xml(repo_base: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<addon id="{REPOSITORY_ADDON_ID}" name="Dashbox Repository" version="{REPOSITORY_ADDON_VERSION}" provider-name="dashbox">
  <requires>
    <import addon="xbmc.addon" version="12.0.0" />
  </requires>
  <extension point="xbmc.addon.repository" name="Dashbox Repository">
    <dir>
      <info compressed="false">{repo_base}/addons.xml</info>
      <checksum>{repo_base}/addons.xml.md5</checksum>
      <datadir zip="true">{repo_base}/</datadir>
      <artdir>{repo_base}/</artdir>
      <hashes>false</hashes>
    </dir>
  </extension>
  <extension point="xbmc.addon.metadata">
    <summary lang="en_GB">Dashbox add-on repository</summary>
    <description lang="en_GB">Repository for the Dashbox Kodi client.</description>
    <platform>all</platform>
    <license>GPL-3.0-only</license>
  </extension>
</addon>
"""
