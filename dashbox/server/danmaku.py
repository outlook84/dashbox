from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException
from fastapi.responses import Response

from ..config import Config
from ..media import danmaku
from ..sites import bilibili


logger = logging.getLogger("dashbox")


async def proxy_bilibili_danmaku(cid: str, config: Config, http_client_provider: Any | None = None) -> Response:
    response = await fetch_bilibili_danmaku(cid, config, http_client_provider)
    return Response(
        content=response.content,
        media_type=response.headers.get("content-type", "application/xml; charset=utf-8"),
        headers={"Cache-Control": "public, max-age=3600"},
    )


async def proxy_bilibili_danmaku_ass(
    cid: str,
    config: Config,
    http_client_provider: Any | None = None,
    *,
    width: int = 1920,
    height: int = 1080,
    font_face: str = "sans-serif",
    font_size: int = danmaku.DEFAULT_FONT_SIZE,
) -> Response:
    response = await fetch_bilibili_danmaku(cid, config, http_client_provider)
    try:
        content = danmaku.convert_bilibili_xml_to_ass(
            response.content,
            width=width,
            height=height,
            font_face=font_face,
            font_size=font_size,
        )
    except ImportError as exc:
        raise HTTPException(status_code=501, detail="biliass is not installed") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="danmaku conversion failed") from exc
    return Response(
        content=content,
        media_type="text/x-ssa; charset=utf-8",
        headers={"Cache-Control": "public, max-age=3600"},
    )


async def fetch_bilibili_danmaku(cid: str, config: Config, http_client_provider: Any | None = None) -> Any:
    import httpx

    url = bilibili.danmaku_xml_upstream_url(cid)
    logger.debug("proxy bilibili danmaku cid=%s", cid)
    headers = {
        "User-Agent": config.effective_user_agent,
        "Referer": "https://www.bilibili.com/",
    }
    try:
        if http_client_provider is not None:
            response = await http_client_provider().get(url, headers=headers, timeout=15.0)
        else:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="danmaku upstream failed") from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=response.status_code, detail="danmaku upstream rejected")
    return response
