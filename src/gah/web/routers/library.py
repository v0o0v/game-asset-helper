"""M5 — 라이브러리 페이지 라우터 (검색 + 결과 fragment + 썸네일).

두 라우터를 노출한다.
  - ``router``    : prefix="/api" — JSON 응답 (/search, /thumbnail/{id})
  - ``router_ui`` : prefix="/ui"  — HTML fragment (/search-results)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["library"])
router_ui = APIRouter(prefix="/ui", tags=["library-ui"])


# ── Pydantic 입력 모델 ─────────────────────────────────────────────────


class SearchBody(BaseModel):
    """POST /api/search 및 /ui/search-results 의 공통 입력 모델."""

    query: str = ""
    label_query: str | None = None
    project_id: str | None = None
    # pack_ids: SearchRequest 에 직접 매핑 필드 없음 — exclude_pack_ids 와 구별.
    # v1 에서는 pack_ids 를 무시하고 향후 필터 확장 시 활용.
    pack_ids: list[int] | None = None
    kind: str | None = None  # "sprite" | "sound" | None
    diversity: Literal["none", "mmr", "round_robin"] = "none"
    diversity_lambda: float | None = None
    count: int = Field(default=20, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    sort: Literal[
        "score", "added_desc", "added_asc",
        "name_asc", "name_desc",
        "size_desc", "size_asc",
    ] = "score"
    # B 탭 칩 선택 + 매칭 모드 (Phase 3 에서 채움)
    labels: list[int] | None = None
    match_mode: Literal["all", "any", "none"] = "all"


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────


def _row_to_dict(row: Any) -> dict[str, Any]:
    """ResultRow dataclass → JSON-직렬화 가능 dict.

    ResultRow 필드: asset_id, pack_id, pack_name, path, score,
    score_breakdown, matched_labels, why, meta.
    name 은 path 의 basename 에서 추출.
    width / height / size_kb 는 meta 에 없으면 None.
    """
    from dataclasses import asdict, is_dataclass

    if is_dataclass(row) and not isinstance(row, type):
        d = asdict(row)
    elif hasattr(row, "model_dump"):
        d = row.model_dump()
    elif hasattr(row, "_asdict"):
        d = row._asdict()
    else:
        d = dict(row.__dict__)

    # name 파생 — path 의 stem
    if "name" not in d or not d.get("name"):
        raw_path = d.get("path", "")
        d["name"] = Path(raw_path).stem if raw_path else ""

    # sprite_meta 에서 width/height 추출 (meta dict 에 있을 수 있음)
    meta = d.get("meta") or {}
    d.setdefault("width", meta.get("width"))
    d.setdefault("height", meta.get("height"))
    d.setdefault("size_kb", meta.get("size_kb"))

    # matched_labels 는 list[dict] 이지만 asdict 이후 그대로 유지됨
    return d


def _apply_sort(rows: list[dict[str, Any]], sort: str) -> list[dict[str, Any]]:
    """sort 옵션에 따라 새 리스트 반환 (in-place 아님)."""
    if sort == "score":
        return rows  # HybridSearcher 가 이미 score DESC 정렬
    key_map = {
        "added_desc": ("added_at", True),
        "added_asc": ("added_at", False),
        "name_asc": ("name", False),
        "name_desc": ("name", True),
        "size_desc": ("size_kb", True),
        "size_asc": ("size_kb", False),
    }
    if sort not in key_map:
        return rows
    key, reverse = key_map[sort]
    try:
        return sorted(rows, key=lambda r: r.get(key) or 0, reverse=reverse)
    except TypeError:
        return rows  # 필드 타입 불일치 시 정렬 안 함


def _asset_row_to_dict(row: Any) -> dict[str, Any]:
    """AssetRow dataclass → JSON-직렬화 가능 dict (디폴트 상태 폴백용).

    ResultRow 와 달리 score / matched_labels / why / score_breakdown 가 없으므로
    기본값으로 채운다.
    """
    from pathlib import Path as _Path

    d: dict[str, Any] = {
        "asset_id": row.id,
        "pack_id": row.pack_id,
        "pack_name": "",       # 디폴트 상태에서는 pack join 없이 빠르게 처리
        "path": row.path,
        "name": _Path(row.path).stem,
        "score": 0.0,
        "score_breakdown": {},
        "matched_labels": [],
        "why": "",
        "meta": {},
        "width": None,
        "height": None,
        "size_kb": row.file_size // 1024 if row.file_size else None,
        "added_at": row.added_at,
        "kind": row.kind,
    }
    return d


def _do_search(deps: Any, body: SearchBody) -> dict[str, Any]:
    """HybridSearcher 호출 핵심 로직 — /api/search 와 /ui/search-results 가 공유.

    SearchRequest 에 offset 필드가 없으므로 fetch_count = count + offset 으로
    더 많이 받아온 뒤 Python 에서 슬라이싱한다.

    빈 검색 (query 비어 + label_query 없음 + 기타 필터 없음) 인 경우에는
    HybridSearcher 를 거치지 않고 store.list_assets() 폴백으로 라이브러리
    전체를 추가일↓ 순으로 반환한다. sort=score 는 이 경우 added_desc 로 전환.
    """
    from ...core.search import SearchRequest

    # ── 빈 검색 판정 ────────────────────────────────────────────────────
    is_empty_search = (
        not body.query
        and not body.label_query
        and not (body.labels or [])
        and not (body.pack_ids or [])
        and not body.kind
    )
    if is_empty_search:
        return _list_all_assets(deps, body)

    # offset 만큼 앞 결과를 버릴 수 있도록 충분히 가져온다.
    fetch_count = body.count + body.offset

    sr = SearchRequest(
        query=body.query,
        label_query=body.label_query,
        project_id=body.project_id,
        kind=body.kind,
        diversity=body.diversity,
        diversity_lambda=body.diversity_lambda,
        count=fetch_count,
        # labels_all/any/none — match_mode 에 따라 분배 (Phase 3 활용)
        # body.labels 는 label id 리스트이나 SearchRequest 는 LabelFilter 리스트.
        # v1 에서는 label_query 로 처리하고 labels 는 패스.
    )
    response = deps.search.hybrid(sr)

    all_rows = [_row_to_dict(r) for r in response.results]
    # fetch_count 개 중 offset 이후만 count 개 취함
    sliced = all_rows[body.offset: body.offset + body.count]
    sliced = _apply_sort(sliced, body.sort)

    total = len(all_rows)
    next_offset: int | None = (
        body.offset + body.count
        if len(all_rows) > body.offset + body.count
        else None
    )
    return {
        "query_id": response.query_id,
        "total": total,
        "rows": sliced,
        "next_offset": next_offset,
    }


def _list_all_assets(deps: Any, body: SearchBody) -> dict[str, Any]:
    """빈 검색 폴백 — store.list_assets() 로 전체 에셋을 가져와 정렬 후 페이지 분할.

    sort=score 는 의미 없으므로 added_desc 로 전환한다.
    """
    effective_sort = body.sort if body.sort != "score" else "added_desc"

    # 전체 에셋을 넉넉하게 가져온다 (큰 라이브러리 대비 limit 높게).
    # store.list_assets 는 ORDER BY path 고정이므로 Python 에서 재정렬.
    try:
        all_assets = deps.store.list_assets(limit=10_000, offset=0)
    except Exception:
        # store API 가 없거나 실패하면 빈 결과 반환
        return {"query_id": None, "total": 0, "rows": [], "next_offset": None}

    all_rows = [_asset_row_to_dict(a) for a in all_assets]
    all_rows = _apply_sort(all_rows, effective_sort)

    total = len(all_rows)
    sliced = all_rows[body.offset: body.offset + body.count]
    next_offset: int | None = (
        body.offset + body.count
        if total > body.offset + body.count
        else None
    )
    return {
        "query_id": None,
        "total": total,
        "rows": sliced,
        "next_offset": next_offset,
    }


# ── /api/search POST ───────────────────────────────────────────────────


@router.post("/search")
def api_search(body: SearchBody, request: Request) -> dict[str, Any]:
    """HybridSearcher 호출 → JSON 결과.

    반환 형태::

        {
          "query_id": int,
          "total": int,
          "rows": [{"asset_id": ..., "name": ..., "score": ..., ...}],
          "next_offset": int | null,
        }
    """
    deps = request.app.state.deps
    return _do_search(deps, body)


# ── /ui/search-results POST (HTML fragment) ────────────────────────────


@router_ui.post("/search-results", response_class=HTMLResponse)
async def ui_search_results(request: Request) -> HTMLResponse:
    """HTMX hx-post 타깃. JSON body 또는 form-data 모두 수용.

    _results_grid.html 을 렌더해 반환한다.
    """
    deps = request.app.state.deps

    # content-type 에 따라 입력 파싱
    body_dict: dict[str, Any] = {}
    ctype = request.headers.get("content-type", "")
    if "application/json" in ctype:
        body_dict = await request.json()
    else:
        # form-data (HTMX 의 hx-include 가 사용하는 경로)
        form = await request.form()
        body_dict = dict(form)
        # 숫자 필드 변환
        for k in ("count", "offset"):
            if k in body_dict and isinstance(body_dict[k], str):
                try:
                    body_dict[k] = int(body_dict[k])
                except ValueError:
                    body_dict.pop(k)
        # multi-value 필드는 v1 에서 무시
        body_dict.pop("pack_ids", None)
        body_dict.pop("labels", None)

    try:
        body = SearchBody(**body_dict)
    except Exception:
        body = SearchBody()  # 잘못된 입력 → 디폴트 (빈 결과)

    result = _do_search(deps, body)

    templates = request.app.state.templates
    ctx = {"request": request, **result}
    return templates.TemplateResponse(request=request, name="_results_grid.html", context=ctx)


# ── /ui/asset-detail/{asset_id} GET ──────────────────────────────────


@router_ui.get("/asset-detail/{asset_id}", response_class=HTMLResponse)
def ui_asset_detail(asset_id: int, request: Request) -> HTMLResponse:
    """자산 상세 모달 HTML fragment.

    카드 클릭 → HTMX hx-get → #asset-detail-modal 에 swap.
    """
    deps = request.app.state.deps
    asset = deps.store.get_asset_by_id(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")

    # pack_name 조회 — pack_id 로 직접 SELECT
    pack_row = deps.store.conn.execute(
        "SELECT name, display_name FROM packs WHERE id = ?",
        (asset.pack_id,),
    ).fetchone()
    pack_name = ""
    if pack_row:
        pack_name = pack_row[1] or pack_row[0]

    # 해상도·파일크기 메타 조회
    width: int | None = None
    height: int | None = None
    size_kb: int | None = asset.file_size // 1024 if asset.file_size else None
    if asset.kind == "sprite":
        sm = deps.store.conn.execute(
            "SELECT width, height FROM sprite_meta WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()
        if sm:
            width, height = sm[0], sm[1]

    # 라벨 조회
    label_map = deps.store.asset_labels_for([asset_id])
    labels = label_map.get(asset_id, [])

    # 파일명(확장자 제외)을 템플릿에 미리 계산해서 전달
    asset_name = Path(asset.path).stem

    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="asset_detail.html",
        context={
            "asset": asset,
            "asset_name": asset_name,
            "pack_name": pack_name,
            "width": width,
            "height": height,
            "size_kb": size_kb,
            "labels": labels,
        },
    )


# ── /api/audio/{asset_id} GET ─────────────────────────────────────────


@router.get("/audio/{asset_id}")
def api_audio(asset_id: int, request: Request) -> Response:
    """사운드 자산 파일 stream. sound kind 에만 허용."""
    import mimetypes

    deps = request.app.state.deps
    asset = deps.store.get_asset_by_id(asset_id)
    if asset is None or asset.kind != "sound":
        raise HTTPException(status_code=404, detail="audio only for sound kind")
    path = Path(asset.path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="audio file missing")
    mime, _ = mimetypes.guess_type(str(path))
    return FileResponse(str(path), media_type=mime or "application/octet-stream")


# ── /ui/audio-player/{asset_id} GET ──────────────────────────────────


@router_ui.get("/audio-player/{asset_id}", response_class=HTMLResponse)
def ui_audio_player(asset_id: int, request: Request) -> HTMLResponse:
    """오디오 인라인 플레이어 fragment (HTMX hx-get → .audio-slot swap)."""
    deps = request.app.state.deps
    asset = deps.store.get_asset_by_id(asset_id)
    if asset is None or asset.kind != "sound":
        raise HTTPException(status_code=404, detail="audio only for sound kind")
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="_audio_player.html",
        context={"asset_id": asset_id},
    )


# ── /api/thumbnail/{asset_id} GET ─────────────────────────────────────


@router.get("/thumbnail/{asset_id}")
def api_thumbnail(asset_id: int, request: Request) -> Response:
    """sprite 자산의 lazy 256×256 PNG. sound/spritesheet → 404.

    ETag 기반 조건부 요청 지원 (304 Not Modified).
    캐시 디렉터리: AppPaths.cache_dir / thumbnails/.
    """
    from ...core.thumbnails import ensure_thumbnail

    deps = request.app.state.deps
    asset = deps.store.get_asset_by_id(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    if asset.kind != "sprite":
        raise HTTPException(status_code=404, detail="thumbnail only for sprite kind")

    asset_path = Path(asset.path)
    cache_dir = deps.paths.cache_dir / "thumbnails"
    thumb = ensure_thumbnail(asset_path, asset.kind, cache_dir, asset_id, max_size=256)
    if thumb is None or not thumb.exists():
        raise HTTPException(status_code=404, detail="thumbnail generation failed")

    # asset_id 를 prefix 로 포함해 동일 mtime 의 다른 에셋 간 충돌 방지
    etag = f'"{asset_id}:{thumb.stat().st_mtime_ns}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)

    return FileResponse(
        str(thumb),
        media_type="image/png",
        headers={
            "ETag": etag,
            "Cache-Control": "public, max-age=86400",
        },
    )
