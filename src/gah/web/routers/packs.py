"""M5 Phase 5A — 팩 관리 라우터.

두 라우터를 노출한다.
  - ``router``    : prefix="/api" — JSON 응답 (GET /packs, PATCH /packs/{id})
  - ``router_ui`` : prefix="/ui"  — HTML fragment (GET /packs)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api", tags=["packs"])
router_ui = APIRouter(prefix="/ui", tags=["packs-ui"])


# ── Pydantic 입력 모델 ─────────────────────────────────────────────────


class PackUpdateBody(BaseModel):
    """PATCH /api/packs/{pack_id} 입력 모델."""

    enabled: bool


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────


def _list_packs_dicts(store: Any, *, include_disabled: bool = True) -> list[dict]:
    """Store.list_packs_with_stats 로 팩 목록 + 통계 반환."""
    return store.list_packs_with_stats(include_disabled=include_disabled)


def _pack_card_response(
    templates: Any,
    request: Request,
    pack_dict: dict,
) -> HTMLResponse:
    """단일 팩 카드 HTML fragment 반환 (PATCH 응답 + /ui/packs 루프용)."""
    return templates.TemplateResponse(
        request=request,
        name="_pack_card.html",
        context={"pack": pack_dict},
    )


# ── GET /api/packs ─────────────────────────────────────────────────────


@router.get("/packs")
def api_packs(request: Request) -> dict[str, Any]:
    """팩 목록 + 에셋 통계 JSON 반환.

    반환 형태::

        {
          "packs": [
            {
              "id": 1, "name": "pack_a", "display_name": "Pack A",
              "vendor": "kenney", "license": "CC0", "enabled": true,
              "asset_count": 3,
              "kind_counts": {"sprite": 2, "sound": 1},
            },
            ...
          ]
        }
    """
    deps = request.app.state.deps
    packs = _list_packs_dicts(deps.store)
    return {"packs": packs}


# ── PATCH /api/packs/{pack_id} ─────────────────────────────────────────


@router.patch("/packs/{pack_id}", response_class=HTMLResponse)
def patch_pack(pack_id: int, body: PackUpdateBody, request: Request) -> HTMLResponse:
    """팩 활성/비활성 토글. 성공 시 업데이트된 팩 카드 HTML fragment 반환.

    hx-target="closest .pack-card" hx-swap="outerHTML" 와 함께 사용.
    존재하지 않는 pack_id → 404.
    """
    deps = request.app.state.deps
    pack = deps.store.get_pack_by_id(pack_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="pack not found")

    deps.store.set_pack_enabled(pack_id, body.enabled)

    # 업데이트 후 최신 통계 포함 팩 dict 조회
    all_packs = _list_packs_dicts(deps.store)
    updated_pack = next((p for p in all_packs if p["id"] == pack_id), None)
    if updated_pack is None:
        raise HTTPException(status_code=404, detail="pack not found after update")

    templates = request.app.state.templates
    return _pack_card_response(templates, request, updated_pack)


# ── GET /ui/packs ──────────────────────────────────────────────────────


@router_ui.get("/packs", response_class=HTMLResponse)
def ui_packs(request: Request) -> HTMLResponse:
    """팩 그리드 HTML fragment (hx-get="/ui/packs" hx-trigger="load" 용).

    packs.html 루프 내에서 hx-swap=outerHTML 에 사용하거나
    /packs 페이지에서 직접 렌더할 때 참조.
    """
    deps = request.app.state.deps
    packs = _list_packs_dicts(deps.store)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="_packs_grid.html",
        context={"packs": packs},
    )
