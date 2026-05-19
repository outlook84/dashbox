from __future__ import annotations

import re
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets"
ADMIN_ASSET_DIR = ASSET_DIR / "admin"
ADMIN_INDEX_PATH = ADMIN_ASSET_DIR / "index.html"
SPIDER_PATH = ASSET_DIR / "dashbox.js"
SPIDER_ASSET_RE = re.compile(r"^dashbox\.[0-9a-f]{12}\.js$")
SPIDER_ASSET_PATH = next(
    (path for path in sorted(ASSET_DIR.glob("dashbox.*.js")) if SPIDER_ASSET_RE.match(path.name)),
    SPIDER_PATH,
)
SPIDER_ROUTE_PATH = f"/spider/{SPIDER_ASSET_PATH.name}"
ICON_FILES = {
    "folder.png": ASSET_DIR / "icon-folder.png",
    "playlist.png": ASSET_DIR / "icon-playlist.png",
    "refresh.png": ASSET_DIR / "icon-refresh.png",
    "search.png": ASSET_DIR / "icon-search.png",
    "video.png": ASSET_DIR / "icon-video.png",
}


def spider_path() -> str:
    return SPIDER_ROUTE_PATH


def admin_index_response() -> FileResponse:
    if not ADMIN_INDEX_PATH.exists():
        raise HTTPException(status_code=404, detail="admin UI has not been built")
    return FileResponse(ADMIN_INDEX_PATH, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"})


def safe_admin_asset_path(filename: str) -> Path | None:
    asset_root = ADMIN_ASSET_DIR / "assets"
    path = asset_root / filename
    try:
        path.relative_to(asset_root)
    except ValueError:
        return None
    if any(part in {"", ".", ".."} for part in Path(filename).parts):
        return None
    return path
