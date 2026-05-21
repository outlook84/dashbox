from __future__ import annotations

import asyncio
import copy
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from . import __project_url__
from .auth.access_code import (
    ADMIN_ACCESS_CODE_MAX_LENGTH,
    ADMIN_ACCESS_CODE_MIN_LENGTH,
    ADMIN_ACCESS_CODE_RE,
    validate_access_code_hash_shape,
    validate_access_code_shape,
)
from .auth.failure_limiter import FailureLimiter
from .config import (
    Config,
    admin_schema_data,
    config_to_json_data,
    parse_config_data,
    write_config_file,
)
from .config.runtime import bind_runtime_config
from .config.ids import normalize_config_ids
from .utils.errors import exception_reason

ADMIN_SESSION_COOKIE = "dashbox_admin_session"
ADMIN_SESSION_TTL_SECONDS = 12 * 60 * 60
ADMIN_SESSION_LIMIT = 128
ADMIN_SETUP_CODE_FILENAME = "admin_setup_code"
ADMIN_ACCESS_CODE_HASH_FILENAME = "admin_access_code_hash"
SUBSCRIPTION_ACCESS_CODE_HASH_PLACEHOLDER = "$2b$12$012345678901234567890u0123456789012345678901234567890"


@dataclass
class AdminSession:
    session_id: str
    created_at: float
    expires_at: float


class AdminSessionStore:
    def __init__(self, *, ttl_seconds: int = ADMIN_SESSION_TTL_SECONDS, limit: int = ADMIN_SESSION_LIMIT) -> None:
        self.ttl_seconds = ttl_seconds
        self.limit = limit
        self._sessions: dict[str, AdminSession] = {}

    def create(self) -> AdminSession:
        self.cleanup()
        while len(self._sessions) >= self.limit:
            oldest_id = min(self._sessions.values(), key=lambda item: item.created_at).session_id
            self._sessions.pop(oldest_id, None)
        now = time.time()
        session = AdminSession(
            session_id=secrets.token_urlsafe(32),
            created_at=now,
            expires_at=now + self.ttl_seconds,
        )
        self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str) -> AdminSession | None:
        session = self._sessions.get(session_id)
        if session is None:
            return None
        if session.expires_at <= time.time():
            self._sessions.pop(session_id, None)
            return None
        return session

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def delete_except(self, session_id: str) -> None:
        self._sessions = {
            current_id: session
            for current_id, session in self._sessions.items()
            if current_id == session_id
        }

    def cleanup(self) -> None:
        now = time.time()
        expired = [session_id for session_id, session in self._sessions.items() if session.expires_at <= now]
        for session_id in expired:
            self._sessions.pop(session_id, None)


def validate_runtime_dependent_config(config: Config, *, data_dir: Path | None) -> None:
    bind_runtime_config(config, data_dir)


class AdminAuthState:
    def __init__(self, secret_dir: Path | None) -> None:
        self.secret_dir = secret_dir
        if self.secret_dir is not None:
            self.access_code_hash_path = self.secret_dir / ADMIN_ACCESS_CODE_HASH_FILENAME
            self.setup_code_path = self.secret_dir / ADMIN_SETUP_CODE_FILENAME
        else:
            self.access_code_hash_path = None
            self.setup_code_path = None
        self.sessions = AdminSessionStore()
        self.failures = FailureLimiter()
        self.access_code_hash = self._load_access_code_hash()
        self.setup_code = "" if self.access_code_hash else self._load_or_create_setup_code()

    @property
    def setup_required(self) -> bool:
        return not self.access_code_hash

    def _load_access_code_hash(self) -> str:
        if self.access_code_hash_path is not None and self.access_code_hash_path.exists():
            value = self.access_code_hash_path.read_text(encoding="utf-8").strip()
            validate_access_code_hash_shape(value)
            return value
        return ""

    def _load_or_create_setup_code(self) -> str:
        if self.setup_code_path is None:
            return ""
        if self.setup_code_path.exists():
            value = self.setup_code_path.read_text(encoding="utf-8").strip()
            if value:
                return value
        assert self.secret_dir is not None
        self.secret_dir.mkdir(parents=True, exist_ok=True)
        value = "".join(secrets.choice("0123456789") for _ in range(12))
        self.setup_code_path.write_text(value + "\n", encoding="utf-8")
        return value

    def complete_setup(self, setup_code: str, access_code: str) -> None:
        if not self.setup_required:
            raise HTTPException(status_code=409, detail="admin setup is already complete")
        if not secrets.compare_digest(setup_code, self.setup_code):
            raise HTTPException(status_code=401, detail="invalid setup code")
        validate_admin_access_code(access_code)
        if self.secret_dir is None or self.access_code_hash_path is None:
            raise HTTPException(status_code=409, detail="admin setup requires --data-dir, DASHBOX_DATA_DIR, --config, or DASHBOX_CONFIG")
        access_code_hash = hash_admin_access_code(access_code)
        self.complete_setup_with_hash(setup_code, access_code_hash)

    def complete_setup_with_hash(self, setup_code: str, access_code_hash: str) -> None:
        if not self.setup_required:
            raise HTTPException(status_code=409, detail="admin setup is already complete")
        if not secrets.compare_digest(setup_code, self.setup_code):
            raise HTTPException(status_code=401, detail="invalid setup code")
        if self.secret_dir is None or self.access_code_hash_path is None:
            raise HTTPException(status_code=409, detail="admin setup requires --data-dir, DASHBOX_DATA_DIR, --config, or DASHBOX_CONFIG")
        self.secret_dir.mkdir(parents=True, exist_ok=True)
        self.access_code_hash = access_code_hash
        self.access_code_hash_path.write_text(self.access_code_hash + "\n", encoding="utf-8")
        self.setup_code = ""
        if self.setup_code_path is not None and self.setup_code_path.exists():
            self.setup_code_path.unlink()

    def update_access_code(self, access_code: str) -> None:
        validate_admin_access_code(access_code)
        if self.secret_dir is None or self.access_code_hash_path is None:
            raise ValueError("admin access code update requires --data-dir, DASHBOX_DATA_DIR, --config, or DASHBOX_CONFIG")
        access_code_hash = hash_admin_access_code(access_code)
        self.update_access_code_with_hash(access_code_hash)

    def update_access_code_with_hash(self, access_code_hash: str) -> None:
        if self.secret_dir is None or self.access_code_hash_path is None:
            raise ValueError("admin access code update requires --data-dir, DASHBOX_DATA_DIR, --config, or DASHBOX_CONFIG")
        self.secret_dir.mkdir(parents=True, exist_ok=True)
        self.access_code_hash = access_code_hash
        self.access_code_hash_path.write_text(self.access_code_hash + "\n", encoding="utf-8")


def register_admin_routes(app: FastAPI, get_state: Callable[[], Any]) -> None:
    config_save_lock = asyncio.Lock()

    def require_admin_session(
        request: Request,
        current: Any = Depends(get_state),
    ) -> AdminSession:
        session_id = request.cookies.get(ADMIN_SESSION_COOKIE, "")
        session = current.admin.sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=401, detail="unauthorized")
        return session

    def require_admin_same_origin(
        request: Request,
        current: Any = Depends(get_state),
    ) -> None:
        if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
            return
        assert_admin_same_origin(request, current.config)

    def set_admin_session_cookie(response: Response, request: Request, session: AdminSession, current: Any) -> None:
        response.set_cookie(
            ADMIN_SESSION_COOKIE,
            session.session_id,
            max_age=current.admin.sessions.ttl_seconds,
            expires=session.expires_at,
            path="/admin",
            httponly=True,
            secure=admin_cookie_secure(request, current.config),
            samesite="strict",
        )

    def clear_admin_session_cookie(response: Response, request: Request, current: Any) -> None:
        response.delete_cookie(
            ADMIN_SESSION_COOKIE,
            path="/admin",
            secure=admin_cookie_secure(request, current.config),
            httponly=True,
            samesite="strict",
        )

    @app.get("/admin/api/session")
    async def admin_session(request: Request, current: Any = Depends(get_state)) -> dict[str, Any]:
        session_id = request.cookies.get(ADMIN_SESSION_COOKIE, "")
        return {
            "authenticated": current.admin.sessions.get(session_id) is not None,
            "setup_required": current.admin.setup_required,
        }

    @app.post("/admin/api/setup", dependencies=[Depends(require_admin_same_origin)])
    async def admin_setup(request: Request, current: Any = Depends(get_state)) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="request body must be a JSON object")
        setup_code = str(body.get("setup_code") or "").strip()
        access_code = str(body.get("access_code") or "")
        key = admin_failure_limiter_key("setup", request)
        if current.admin.failures.is_limited(key):
            return json_response({"ok": False}, status_code=429)
        try:
            if not current.admin.setup_required:
                raise HTTPException(status_code=409, detail="admin setup is already complete")
            if not secrets.compare_digest(setup_code, current.admin.setup_code):
                raise HTTPException(status_code=401, detail="invalid setup code")
            validate_admin_access_code(access_code)
            access_code_hash = await asyncio.to_thread(hash_admin_access_code, access_code)
            current.admin.complete_setup_with_hash(setup_code, access_code_hash)
        except HTTPException:
            current.admin.failures.record_failure(key)
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        current.admin.failures.clear(key)
        session = current.admin.sessions.create()
        response = json_response({"ok": True})
        set_admin_session_cookie(response, request, session, current)
        return response

    @app.post("/admin/api/login", dependencies=[Depends(require_admin_same_origin)])
    async def admin_login(request: Request, current: Any = Depends(get_state)) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="request body must be a JSON object")
        if current.admin.setup_required:
            raise HTTPException(status_code=409, detail="admin setup is required")
        access_code = str(body.get("access_code") or "")
        key = admin_failure_limiter_key("login", request)
        if current.admin.failures.is_limited(key):
            return json_response({"ok": False}, status_code=429)
        if not await asyncio.to_thread(verify_admin_access_code, access_code, current.admin.access_code_hash):
            current.admin.failures.record_failure(key)
            return json_response({"ok": False}, status_code=401)
        current.admin.failures.clear(key)
        session = current.admin.sessions.create()
        response = json_response({"ok": True})
        set_admin_session_cookie(response, request, session, current)
        return response

    @app.post(
        "/admin/api/logout",
        dependencies=[Depends(require_admin_same_origin)],
    )
    async def admin_logout(
        request: Request,
        current: Any = Depends(get_state),
    ) -> JSONResponse:
        session_id = request.cookies.get(ADMIN_SESSION_COOKIE, "")
        if session_id:
            current.admin.sessions.delete(session_id)
        response = json_response({"ok": True})
        clear_admin_session_cookie(response, request, current)
        return response

    @app.get("/admin/api/status", dependencies=[Depends(require_admin_session)])
    async def admin_status(current: Any = Depends(get_state)) -> dict[str, Any]:
        config_path = current.config_path
        return {
            "ok": True,
            "config_path": str(config_path) if config_path else "",
            "config_writable": config_file_writable(config_path),
            "project_url": __project_url__,
            "version": app.version,
        }

    @app.get("/admin/api/config", dependencies=[Depends(require_admin_session)])
    async def admin_config(current: Any = Depends(get_state)) -> JSONResponse:
        return json_response({
            "config": admin_config_response_data(current.config),
            "config_path": str(current.config_path) if current.config_path else "",
            "env_overrides": admin_env_overrides(current.config),
            "effective_values": admin_effective_values(current.config),
        })

    @app.post(
        "/admin/api/config/validate",
        dependencies=[Depends(require_admin_session), Depends(require_admin_same_origin)],
    )
    async def admin_validate_config(request: Request, current: Any = Depends(get_state)) -> JSONResponse:
        try:
            body = await request.json()
            data = body.get("config") if isinstance(body, dict) else None
            if not isinstance(data, dict):
                raise ValueError("config must be an object")
            data = admin_editable_config_to_file_data(data, current.config, hash_access_code=False)
            normalize_result = normalize_config_ids(data)
            file_config = parse_config_data(normalize_result.config, apply_env=False)
            validate_runtime_dependent_config(file_config, data_dir=current.data_dir)
        except ValueError as exc:
            return json_response({"ok": False, "error": str(exc)}, status_code=400)
        except Exception as exc:
            return json_response({"ok": False, "error": exception_reason(exc)}, status_code=400)
        return json_response({"ok": True})

    @app.post(
        "/admin/api/config/normalize",
        dependencies=[Depends(require_admin_session), Depends(require_admin_same_origin)],
    )
    async def admin_normalize_config(request: Request, current: Any = Depends(get_state)) -> JSONResponse:
        try:
            body = await request.json()
            data = body.get("config") if isinstance(body, dict) else None
            if not isinstance(data, dict):
                raise ValueError("config must be an object")
            result = normalize_config_ids(data)
            file_data = admin_editable_config_to_file_data(result.config, current.config, hash_access_code=False)
            file_config = parse_config_data(file_data, apply_env=False)
            validate_runtime_dependent_config(file_config, data_dir=current.data_dir)
        except ValueError as exc:
            return json_response({"ok": False, "error": str(exc)}, status_code=400)
        except Exception as exc:
            return json_response({"ok": False, "error": exception_reason(exc)}, status_code=400)
        return json_response({
            "ok": True,
            "config": admin_editable_config_response_data(result.config),
            "changes": [change.__dict__ for change in result.changes],
            "warnings": list(result.warnings),
        })

    @app.put(
        "/admin/api/config",
        dependencies=[Depends(require_admin_session), Depends(require_admin_same_origin)],
    )
    async def admin_save_config(request: Request, current: Any = Depends(get_state)) -> JSONResponse:
        if current.config_path is None:
            return json_response({
                "ok": False,
                "error": "dashbox must be started with --data-dir, DASHBOX_DATA_DIR, --config, or DASHBOX_CONFIG to save config",
            }, status_code=409)
        try:
            body = await request.json()
            data = body.get("config") if isinstance(body, dict) else None
            if not isinstance(data, dict):
                raise ValueError("config must be an object")
            data = await asyncio.to_thread(admin_editable_config_to_file_data, data, current.config)
            normalize_result = normalize_config_ids(data)
            file_config = parse_config_data(normalize_result.config, apply_env=False)
            validate_runtime_dependent_config(file_config, data_dir=current.data_dir)
            config_data = config_to_json_data(file_config)
            runtime_file_config = parse_config_data(config_data, apply_env=True)
        except ValueError as exc:
            return json_response({"ok": False, "error": str(exc)}, status_code=400)
        except Exception as exc:
            return json_response({"ok": False, "error": exception_reason(exc)}, status_code=400)
        async with config_save_lock:
            try:
                write_config_file(current.config_path, config_data)
                await current.reload_config(runtime_file_config)
            except Exception as exc:
                return json_response({"ok": False, "error": exception_reason(exc)}, status_code=500)
        return json_response({
            "ok": True,
            "config": admin_config_response_data(current.config),
            "config_path": str(current.config_path),
            "env_overrides": admin_env_overrides(current.config),
            "effective_values": admin_effective_values(current.config),
        })

    @app.get("/admin/api/schema", dependencies=[Depends(require_admin_session)])
    async def admin_schema() -> dict[str, Any]:
        return admin_schema_data()

    @app.get("/admin/api/cookies", dependencies=[Depends(require_admin_session)])
    async def admin_cookie_status(current: Any = Depends(get_state)) -> JSONResponse:
        return json_response(current.service.browser_cookie_status())

    @app.post(
        "/admin/api/cookies/reload",
        dependencies=[Depends(require_admin_session), Depends(require_admin_same_origin)],
    )
    async def admin_cookie_reload(
        current: Any = Depends(get_state),
        load: bool = False,
    ) -> JSONResponse:
        return json_response(await current.service.reload_browser_cookies_async(load=load))

    @app.post(
        "/admin/api/subscription-access-code/hash",
        dependencies=[Depends(require_admin_session), Depends(require_admin_same_origin)],
    )
    async def admin_hash_subscription_access_code(request: Request) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="request body must be a JSON object")
        access_code = str(body.get("access_code") or "")
        try:
            access_code_hash = await asyncio.to_thread(hash_subscription_access_code, access_code)
        except ValueError as exc:
            return json_response({"ok": False, "error": str(exc)}, status_code=400)
        except Exception as exc:
            return json_response({"ok": False, "error": exception_reason(exc)}, status_code=500)
        return json_response({"ok": True, "access_code_hash": access_code_hash})

    @app.post("/admin/api/access-code", dependencies=[Depends(require_admin_same_origin)])
    async def admin_update_access_code(
        request: Request,
        current: Any = Depends(get_state),
        session: AdminSession = Depends(require_admin_session),
    ) -> JSONResponse:
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="request body must be a JSON object")
        current_access_code = str(body.get("current_access_code") or "")
        new_access_code = str(body.get("new_access_code") or "")
        if not await asyncio.to_thread(verify_admin_access_code, current_access_code, current.admin.access_code_hash):
            return json_response({"ok": False, "error": "current access code is incorrect"}, status_code=401)
        try:
            validate_admin_access_code(new_access_code)
            access_code_hash = await asyncio.to_thread(hash_admin_access_code, new_access_code)
            current.admin.update_access_code_with_hash(access_code_hash)
        except ValueError as exc:
            return json_response({"ok": False, "error": str(exc)}, status_code=400)
        current.admin.sessions.delete_except(session.session_id)
        return json_response({"ok": True})


def validate_admin_access_code(code: str) -> None:
    if not ADMIN_ACCESS_CODE_RE.fullmatch(code):
        raise ValueError(
            f"admin access code must be {ADMIN_ACCESS_CODE_MIN_LENGTH} to {ADMIN_ACCESS_CODE_MAX_LENGTH} non-whitespace characters"
        )


def hash_admin_access_code(code: str) -> str:
    validate_admin_access_code(code)
    try:
        import bcrypt
    except ImportError as exc:
        raise RuntimeError("bcrypt is required for admin access code authentication") from exc
    return bcrypt.hashpw(code.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_admin_access_code(code: str, access_code_hash: str) -> bool:
    try:
        validate_admin_access_code(code)
        validate_access_code_hash_shape(access_code_hash)
    except ValueError:
        return False
    candidate_hash = "$2a$" + access_code_hash[4:] if access_code_hash.startswith("$2y$") else access_code_hash
    try:
        import bcrypt
    except ImportError as exc:
        raise RuntimeError("bcrypt is required for admin access code authentication") from exc
    return bool(bcrypt.checkpw(code.encode("utf-8"), candidate_hash.encode("ascii")))


def hash_subscription_access_code(code: str) -> str:
    code = code.strip()
    if not validate_access_code_shape(code):
        raise ValueError("access code must be 4 to 12 digits")
    try:
        import bcrypt
    except ImportError as exc:
        raise RuntimeError("bcrypt is required for access_code authentication") from exc
    return bcrypt.hashpw(code.encode("ascii"), bcrypt.gensalt()).decode("ascii")


def admin_config_response_data(config: Config) -> dict[str, Any]:
    data = config_to_json_data(config)
    redact_admin_config_secrets(data)
    return data


def admin_editable_config_response_data(data: dict[str, Any]) -> dict[str, Any]:
    next_data = copy.deepcopy(data)
    redact_admin_config_secrets(next_data, preserve_editable_state=True)
    return next_data


def redact_admin_config_secrets(data: dict[str, Any], *, preserve_editable_state: bool = False) -> None:
    for sub in data.get("subs", []):
        if not isinstance(sub, dict):
            continue
        if preserve_editable_state and "access_code_hash" not in sub:
            continue
        access_code_hash = str(sub.pop("access_code_hash", "") or "")
        sub["access_code_hash_set"] = bool(access_code_hash)
        sub["access_code_hash_action"] = "keep" if access_code_hash else "clear"


def admin_editable_config_to_file_data(
    data: dict[str, Any],
    current_config: Config,
    *,
    hash_access_code: bool = True,
) -> dict[str, Any]:
    next_data = copy.deepcopy(data)
    subs = next_data.get("subs")
    if not isinstance(subs, list):
        return next_data
    current_hash_by_id = {sub.id: sub.access_code_hash for sub in current_config.subs}
    for sub in subs:
        if not isinstance(sub, dict):
            continue
        sub_id = str(sub.get("id") or "")
        auth_mode = str(sub.get("auth_mode") or "").strip().lower()
        access_code = str(sub.pop("access_code", "") or "").strip()
        action = str(sub.pop("access_code_hash_action", "") or "").strip()
        sub.pop("access_code_hash_set", None)

        if auth_mode == "anonymous":
            if access_code:
                raise ValueError(f"subscription {sub_id} auth_mode anonymous must not set access_code")
            sub.pop("access_code_hash", None)
            continue

        if access_code:
            if hash_access_code:
                sub["access_code_hash"] = hash_subscription_access_code(access_code)
            else:
                if not validate_access_code_shape(access_code):
                    raise ValueError("access code must be 4 to 12 digits")
                sub["access_code_hash"] = SUBSCRIPTION_ACCESS_CODE_HASH_PLACEHOLDER
            action = "replace"
        if not action:
            action = "replace"
        if action == "keep":
            current_hash = current_hash_by_id.get(sub_id, "")
            if not current_hash:
                raise ValueError(f"subscription {sub_id} access_code_hash cannot keep missing existing value")
            sub["access_code_hash"] = current_hash
        elif action == "replace":
            pass
        elif action == "clear":
            sub.pop("access_code_hash", None)
        else:
            raise ValueError(f"subscription {sub_id} access_code_hash_action must be keep, replace, or clear")
    return next_data


def admin_failure_limiter_key(action: str, request: Request) -> str:
    host = request.client.host if request.client else ""
    return f"admin:{action}|{host}"


def admin_cookie_secure(request: Request, config: Config) -> bool:
    return admin_request_scheme(request) == "https" or config.public_base_url.lower().startswith("https://")


def assert_admin_same_origin(request: Request, config: Config) -> None:
    fetch_site = request.headers.get("sec-fetch-site", "").strip().lower()
    if fetch_site and fetch_site not in {"same-origin", "same-site", "none"}:
        raise HTTPException(status_code=403, detail="cross-origin admin write is not allowed")
    allowed = {request_origin(request)}
    if config.public_base_url:
        public_origin = origin_from_url(config.public_base_url)
        if public_origin:
            allowed.add(public_origin)
    origin = request.headers.get("origin", "").strip()
    if origin:
        if origin_from_url(origin) not in allowed:
            raise HTTPException(status_code=403, detail="cross-origin admin write is not allowed")
        return
    referer = request.headers.get("referer", "").strip()
    if referer and origin_from_url(referer) not in allowed:
        raise HTTPException(status_code=403, detail="cross-origin admin write is not allowed")


def request_origin(request: Request) -> str:
    host = request.headers.get("host", "")
    return f"{admin_request_scheme(request)}://{host}".rstrip("/")


def admin_request_scheme(request: Request) -> str:
    if request.url.scheme == "https":
        return "https"
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0].strip().lower()
    if forwarded_proto in {"http", "https"}:
        return forwarded_proto
    return request.url.scheme


def origin_from_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return ""
    if not parts.scheme or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}".rstrip("/")


def admin_env_overrides(config: Config) -> dict[str, Any]:
    return {
        "image_proxy_mode": config.image_proxy_mode.value,
        "upstream_timeout": config.upstream_timeout,
        "public_base_url": config.public_base_url,
    }


def admin_effective_values(config: Config) -> dict[str, Any]:
    return {
        "user_agent": config.effective_user_agent,
    }


def config_file_writable(path: Path | None) -> bool:
    if path is None:
        return False
    if path.exists():
        return os.access(path, os.W_OK)
    parent = path.parent if str(path.parent) else Path.cwd()
    return parent.exists() and os.access(parent, os.W_OK)


def json_response(value: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        content=value,
        status_code=status_code,
        headers={"Cache-Control": "no-store"},
    )
