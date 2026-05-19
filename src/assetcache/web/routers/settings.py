"""M8 — /settings 페이지 + POST /api/settings (언어/테마/자동 시작)."""
from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from assetcache.config import save_config
import assetcache.platform.autostart as _autostart_mod

log = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])


class SettingsUpdate(BaseModel):
    """설정 업데이트 페이로드 — 각 필드는 선택적으로 None."""
    ui_language: Optional[Literal["ko", "en", "auto"]] = None
    ui_theme: Optional[Literal["auto", "light", "dark"]] = None
    autostart: Optional[bool] = None


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    """설정 페이지 — 언어 / 테마 / 자동 시작 옵션."""
    deps = request.app.state.deps
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "page": "settings",
            "config": deps.config,
            "autostart_actual": _autostart_mod.is_autostart_enabled(),
        },
    )


@router.post("/api/settings")
async def update_settings(
    payload: SettingsUpdate,
    request: Request,
) -> JSONResponse:
    """설정 업데이트 — Config 저장 + 언어 변경 시 쿠키 설정."""
    deps = request.app.state.deps
    cfg = deps.config

    if payload.ui_language is not None:
        cfg.ui_language = payload.ui_language

    if payload.ui_theme is not None:
        cfg.ui_theme = payload.ui_theme

    if payload.autostart is not None:
        try:
            _autostart_mod.set_autostart(payload.autostart)
            cfg.autostart = payload.autostart
        except OSError as e:
            return JSONResponse(
                {"ok": False, "error": str(e)},
                status_code=500,
            )

    # config 영속 저장
    try:
        save_config(cfg, deps.paths.config_path)
    except Exception as e:
        log.warning("설정 저장 실패: %s", e)

    response = JSONResponse({"ok": True})
    # 언어 변경 시 쿠키 동기화 (LocaleMiddleware 가 읽음).
    # "auto" 면 기존 쿠키 삭제 — 안 그러면 잔존 쿠키가 Config.ui_language 보다
    # 우선이라 "자동 감지" 가 실제로 자동 동작 안 함.
    if payload.ui_language == "auto":
        response.delete_cookie("assetcache_locale")
    elif payload.ui_language is not None:
        response.set_cookie(
            "assetcache_locale",
            payload.ui_language,
            max_age=31_536_000,
            samesite="lax",
        )
    return response
