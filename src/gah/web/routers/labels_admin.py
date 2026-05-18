"""M5 Phase 5B — 라벨 관리 라우터 (Task 5.3).

두 라우터를 노출한다.
  - ``router``    : prefix="/api"  — JSON CRUD (GET/POST/PATCH/DELETE + export/import)
  - ``router_ui`` : prefix="/ui"   — HTML fragment (GET /labels/admin)
"""
from __future__ import annotations

import json
import time
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from gah.core.labels import SEED_LABELS, LabelValidationError
from gah.web import sse_bus

router = APIRouter(prefix="/api", tags=["labels_admin"])
router_ui = APIRouter(prefix="/ui", tags=["labels_admin-ui"])

# 유효한 axis 집합 (SEED_LABELS 가 source of truth)
_VALID_AXES: frozenset[str] = frozenset(SEED_LABELS.keys())


# ── Pydantic 입력 모델 ──────────────────────────────────────────────────


class LabelCreateBody(BaseModel):
    """POST /api/labels 입력 모델."""

    axis: str
    label: str
    description: str | None = None
    source: str = "user"


class LabelUpdateBody(BaseModel):
    """PATCH /api/labels/{label_id} 입력 모델.

    description 과 enabled 중 하나 이상 지정.
    """

    description: str | None = None
    enabled: bool | None = None


# ── 내부 헬퍼 ──────────────────────────────────────────────────────────


def _label_row_to_dict(row: Any) -> dict:
    return {
        "id": row.id,
        "axis": row.axis,
        "label": row.label,
        "description": row.description,
        "source": row.source,
        "enabled": row.enabled,
    }


def _broadcast_signature(registry: Any) -> None:
    """라벨 변경 시 새 signature 를 SSE broadcast."""
    sig = registry.label_catalog_signature()
    sse_bus.broadcast("labels_signature_changed", {"signature": sig})


def _label_row_response(
    request: Request, label_dict: dict, *, status_code: int = 200
) -> Response:
    """단일 라벨 행 HTML fragment 반환 (HTMX outerHTML/beforeend 용)."""
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="_label_row.html",
        context={"label": label_dict},
        status_code=status_code,
    )


# ── GET /api/labels ─────────────────────────────────────────────────────


@router.get("/labels")
def api_get_labels(request: Request, axis: str | None = None) -> dict:
    """전체 라벨 목록(또는 axis 로 필터링) + 현재 signature 반환.

    반환 형태::

        {
          "signature": "16hex",
          "labels": [
            {"id": 1, "axis": "category", "label": "character",
             "description": "...", "source": "seed", "enabled": true},
            ...
          ]
        }
    """
    deps = request.app.state.deps
    rows = deps.registry.list_labels(
        axis=axis, enabled_only=False, with_description=True
    )
    return {
        "signature": deps.registry.label_catalog_signature(),
        "labels": [_label_row_to_dict(r) for r in rows],
    }


# ── POST /api/labels ────────────────────────────────────────────────────


@router.post("/labels")
def api_post_label(body: LabelCreateBody, request: Request) -> Response:
    """새 라벨 추가.

    * axis 가 24 seed axis 에 없으면 400.
    * 라벨 토큰이 regex 불일치면 400 (``LabelValidationError``).
    * 성공 시 201 + ``_label_row.html`` HTML fragment (HTMX beforeend 용).
    * SSE ``labels_signature_changed`` broadcast.
    """
    if body.axis not in _VALID_AXES:
        raise HTTPException(
            status_code=400,
            detail=f"알 수 없는 axis: {body.axis!r}. 유효한 axis: {sorted(_VALID_AXES)}",
        )
    deps = request.app.state.deps
    try:
        label_id, _was_new = deps.registry.add_label(
            body.axis,
            body.label,
            source=body.source,
            description=body.description,
        )
    except LabelValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = deps.store.get_label_by_id(label_id)
    if row is None:  # pragma: no cover — add_label 직후라 발생 불가
        raise HTTPException(status_code=500, detail="라벨 조회 실패")

    _broadcast_signature(deps.registry)
    return _label_row_response(request, _label_row_to_dict(row), status_code=201)


# ── PATCH /api/labels/{label_id} ────────────────────────────────────────


@router.patch("/labels/{label_id}")
def api_patch_label(label_id: int, body: LabelUpdateBody, request: Request) -> Response:
    """라벨 description / enabled 갱신.

    * 존재하지 않는 label_id → 404.
    * 성공 시 ``_label_row.html`` HTML fragment (HTMX outerHTML 용) + SSE broadcast.
    """
    deps = request.app.state.deps
    existing = deps.store.get_label_by_id(label_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="라벨을 찾을 수 없습니다")

    if body.description is None and body.enabled is None:
        raise HTTPException(status_code=400, detail="description 또는 enabled 중 하나 이상 필요")

    deps.store.update_label(
        label_id,
        description=body.description,
        enabled=body.enabled,
    )

    # LabelRegistry 캐시 무효화
    if body.enabled is not None:
        deps.registry.invalidate()

    row = deps.store.get_label_by_id(label_id)
    if row is None:  # pragma: no cover
        raise HTTPException(status_code=500, detail="라벨 갱신 후 조회 실패")

    _broadcast_signature(deps.registry)
    return _label_row_response(request, _label_row_to_dict(row))


# ── DELETE /api/labels/{label_id} ───────────────────────────────────────


@router.delete("/labels/{label_id}")
def api_delete_label(label_id: int, request: Request) -> Response:
    """라벨 삭제.

    * 존재하지 않으면 404.
    * asset_labels 에서 참조 중이면 400 (in-use 보호).
    * 성공 시 200 빈 응답 + SSE broadcast.
      HTMX ``hx-swap="delete"`` 가 클라이언트 측에서 행을 제거한다.
    """
    deps = request.app.state.deps
    existing = deps.store.get_label_by_id(label_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="라벨을 찾을 수 없습니다")

    in_use = deps.store.count_asset_labels_for_label_id(label_id)
    if in_use > 0:
        raise HTTPException(
            status_code=400,
            detail=f"라벨이 {in_use}개 에셋에서 사용 중입니다. 삭제할 수 없습니다.",
        )

    deps.store.delete_label(label_id)
    deps.registry.invalidate()
    _broadcast_signature(deps.registry)
    return Response(status_code=200)


# ── GET /api/labels/export ──────────────────────────────────────────────


@router.get("/labels/export")
def api_export_labels(request: Request) -> Response:
    """전체 라벨 어휘를 JSON 파일로 다운로드.

    반환 형태 (list)::

        [
          {"axis": "category", "label": "character", "description": "...",
           "source": "seed", "enabled": true},
          ...
        ]
    """
    deps = request.app.state.deps
    rows = deps.registry.list_labels(
        axis=None, enabled_only=False, with_description=True
    )
    export_data = [
        {
            "axis": r.axis,
            "label": r.label,
            "description": r.description,
            "source": r.source,
            "enabled": r.enabled,
        }
        for r in rows
    ]
    json_bytes = json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8")
    return Response(
        content=json_bytes,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=labels.json"},
    )


# ── POST /api/labels/import ─────────────────────────────────────────────


@router.post("/labels/import")
async def api_import_labels(
    request: Request,
    file: UploadFile = File(...),
) -> dict:
    """라벨 어휘 bulk import (multipart/form-data 파일 업로드).

    각 항목: {"axis": str, "label": str, "description"?: str, "enabled"?: bool}

    * axis 가 유효하지 않으면 skip (warnings 에 기록).
    * (axis, label) 이 이미 존재하면 description/enabled 갱신 (skipped 카운트).
    * 신규이면 insert (imported 카운트).
    * SSE broadcast.
    """
    try:
        raw = await file.read()
        body = json.loads(raw)
        if not isinstance(body, list):
            raise ValueError("최상위 레벨이 JSON 배열이어야 합니다")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "400_invalid_json", "message": str(exc)},
        ) from exc

    deps = request.app.state.deps
    imported = 0
    skipped = 0
    errors: list[str] = []

    for item in body:
        axis = item.get("axis", "")
        label = item.get("label", "")
        description = item.get("description")
        enabled = item.get("enabled", True)

        if axis not in _VALID_AXES:
            errors.append(f"알 수 없는 axis: {axis!r}")
            skipped += 1
            continue

        try:
            _label_id, was_new = deps.registry.add_label(
                axis, label, description=description, source="import"
            )
            if was_new:
                imported += 1
            else:
                # 이미 존재 — enabled 상태만 추가로 반영
                if not enabled:
                    deps.store.update_label(_label_id, enabled=False)
                skipped += 1
        except LabelValidationError as exc:
            errors.append(str(exc))
            skipped += 1

    if imported > 0 or skipped > 0:
        deps.registry.invalidate()
        _broadcast_signature(deps.registry)

    return {"imported": imported, "skipped": skipped, "errors": errors}


# ── GET /ui/labels/admin ────────────────────────────────────────────────


@router_ui.get("/labels/admin", response_class=HTMLResponse)
def ui_labels_admin(request: Request) -> HTMLResponse:
    """라벨 관리 HTML fragment (HTMX swap 용).

    24 axis 별 라벨 목록 + CRUD UI 를 렌더한다.
    """
    deps = request.app.state.deps
    templates = request.app.state.templates
    axes = sorted(SEED_LABELS.keys())
    labels_by_axis = {
        axis: deps.registry.list_labels(
            axis=axis, enabled_only=False, with_description=True
        )
        for axis in axes
    }
    return templates.TemplateResponse(
        request=request,
        name="_labels_admin_grid.html",
        context={
            "axes": axes,
            "labels_by_axis": labels_by_axis,
            "signature": deps.registry.label_catalog_signature(),
        },
    )
