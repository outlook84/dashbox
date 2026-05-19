from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from ..utils.errors import exception_reason
from ..media import playback
from ..media.dash import DashSession
from .state import AppState


logger = logging.getLogger("dashbox")


async def proxy_segment(url: str, headers: dict[str, str], request: Request, http_client_provider: Any | None = None) -> Response:
    import httpx

    client = http_client_provider() if http_client_provider is not None else httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    close_client = http_client_provider is None
    upstream_headers = dict(headers)
    if range_header := request.headers.get("range"):
        upstream_headers["Range"] = range_header
    method = "HEAD" if request.method == "HEAD" else "GET"
    upstream_request = client.build_request(method, url, headers=upstream_headers)
    upstream = await client.send(upstream_request, stream=True)

    async def body():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            if close_client:
                await client.aclose()

    response_headers = {}
    for key in ("content-length", "content-range", "accept-ranges"):
        value = upstream.headers.get(key)
        if value:
            response_headers[key] = value
    if method == "HEAD":
        await upstream.aclose()
        if close_client:
            await client.aclose()
        return Response(
            content=b"",
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "application/octet-stream"),
            headers=response_headers,
        )
    if upstream.status_code in (403, 404, 410):
        content = await upstream.aread()
        await upstream.aclose()
        if close_client:
            await client.aclose()
        return Response(
            content=content,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "application/octet-stream"),
            headers=response_headers,
        )
    return StreamingResponse(
        body(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", "application/octet-stream"),
        headers=response_headers,
    )


async def proxy_dash_session_segment(
    session: DashSession,
    track_index: int,
    segment_index: int,
    request: Request,
    state: AppState | None = None,
) -> Response:
    if track_index < 0 or track_index >= len(session.tracks):
        raise HTTPException(status_code=404, detail="track not found")
    track = session.tracks[track_index]
    if segment_index < 0 or segment_index >= len(track.segments):
        raise HTTPException(status_code=404, detail="segment not found")
    http_client_provider = state.stream_http_client.client if state is not None else None
    return await proxy_segment(track.segments[segment_index].url, track.headers or {}, request, http_client_provider)


async def refresh_dash_session(session: DashSession, state: AppState) -> DashSession | None:
    if not session.raw_id:
        return None
    service = state.service_for_scope(session.scope)
    try:
        info = await service.playable_info_async(session.raw_id, force_refresh=True)
    except Exception as exc:
        logger.warning("dash session refresh extract failed token=%s url=%s reason=%s", session.token, session.raw_id, exception_reason(exc))
        logger.debug("dash session refresh extract failed", exc_info=True)
        return None
    candidate_sets = playback.dash_candidate_sets_from_info(info, session.scope)
    for candidates in candidate_sets:
        try:
            refreshed = state.dash_store.refresh(session.token, info, [fmt for fmt in candidates if isinstance(fmt, dict)])
        except ValueError as exc:
            logger.warning("dash session refresh failed token=%s url=%s reason=%s", session.token, session.raw_id, exception_reason(exc))
            logger.debug("dash session refresh failed", exc_info=True)
            continue
        if refreshed:
            return refreshed
    if candidate_sets:
        logger.warning("dash session refresh skipped due to structure mismatch token=%s url=%s", session.token, session.raw_id)
        raise HTTPException(status_code=502, detail="dash session refresh changed media structure")
    return None
