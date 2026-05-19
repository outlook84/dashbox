from __future__ import annotations

import os
from typing import Any

from .model import IMAGE_PROXY_MODE_ENV, MAX_UPSTREAM_TIMEOUT, PUBLIC_BASE_URL_ENV, UPSTREAM_TIMEOUT_ENV, ImageProxyMode
from .parse import parse_image_proxy_mode, parse_positive_int

def image_proxy_mode_from_env() -> ImageProxyMode:
    value = os.environ.get(IMAGE_PROXY_MODE_ENV)
    if value is None or not value.strip():
        return ImageProxyMode.KNOWN
    return parse_image_proxy_mode(value, IMAGE_PROXY_MODE_ENV)


def upstream_timeout_from_env() -> int:
    value = os.environ.get(UPSTREAM_TIMEOUT_ENV)
    if value is None or not value.strip():
        return 30
    return parse_positive_int(parse_env_int(value, UPSTREAM_TIMEOUT_ENV), UPSTREAM_TIMEOUT_ENV, maximum=MAX_UPSTREAM_TIMEOUT)


def public_base_url_from_env() -> str:
    value = os.environ.get(PUBLIC_BASE_URL_ENV)
    if value is None:
        return ""
    return value.strip().rstrip("/")


def runtime_config_values_from_env() -> dict[str, Any]:
    return {
        "image_proxy_mode": image_proxy_mode_from_env(),
        "upstream_timeout": upstream_timeout_from_env(),
        "public_base_url": public_base_url_from_env(),
    }


def parse_env_int(value: str, path: str) -> int:
    try:
        return int(value.strip())
    except ValueError:
        raise ValueError(f"unsupported {path}: {value}. Expected integer") from None
