"""M8 — /settings 페이지 + POST /api/settings (언어/테마/자동 시작).

M11 Phase 5 — multi-backend LLM 설정용 3 endpoint 추가:
- POST /api/settings/backends/{name}      — backend 설정 갱신
- POST /api/settings/backends/{name}/test — backend.test_connection 호출
- POST /api/settings/chains               — chain 순서 갱신

M11.1 Phase 5 (task 5.1) — Gemini Batch API 설정 endpoint 추가:
- POST /settings/batch               — cfg.batch 업데이트 + save_config
- POST /settings/batch/jobs/{id}/cancel — BatchManager.cancel(id) 호출
"""
from __future__ import annotations

import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from assetcache.config import Config, save_config
import assetcache.platform.autostart as _autostart_mod

log = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])


# M11 — backend / chain settings
_VALID_BACKEND_KEYS = frozenset(
    {"enabled", "api_key", "model_image", "model_audio", "model_embed"}
)
_VALID_MODALITIES = ("chat_image", "chat_spritesheet", "chat_audio", "text_embed")


def _build_registry_for_test(cfg: Config) -> Any:
    """test_connection 만 위한 가벼운 BackendRegistry — 최신 cfg 기반.

    monkeypatch 가능한 별도 함수 — 테스트에서 SDK 호출 회피.
    """
    from assetcache.core.llm.registry import BackendRegistry

    return BackendRegistry.from_config(cfg)


class SettingsUpdate(BaseModel):
    """설정 업데이트 페이로드 — 각 필드는 선택적으로 None."""
    ui_language: Optional[Literal["ko", "en", "auto"]] = None
    ui_theme: Optional[Literal["auto", "light", "dark"]] = None
    autostart: Optional[bool] = None


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    """설정 페이지 — 언어 / 테마 / 자동 시작 + M11 backend / chain + M11.1 batch."""
    deps = request.app.state.deps
    templates = request.app.state.templates
    # M11+ — partial include 에 사용할 lang 변수. LocaleMiddleware 가
    # request.state.locale 셋팅 (정확한 키는 'locale' — locale_middleware.py 참조).
    # 없거나 ko/en 외 값이면 "en" 폴백.
    lang = getattr(request.state, "locale", "en")
    if lang not in ("ko", "en"):
        lang = "en"
    # M11.1 — active batch jobs (state IN ('submitted', 'running'))
    try:
        active_batch_jobs = deps.store.list_active_batch_jobs()
    except Exception:
        active_batch_jobs = []
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "page": "settings",
            "config": deps.config,
            "autostart_actual": _autostart_mod.is_autostart_enabled(),
            "lang": lang,
            "active_batch_jobs": active_batch_jobs,
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


# ---- M11 Phase 5: backend / chain settings ----


@router.post("/api/settings/backends/{name}")
async def update_backend(name: str, request: Request) -> JSONResponse:
    """backend 설정 갱신 — enabled/api_key/model_* 키만 적용 (PATCH 의미)."""
    deps = request.app.state.deps
    cfg: Config = deps.config
    if name not in cfg.backends:
        return JSONResponse(
            {"ok": False, "error": f"unknown backend: {name}"}, status_code=404
        )
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        return JSONResponse(
            {"ok": False, "error": "body must be a JSON object"}, status_code=400
        )
    for key, value in body.items():
        if key in _VALID_BACKEND_KEYS:
            cfg.backends[name][key] = value
    try:
        save_config(cfg, deps.paths.config_path)
    except Exception as e:
        log.warning("config save failed: %s", e)
    return JSONResponse({"ok": True})


@router.post("/api/settings/backends/{name}/test")
async def test_backend(name: str, request: Request) -> JSONResponse:
    """현재 cfg 기반으로 backend.test_connection() 호출 → {ok, message}."""
    deps = request.app.state.deps
    cfg: Config = deps.config
    if name not in cfg.backends:
        return JSONResponse(
            {"ok": False, "error": f"unknown backend: {name}"}, status_code=404
        )
    registry = _build_registry_for_test(cfg)
    backend = registry.get_backend(name)
    if backend is None:
        return JSONResponse(
            {
                "ok": False,
                "message": "backend not configured (enabled=False or api_key missing)",
            }
        )
    try:
        ok = bool(backend.test_connection())
    except Exception as e:  # pragma: no cover - safety net
        log.warning("backend %s test_connection raised: %s", name, e)
        return JSONResponse({"ok": False, "error": str(e)})
    return JSONResponse({"ok": ok})


@router.post("/api/settings/chains")
async def update_chains(request: Request) -> JSONResponse:
    """chain 순서 갱신 — JSON body 의 각 키는 modality, 값은 backend 이름 리스트."""
    deps = request.app.state.deps
    cfg: Config = deps.config
    try:
        body = await request.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        return JSONResponse(
            {"ok": False, "error": "body must be a JSON object"}, status_code=400
        )
    known_backends = set(cfg.backends.keys())
    # validate first — 부분 적용 회피
    for modality, order in body.items():
        if modality not in _VALID_MODALITIES:
            return JSONResponse(
                {"ok": False, "error": f"unknown modality: {modality}"},
                status_code=400,
            )
        if not isinstance(order, list):
            return JSONResponse(
                {"ok": False, "error": f"chain must be a list: {modality}"},
                status_code=400,
            )
        for backend_name in order:
            if backend_name not in known_backends:
                return JSONResponse(
                    {
                        "ok": False,
                        "error": f"unknown backend: {backend_name}",
                    },
                    status_code=400,
                )
    # apply
    for modality, order in body.items():
        cfg.chains[modality] = [str(x) for x in order]
    try:
        save_config(cfg, deps.paths.config_path)
    except Exception as e:
        log.warning("config save failed: %s", e)
    return JSONResponse({"ok": True})


# ---- M11.1 Phase 5 task 5.1: batch settings ----

_VALID_TOGGLES = frozenset({"auto", "forced_on", "forced_off"})


@router.post("/settings/batch")
async def post_batch_settings(
    request: Request,
    threshold: int = Form(...),
    toggle: str = Form(...),
    poll_interval_seconds: int = Form(1800),
) -> RedirectResponse:
    """cfg.batch 업데이트 + save_config → /settings 리다이렉트.

    threshold: 1~200 clamp.
    toggle: auto/forced_on/forced_off (그 외 → "auto" 폴백).
    poll_interval_seconds: 그대로 저장.
    """
    deps = request.app.state.deps
    cfg: Config = deps.config

    # 유효성 검사 + clamp
    threshold = max(1, min(threshold, 200))
    if toggle not in _VALID_TOGGLES:
        toggle = "auto"

    cfg.batch.threshold = threshold
    cfg.batch.toggle = toggle  # type: ignore[assignment]
    cfg.batch.poll_interval_seconds = poll_interval_seconds

    try:
        save_config(cfg, deps.paths.config_path)
    except Exception as e:
        log.warning("batch config save failed: %s", e)

    return RedirectResponse("/settings", status_code=303)


@router.post("/settings/batch/jobs/{job_id}/cancel")
async def post_cancel_batch_job(
    request: Request,
    job_id: int,
) -> RedirectResponse:
    """BatchManager.cancel(job_id) 호출 → /settings 리다이렉트.

    deps.batch_manager 가 None 이면 404 반환 (배치 기능 미설정).
    """
    deps = request.app.state.deps
    bm = deps.batch_manager
    if bm is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="batch_manager not configured")
    bm.cancel(job_id)
    return RedirectResponse("/settings", status_code=303)
