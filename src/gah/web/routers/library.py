"""M5 — 라이브러리 페이지 라우터 (검색 + 결과 fragment + 썸네일).

두 라우터를 노출한다.
  - ``router``    : prefix="/api" — JSON 응답 (/search, /thumbnail/{id})
  - ``router_ui`` : prefix="/ui"  — HTML fragment (/search-results)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from ..deps import resolve_asset_path
from ...core.ollama_client import OllamaError

log = logging.getLogger(__name__)

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
    # M6 — spritesheet 의 frame 정보를 top-level 로 flatten
    d.setdefault("frame_count", meta.get("frame_count"))
    d.setdefault("frame_w", meta.get("frame_w"))
    d.setdefault("frame_h", meta.get("frame_h"))

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
        # M6 — frame_count 는 sprite_meta JOIN 없이 빠르게 처리하지 않으므로 None.
        # 시트 카드는 검색 경로에서만 배지 노출.
        "frame_count": None,
        "frame_w": None,
        "frame_h": None,
    }
    return d


def _do_search(deps: Any, body: SearchBody) -> dict[str, Any]:
    """HybridSearcher 호출 핵심 로직 — /api/search 와 /ui/search-results 가 공유.

    SearchRequest 에 offset 필드가 없으므로 fetch_count = count + offset 으로
    더 많이 받아온 뒤 Python 에서 슬라이싱한다.

    빈 검색 (query 비어 + label_query 없음 + 기타 필터 없음) 인 경우에는
    HybridSearcher 를 거치지 않고 store.list_assets() 폴백으로 라이브러리
    전체를 추가일↓ 순으로 반환한다. sort=score 는 이 경우 added_desc 로 전환.

    Phase 3 추가:
    - body.labels (label id list) → LabelFilter list → match_mode 에 따라
      labels_all / labels_any / labels_none 분배
    - body.pack_ids → SearchRequest 후 Python 후처리 필터 (v1 단순화)

    **알려진 한계** — ``body.pack_ids`` 가 지정되면 SearchRequest 결과를 Python
    후처리로 필터하므로, ``next_offset`` 이 Searcher 가 본 row 수가 아니라 필터 후
    row 수 기준으로 계산된다. 페이지네이션이 조기 종료될 수 있다 (예: pack_b 자산이
    DB 에 80개 있어도 ``fetch_count`` 안에서 절반만 매칭되면 total 이 작게 보고됨).
    이는 v1 단순화 결과이며, M6 이후 ``SearchRequest.pack_ids`` 직접 매핑 또는
    ``fetch_count`` 오버페치로 개선 권장.
    """
    from ...core.search import LabelFilter, SearchRequest

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

    # ── labels list[int] → LabelFilter 매핑 ────────────────────────────
    labels_all_list: list[LabelFilter] = []
    labels_any_list: list[LabelFilter] = []
    labels_none_list: list[LabelFilter] = []

    raw_labels = body.labels or []
    if raw_labels:
        all_label_rows = deps.store.list_labels_raw(axis=None, enabled_only=True)
        id_to_lf: dict[int, LabelFilter] = {
            r.id: LabelFilter(axis=r.axis, label=r.label) for r in all_label_rows
        }
        filters = [id_to_lf[lid] for lid in raw_labels if lid in id_to_lf]
        if filters:
            if body.match_mode == "all":
                labels_all_list = filters
            elif body.match_mode == "any":
                labels_any_list = filters
            elif body.match_mode == "none":
                labels_none_list = filters

    sr = SearchRequest(
        query=body.query,
        label_query=body.label_query,
        project_id=body.project_id,
        kind=body.kind,
        diversity=body.diversity,
        diversity_lambda=body.diversity_lambda,
        count=fetch_count,
        labels_all=labels_all_list,
        labels_any=labels_any_list,
        labels_none=labels_none_list,
    )
    try:
        response = deps.search.hybrid(sr)
    except OllamaError as e:
        log.warning("검색 실패 — Ollama 미가용: %s", e)
        return {
            "query_id": None,
            "total": 0,
            "rows": [],
            "next_offset": None,
            "error": "ollama_unavailable",
            "error_message": "검색 서비스 (Ollama) 가 사용 가능하지 않습니다. Ollama 서버가 떠 있는지 확인하세요.",
        }

    all_rows = [_row_to_dict(r) for r in response.results]

    # ── pack_ids 후처리 필터 (v1 — Python list comprehension) ──────────
    if body.pack_ids:
        pack_id_set = set(body.pack_ids)
        all_rows = [r for r in all_rows if r.get("pack_id") in pack_id_set]

    # fetch_count 개 중 offset 이후만 count 개 취함
    sliced = all_rows[body.offset: body.offset + body.count]
    sliced = _apply_sort(sliced, body.sort)

    total = len(all_rows)
    next_offset: int | None = (
        body.offset + body.count
        if total > body.offset + body.count
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

    # M6 — spritesheet 행에 frame_count 보충 (sprite_meta JOIN)
    sheet_ids = [r["asset_id"] for r in all_rows if r["kind"] == "spritesheet"]
    if sheet_ids:
        placeholders = ",".join("?" * len(sheet_ids))
        frame_rows = deps.store.conn.execute(
            f"SELECT asset_id, frame_w, frame_h, frame_count FROM sprite_meta WHERE asset_id IN ({placeholders})",
            sheet_ids,
        ).fetchall()
        frame_map = {
            int(fr[0]): {
                "frame_w": int(fr[1]) if fr[1] is not None else None,
                "frame_h": int(fr[2]) if fr[2] is not None else None,
                "frame_count": int(fr[3]) if fr[3] is not None else None,
            }
            for fr in frame_rows
        }
        for row in all_rows:
            if row["kind"] == "spritesheet" and row["asset_id"] in frame_map:
                row.update(frame_map[row["asset_id"]])

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
    result = _do_search(deps, body)
    if result.get("error") == "ollama_unavailable":
        raise HTTPException(
            status_code=503,
            detail={
                "code": "503_ollama_unavailable",
                "message": result.get("error_message", "Ollama unavailable"),
            },
        )
    return result


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
        # JSON-encoded 필드 파싱 (hidden input 으로 전달된 labels / pack_ids)
        import json as _json
        for json_key in ("labels", "pack_ids"):
            raw = body_dict.get(json_key)
            if isinstance(raw, str):
                try:
                    parsed = _json.loads(raw)
                    if isinstance(parsed, list):
                        body_dict[json_key] = [
                            int(x) for x in parsed
                            if str(x).strip()
                        ]
                    else:
                        body_dict.pop(json_key)
                except (_json.JSONDecodeError, ValueError):
                    body_dict.pop(json_key)

    try:
        body = SearchBody(**body_dict)
    except Exception:
        body = SearchBody()  # 잘못된 입력 → 디폴트 (빈 결과)

    result = _do_search(deps, body)

    templates = request.app.state.templates

    # Ollama 미가용 등 검색 실패 → 친화 메시지 fragment (200)
    if result.get("error"):
        return templates.TemplateResponse(
            request=request,
            name="_search_error.html",
            context={"request": request, **result},
            status_code=200,
        )

    # M7 Phase 5 — 활성 프로젝트 ID 를 카드 템플릿에 전달 (채택 버튼 disabled 처리)
    active_project_id = deps.config.active_project_id
    ctx = {"request": request, "active_project_id": active_project_id, **result}
    # offset>0 은 페이지네이션 — toolbar 없이 카드만 반환해 중복을 방지한다.
    template_name = "_results_grid.html" if body.offset == 0 else "_results_cards_only.html"
    return templates.TemplateResponse(request=request, name=template_name, context=ctx)


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

    # pack_name 조회 — get_pack_by_id 헬퍼 사용
    pack_obj = deps.store.get_pack_by_id(asset.pack_id)
    pack_name = ""
    if pack_obj:
        pack_name = pack_obj.display_name or pack_obj.name

    # 해상도·파일크기 메타 조회
    width: int | None = None
    height: int | None = None
    size_kb: int | None = asset.file_size // 1024 if asset.file_size else None
    if asset.kind in ("sprite", "spritesheet"):
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
    path = resolve_asset_path(deps, asset.path)
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


# ── 가중치 공통 헬퍼 ──────────────────────────────────────────────────


def _apply_weights_to_config(deps: Any, w: dict[str, float]) -> None:
    """Config 가중치 6채널을 runtime 에 즉시 반영.

    Config 는 mutable @dataclass (frozen=False) 이므로 attribute 직접 할당.
    HybridSearcher 는 hybrid() 호출 시마다 self.config.weight_* 를 읽으므로
    동일 Config 객체를 mutate 하면 다음 검색부터 즉시 반영된다.
    WebDeps 는 frozen=True 라 deps 자체는 교체 불가지만, deps.config 가
    mutable 이라 내부 필드 직접 할당으로 충분.
    """
    deps.config.weight_semantic = float(w["semantic"])
    deps.config.weight_keyword = float(w["keyword"])
    deps.config.weight_label_match = float(w["label_match"])
    deps.config.weight_consistency = float(w["consistency"])
    deps.config.weight_recency = float(w["recency"])
    deps.config.weight_feedback = float(w["feedback"])


# ── /api/preset/{name} POST ────────────────────────────────────────────


PRESETS: dict[str, dict[str, float]] = {
    "balanced": {
        "semantic": 0.35,
        "keyword": 0.10,
        "label_match": 0.20,
        "consistency": 0.20,
        "recency": 0.05,
        "feedback": 0.10,
    },
    "consistency": {
        "semantic": 0.25,
        "keyword": 0.05,
        "label_match": 0.20,
        "consistency": 0.40,
        "recency": 0.05,
        "feedback": 0.05,
    },
    "novelty": {
        "semantic": 0.40,
        "keyword": 0.15,
        "label_match": 0.20,
        "consistency": 0.05,
        "recency": 0.10,
        "feedback": 0.10,
    },
}


@router.post("/preset/{name}")
def api_preset(name: str, request: Request) -> dict[str, Any]:
    """가중치 프리셋 적용 — balanced / consistency / novelty 3가지.

    Config 를 즉시 갱신하고 프리셋 이름 + 적용된 가중치를 반환한다.
    디스크 저장은 하지 않음 (런타임 갱신만). 다음 부팅 시 디폴트로 복귀.
    """
    if name not in PRESETS:
        raise HTTPException(status_code=404, detail=f"unknown preset: {name}")
    deps = request.app.state.deps
    weights = PRESETS[name]
    _apply_weights_to_config(deps, weights)
    return {"preset": name, "weights": weights}


# ── /api/weights POST ──────────────────────────────────────────────────


class WeightsBody(BaseModel):
    """POST /api/weights 입력 모델 — 6채널 가중치 (0~1 각각)."""

    semantic: float = Field(ge=0, le=1)
    keyword: float = Field(ge=0, le=1)
    label_match: float = Field(ge=0, le=1)
    consistency: float = Field(ge=0, le=1)
    recency: float = Field(ge=0, le=1)
    feedback: float = Field(ge=0, le=1)


@router.post("/weights")
def api_weights(body: WeightsBody, request: Request) -> dict[str, float]:
    """슬라이더 직접 조정 — 6채널 가중치를 즉시 갱신.

    합이 1이 아니어도 허용 (정규화는 frontend 책임).
    Config 런타임 갱신만 수행 (디스크 저장 없음).
    """
    deps = request.app.state.deps
    _apply_weights_to_config(deps, body.model_dump())
    return body.model_dump()


# ── /api/thumbnail/{asset_id} GET ─────────────────────────────────────


@router.get("/thumbnail/{asset_id}")
def api_thumbnail(asset_id: int, request: Request) -> Response:
    """sprite + spritesheet 자산의 lazy 256×256 PNG. sound → 404.

    ETag 기반 조건부 요청 지원 (304 Not Modified).
    캐시 디렉터리: AppPaths.cache_dir / thumbnails/.
    """
    from ...core.thumbnails import ensure_thumbnail

    deps = request.app.state.deps
    asset = deps.store.get_asset_by_id(asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    if asset.kind not in ("sprite", "spritesheet"):
        raise HTTPException(status_code=404, detail="thumbnail only for image kinds")

    asset_path = resolve_asset_path(deps, asset.path)
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


# ── /api/usage/summary + /ui/usage/detail ─────────────────────────────

_USAGE_WINDOW_SECONDS = 2_592_000  # 30일


@router.get("/usage/summary")
def api_usage_summary(request: Request, project_id: int | None = None) -> dict[str, Any]:
    """프로젝트 통일성/페널티 요약 반환.

    project_id 없으면 글로벌 단순화 (v1 — top_packs=[], rejected_count=0).
    project_id 있으면 Store.project_usage_summary 결과를 변환.
    """
    if project_id is None:
        return {
            "top_packs": [],
            "rejected_count": 0,
            "window_seconds": _USAGE_WINDOW_SECONDS,
        }
    deps = request.app.state.deps
    summary = deps.store.project_usage_summary(project_id)
    # pack_uses: {pack_id: count} → 상위 5개 팩
    sorted_packs = sorted(summary.pack_uses.items(), key=lambda x: x[1], reverse=True)[:5]
    top_packs = []
    for pid, cnt in sorted_packs:
        pack_obj = deps.store.get_pack_by_id(int(pid))
        pack_name = (pack_obj.display_name or pack_obj.name) if pack_obj else str(pid)
        top_packs.append({"pack_id": pid, "pack_name": pack_name, "uses": cnt})
    # rejected_count: feedback_records 는 별도 API — v1 은 0 고정
    return {
        "top_packs": top_packs,
        "rejected_count": 0,
        "window_seconds": _USAGE_WINDOW_SECONDS,
    }


@router_ui.get("/usage/detail", response_class=HTMLResponse)
def ui_usage_detail(request: Request, project_id: int | None = None) -> HTMLResponse:
    """통일성/페널티 상세 모달 fragment."""
    summary = api_usage_summary(request, project_id=project_id)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request=request,
        name="_modal_usage.html",
        context={"summary": summary},
    )
