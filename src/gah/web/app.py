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

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import gah
from .deps import WebDeps
from .i18n import setup_jinja_i18n
from .routers import (
    feedback,
    filters,
    health,
    labels_admin,
    library,
    packs,
    pages,
    picks,
    saved_searches,
    sse,
)

log = logging.getLogger(__name__)


def _static_dir() -> Path:
    """패키지 내 static 디렉터리 경로."""
    return Path(__file__).parent / "static"


def _templates_dir() -> Path:
    """패키지 내 templates 디렉터리 경로."""
    return Path(__file__).parent / "templates"


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
        title="Game Asset Helper",
        version=gah.__version__,
        lifespan=_lifespan,
    )
    app.state.deps = deps
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    templates = Jinja2Templates(directory=str(templates_dir))
    setup_jinja_i18n(templates.env)
    app.state.templates = templates

    # 10 라우터 등록 (library 는 /api + /ui 두 라우터, pages 는 HTML 페이지)
    app.include_router(health.router)
    app.include_router(library.router)
    app.include_router(library.router_ui)
    app.include_router(filters.router)
    app.include_router(saved_searches.router)
    app.include_router(feedback.router)
    app.include_router(packs.router)
    app.include_router(labels_admin.router)
    app.include_router(picks.router)
    app.include_router(picks.router_ui)  # /ui/pick-card/{rid} HTML fragment
    app.include_router(sse.router)
    app.include_router(pages.router)  # HTML 페이지 라우트 (/, /library)

    return app
