"""M5 Phase 6A — 사용자 피드백 라우터.

두 엔드포인트:
  POST /api/record-use  — 자산 채택 기록 (asset_detail 모달 [채택] 버튼)
  POST /api/feedback    — 부정/긍정 피드백 기록 ([거부] 버튼)

asset_detail.html 은 hx-vals 로 JSON body 를 전송하므로 두 엔드포인트 모두
htmx-json-enc 확장이 보내는 application/json body 를 Pydantic 으로 파싱한다.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["feedback"])


# ── Pydantic 입력 모델 ─────────────────────────────────────────────────


class RecordUseBody(BaseModel):
    """POST /api/record-use 입력."""

    asset_id: int = Field(..., ge=1)
    project_id: str | None = None


class FeedbackBody(BaseModel):
    """POST /api/feedback 입력."""

    asset_id: int = Field(..., ge=1)
    reason: str = "negative"  # "negative" | "positive" | "irrelevant"
    query_id: int | None = None


# ── POST /api/record-use ───────────────────────────────────────────────


@router.post("/record-use")
def api_record_use(body: RecordUseBody, request: Request) -> dict:
    """자산 채택 기록 — asset_detail 모달 [채택] 버튼 호출.

    project_id 가 없으면 "_web_manual" 프로젝트 슬롯에 기록.
    성공 시 {"ok": true, "usage_id": int} 반환.
    """
    deps = request.app.state.deps
    # 자산 존재 확인
    asset = deps.store.get_asset_by_id(body.asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")

    project_id_str = body.project_id or "_web_manual"
    with deps.store.write_lock:
        project = deps.store.upsert_project(project_id_str)
        usage_id = deps.usage.record_explicit(
            project.id,
            body.asset_id,
            source="manual",
        )
    log.info("record-use: asset=%s project=%s usage_id=%s", body.asset_id, project_id_str, usage_id)
    return {"ok": True, "usage_id": int(usage_id)}


# ── POST /api/feedback ─────────────────────────────────────────────────


@router.post("/feedback")
def api_feedback(body: FeedbackBody, request: Request) -> dict:
    """피드백 기록 — asset_detail 모달 [거부] 버튼 호출.

    Config 의 feedback_*_weight 로 signed weight 를 계산한다.
    project_id 를 query_id 에서 역조회; 없거나 global query 면 skipped=True.
    """
    deps = request.app.state.deps

    # 자산 존재 확인
    asset = deps.store.get_asset_by_id(body.asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")

    weight_map = {
        "negative": deps.config.feedback_negative_weight,
        "positive": deps.config.feedback_positive_weight,
        "irrelevant": deps.config.feedback_irrelevant_weight,
    }
    reason = body.reason if body.reason in weight_map else "negative"
    weight = float(weight_map[reason])

    # query_id 가 없으면 project_id 매핑 불가 → skipped
    if body.query_id is None:
        log.info("feedback skipped (no query_id): asset=%s", body.asset_id)
        return {"ok": True, "skipped": True}

    row = deps.store.conn.execute(
        "SELECT project_id FROM search_queries WHERE id = ?",
        (int(body.query_id),),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"query_id={body.query_id} 없음")
    project_id = int(row[0]) if row[0] is not None else None
    if project_id is None:
        log.info("feedback skipped (global query, no project): asset=%s", body.asset_id)
        return {"ok": True, "skipped": True}

    with deps.store.write_lock:
        deps.store.insert_feedback_record(
            project_id=project_id,
            asset_id=int(body.asset_id),
            query_id=int(body.query_id),
            reason=reason,
            weight=weight,
        )
    log.info(
        "feedback recorded: asset=%s query=%s reason=%s weight=%s",
        body.asset_id, body.query_id, reason, weight,
    )
    return {"ok": True}
