"""M5 Phase 4A/4B — Claude request_user_pick 라우터.

Task 4.1: POST /internal/user-pick — MCP loopback long-poll 진입점.
Task 4.2: POST /api/user-pick/{rid} — 사용자 응답 (채택).
          POST /api/user-pick/{rid}/cancel — 사용자 거부.
Task 4.4: GET  /ui/pick-card/{rid}  — _pick_card.html fragment 렌더.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..deps import WebDeps
from ..pending import MaxPendingExceeded, UserCancelledError
from ..sse_bus import broadcast

log = logging.getLogger(__name__)

router = APIRouter(tags=["picks"])  # /internal/user-pick 은 prefix 없음

# /ui/* prefix 를 쓰는 UI fragment 라우터
router_ui = APIRouter(prefix="/ui", tags=["picks-ui"])


# ─── 트레이 브리지 헬퍼 ──────────────────────────────────────────────────────


def _notify_tray_pick_count(deps: WebDeps) -> None:
    """현재 pending 카운트를 tray bridge 로 emit. bridge 가 None 이면 no-op.

    uvicorn worker thread 에서 호출되어도 TrayBridge 의 AutoConnection 이
    main thread 로 마샬링하므로 thread-safe 하다.

    snapshot 은 모든 status (pending/resolved/expired/cancelled) 항목을 반환
    하므로 status="pending" 만 카운트해야 채택/거부/만료 후 0 으로 감소한다.
    """
    if deps.tray_bridge is None:
        return
    count = sum(
        1 for p in deps.pending_picks.snapshot() if p["status"] == "pending"
    )
    deps.tray_bridge.pickCountChanged.emit(count)


# ─── Pydantic 모델 ────────────────────────────────────────────────────────────


class InternalPickRequest(BaseModel):
    """MCP server 가 /internal/user-pick 에 POST 하는 요청 바디."""

    candidates: list[int] = Field(min_length=1, max_length=10)
    reason: str | None = None
    project_id: str | None = None
    timeout_seconds: int = Field(default=300, ge=10, le=1800)


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

    # 등록 직후 카운트 변경 알림
    _notify_tray_pick_count(deps)

    # 브라우저에 pick 요청 이벤트 push
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

    finally:
        # 결과 경로(200/408/499) 모두에서 카운트 재알림
        _notify_tray_pick_count(deps)


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

    broadcast("user_pick_resolved", {
        "request_id": rid,
        "picked_asset_id": body.picked_asset_id,
    })
    _notify_tray_pick_count(deps)
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

    broadcast("user_pick_resolved", {
        "request_id": rid,
        "cancelled": True,
    })
    _notify_tray_pick_count(deps)
    log.info("user-pick cancelled: rid=%s", rid)
    return {"ok": True}


# ─── Task 4.4 — /ui/pick-card/{rid} HTML fragment ────────────────────────────


@router_ui.get("/pick-card/{rid}")
def ui_pick_card(rid: str, request: Request):
    """pending pick 의 후보 에셋을 _pick_card.html fragment 로 렌더.

    - 200: pick-card-group HTML
    - 404: rid 없음
    """
    deps = request.app.state.deps
    snap = {p["request_id"]: p for p in deps.pending_picks.snapshot()}
    if rid not in snap:
        raise HTTPException(status_code=404)

    pending = snap[rid]

    # 후보 에셋 메타 수집 — Store.get_asset_by_id + Pack 이름 join
    candidates = []
    for asset_id in pending["candidates"]:
        asset_row = deps.store.get_asset_by_id(asset_id)
        if asset_row is None:
            log.warning("pick-card: asset_id=%s 없음 (rid=%s)", asset_id, rid)
            continue
        pack_row = deps.store.get_pack_by_id(asset_row.pack_id)
        pack_name = pack_row.display_name or pack_row.name if pack_row else ""

        # sprite 크기 — sprite_meta 에서 조회
        width: int | None = None
        height: int | None = None
        if asset_row.kind == "sprite":
            sm = deps.store.conn.execute(
                "SELECT width, height FROM sprite_meta WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
            if sm:
                width, height = sm[0], sm[1]

        size_kb: int | None = (
            asset_row.file_size // 1024 if asset_row.file_size else None
        )

        candidates.append({
            "asset_id": asset_id,
            "name": Path(asset_row.path).stem,
            "kind": asset_row.kind,
            "pack_name": pack_name,
            "width": width,
            "height": height,
            "size_kb": size_kb,
        })

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="_pick_card.html",
        context={
            "rid": rid,
            "reason": pending["reason"],
            "candidates": candidates,
        },
    )
