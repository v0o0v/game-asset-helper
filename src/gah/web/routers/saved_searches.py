"""M5 — 저장된 검색 라우터 (Phase 3D-2 가 실 구현)."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["saved_searches"])


class SaveBody(BaseModel):
    name: str
    query: dict  # 검색 바 + 필터 + 가중치 등 query 상태
    project_id: int | None = None


@router.get("/saved-searches")
def list_saved(request: Request, project_id: int | None = None) -> list[dict]:
    """저장된 검색 목록 반환 (last_used_at DESC, created_at DESC)."""
    deps = request.app.state.deps
    rows = deps.store.list_saved_searches(project_id=project_id)
    return [
        {
            "id": r.id,
            "name": r.name,
            "query": json.loads(r.query_json),
            "project_id": r.project_id,
            "created_at": r.created_at,
            "last_used_at": r.last_used_at,
        }
        for r in rows
    ]


@router.post("/saved-searches")
def save_saved(body: SaveBody, request: Request) -> dict:
    """저장된 검색 upsert (동일 이름 재저장 시 query 교체)."""
    deps = request.app.state.deps
    ss_id = deps.store.upsert_saved_search(
        project_id=body.project_id,
        name=body.name,
        query_json=json.dumps(body.query, ensure_ascii=False),
    )
    return {"id": ss_id, "name": body.name}


@router.delete("/saved-searches/{name}")
def delete_saved(name: str, request: Request, project_id: int | None = None) -> dict:
    """저장된 검색 삭제."""
    deps = request.app.state.deps
    ok = deps.store.delete_saved_search(project_id=project_id, name=name)
    if not ok:
        raise HTTPException(status_code=404, detail="not found")
    return {"deleted": name}


@router.post("/saved-searches/run/{ss_id}")
def run_saved(ss_id: int, request: Request) -> dict:
    """저장된 검색 실행 — last_used_at 갱신 후 query dict 반환."""
    deps = request.app.state.deps
    # last_used_at 갱신
    deps.store.update_saved_search_last_used(ss_id)
    # get_saved_search_by_id 헬퍼로 조회 (project_id 무관하게 id 로 직접 탐색)
    ss = deps.store.get_saved_search_by_id(ss_id)
    if ss is None:
        raise HTTPException(status_code=404, detail="not found")
    return {
        "id": ss.id,
        "name": ss.name,
        "query": json.loads(ss.query_json),
    }
