"""M5 Phase 4A — Claude request_user_pick 라우터.

Task 4.1: POST /internal/user-pick — MCP loopback long-poll 진입점.
Task 4.2: POST /api/user-pick/{rid} — 사용자 응답 (채택).
          POST /api/user-pick/{rid}/cancel — 사용자 거부.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..pending import MaxPendingExceeded, UserCancelledError

log = logging.getLogger(__name__)

router = APIRouter(tags=["picks"])  # /internal/user-pick 은 prefix 없음


# ─── Pydantic 모델 ────────────────────────────────────────────────────────────


class InternalPickRequest(BaseModel):
    """MCP server 가 /internal/user-pick 에 POST 하는 요청 바디."""

    candidates: list[int] = Field(min_length=1, max_length=10)
    reason: str | None = None
    project_id: str | None = None
    timeout_seconds: int = Field(default=300, ge=1, le=1800)


class UserPickBody(BaseModel):
    """사용자가 /api/user-pick/{rid} 에 POST 하는 응답 바디."""

    picked_asset_id: int
    user_note: str | None = None


# ─── Task 4.1 — MCP loopback long-poll ───────────────────────────────────────


@router.post("/internal/user-pick")
async def internal_user_pick(req: InternalPickRequest, request: Request) -> dict:
    """MCP server 의 request_user_pick 도구가 호출하는 long-poll 엔드포인트.

    PendingPickQueue 에 등록 후 asyncio.Future 를 대기.
    사용자가 브라우저에서 채택/거부하면 Future 가 해소되고 응답을 반환.

    - 200: 사용자 채택 → {picked_asset_id, user_note, picked_at}
    - 408: timeout → {code: "408_timeout"}
    - 499: 사용자 거부 → {code: "499_user_cancelled"}
    - 503: pending 한도 초과 → {code: "503_too_many_pending"}
    """
    deps = request.app.state.deps
    try:
        pending = deps.pending_picks.register(req.candidates, req.reason, req.project_id)
    except MaxPendingExceeded:
        raise HTTPException(
            status_code=503,
            detail={"code": "503_too_many_pending"},
        )

    # 브라우저에 pick 요청 이벤트 push
    from ..sse_bus import broadcast
    broadcast("user_pick_request", {
        "request_id": pending.request_id,
        "candidates": req.candidates,
        "reason": req.reason,
        "project_id": req.project_id,
    })

    log.info(
        "user-pick 등록: rid=%s candidates=%s reason=%r",
        pending.request_id, req.candidates, req.reason,
    )

    try:
        result = await asyncio.wait_for(pending.future, timeout=req.timeout_seconds)
        # TODO (Phase 4C): _auto_record_asset_use(deps, result, req.project_id)
        # TODO (Phase 4D): _notify_tray_pick_count(deps)
        return result

    except asyncio.TimeoutError:
        deps.pending_picks.expire(pending.request_id)
        log.info("user-pick timeout: rid=%s", pending.request_id)
        raise HTTPException(
            status_code=408,
            detail={"code": "408_timeout"},
        )

    except asyncio.CancelledError:
        # future.cancel() 이 호출된 경우 — sweeper 만료 또는 cancel()
        snap = {p["request_id"]: p for p in deps.pending_picks.snapshot()}
        st = snap.get(pending.request_id, {}).get("status")
        log.info("user-pick CancelledError: rid=%s status=%s", pending.request_id, st)
        if st == "cancelled":
            raise HTTPException(
                status_code=499,
                detail={"code": "499_user_cancelled"},
            )
        raise HTTPException(
            status_code=408,
            detail={"code": "408_timeout"},
        )

    except UserCancelledError:
        log.info("user-pick UserCancelledError: rid=%s", pending.request_id)
        raise HTTPException(
            status_code=499,
            detail={"code": "499_user_cancelled"},
        )


# ─── Task 4.2 — 사용자 응답/거부 ────────────────────────────────────────────


@router.post("/api/user-pick/{rid}")
def api_user_pick(rid: str, body: UserPickBody, request: Request) -> dict:
    """사용자가 브라우저에서 [채택] 버튼 클릭 시 호출.

    - 200 {"ok": true}: 성공적으로 resolve
    - 404: rid 없음
    - 409 {"code": "409_already_resolved"}: 이미 처리된 rid
    """
    deps = request.app.state.deps
    ok = deps.pending_picks.resolve(rid, body.picked_asset_id, body.user_note)
    if not ok:
        snap = {p["request_id"]: p for p in deps.pending_picks.snapshot()}
        if rid not in snap:
            raise HTTPException(status_code=404)
        raise HTTPException(
            status_code=409,
            detail={"code": "409_already_resolved"},
        )

    from ..sse_bus import broadcast
    broadcast("user_pick_resolved", {
        "request_id": rid,
        "picked_asset_id": body.picked_asset_id,
    })
    log.info("user-pick resolved: rid=%s asset_id=%s", rid, body.picked_asset_id)
    return {"ok": True}


@router.post("/api/user-pick/{rid}/cancel")
def api_user_pick_cancel(rid: str, request: Request) -> dict:
    """사용자가 브라우저에서 [✕ 거부] 버튼 클릭 시 호출.

    - 200 {"ok": true}: 성공적으로 cancel
    - 404: rid 없음
    """
    deps = request.app.state.deps
    ok = deps.pending_picks.cancel(rid, "user_cancelled")
    if not ok:
        raise HTTPException(status_code=404)

    from ..sse_bus import broadcast
    broadcast("user_pick_resolved", {
        "request_id": rid,
        "cancelled": True,
    })
    log.info("user-pick cancelled: rid=%s", rid)
    return {"ok": True}
