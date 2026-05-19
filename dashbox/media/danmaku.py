from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


DEFAULT_FONT_SIZE = 32


def convert_bilibili_xml_to_ass(
    xml: bytes | str,
    *,
    width: int = 1920,
    height: int = 1080,
    font_face: str = "sans-serif",
    font_size: int = DEFAULT_FONT_SIZE,
) -> str:
    from biliass import convert_to_ass

    try:
        value = convert_to_ass(
            xml,
            width,
            height,
            input_format="xml",
            display_region_ratio=1.0,
            font_face=font_face,
            font_size=font_size,
            text_opacity=0.8,
            duration_marquee=15.0,
            duration_still=10.0,
            block_options=None,
            reduce_comments=False,
        )
    except TypeError:
        value = convert_to_ass(xml, width, height)
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def kodi_danmaku_subtitle(danmaku_url: str, *, font_size: int = 0) -> dict[str, Any] | None:
    ass_url = bilibili_xml_danmaku_ass_url(danmaku_url)
    if not ass_url:
        return None
    if font_size > 0:
        ass_url = url_with_font_size(ass_url, font_size)
    return {
        "url": ass_url,
        "name": "Danmaku",
        "language": "zh",
        "format": "ass",
    }


def bilibili_xml_danmaku_ass_url(value: str) -> str:
    if not value:
        return ""
    try:
        parts = urlsplit(value)
    except ValueError:
        return ""
    if "/danmaku/bilibili/" not in parts.path or not parts.path.endswith(".xml"):
        return ""
    path = parts.path.removesuffix(".xml") + ".ass"
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def url_with_font_size(value: str, font_size: int) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    query = [(key, item) for key, item in parse_qsl(parts.query, keep_blank_values=True) if key != "font_size"]
    query.append(("font_size", str(font_size)))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
