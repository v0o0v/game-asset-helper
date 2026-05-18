"""M7 — /unity-asset-store 페이지 + /api/unity-packages 그룹."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from gah.core.unity_import.cache_paths import detect_cache_path
from gah.core.unity_import.importer import UnityImporter
from gah.core.unity_import.scanner import UnityAssetStoreScanner
from gah.core.unity_import.unitypackage import parse_pathnames

log = logging.getLogger(__name__)

router = APIRouter()


# ── GET /unity-asset-store ─────────────────────────────────────────────


_SORT_FIELDS = {
    "publisher", "category", "asset_name",
    "package_size", "import_state", "preview_asset_count",
    "first_seen_at",
}


@router.get("/unity-asset-store", response_class=HTMLResponse)
async def unity_page(request: Request) -> HTMLResponse:
    """Unity Asset Store 발견 패키지 표 페이지."""
    deps = request.app.state.deps
    templates = request.app.state.templates

    cache = detect_cache_path(deps.config)
    items = list(deps.store.list_unity_imports()) if cache else []

    # 정렬 (M7 patch) — query param ?sort=...&order=asc|desc
    sort_field = request.query_params.get("sort", "asset_name")
    if sort_field not in _SORT_FIELDS:
        sort_field = "asset_name"
    sort_order = request.query_params.get("order", "asc")
    if sort_order not in ("asc", "desc"):
        sort_order = "asc"

    def _key(it):
        v = getattr(it, sort_field, None)
        if isinstance(v, (int, float)):
            return (0, v)
        return (1 if v is None else 0, (v or "").lower() if isinstance(v, str) else "")

    items.sort(key=_key, reverse=(sort_order == "desc"))

    focus = request.query_params.get("focus")
    return templates.TemplateResponse(
        request=request,
        name="unity_asset_store.html",
        context={
            "items": items,
            "cache_path": str(cache) if cache else None,
            "focus_id": int(focus) if focus and focus.isdigit() else None,
            "page": "unity_asset_store",
            "sort_field": sort_field,
            "sort_order": sort_order,
        },
    )


# ── POST /api/unity-packages/scan ─────────────────────────────────────

# NOTE: scan 은 가변 body 없이도 동작하므로 Optional body 로 허용
from typing import Any


@router.post("/api/unity-packages/scan")
async def api_scan(request: Request) -> dict[str, Any]:
    """캐시 디렉터리를 스캔해 unity_imports 를 갱신한다."""
    deps = request.app.state.deps

    # body 파싱 (없으면 빈 dict)
    try:
        body: dict[str, Any] = await request.json()
    except Exception:
        body = {}

    cache = detect_cache_path(deps.config)
    if cache is None:
        raise HTTPException(status_code=503, detail="cache_not_found")

    scanner = UnityAssetStoreScanner(store=deps.store)
    result = scanner.run_once(
        cache_path=cache,
        force=bool(body.get("force", False)),
    )
    return {
        "scanned": result.scanned,
        "new": result.new,
        "updated": result.updated,
        "unchanged": result.unchanged,
        "removed": result.removed,
    }


# ── POST /api/unity-packages/{uid}/import ────────────────────────────


@router.post("/api/unity-packages/{uid}/import")
async def api_import(uid: int, request: Request) -> dict[str, Any]:
    """패키지를 GAH 라이브러리로 임포트한다."""
    deps = request.app.state.deps
    row = deps.store.get_unity_import_by_id(uid)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")

    deps.store.update_unity_state(uid, "import_pending")
    library_root = deps.library_root or deps.paths.library_dir
    importer = UnityImporter(store=deps.store, library_root=library_root)
    result = importer.import_package(uid)
    return {
        "state": result.state,
        "pack_name": result.pack_name,
        "asset_count": result.asset_count,
        "error": result.error,
    }


# ── POST /api/unity-packages/{uid}/skip ──────────────────────────────


@router.post("/api/unity-packages/{uid}/skip")
async def api_skip(uid: int, request: Request) -> dict[str, Any]:
    """패키지를 건너뜀(skipped) 상태로 전환한다."""
    deps = request.app.state.deps
    row = deps.store.get_unity_import_by_id(uid)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    deps.store.update_unity_state(uid, "skipped")
    return {"ok": True}


# ── POST /api/unity-packages/{uid}/restore ────────────────────────────


@router.post("/api/unity-packages/{uid}/restore")
async def api_restore(uid: int, request: Request) -> dict[str, Any]:
    """건너뜬 패키지를 다시 discovered 후보로 되돌린다."""
    deps = request.app.state.deps
    row = deps.store.get_unity_import_by_id(uid)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    deps.store.update_unity_state(uid, "discovered")
    return {"ok": True}
