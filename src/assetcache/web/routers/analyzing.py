"""/analyzing — 분석 진행 dashboard (M11.1 task 5.2 + 5.3).

GET /analyzing        → page shell (extends base.html) + initial render
GET /analyzing/partial → HTMX 5초 polling target (sections A+B)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/analyzing", tags=["analyzing"])


def _build_view_model(deps) -> dict:
    """WebDeps 에서 /analyzing 뷰 모델 구성.

    deps.queue 가 None 이면 (MCP-only 모드 / 테스트) 빈 snapshot 반환.
    """
    aq = deps.queue  # AnalysisQueue | None

    if aq is None:
        return {
            "summary": {
                "interactive_count": 0,
                "batch_image": 0,
                "batch_audio": 0,
                "batch_embed": 0,
                "eta_seconds": None,
            },
            "interactive": {
                "in_flight_path": None,
                "queue": [],
            },
        }

    progress = aq.progress()
    # pending_by_modality 는 DB + queue size 합산
    batch_image = aq.pending_by_modality("chat_image")
    batch_audio = aq.pending_by_modality("chat_audio")
    batch_embed = aq.pending_by_modality("text_embed")
    interactive_assets = aq.snapshot_queue(limit=50)

    return {
        "summary": {
            "interactive_count": progress.pending,
            "batch_image": batch_image,
            "batch_audio": batch_audio,
            "batch_embed": batch_embed,
            "eta_seconds": progress.eta_seconds,
        },
        "interactive": {
            "in_flight_path": progress.in_flight_path,
            "queue": interactive_assets,
        },
    }


@router.get("", response_class=HTMLResponse)
async def get_dashboard(request: Request) -> HTMLResponse:
    """분석 진행 대시보드 페이지 (page shell)."""
    deps = request.app.state.deps
    templates = request.app.state.templates
    vm = _build_view_model(deps)
    return templates.TemplateResponse(
        request=request,
        name="analyzing/index.html",
        context={"page": "analyzing", **vm},
    )


@router.get("/partial", response_class=HTMLResponse)
async def get_partial(request: Request) -> HTMLResponse:
    """HTMX polling target — sections A+B (5초마다 교체)."""
    deps = request.app.state.deps
    templates = request.app.state.templates
    vm = _build_view_model(deps)
    return templates.TemplateResponse(
        request=request,
        name="analyzing/_partial.html",
        context={"page": "analyzing", **vm},
    )
