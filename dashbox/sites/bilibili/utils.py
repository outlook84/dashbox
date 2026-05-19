from __future__ import annotations

import asyncio
import html
import json
from collections.abc import Awaitable
from typing import Any

from ..hosts import url_parts_for_host
from ..html_extract import parse_html

def clean_html_text(value: str) -> str:
    return clean_title(" ".join(parse_html(html.unescape(value)).text().split()))


def normalize_image_url(value: str) -> str:
    if value.startswith("//"):
        return f"https:{value}"
    return value


def space_archive_collection_info(fallback_id: str, meta: dict[str, Any], entries: Any) -> dict[str, Any]:
    return {
        "title": str(meta.get("name") or fallback_id),
        "thumbnail": str(meta.get("cover") or ""),
        "description": str(meta.get("description") or ""),
        "total": positive_int(meta.get("total")),
        "entries": dict_list(entries),
    }


def collection_count_fields(info: dict[str, Any], loaded_count: int, fallback_key: str = "", fallback: str = "") -> dict[str, Any]:
    total = positive_int(info.get("total"))
    count = total or loaded_count
    if count:
        return {"remarks_key": "item_count", "item_count": count}
    if fallback_key:
        return {"remarks_key": fallback_key}
    return {"remarks": fallback}


def positive_int(value: Any) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return count if count > 0 else 0


def dict_list(value: Any) -> list[dict[str, Any]]:
    return [item for item in value or [] if isinstance(item, dict)]


def payload_value(payload: dict[str, Any], key: str = "data") -> Any:
    return payload.get(key) if payload.get("code") == 0 else {}


def payload_dict(payload: dict[str, Any], key: str = "data") -> dict[str, Any]:
    value = payload_value(payload, key)
    return value if isinstance(value, dict) else {}


async def gather_limited(limit: int, *aws: Awaitable[Any]) -> list[Any]:
    sem = asyncio.Semaphore(limit)

    async def run(aw: Awaitable[Any]) -> Any:
        async with sem:
            return await aw

    return await asyncio.gather(*(run(aw) for aw in aws))


def parse_initial_state(html_text: str) -> dict[str, Any]:
    raw = initial_state_json_text(html_text)
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def initial_state_json_text(html_text: str) -> str:
    marker = "window.__INITIAL_STATE__"
    marker_at = html_text.find(marker)
    if marker_at < 0:
        return ""
    assign_at = html_text.find("=", marker_at + len(marker))
    if assign_at < 0:
        return ""
    object_start = html_text.find("{", assign_at + 1)
    if object_start < 0:
        return ""
    return balanced_json_object_text(html_text, object_start)


def balanced_json_object_text(value: str, start: int) -> str:
    depth = 0
    quote = ""
    escaped = False
    for index in range(start, len(value)):
        char = value[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return value[start:index + 1]
    return ""


def find_cid(value: Any, depth: int = 0) -> str:
    if depth > 6:
        return ""
    if isinstance(value, dict):
        for key in ("cid", "cid_id", "danmaku_id", "comment_id"):
            cid = cid_text(value.get(key))
            if cid:
                return cid
        for key, item in value.items():
            if key in ("formats", "requested_formats", "thumbnails", "subtitles", "automatic_captions"):
                continue
            cid = find_cid(item, depth + 1)
            if cid:
                return cid
    elif isinstance(value, list):
        for item in value:
            cid = find_cid(item, depth + 1)
            if cid:
                return cid
    return ""


def cid_text(value: Any) -> str:
    if isinstance(value, int) and value > 0:
        return str(value)
    if isinstance(value, str) and value.isdecimal() and int(value) > 0:
        return value
    return ""


def positive_int_text(value: Any) -> str:
    text = cid_text(value)
    return str(int(text)) if text else ""


def find_cid_from_formats(info: dict[str, Any]) -> str:
    candidates: list[Any] = []
    formats = info.get("formats")
    if isinstance(formats, list):
        candidates.extend(formats)
    for fmt in candidates:
        if not isinstance(fmt, dict):
            continue
        url = fmt.get("url")
        if not isinstance(url, str):
            continue
        cid = cid_from_bilivideo_url(url)
        if cid:
            return cid
    return ""


def cid_from_bilivideo_url(url: str) -> str:
    parts = url_parts_for_host(url, "bilivideo.com")
    if parts is None:
        return ""
    segments = [segment for segment in parts.path.split("/") if segment]
    try:
        index = segments.index("upgcxcode")
    except ValueError:
        return ""
    if len(segments) <= index + 3:
        return ""
    cid = segments[index + 3]
    return cid if cid.isdigit() else ""




def clean_title(value: str) -> str:
    return value.strip()


def clean_content(value: str) -> str:
    return " ".join(value.replace("\u00a0", " ").replace("\u3000", " ").split())
