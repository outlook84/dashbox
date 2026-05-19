from __future__ import annotations

from .scope import PlaybackScope

DIRECT_CANDIDATE_TRANSPORT_ORDER = ("hls", "progressive", "dash")
PROXY_CANDIDATE_TRANSPORT_ORDER = ("dash", "hls", "progressive")


def should_proxy_dash_media_url(scope: PlaybackScope | None) -> bool:
    return bool(scope and scope.proxy_dash_media_url)


def candidate_transport_order_for_scope(scope: PlaybackScope | None = None) -> tuple[str, ...]:
    if should_proxy_dash_media_url(scope):
        return PROXY_CANDIDATE_TRANSPORT_ORDER
    return DIRECT_CANDIDATE_TRANSPORT_ORDER


def candidate_transport_score(candidate_transport: str, candidate_transport_order: tuple[str, ...]) -> int:
    try:
        return len(candidate_transport_order) - candidate_transport_order.index(candidate_transport)
    except ValueError:
        return 0
