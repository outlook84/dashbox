from __future__ import annotations

import hashlib
import random
import time
from typing import Any
from urllib.parse import quote, urlencode

WBI_MIXIN_KEY_ENC_TAB = (
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
)
WBI_MIXIN_KEY_TTL_SECONDS = 6 * 60 * 60

def parse_cookie_header(value: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for item in value.split(";"):
        if "=" not in item:
            continue
        key, cookie_value = item.split("=", 1)
        key = key.strip()
        if key:
            cookies[key] = cookie_value.strip()
    return cookies


def cookie_header_from_dict(cookies: dict[str, str]) -> str:
    return "; ".join(f"{key}={value}" for key, value in cookies.items() if key and value)


def wbi_image_key(url: str) -> str:
    path = url.split("?", 1)[0].rstrip("/")
    filename = path.rsplit("/", 1)[-1]
    return filename.rsplit(".", 1)[0]


def wbi_mixin_key_from_nav(payload: dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    wbi_img = data.get("wbi_img") if isinstance(data.get("wbi_img"), dict) else {}
    raw = wbi_image_key(str(wbi_img.get("img_url") or "")) + wbi_image_key(str(wbi_img.get("sub_url") or ""))
    return "".join(raw[index] for index in WBI_MIXIN_KEY_ENC_TAB if index < len(raw))[:32]


def encode_wbi_params(params: dict[str, Any], mixin_key: str) -> dict[str, Any]:
    signed = dict(params)
    signed["wts"] = int(time.time())
    signed.setdefault("web_location", 1550101)
    filtered = {
        key: "".join(char for char in str(value) if char not in "!'()*")
        for key, value in signed.items()
    }
    query = urlencode(sorted(filtered.items()), quote_via=quote)
    filtered["w_rid"] = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
    return filtered


def add_wbi2_params(params: dict[str, Any]) -> dict[str, Any]:
    dm_rand = "ABCDEFGHIJK"
    params.update(
        {
            "dm_img_list": "[]",
            "dm_img_str": "".join(random.sample(dm_rand, 2)),
            "dm_cover_img_str": "".join(random.sample(dm_rand, 2)),
            "dm_img_inter": '{"ds":[],"wh":[0,0,0],"of":[0,0,0]}',
        }
    )
    return params


def wbi_signature_is_invalid(payload: dict[str, Any]) -> bool:
    code = payload.get("code")
    message = str(payload.get("message") or "").lower()
    return code in {-352, -403} and any(token in message for token in ("wbi", "w_rid", "signature", "签名"))
