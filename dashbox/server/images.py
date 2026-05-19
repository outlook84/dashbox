from __future__ import annotations

from typing import Any


def scope_image_urls(page: Any, *, protocol: str = "", sub_id: str = "") -> None:
    if not protocol and not sub_id:
        return
    if not isinstance(page, dict):
        return
    for item in page.get("list") or []:
        if not isinstance(item, dict):
            continue
        vod_pic = str(item.get("vod_pic") or "")
        scoped = scoped_image_url(vod_pic, protocol=protocol, sub_id=sub_id)
        if scoped:
            item["vod_pic"] = scoped


def scoped_image_url(value: str, *, protocol: str = "", sub_id: str = "") -> str:
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    parts = urlsplit(value)
    if parts.path != "/image":
        return ""
    query = parse_qsl(parts.query, keep_blank_values=True)
    if not any(key == "url" for key, _value in query):
        return ""
    scoped = [(key, value) for key, value in query if key not in {"protocol", "sub_id"}]
    if protocol:
        scoped.append(("protocol", protocol))
    if sub_id:
        scoped.append(("sub_id", sub_id))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(scoped), parts.fragment))


def scope_kodi_image_urls(page: Any, *, sub_id: str = "") -> None:
    if not isinstance(page, dict):
        return
    for item in page.get("items") or []:
        if not isinstance(item, dict):
            continue
        art = item.get("art")
        if not isinstance(art, dict):
            continue
        for key, value in list(art.items()):
            scoped = scoped_image_url(str(value or ""), protocol="kodi", sub_id=sub_id)
            if scoped:
                art[key] = scoped
