"""M7 Phase 5.1 — 활성 프로젝트 API + SSE broadcast + 채택 endpoint.

4 endpoints + SSE stream:
  GET  /api/active-project          현재 활성 → {active: {id, external_id, display_name}|null}
  PUT  /api/active-project          body {project_id: int|null} → config 갱신 + SSE broadcast
  POST /api/projects                body {external_id, display_name?} → upsert + 응답 {id, ...}
  POST /api/assets/{asset_id}/adopt body {context?, query_id?} → record_asset_use(source="user_web")
  GET  /api/active-project/stream   SSE long-poll, event: active_project_changed
"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["projects"])

# SSE 구독자 큐 (single-process, M5 의 pending-pick 패턴 따라)
_subscribers: list[asyncio.Queue] = []


def _broadcast(event: dict) -> None:
    """모든 구독자에게 이벤트 push."""
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass


# ── GET /api/active-project ──────────────────────────────────────────────────


@router.get("/active-project")
async def get_active(request: Request):
    """현재 활성 프로젝트 반환. 없으면 {active: null}."""
    deps = request.app.state.deps
    pid = deps.config.active_project_id
    if pid is None:
        return {"active": None}
    p = deps.store.get_project_by_id(pid)
    if p is None:
        # config 에 저장됐지만 DB 에 없으면 null 처리
        return {"active": None}
    return {
        "active": {
            "id": p.id,
            "external_id": p.external_id,
            "display_name": p.display_name,
        }
    }


# ── PUT /api/active-project ──────────────────────────────────────────────────


@router.put("/active-project")
async def put_active(request: Request):
    """활성 프로젝트 설정/해제.

    body: {project_id: int|null}
    - project_id 가 null 이면 active_project_id = None 으로 해제.
    - project_id 가 int 이면 DB 에서 존재 확인 후 설정.
    """
    deps = request.app.state.deps
    body = await request.json()
    pid = body.get("project_id")

    if pid is not None and not isinstance(pid, int):
        raise HTTPException(400, "project_id must be int or null")

    # 존재 검증
    if pid is not None and deps.store.get_project_by_id(pid) is None:
        raise HTTPException(404, "project not found")

    # Config 갱신 (mutable dataclass)
    deps.config.active_project_id = pid

    # config 영속 저장
    try:
        from gah.config import save_config
        save_config(deps.config, deps.paths.config_path)
    except Exception as e:
        log.warning("active_project_id config 저장 실패: %s", e)

    # SSE broadcast
    _broadcast({"event": "active_project_changed", "project_id": pid})

    log.info("active_project_id 변경: %s", pid)
    return {"ok": True}


# ── POST /api/projects ───────────────────────────────────────────────────────


@router.post("/projects")
async def post_project(request: Request):
    """프로젝트 upsert (external_id 기준). 이미 있으면 id 반환."""
    deps = request.app.state.deps
    body = await request.json()
    ext_id = body.get("external_id")
    display_name = body.get("display_name")

    if not ext_id:
        raise HTTPException(400, "external_id required")

    pid = deps.store.upsert_project_id(external_id=ext_id, display_name=display_name)
    return {
        "id": pid,
        "external_id": ext_id,
        "display_name": display_name,
    }


# ── GET /api/projects ────────────────────────────────────────────────────────


@router.get("/projects")
async def list_projects(request: Request):
    """프로젝트 목록 반환 (헤더 드롭다운용)."""
    deps = request.app.state.deps
    summaries = deps.store.list_projects_with_summary()
    items = [
        {
            "id": s.id,
            "external_id": s.external_id,
            "display_name": s.display_name,
            "asset_count": s.asset_count,
        }
        for s in summaries
    ]
    return {"items": items}


# ── POST /api/assets/{asset_id}/adopt ────────────────────────────────────────


@router.post("/assets/{asset_id}/adopt")
async def post_adopt(asset_id: int, request: Request):
    """활성 프로젝트에 자산 채택 기록.

    활성 프로젝트 없으면 400.
    source="user_web" 으로 기록.
    """
    deps = request.app.state.deps
    pid = deps.config.active_project_id
    if pid is None:
        raise HTTPException(400, "no_active_project")

    asset = deps.store.get_asset_by_id(asset_id)
    if asset is None:
        raise HTTPException(404, "asset not found")

    body_dict: dict = {}
    try:
        body_dict = await request.json()
    except Exception:
        pass

    deps.store.record_asset_use(
        project_id=pid,
        asset_id=asset_id,
        pack_id=asset.pack_id,
        source="user_web",
        context=body_dict.get("context"),
        used_at=int(time.time()),
    )
    log.info("adopt: asset=%s project=%s source=user_web", asset_id, pid)
    return {"ok": True}


# ── GET /api/active-project/stream ───────────────────────────────────────────


@router.get("/active-project/stream")
async def active_stream(request: Request):
    """SSE long-poll — active_project_changed 이벤트 스트림."""
    q: asyncio.Queue = asyncio.Queue(maxsize=10)
    _subscribers.append(q)

    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield {
                        "event": event["event"],
                        "data": json.dumps(event),
                    }
                except asyncio.TimeoutError:
                    # keepalive comment
                    yield {"comment": "keepalive"}
        finally:
            if q in _subscribers:
                _subscribers.remove(q)

    return EventSourceResponse(gen())
