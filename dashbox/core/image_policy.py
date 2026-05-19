from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit

from ..config import DEFAULT_USER_AGENT, ImageProxyMode
from ..sites import registry


def is_proxyable_thumbnail_url(url: str) -> bool:
    return registry.image_url_is_proxyable(url)


def is_supported_image_proxy_url(url: str, mode: ImageProxyMode) -> bool:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if mode == ImageProxyMode.OFF:
        return False
    if mode == ImageProxyMode.KNOWN:
        return is_proxyable_thumbnail_url(url)
    return parts.scheme in {"http", "https"} and bool(host) and not is_blocked_image_proxy_host(host)


def is_blocked_image_proxy_host(host: str) -> bool:
    value = host.strip().strip("[]").lower()
    if value in {"localhost", "localhost.localdomain"} or value.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return is_blocked_image_proxy_ip(address)


def is_blocked_image_proxy_address(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return True
    return is_blocked_image_proxy_ip(parsed)


def is_blocked_image_proxy_ip(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return is_blocked_image_proxy_ip(address.ipv4_mapped)
    return (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
        or str(address) == "255.255.255.255"
    )


async def image_proxy_host_resolves_to_blocked_address(host: str) -> bool:
    value = host.strip().strip("[]").lower()
    if not value:
        return True
    if is_blocked_image_proxy_host(value):
        return True
    try:
        loop = asyncio.get_running_loop()
        resolved = await loop.getaddrinfo(value, None, type=socket.SOCK_STREAM)
    except socket.gaierror:
        return False
    addresses = {item[4][0] for item in resolved if item[4]}
    return not addresses or any(is_blocked_image_proxy_address(address) for address in addresses)


def thumbnail_url(url: str, base_url: str = "") -> str:
    if not is_proxyable_thumbnail_url(url):
        return url
    return with_image_headers(url)


def proxied_thumbnail_url(url: str, base_url: str, mode: ImageProxyMode = ImageProxyMode.KNOWN) -> str:
    from urllib.parse import urlencode

    if not base_url or not is_supported_image_proxy_url(url, mode):
        return url
    return f"{base_url.rstrip()}/image?{urlencode({'url': url})}"


def referer_for_image_url(url: str) -> str:
    return registry.image_referer_for_url(url)


def with_image_headers(url: str) -> str:
    referer = referer_for_image_url(url)
    if not referer or "@Referer=" in url or "@Headers=" in url:
        return url
    if "@User-Agent=" in url:
        return f"{url}@Referer={referer}"
    return f"{url}@Referer={referer}@User-Agent={DEFAULT_USER_AGENT}"
