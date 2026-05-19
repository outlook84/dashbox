from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time


DEFAULT_ACCESS_TOKEN_TTL_SECONDS = 12 * 60 * 60


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def access_code_hash_fingerprint(access_code_hash: str) -> str:
    return _b64url_encode(hashlib.sha256(access_code_hash.encode("utf-8")).digest())


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def issue_access_token(
    *,
    secret: bytes,
    sub_id: str,
    audience: str,
    access_code_hash: str,
    ttl_seconds: int = DEFAULT_ACCESS_TOKEN_TTL_SECONDS,
    now: float | None = None,
) -> tuple[str, int]:
    current = int(time.time() if now is None else now)
    expires_at = current + ttl_seconds
    fingerprint = access_code_hash_fingerprint(access_code_hash)
    payload = {
        "audience": audience,
        "expires_at": expires_at,
        "fingerprint": fingerprint,
        "sub_id": sub_id,
    }
    signature = _b64url_encode(hmac.new(secret, _canonical_json(payload), hashlib.sha256).digest())
    token = _b64url_encode(_canonical_json({"payload": payload, "signature": signature}))
    return token, expires_at


def issue_media_token(
    *,
    secret: bytes,
    session_id: str,
    sub_id: str,
    audience: str,
    access_code_hash: str,
) -> str:
    fingerprint = access_code_hash_fingerprint(access_code_hash)
    payload = {
        "audience": audience,
        "fingerprint": fingerprint,
        "kind": "media",
        "session_id": session_id,
        "sub_id": sub_id,
    }
    signature = _b64url_encode(hmac.new(secret, _canonical_json(payload), hashlib.sha256).digest())
    return _b64url_encode(_canonical_json({"payload": payload, "signature": signature}))


def validate_access_token(
    token: str,
    *,
    secret: bytes,
    sub_id: str,
    audience: str,
    access_code_hash: str,
    now: float | None = None,
) -> bool:
    try:
        envelope = json.loads(_b64url_decode(token).decode("utf-8"))
    except Exception:
        return False
    if not isinstance(envelope, dict):
        return False
    payload = envelope.get("payload")
    signature = envelope.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, str):
        return False
    token_sub_id = payload.get("sub_id")
    token_audience = payload.get("audience")
    expires_at = payload.get("expires_at")
    fingerprint = payload.get("fingerprint")
    if (
        not isinstance(token_sub_id, str)
        or not isinstance(token_audience, str)
        or not isinstance(expires_at, int)
        or isinstance(expires_at, bool)
        or not isinstance(fingerprint, str)
    ):
        return False
    if token_sub_id != sub_id or token_audience != audience:
        return False
    current = int(time.time() if now is None else now)
    if expires_at <= current:
        return False
    expected_fingerprint = access_code_hash_fingerprint(access_code_hash)
    if not hmac.compare_digest(fingerprint, expected_fingerprint):
        return False
    expected_signature = _b64url_encode(hmac.new(secret, _canonical_json(payload), hashlib.sha256).digest())
    return hmac.compare_digest(signature, expected_signature)


def validate_media_token(
    token: str,
    *,
    secret: bytes,
    session_id: str,
    sub_id: str,
    audience: str,
    access_code_hash: str,
) -> bool:
    try:
        envelope = json.loads(_b64url_decode(token).decode("utf-8"))
    except Exception:
        return False
    if not isinstance(envelope, dict):
        return False
    payload = envelope.get("payload")
    signature = envelope.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, str):
        return False
    token_kind = payload.get("kind")
    token_session_id = payload.get("session_id")
    token_sub_id = payload.get("sub_id")
    token_audience = payload.get("audience")
    fingerprint = payload.get("fingerprint")
    if (
        token_kind != "media"
        or not isinstance(token_session_id, str)
        or not isinstance(token_sub_id, str)
        or not isinstance(token_audience, str)
        or not isinstance(fingerprint, str)
    ):
        return False
    if token_session_id != session_id or token_sub_id != sub_id or token_audience != audience:
        return False
    expected_fingerprint = access_code_hash_fingerprint(access_code_hash)
    if not hmac.compare_digest(fingerprint, expected_fingerprint):
        return False
    expected_signature = _b64url_encode(hmac.new(secret, _canonical_json(payload), hashlib.sha256).digest())
    return hmac.compare_digest(signature, expected_signature)
