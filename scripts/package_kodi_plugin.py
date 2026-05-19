from __future__ import annotations

from pathlib import Path

from dashbox.adapters import kodi_repository


def addon_version(plugin_dir: Path) -> str:
    return kodi_repository.addon_version(plugin_dir)


def main() -> int:
    import sys

    plugin_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "dashbox/kodi/plugin.video.dashbox")
    output = Path(sys.argv[2] if len(sys.argv) > 2 else f"kodi/plugin.video.dashbox-{addon_version(plugin_dir)}.zip")
    default_gateway = sys.argv[3] if len(sys.argv) > 3 else ""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    output.write_bytes(kodi_repository.package_zip(plugin_dir, default_gateway=default_gateway))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
