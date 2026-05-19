from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from ..auth.tokens import issue_media_token, validate_access_token, validate_media_token
from ..config import Subscription
from ..media.dash import DashSession
from ..media.inline_manifest import InlineManifestSession
from ..media.scope import PlaybackScope
from .state import AppState
from .utils import json_response


def authorize_protocol_request(sub: Subscription, request: Request, state: AppState, *, audience: str) -> JSONResponse | None:
    token = request.headers.get("x-access-token", "").strip()
    if token and validate_access_token(
        token,
        secret=state.token_secret,
        sub_id=sub.id,
        audience=audience,
        access_code_hash=sub.access_code_hash,
    ):
        return None
    return json_response({"error": "unauthorized"}, status_code=401)


def authorize_media_dash_request(session: DashSession, request: Request, state: AppState) -> None:
    authorize_media_scope(session.token, session.scope, request, state)


def authorize_media_inline_request(session: InlineManifestSession, request: Request, state: AppState) -> None:
    authorize_media_scope(session.token, session.scope, request, state)


def authorize_media_scope(session_id: str, scope: PlaybackScope | None, request: Request, state: AppState) -> None:
    if scope is None:
        raise HTTPException(status_code=401, detail="unauthorized")
    sub = state.subscriptions.sub_by_id(scope.sub_id)
    token = request.headers.get("x-media-token", "").strip()
    if token and validate_media_token(
        token,
        secret=state.token_secret,
        session_id=session_id,
        sub_id=scope.sub_id,
        audience=scope.protocol,
        access_code_hash=sub.access_code_hash,
    ):
        return
    raise HTTPException(status_code=401, detail="unauthorized")


def attach_media_token(value: dict[str, Any], state: AppState) -> None:
    session_id = session_id_from_manifest_url(str(value.get("url") or ""))
    if not session_id:
        return
    session = state.dash_store.get(session_id, touch=False)
    scope = session.scope if session else None
    if scope is None:
        inline_session = state.inline_manifest_store.get(session_id, touch=False)
        scope = inline_session.scope if inline_session else None
    if scope is None:
        return
    sub = state.subscriptions.sub_by_id(scope.sub_id)
    token = issue_media_token(
        secret=state.token_secret,
        session_id=session_id,
        sub_id=scope.sub_id,
        audience=scope.protocol,
        access_code_hash=sub.access_code_hash,
    )
    header_key = "headers" if "headers" in value else "header"
    headers = value.get(header_key)
    if not isinstance(headers, dict):
        headers = {}
    headers = {key: header_value for key, header_value in headers.items() if key.lower() != "x-media-token"}
    value[header_key] = {**headers, "X-Media-Token": token}


def media_token_from_headers(headers: Any) -> str:
    if not isinstance(headers, dict):
        return ""
    for key, value in headers.items():
        if str(key).lower() == "x-media-token":
            return str(value)
    return ""


def session_id_from_manifest_url(url: str) -> str:
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        return ""
    segments = [segment for segment in parts.path.split("/") if segment]
    if len(segments) < 3 or segments[-1] != "manifest.mpd":
        return ""
    if segments[-3] != "media":
        return ""
    return segments[-2]


def failure_limiter_key(sub_id: str, request: Request) -> str:
    host = request.client.host if request.client else ""
    return f"{sub_id}|{host}"
