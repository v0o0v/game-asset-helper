"""/analyzing — 분석 진행 dashboard (M11.1 task 5.2 + 5.3).

GET  /analyzing                      → page shell (extends base.html) + initial render
GET  /analyzing/partial              → HTMX 5초 polling target (sections A+B+C+D)
POST /analyzing/batch/<id>/cancel    → BatchManager.cancel + 303 redirect
"""
from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/analyzing", tags=["analyzing"])


def _build_view_model(deps) -> dict:
    """WebDeps 에서 /analyzing 뷰 모델 구성.

    deps.queue 가 None 이면 (MCP-only 모드 / 테스트) 빈 snapshot 반환.
    deps.store 가 None 이면 batch_jobs / recent_failures 빈 목록 반환.
    """
    aq = deps.queue  # AnalysisQueue | None

    if aq is None:
        summary = {
            "interactive_count": 0,
            "batch_image": 0,
            "batch_spritesheet": 0,
            "batch_audio": 0,
            "batch_embed": 0,
            "eta_seconds": None,
        }
        interactive = {
            "in_flight_path": None,
            "queue": [],
        }
    else:
        progress = aq.progress()
        # pending_by_modality 는 DB + queue size 합산
        batch_image = aq.pending_by_modality("chat_image")
        batch_spritesheet = aq.pending_by_modality("chat_spritesheet")
        batch_audio = aq.pending_by_modality("chat_audio")
        batch_embed = aq.pending_by_modality("text_embed")
        interactive_assets = aq.snapshot_queue(limit=50)

        summary = {
            "interactive_count": progress.pending,
            "batch_image": batch_image,
            "batch_spritesheet": batch_spritesheet,
            "batch_audio": batch_audio,
            "batch_embed": batch_embed,
            "eta_seconds": progress.eta_seconds,
        }
        interactive = {
            "in_flight_path": progress.in_flight_path,
            "queue": interactive_assets,
        }

    # Section C — 진행 중 batch jobs (submitted / running)
    # Section D — 최근 실패 에셋 (analysis_state='failed')
    if deps.store is not None:
        raw_jobs = deps.store.list_active_batch_jobs()
        recent_failures = deps.store.list_recent_failures(limit=20)
    else:
        raw_jobs = []
        recent_failures = []

    now_ts = int(time.time())
    batch_jobs = [
        {
            "id": job.id,
            "modality": job.modality,
            "backend": job.backend,
            "asset_count": job.asset_count,
            "state": job.state,
            "submitted_minutes_ago": max(0, (now_ts - job.submitted_at) // 60),
        }
        for job in raw_jobs
    ]

    return {
        "summary": summary,
        "interactive": interactive,
        "batch_jobs": batch_jobs,
        "recent_failures": recent_failures,
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
    """HTMX polling target — sections A+B+C+D (5초마다 교체)."""
    deps = request.app.state.deps
    templates = request.app.state.templates
    vm = _build_view_model(deps)
    return templates.TemplateResponse(
        request=request,
        name="analyzing/_partial.html",
        context={"page": "analyzing", **vm},
    )


@router.post("/batch/{batch_job_id}/cancel")
async def cancel_batch_job(request: Request, batch_job_id: int):
    """진행 중 batch job 취소 — BatchManager.cancel 호출 후 303 redirect."""
    deps = request.app.state.deps
    if deps.batch_manager is None:
        raise HTTPException(status_code=404, detail="batch manager not configured")
    deps.batch_manager.cancel(batch_job_id)
    return RedirectResponse("/analyzing", status_code=303)
