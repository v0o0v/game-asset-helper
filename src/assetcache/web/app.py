"""M5 — FastAPI 앱 팩토리.

`build_app(deps)` 가 FastAPI 인스턴스를 반환. lifespan 에서 PendingPickQueue
의 cleanup_expired 백그라운드 잡 실행. 라우터 10개 등록 (Phase 2B 에서
pages.router 추가 — /, /library HTML 페이지).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import assetcache
from .deps import WebDeps
from .i18n import _load_translations, setup_jinja_i18n
from .locale_middleware import LocaleMiddleware
from .routers import (
    feedback,
    filters,
    health,
    labels_admin,
    library,
    migration as migration_router,
    packs,
    pages,
    picks,
    projects,
    saved_searches,
    settings as settings_router,
    sse,
    unity_asset_store,
    updates as updates_router,
)
from .routers.projects import router_pages as projects_pages_router

log = logging.getLogger(__name__)


def _static_dir() -> Path:
    """패키지 내 static 디렉터리 경로."""
    return Path(__file__).parent / "static"


def _templates_dir() -> Path:
    """패키지 내 templates 디렉터리 경로."""
    return Path(__file__).parent / "templates"


def _locale_dir() -> Path:
    """패키지 내 locale 디렉터리 경로."""
    return Path(__file__).parent / "locale"


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI):
    """FastAPI lifespan — cleanup 백그라운드 잡을 시작하고 종료 시 cancel."""
    deps: WebDeps = app.state.deps
    cleanup_task = asyncio.create_task(_cleanup_loop(deps))
    log.info("FastAPI lifespan 진입 — cleanup 잡 시작")
    try:
        yield
    finally:
        cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task
        log.info("FastAPI lifespan 종료 — cleanup 잡 cancel 완료")


async def _cleanup_loop(deps: WebDeps) -> None:
    """5초마다 PendingPickQueue.cleanup_expired 호출."""
    ttl = deps.config.claude_pick_timeout_seconds + 60  # grace
    while True:
        await asyncio.sleep(5)
        try:
            n = deps.pending_picks.cleanup_expired(time.time(), ttl)
            if n > 0:
                log.info("PendingPick cleanup: %d 항목 만료", n)
        except Exception:  # pragma: no cover
            log.exception("cleanup_expired 실패")


def build_app(deps: WebDeps) -> FastAPI:
    """라우터 10개 + 정적 자원 + 템플릿이 wire-up 된 FastAPI 인스턴스 반환."""
    static_dir = _static_dir()
    templates_dir = _templates_dir()
    templates_dir.mkdir(parents=True, exist_ok=True)  # Phase 1B 시점엔 비어 있어도 OK

    app = FastAPI(
        title="AssetCacheMCP",
        version=assetcache.__version__,
        lifespan=_lifespan,
    )
    app.state.deps = deps

    # M8 — boot 시 i18n 카탈로그 1회 로드 + locale 미들웨어 등록
    _load_translations(_locale_dir())
    app.state.config = deps.config  # LocaleMiddleware 가 참조
    app.add_middleware(LocaleMiddleware)

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    templates = Jinja2Templates(directory=str(templates_dir))
    setup_jinja_i18n(templates.env)

    # M7 patch — Unity Asset Store 표의 byte size 를 인간 가독 단위로.
    def _humansize(n: int | None) -> str:
        if n is None:
            return "—"
        f = float(n)
        for unit in ("B", "KB", "MB", "GB"):
            if f < 1024 or unit == "GB":
                return f"{f:.0f} {unit}" if unit == "B" else f"{f:.1f} {unit}"
            f /= 1024
        return f"{f:.1f} GB"

    templates.env.filters["humansize"] = _humansize

    # M7 patch — Unity Asset Store 표의 first_seen_at 등 unix timestamp →
    # "YYYY-MM-DD HH:MM" 표시.
    def _datetime_fmt(ts) -> str:
        if ts is None:
            return "—"
        from datetime import datetime
        try:
            return datetime.fromtimestamp(int(ts)).strftime("%Y-%m-%d %H:%M")
        except (ValueError, OSError):
            return "—"

    templates.env.filters["datetime"] = _datetime_fmt
    app.state.templates = templates

    # 10 라우터 등록 (library 는 /api + /ui 두 라우터, pages 는 HTML 페이지)
    app.include_router(health.router)
    app.include_router(library.router)
    app.include_router(library.router_ui)
    app.include_router(filters.router)
    app.include_router(saved_searches.router)
    app.include_router(feedback.router)
    app.include_router(packs.router)
    app.include_router(packs.router_ui)
    app.include_router(labels_admin.router)
    app.include_router(labels_admin.router_ui)
    app.include_router(picks.router)
    app.include_router(picks.router_ui)  # /ui/pick-card/{rid} HTML fragment
    app.include_router(sse.router)
    app.include_router(pages.router)  # HTML 페이지 라우트 (/, /library)
    app.include_router(unity_asset_store.router)    # M7 Unity Asset Store
    app.include_router(projects.router)             # M7 Phase 5 — 활성 프로젝트 API
    app.include_router(projects_pages_router)       # M7 Phase 6 — 프로젝트 HTML 페이지
    app.include_router(settings_router.router)       # M8 — 설정 페이지
    app.include_router(migration_router.router)      # M10 — 마이그레이션 API
    app.include_router(updates_router.router)        # M10 — PyPI 업데이트 알림 API

    # ── 전역 에러 핸들러 ──────────────────────────────────────────────
    # /api/* 경로는 JSON 응답 유지; 그 외 경로는 친절한 HTML 에러 페이지 반환.

    def _error_response(
        request: Request,
        status_code: int,
        message: str,
    ) -> HTMLResponse:
        """HTMX 여부에 따라 fragment 또는 전체 페이지 에러 템플릿 반환."""
        is_htmx = request.headers.get("HX-Request") == "true"
        tpl_name = "error_fragment.html" if is_htmx else "error.html"
        return templates.TemplateResponse(
            request=request,
            name=tpl_name,
            context={"status_code": status_code, "message": message, "page": "error"},
            status_code=status_code,
        )

    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc: HTTPException) -> HTMLResponse | JSONResponse:
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=404,
                content={"detail": exc.detail if exc.detail else "Not Found"},
            )
        return _error_response(request, 404, "페이지를 찾을 수 없습니다")

    @app.exception_handler(500)
    async def server_error_handler(request: Request, exc: Exception) -> HTMLResponse | JSONResponse:
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal Server Error"},
            )
        return _error_response(request, 500, "서버 내부 오류가 발생했습니다")

    return app
