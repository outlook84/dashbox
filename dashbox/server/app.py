from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from .. import i18n
from ..admin import register_admin_routes
from ..adapters import kodi, kodi_repository, tvbox
from ..auth.access_code import validate_access_code_shape, verify_access_code
from ..auth.tokens import issue_access_token
from ..config import AuthMode, Config, ImageProxyMode, Subscription, VodStyle
from ..core import image_policy
from ..core.image_proxy import proxy_image, proxy_image_head, register_image_urls, trigger_image_prefetch
from ..core.media_service import dumps_json
from ..utils.errors import exception_reason
from ..media import danmaku
from ..media.dash import build_mpd
from .auth import attach_media_token, authorize_media_dash_request, authorize_media_inline_request, authorize_protocol_request, failure_limiter_key
from .danmaku import proxy_bilibili_danmaku, proxy_bilibili_danmaku_ass
from .images import scope_image_urls, scope_kodi_image_urls
from .kodi_playback import attach_kodi_danmaku_subtitle, localize_kodi_data_manifest, sync_inputstream_headers, wrap_kodi_subtitle_urls
from .media_proxy import proxy_dash_session_segment, refresh_dash_session
from .middleware import HeadRequestMiddleware
from .state import AppState
from .static import ICON_FILES, SPIDER_ASSET_PATH, admin_index_response, safe_admin_asset_path, spider_path
from .. import __version__
from .utils import base_url, json_response, log_js_environment, log_startup_versions, request_locale, scoped_identity_key, set_tvbox_icon_base_url
from ..sites import youtube_subtitles


logger = logging.getLogger("dashbox")

def create_app(
    config: Config | None = None,
    *,
    config_path: str | Path | None = None,
    data_dir: str | Path | None = None,
) -> FastAPI:
    state = AppState(config or Config(), config_path=config_path, data_dir=data_dir)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await state.http_client.aopen()
        await state.stream_http_client.aopen()
        log_startup_versions(state)
        log_js_environment(state)
        logger.info("dashbox started")
        try:
            yield
        finally:
            await state.image_fetcher.aclose()
            await state.stream_http_client.aclose()
            await state.http_client.aclose()

    app = FastAPI(title="dashbox", version=__version__, lifespan=lifespan)
    app.add_middleware(HeadRequestMiddleware)
    app.state.dashbox = state

    def get_state() -> AppState:
        return app.state.dashbox

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"ok": "true"}

    @app.get("/subtitle/{filename:path}")
    async def subtitle_redirect(filename: str, url: str = Query("")) -> RedirectResponse:
        if not filename.strip():
            raise HTTPException(status_code=404, detail="subtitle filename is required")
        if not youtube_subtitles.is_subtitle_redirect_target(url):
            raise HTTPException(status_code=400, detail="invalid subtitle url")
        return RedirectResponse(url, status_code=302)

    register_admin_routes(app, get_state)

    @app.get("/admin")
    @app.get("/admin/")
    async def admin_ui() -> FileResponse:
        return admin_index_response()

    @app.get("/admin/assets/{filename:path}")
    async def admin_asset(filename: str) -> FileResponse:
        path = safe_admin_asset_path(filename)
        if path is None or not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="admin asset not found")
        return FileResponse(path, headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.get("/admin/{path:path}")
    async def admin_ui_fallback(path: str) -> FileResponse:
        return admin_index_response()

    @app.get("/sub")
    async def sub(request: Request, current: AppState = Depends(get_state)) -> dict[str, Any]:
        raise HTTPException(status_code=404, detail="subscription id is required")

    @app.get("/sub/{sub_id}")
    async def tvbox_sub(sub_id: str, request: Request, current: AppState = Depends(get_state)) -> dict[str, Any]:
        sub = current.subscriptions.tvbox_sub_by_id(sub_id)
        return tvbox_subscription_response(sub, base_url(current.config, request))

    def tvbox_subscription_response(sub: Subscription, base: str) -> dict[str, Any]:
        tvbox_config = sub.tvbox
        if tvbox_config is None:
            raise HTTPException(status_code=404, detail="subscription not found")
        site_key = scoped_identity_key(tvbox_config.site_key, base)
        storage_key = scoped_identity_key(f"dashbox_tvbox_{sub.id}", base)
        site = {
            "key": site_key,
            "name": tvbox_config.site_name,
            "type": 3,
            "api": base + spider_path(),
            "ext": dumps_json({
                "gateway": base + "/tvbox/" + sub.id,
                "assetBase": base,
                "skey": storage_key,
                "locale": tvbox_config.locale,
                "vodStyle": tvbox.normalize_vod_style(tvbox_config.vod_style),
                "labels": i18n.spider_labels(tvbox_config.locale),
            }),
            "searchable": 1,
            "quickSearch": 1,
            "filterable": 1,
            "changeable": 0,
            "timeout": 60,
        }
        if tvbox.normalize_vod_style(tvbox_config.vod_style) != VodStyle.LIST:
            site["style"] = tvbox.vod_style_fields(tvbox_config.vod_style)["style"]
        return {
            "sites": [site],
            "parses": [],
            "lives": [{
                "name": "Dashbox",
                "type": "0",
                "url": "",
            }],
        }

    @app.get("/spider/{filename}")
    async def spider(filename: str) -> FileResponse:
        if filename != SPIDER_ASSET_PATH.name:
            raise HTTPException(status_code=404, detail="spider not found")
        return FileResponse(SPIDER_ASSET_PATH, media_type="application/javascript; charset=utf-8")

    @app.get("/assets/icons/{filename}")
    async def icon(filename: str) -> FileResponse:
        path = ICON_FILES.get(filename)
        if not path or not path.exists():
            raise HTTPException(status_code=404, detail="icon not found")
        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.get("/tvbox/{sub_id}/home")
    async def home(sub_id: str, request: Request, current: AppState = Depends(get_state)) -> JSONResponse:
        sub = current.subscriptions.tvbox_sub_by_id(sub_id)
        unauthorized = authorize_protocol_request(sub, request, current, audience="tvbox")
        if unauthorized:
            return unauthorized
        return json_response(current.tvbox_service(sub_id).home())

    @app.get("/tvbox/{sub_id}/category")
    async def category(
        sub_id: str,
        request: Request,
        current: AppState = Depends(get_state),
        tid: str = Query("url"),
        refresh: bool = Query(False),
    ) -> JSONResponse:
        unauthorized = authorize_protocol_request(current.subscriptions.tvbox_sub_by_id(sub_id), request, current, audience="tvbox")
        if unauthorized:
            return unauthorized
        base = base_url(current.config, request)
        set_tvbox_icon_base_url(base)
        service = current.tvbox_service(sub_id)
        value = await service.category(tid, base, refresh=refresh)
        scope_image_urls(value, protocol="tvbox", sub_id=sub_id)
        await register_image_urls(
            tid,
            tvbox.image_upstream_urls_from_page(value, current.config),
            current,
            protocol="tvbox",
            sub_id=sub_id,
        )
        return json_response(value)

    @app.get("/tvbox/{sub_id}/search")
    async def search(
        sub_id: str,
        request: Request,
        current: AppState = Depends(get_state),
        key: str = Query(""),
    ) -> JSONResponse:
        unauthorized = authorize_protocol_request(current.subscriptions.tvbox_sub_by_id(sub_id), request, current, audience="tvbox")
        if unauthorized:
            return unauthorized
        service = current.tvbox_service(sub_id)
        try:
            base = base_url(current.config, request)
            set_tvbox_icon_base_url(base)
            value = await service.search(key, base)
            scope_image_urls(value, protocol="tvbox", sub_id=sub_id)
            return json_response(value)
        except Exception as exc:
            logger.exception("tvbox request failed")
            return json_response({"error": exception_reason(exc)}, status_code=400)

    @app.get("/tvbox/{sub_id}/detail")
    async def detail(
        sub_id: str,
        request: Request,
        current: AppState = Depends(get_state),
        id: str = Query(""),
    ) -> JSONResponse:
        unauthorized = authorize_protocol_request(current.subscriptions.tvbox_sub_by_id(sub_id), request, current, audience="tvbox")
        if unauthorized:
            return unauthorized
        if not id:
            raise HTTPException(status_code=400, detail="missing id")
        service = current.tvbox_service(sub_id)
        try:
            base = base_url(current.config, request)
            set_tvbox_icon_base_url(base)
            value = await service.detail(id, base)
            scope_image_urls(value, protocol="tvbox", sub_id=sub_id)
            return json_response(value)
        except Exception as exc:
            logger.exception("tvbox request failed")
            return json_response({"error": exception_reason(exc)}, status_code=400)

    @app.get("/tvbox/{sub_id}/play")
    async def play(
        sub_id: str,
        request: Request,
        current: AppState = Depends(get_state),
        id: str = Query(""),
    ) -> JSONResponse:
        unauthorized = authorize_protocol_request(current.subscriptions.tvbox_sub_by_id(sub_id), request, current, audience="tvbox")
        if unauthorized:
            return unauthorized
        if not id:
            raise HTTPException(status_code=400, detail="missing id")
        service = current.tvbox_service(sub_id)
        try:
            value = await service.play(id, base_url(current.config, request))
            attach_media_token(value, current)
            return json_response(value)
        except Exception as exc:
            logger.exception("tvbox request failed")
            return json_response({"error": exception_reason(exc)}, status_code=400)

    @app.post("/tvbox/{sub_id}/auth")
    async def tvbox_auth(sub_id: str, request: Request, current: AppState = Depends(get_state)) -> JSONResponse:
        sub = current.subscriptions.tvbox_sub_by_id(sub_id)
        if sub.auth_mode == AuthMode.ANONYMOUS:
            token, expires_at = issue_access_token(
                secret=current.token_secret,
                sub_id=sub.id,
                audience="tvbox",
                access_code_hash=sub.access_code_hash,
            )
            return json_response({"ok": True, "access_token": token, "expires_at": expires_at})
        key = failure_limiter_key(sub.id, request)
        if current.auth_failures.is_limited(key):
            return json_response({"ok": False}, status_code=429)
        try:
            body = await request.json()
        except Exception:
            body = {}
        code = str(body.get("code") or "").strip() if isinstance(body, dict) else ""
        if not validate_access_code_shape(code):
            return json_response({"ok": False}, status_code=400)
        if not verify_access_code(code, sub.access_code_hash):
            current.auth_failures.record_failure(key)
            return json_response({"ok": False}, status_code=401)
        current.auth_failures.clear(key)
        token, expires_at = issue_access_token(
            secret=current.token_secret,
            sub_id=sub.id,
            audience="tvbox",
            access_code_hash=sub.access_code_hash,
        )
        return json_response({"ok": True, "access_token": token, "expires_at": expires_at})

    @app.post("/api/v1/subs/{sub_id}/auth")
    async def api_auth(sub_id: str, request: Request, current: AppState = Depends(get_state)) -> JSONResponse:
        sub = current.subscriptions.kodi_sub_by_id(sub_id)
        if sub.auth_mode == AuthMode.ANONYMOUS:
            token, expires_at = issue_access_token(
                secret=current.token_secret,
                sub_id=sub.id,
                audience="kodi",
                access_code_hash=sub.access_code_hash,
            )
            return json_response({"ok": True, "access_token": token, "expires_at": expires_at})
        key = failure_limiter_key(sub.id, request)
        if current.auth_failures.is_limited(key):
            return json_response({"ok": False}, status_code=429)
        try:
            body = await request.json()
        except Exception:
            body = {}
        code = str(body.get("code") or "").strip() if isinstance(body, dict) else ""
        if not validate_access_code_shape(code):
            return json_response({"ok": False}, status_code=400)
        if not verify_access_code(code, sub.access_code_hash):
            current.auth_failures.record_failure(key)
            return json_response({"ok": False}, status_code=401)
        current.auth_failures.clear(key)
        token, expires_at = issue_access_token(
            secret=current.token_secret,
            sub_id=sub.id,
            audience="kodi",
            access_code_hash=sub.access_code_hash,
        )
        return json_response({"ok": True, "access_token": token, "expires_at": expires_at})

    @app.get("/api/v1/subs/{sub_id}/home")
    async def api_home(sub_id: str, request: Request, current: AppState = Depends(get_state)) -> JSONResponse:
        unauthorized = authorize_protocol_request(current.subscriptions.kodi_sub_by_id(sub_id), request, current, audience="kodi")
        if unauthorized:
            return unauthorized
        service = current.kodi_service(sub_id)
        with i18n.use_locale(request_locale(request)):
            base = base_url(current.config, request)
            value = service.page_response(await service.root_page(base), base)
        return json_response(value)

    @app.get("/api/v1/subs/{sub_id}/items")
    async def api_items(
        sub_id: str,
        request: Request,
        current: AppState = Depends(get_state),
        id: str = Query(""),
        refresh: bool = Query(False),
    ) -> JSONResponse:
        unauthorized = authorize_protocol_request(current.subscriptions.kodi_sub_by_id(sub_id), request, current, audience="kodi")
        if unauthorized:
            return unauthorized
        if not id:
            raise HTTPException(status_code=400, detail="missing id")
        service = current.kodi_service(sub_id)
        try:
            base = base_url(current.config, request)
            locale = request_locale(request)
            with i18n.use_locale(locale):
                page = await service.item_page(id, base, refresh=refresh, locale=locale)
                value = service.page_response(page, base)
            scope_kodi_image_urls(value, sub_id=sub_id)
            await register_image_urls(id, kodi.image_upstream_urls_from_page(value, current.config), current, protocol="kodi", sub_id=sub_id)
            return json_response(value)
        except Exception as exc:
            logger.exception("kodi request failed")
            return json_response({"error": exception_reason(exc)}, status_code=400)

    @app.get("/api/v1/subs/{sub_id}/detail")
    async def api_detail(
        sub_id: str,
        request: Request,
        current: AppState = Depends(get_state),
        id: str = Query(""),
    ) -> JSONResponse:
        unauthorized = authorize_protocol_request(current.subscriptions.kodi_sub_by_id(sub_id), request, current, audience="kodi")
        if unauthorized:
            return unauthorized
        if not id:
            raise HTTPException(status_code=400, detail="missing id")
        service = current.kodi_service(sub_id)
        try:
            base = base_url(current.config, request)
            locale = request_locale(request)
            with i18n.use_locale(locale):
                page = await service.detail_page(id, base, locale=locale)
                value = service.page_response(page, base)
            scope_kodi_image_urls(value, sub_id=sub_id)
            await register_image_urls(id, kodi.image_upstream_urls_from_page(value, current.config), current, protocol="kodi", sub_id=sub_id)
            return json_response(value)
        except Exception as exc:
            logger.exception("kodi request failed")
            return json_response({"error": exception_reason(exc)}, status_code=400)

    @app.get("/api/v1/subs/{sub_id}/search")
    async def api_search(
        sub_id: str,
        request: Request,
        current: AppState = Depends(get_state),
        key: str = Query(""),
    ) -> JSONResponse:
        unauthorized = authorize_protocol_request(current.subscriptions.kodi_sub_by_id(sub_id), request, current, audience="kodi")
        if unauthorized:
            return unauthorized
        service = current.kodi_service(sub_id)
        try:
            base = base_url(current.config, request)
            locale = request_locale(request)
            with i18n.use_locale(locale):
                page = await service.search_page(key, base, locale=locale)
                value = service.page_response(page, base)
            scope_kodi_image_urls(value, sub_id=sub_id)
            return json_response(value)
        except Exception as exc:
            logger.exception("kodi request failed")
            return json_response({"error": exception_reason(exc)}, status_code=400)

    @app.post("/api/v1/subs/{sub_id}/play")
    async def api_play(sub_id: str, request: Request, current: AppState = Depends(get_state)) -> JSONResponse:
        unauthorized = authorize_protocol_request(current.subscriptions.kodi_sub_by_id(sub_id), request, current, audience="kodi")
        if unauthorized:
            return unauthorized
        try:
            body = await request.json()
        except Exception:
            body = {}
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="request body must be an object")
        play_id = str(body.get("id") or "").strip()
        if not play_id:
            raise HTTPException(status_code=400, detail="missing id")
        service = current.kodi_service(sub_id)
        try:
            base = base_url(current.config, request)
            value = await service.play(play_id, base, body.get("playback"))
            localize_kodi_data_manifest(value, sub_id, base, current)
            attach_kodi_danmaku_subtitle(value, body.get("playback"))
            wrap_kodi_subtitle_urls(value, base)
            attach_media_token(value, current)
            sync_inputstream_headers(value, current)
            return json_response(value)
        except ValueError as exc:
            return json_response({"error": exception_reason(exc)}, status_code=400)
        except Exception as exc:
            logger.exception("kodi request failed")
            return json_response({"error": exception_reason(exc)}, status_code=400)

    @app.get("/repo/")
    async def kodi_repository_index(request: Request, current: AppState = Depends(get_state)) -> Response:
        repo = current.kodi_repo
        repository_filename = kodi_repository.repository_package_filename(base_url(current.config, request))
        content = (
            "<!doctype html><html><body>"
            '<a href="addons.xml">addons.xml</a><br>'
            '<a href="addons.xml.md5">addons.xml.md5</a><br>'
            f'<a href="{kodi_repository.REPOSITORY_ADDON_ID}/{repository_filename}">{repository_filename}</a><br>'
            f'<a href="{repo.addon_id}/{repo.package_filename}">{repo.package_filename}</a>'
            "</body></html>"
        )
        return Response(content=content, media_type="text/html; charset=utf-8")

    @app.get("/repo/addons.xml")
    async def kodi_repository_addons(request: Request, current: AppState = Depends(get_state)) -> Response:
        return Response(
            content=kodi_repository.addons_xml(base_url=base_url(current.config, request)),
            media_type="application/xml; charset=utf-8",
        )

    @app.get("/repo/addons.xml.md5")
    async def kodi_repository_addons_md5(request: Request, current: AppState = Depends(get_state)) -> Response:
        return Response(
            content=kodi_repository.addons_xml_md5(base_url=base_url(current.config, request)),
            media_type="text/plain; charset=utf-8",
        )

    @app.get("/repo.zip")
    async def kodi_repository_package_shortcut(request: Request, current: AppState = Depends(get_state)) -> Response:
        filename = kodi_repository.repository_package_filename(base_url(current.config, request))
        return Response(
            content=kodi_repository.repository_package_zip(base_url(current.config, request)),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )

    @app.get("/repo/{addon_id}/")
    async def kodi_repository_addon_index(addon_id: str, request: Request, current: AppState = Depends(get_state)) -> Response:
        repo = current.kodi_repo
        if addon_id == kodi_repository.REPOSITORY_ADDON_ID:
            filename = kodi_repository.repository_package_filename(base_url(current.config, request))
            content = f'<!doctype html><html><body><a href="{filename}">{filename}</a></body></html>'
            return Response(content=content, media_type="text/html; charset=utf-8")
        if addon_id != repo.addon_id:
            raise HTTPException(status_code=404, detail="kodi addon not found")
        content = f'<!doctype html><html><body><a href="{repo.package_filename}">{repo.package_filename}</a></body></html>'
        return Response(content=content, media_type="text/html; charset=utf-8")

    @app.get("/repo/{addon_id}/{filename}")
    async def kodi_repository_package(
        addon_id: str,
        filename: str,
        request: Request,
        current: AppState = Depends(get_state),
    ) -> Response:
        repo = current.kodi_repo
        base = base_url(current.config, request)
        if addon_id == repo.addon_id and filename == "icon.png":
            icon_path = kodi_repository.PLUGIN_DIR / "icon.png"
            if not icon_path.exists():
                raise HTTPException(status_code=404, detail="kodi addon icon not found")
            return FileResponse(
                icon_path,
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=31536000, immutable"},
            )
        if addon_id == kodi_repository.REPOSITORY_ADDON_ID and filename in {
            kodi_repository.repository_package_filename(),
            kodi_repository.repository_package_filename(base),
        }:
            return Response(
                content=kodi_repository.repository_package_zip(base),
                media_type="application/zip",
                headers={
                    "Content-Disposition": f'attachment; filename="{kodi_repository.repository_package_filename(base)}"',
                    "Cache-Control": "no-store",
                },
            )
        if addon_id == repo.addon_id and filename == f"{repo.package_filename}.sha256":
            return Response(
                content=kodi_repository.package_zip_sha256(default_gateway=base),
                media_type="text/plain; charset=utf-8",
                headers={"Cache-Control": "no-store"},
            )
        if addon_id != repo.addon_id or filename != repo.package_filename:
            raise HTTPException(status_code=404, detail="kodi addon package not found")
        return Response(
            content=kodi_repository.package_zip(default_gateway=base),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )

    @app.get("/media/{session_id}/manifest.mpd")
    async def media_manifest(
        request: Request,
        session_id: str,
        current: AppState = Depends(get_state),
    ) -> Response:
        session = current.dash_store.get(session_id, touch=False)
        if session:
            authorize_media_dash_request(session, request, current)
            current.dash_store.touch(session_id)
            mpd = build_mpd(
                session,
                str(request.url_for("media_segment", session_id=session_id, track_index=0, segment_index=0)).rsplit("/", 3)[0],
            )
            return Response(content=mpd, media_type="application/dash+xml; charset=utf-8")
        inline_session = current.inline_manifest_store.get(session_id, touch=False)
        if inline_session:
            authorize_media_inline_request(inline_session, request, current)
            current.inline_manifest_store.touch(session_id)
            return Response(content=inline_session.content, media_type=inline_session.media_type)
        raise HTTPException(status_code=404, detail="dash session not found")

    @app.head("/media/{session_id}/{track_index}/{segment_index}", name="media_segment_head")
    @app.get("/media/{session_id}/{track_index}/{segment_index}", name="media_segment")
    async def media_segment(
        request: Request,
        session_id: str,
        track_index: int,
        segment_index: int,
        current: AppState = Depends(get_state),
    ) -> Response:
        session = current.dash_store.get(session_id, touch=False)
        if not session:
            raise HTTPException(status_code=404, detail="dash session not found")
        authorize_media_dash_request(session, request, current)
        current.dash_store.touch(session_id)
        response = await proxy_dash_session_segment(session, track_index, segment_index, request, current)
        if response.status_code not in (403, 404, 410):
            return response
        refreshed = await refresh_dash_session(session, current)
        if not refreshed:
            return response
        return await proxy_dash_session_segment(refreshed, track_index, segment_index, request, current)

    @app.get("/danmaku/bilibili/{cid}.xml")
    async def bilibili_danmaku(
        cid: str,
        current: AppState = Depends(get_state),
    ) -> Response:
        if not cid.isdecimal():
            raise HTTPException(status_code=404, detail="danmaku not found")
        return await proxy_bilibili_danmaku(cid, current.config, current.http_client.client)

    @app.get("/danmaku/bilibili/{cid}.ass")
    async def bilibili_danmaku_ass(
        cid: str,
        current: AppState = Depends(get_state),
        width: int = Query(1920, ge=320, le=7680),
        height: int = Query(1080, ge=180, le=4320),
        font_size: int = Query(danmaku.DEFAULT_FONT_SIZE, ge=8, le=200),
        font_face: str = Query("sans-serif", min_length=1, max_length=128),
    ) -> Response:
        if not cid.isdecimal():
            raise HTTPException(status_code=404, detail="danmaku not found")
        return await proxy_bilibili_danmaku_ass(
            cid,
            current.config,
            current.http_client.client,
            width=width,
            height=height,
            font_face=font_face,
            font_size=font_size,
        )

    @app.head("/image")
    @app.get("/image")
    async def image(
        request: Request,
        url: str = Query(""),
        protocol: str = Query(""),
        sub_id: str = Query(""),
        current: AppState = Depends(get_state),
    ) -> Response:
        if current.config.image_proxy_mode == ImageProxyMode.OFF:
            raise HTTPException(status_code=404, detail="image proxy disabled")
        if not image_policy.is_supported_image_proxy_url(url, current.config.image_proxy_mode):
            raise HTTPException(status_code=400, detail="unsupported image upstream")
        if request.method == "HEAD":
            return await proxy_image_head(url, current.config, request, current.image_cache)
        await trigger_image_prefetch(url, current, protocol=protocol, sub_id=sub_id)
        return await proxy_image(url, current.config, request, current.image_cache, current.image_fetcher)

    return app




if __name__ == "__main__":
    from .cli import main

    main()
