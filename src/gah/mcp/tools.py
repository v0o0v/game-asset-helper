"""MCP 12 도구 함수 — store/search/usage/registry/queue 위 얇은 어댑터.

Write 도구는 ``store.write_lock`` 안에서 실행 (M2.1 패턴). 워커가 없는
환경(``deps.queue is None``)에서 ``request_rescan`` 은 mark_pending 만
하고 OK + warnings 응답.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..config import AppPaths, Config, default_app_paths
from ..core.label_query import (
    AmbiguousLabel,
    UnsupportedExpression,
    parse_label_query,
)
from ..core.labels import LabelRegistry
from ..core.search import HybridSearcher, LabelFilter, SearchRequest
from ..core.store import Store
from ..core.suggest_packs import enrich_sample
from ..core.usage_tracker import UsageTracker
from .models import (
    AxisLabel,
    DeleteSavedSearchRequest,
    DescribeLabelRequest,
    DescribeLabelResult,
    FindAssetRequest,
    FindAssetResult,
    GetAssetRequest,
    GetAssetResult,
    ListAssetsRequest,
    ListAssetsResult,
    ListLabelAxesResult,
    ListLabelsRequest,
    ListLabelsResult,
    ListPacksResult,
    ListSavedSearchesResult,
    RecordAssetUseRequest,
    RecordAssetUseResult,
    ReportFeedbackRequest,
    RequestRescanRequest,
    RequestUserPickRequest,
    RequestUserPickResult,
    RunSavedSearchRequest,
    SaveSearchRequest,
    SaveSearchResult,
    SetProjectPinRequest,
    SuggestAnimationFramesRequest,
    SuggestAnimationFramesResult,
    SuggestPacksRequest,
    SuggestPacksResult,
)

log = logging.getLogger(__name__)


# ── 의존성 + 에러 ────────────────────────────────────────────────────


@dataclass
class ToolDeps:
    store: Store
    search: HybridSearcher
    usage: UsageTracker
    registry: LabelRegistry
    queue: Any | None       # AnalysisQueue 또는 None (--mcp 단독 실행 시)
    config: Config
    # M4: suggest_packs 의 썸네일 캐시 디렉터리 (None → default_app_paths 폴백).
    paths: AppPaths | None = None


class McpToolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ── 헬퍼 ─────────────────────────────────────────────────────────────


def _ax(items: list[AxisLabel]) -> list[LabelFilter]:
    return [LabelFilter(axis=x.axis, label=x.label) for x in items]


# ── find_asset ───────────────────────────────────────────────────────


def tool_find_asset(deps: ToolDeps, req: FindAssetRequest) -> FindAssetResult:
    filters = req.filters
    if hasattr(filters, "model_dump"):
        filters_dict = filters.model_dump(exclude_none=True)
    else:
        filters_dict = dict(filters or {})

    # M4: label_query 파싱 (있다면) — 구조화 labels_* 와 병합 후 search 에 전달.
    if req.label_query:
        try:
            parse_label_query(req.label_query, deps.registry)
        except AmbiguousLabel as e:
            raise McpToolError(
                "400_invalid_input",
                f"라벨 '{e.label}' 모호 — 가능한 axis: {', '.join(e.candidates)}",
            ) from e
        except UnsupportedExpression as e:
            raise McpToolError("400_invalid_input", str(e)) from e

    sreq = SearchRequest(
        query=req.query,
        kind=req.kind,
        count=req.count,
        project_id=req.project_id,
        prefer_pack_id=req.prefer_pack_id,
        force_pack_id=req.force_pack_id,
        exclude_pack_ids=list(req.exclude_pack_ids),
        consistency_weight_override=req.consistency_weight_override,
        label_match_weight_override=req.label_match_weight_override,
        filters=filters_dict,
        labels_all=_ax(req.labels_all),
        labels_any=_ax(req.labels_any),
        labels_none=_ax(req.labels_none),
        label_query=req.label_query,
        diversity=req.diversity,
        diversity_lambda=req.diversity_lambda,
        weight_feedback_override=req.weight_feedback_override,
    )
    results = deps.search.hybrid(sreq)
    return FindAssetResult(
        query_id=results.query_id,
        results=[
            {
                "asset_id": r.asset_id,
                "pack_id": r.pack_id,
                "pack_name": r.pack_name,
                "path": r.path,
                "score": r.score,
                "score_breakdown": r.score_breakdown,
                "matched_labels": r.matched_labels,
                "why": r.why,
                "meta": r.meta,
            }
            for r in results.results
        ],
    )


# ── get_asset ────────────────────────────────────────────────────────


def tool_get_asset(deps: ToolDeps, req: GetAssetRequest) -> GetAssetResult:
    if req.asset_id is not None:
        row = deps.store.conn.execute(
            "SELECT a.id, a.pack_id, p.name, a.path, a.kind, a.analysis_state "
            "FROM assets a JOIN packs p ON p.id = a.pack_id WHERE a.id = ?",
            (int(req.asset_id),),
        ).fetchone()
    else:
        row = deps.store.conn.execute(
            "SELECT a.id, a.pack_id, p.name, a.path, a.kind, a.analysis_state "
            "FROM assets a JOIN packs p ON p.id = a.pack_id WHERE a.path = ?",
            (req.path,),
        ).fetchone()
    if row is None:
        raise McpToolError("404_not_found", "asset not found")
    aid = int(row[0])
    labels_by_aid = deps.store.asset_labels_for([aid])
    labels = [
        {"axis": l.axis, "label": l.label, "score": l.score, "source": l.source}
        for l in labels_by_aid.get(aid, [])
    ]
    return GetAssetResult(
        asset_id=aid, pack_id=int(row[1]), pack_name=str(row[2]),
        path=str(row[3]), kind=str(row[4]), analysis_state=str(row[5]),
        meta={}, labels=labels,
    )


# ── list_assets ──────────────────────────────────────────────────────


def tool_list_assets(deps: ToolDeps, req: ListAssetsRequest) -> ListAssetsResult:
    where: list[str] = []
    params: list[Any] = []
    if req.pack_id is not None:
        where.append("a.pack_id = ?")
        params.append(int(req.pack_id))
    if req.kind is not None:
        where.append("a.kind = ?")
        params.append(req.kind)
    wsql = ("WHERE " + " AND ".join(where)) if where else ""
    total = deps.store.conn.execute(
        f"SELECT COUNT(*) FROM assets a {wsql}", params
    ).fetchone()[0]
    offset = (max(1, req.page) - 1) * max(1, req.page_size)
    rows = deps.store.conn.execute(
        f"SELECT a.id, a.pack_id, p.name, a.path, a.kind, a.analysis_state "
        f"FROM assets a JOIN packs p ON p.id = a.pack_id {wsql} "
        f"ORDER BY a.id LIMIT ? OFFSET ?",
        params + [int(req.page_size), int(offset)],
    ).fetchall()
    return ListAssetsResult(
        page=req.page, page_size=req.page_size, total=int(total),
        assets=[
            {"asset_id": int(r[0]), "pack_id": int(r[1]), "pack_name": r[2],
             "path": r[3], "kind": r[4], "analysis_state": r[5]}
            for r in rows
        ],
    )


# ── list_packs ───────────────────────────────────────────────────────


def tool_list_packs(deps: ToolDeps) -> ListPacksResult:
    rows = deps.store.conn.execute(
        "SELECT id, name, display_name, vendor, license, source_url, aggregate_meta "
        "FROM packs WHERE enabled = 1 ORDER BY name"
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        pack_id = int(r[0])
        out.append({
            "pack_id": pack_id,
            "name": r[1],
            "display_name": r[2],
            "vendor": r[3],
            "license": r[4],
            "source_url": r[5],
            "asset_counts": deps.store.asset_count_by_kind(pack_id),
            "aggregate_meta": _json_or_empty(r[6]),
        })
    return ListPacksResult(packs=out)


def _json_or_empty(blob) -> dict[str, Any]:
    import json as _json

    if not blob:
        return {}
    try:
        return _json.loads(blob)
    except (ValueError, TypeError):
        return {}


# ── suggest_packs ────────────────────────────────────────────────────


def tool_suggest_packs(deps: ToolDeps, req: SuggestPacksRequest) -> SuggestPacksResult:
    """find_asset 의 결과를 그룹화 — pack 단위 score_breakdown 산출."""
    # 1) 자산 단위 hybrid search (k 를 넉넉히)
    sreq = SearchRequest(
        query=req.query or "",
        kind=req.kind,
        count=200,
        project_id=req.project_id,
    )
    results = deps.search.hybrid(sreq)

    # 2) 팩별 그룹
    by_pack: dict[int, list] = {}
    for r in results.results:
        by_pack.setdefault(r.pack_id, []).append(r)

    project_row = (
        deps.store.get_project(req.project_id) if req.project_id else None
    )
    summary = (
        deps.store.project_usage_summary(project_row.id)
        if project_row else None
    )

    packs_out: list[dict[str, Any]] = []
    for pack_id, items in by_pack.items():
        if len(items) < req.min_matching_assets:
            continue
        top1 = max(r.score for r in items)
        mean_top3 = sum(r.score for r in sorted(
            items, key=lambda x: x.score, reverse=True)[:3]) / min(3, len(items))
        pack_row = deps.store.conn.execute(
            "SELECT name, display_name, vendor, license, source_url "
            "FROM packs WHERE id = ?", (pack_id,),
        ).fetchone()
        cons_score = 0.0
        if summary is not None:
            from ..core.store import PackRow

            pr = PackRow(
                id=pack_id, name=pack_row[0], display_name=pack_row[1],
                vendor=pack_row[2], source_url=pack_row[4], license=pack_row[3],
                description=None, enabled=True, added_at=0, scanned_at=None,
            )
            cresult = deps.search.consistency.score_pack(
                project_id=project_row.id, pack=pr, summary=summary,
                blocked_packs=set(project_row.blocked_packs) if project_row else set(),
                pinned_pack_id=project_row.pinned_pack_id if project_row else None,
            )
            cons_score = cresult.score
        pack_score = (
            0.45 * top1 + 0.20 * mean_top3 + 0.25 * cons_score + 0.05 * 0.0 + 0.05 * 0.0
        )
        samples = []
        if req.include_samples:
            _paths = deps.paths if deps.paths is not None else default_app_paths()
            cache_dir = _paths.cache_dir / "thumbnails"
            lib_root = _paths.library_dir
            for r in sorted(items, key=lambda x: x.score, reverse=True)[:3]:
                asset_row = deps.store.get_asset_by_id(r.asset_id)
                if asset_row is None:
                    continue
                sample = enrich_sample(
                    asset_row, deps.store, cache_dir,
                    library_root=lib_root,
                    include_thumbnails=req.include_thumbnails,
                )
                sample["score"] = r.score
                samples.append(sample)
        packs_out.append({
            "pack_id": pack_id,
            "name": pack_row[0],
            "vendor": pack_row[2],
            "license": pack_row[3],
            "source_url": pack_row[4],
            "matching_asset_count": len(items),
            "score": pack_score,
            "score_breakdown": {
                "semantic_top1": top1,
                "semantic_mean_top3": mean_top3,
                "consistency": cons_score,
                "vendor_familiarity": 0.0,
                "recency": 0.0,
            },
            "samples": samples,
        })

    packs_out.sort(key=lambda p: p["score"], reverse=True)
    packs_out = packs_out[: req.count]
    proj_context: dict[str, Any] = {}
    if project_row is not None:
        proj_context = {
            "project_id": project_row.external_id,
            "pinned_pack_id": project_row.pinned_pack_id,
            "pack_usage": [
                {"pack_id": pid, "uses": cnt}
                for pid, cnt in (summary.pack_uses.items() if summary else [])
            ],
        }
    return SuggestPacksResult(
        query_id=results.query_id,
        project_context=proj_context,
        packs=packs_out,
    )


# ── record_asset_use ─────────────────────────────────────────────────


def tool_record_asset_use(
    deps: ToolDeps, req: RecordAssetUseRequest
) -> RecordAssetUseResult:
    with deps.store.write_lock:
        project = deps.store.upsert_project(req.project_id)
        usage_id = deps.usage.record_explicit(
            project.id, req.asset_id, query_id=req.query_id, context=req.context,
            source=req.source,
        )
    return RecordAssetUseResult(ok=True, usage_id=int(usage_id))


# ── set_project_pin ──────────────────────────────────────────────────


def tool_set_project_pin(deps: ToolDeps, req: SetProjectPinRequest) -> dict:
    with deps.store.write_lock:
        project = deps.store.upsert_project(req.project_id)
        deps.store.set_project_pin(project.id, req.pinned_pack_id)
        deps.store.set_blocked_packs(project.id, list(req.blocked_pack_ids))
    return {"ok": True}


# ── request_rescan ───────────────────────────────────────────────────


def tool_request_rescan(deps: ToolDeps, req: RequestRescanRequest) -> dict:
    if deps.queue is None:
        # 워커 없음 — 직접 mark_pending 만.
        enqueued = 0
        with deps.store.write_lock:
            if req.pack_id is not None:
                rows = deps.store.conn.execute(
                    "UPDATE assets SET analysis_state='pending' WHERE pack_id=?",
                    (int(req.pack_id),),
                )
                enqueued = rows.rowcount or 0
            elif req.asset_id is not None:
                rows = deps.store.conn.execute(
                    "UPDATE assets SET analysis_state='pending' WHERE id=?",
                    (int(req.asset_id),),
                )
                enqueued = rows.rowcount or 0
            elif req.all:
                rows = deps.store.conn.execute(
                    "UPDATE assets SET analysis_state='pending'"
                )
                enqueued = rows.rowcount or 0
        return {
            "enqueued": int(enqueued),
            "warnings": ["no live worker; will be processed on next GUI startup"],
        }
    # 활성 워커가 있는 경우 — 큐에 직접 enqueue.
    if req.pack_id is not None:
        n = deps.queue.enqueue_pack(req.pack_id)
    elif req.asset_id is not None:
        n = deps.queue.enqueue_asset(req.asset_id)
    elif req.all:
        n = 0
        for pack_row in deps.store.conn.execute("SELECT id FROM packs").fetchall():
            n += deps.queue.enqueue_pack(int(pack_row[0]))
    else:
        n = 0
    return {"enqueued": int(n)}


# ── report_feedback ──────────────────────────────────────────────────


def tool_report_feedback(deps: ToolDeps, req: ReportFeedbackRequest) -> dict:
    """M4 페널티 학습 — Config.feedback_*_weight 로 signed weight 변환 후
    feedback_records 에 누적.

    project_id 없는 query (global) 는 페널티 학습 비활성 — log + skipped=True.
    """
    weight_map = {
        "negative": deps.config.feedback_negative_weight,
        "positive": deps.config.feedback_positive_weight,
        "irrelevant": deps.config.feedback_irrelevant_weight,
    }
    weight = float(weight_map[req.reason])
    # query_id → project_id 매핑.
    row = deps.store.conn.execute(
        "SELECT project_id FROM search_queries WHERE id = ?", (int(req.query_id),),
    ).fetchone()
    if row is None:
        raise McpToolError("404_not_found", f"query_id={req.query_id} 없음")
    project_id = int(row[0]) if row[0] is not None else None
    if project_id is None:
        log.info("feedback skipped (global query, no project): %s", req)
        return {"ok": True, "skipped": True}
    with deps.store.write_lock:
        deps.store.insert_feedback_record(
            project_id=project_id, asset_id=int(req.asset_id),
            query_id=int(req.query_id), reason=req.reason, weight=weight,
        )
    log.info(
        "feedback recorded: project=%s asset=%s reason=%s weight=%s",
        project_id, req.asset_id, req.reason, weight,
    )
    return {"ok": True}


# ── label vocabulary 메타 ────────────────────────────────────────────


def tool_list_label_axes(deps: ToolDeps) -> ListLabelAxesResult:
    return ListLabelAxesResult(axes=deps.registry.list_axes())


def tool_list_labels(deps: ToolDeps, req: ListLabelsRequest) -> ListLabelsResult:
    rows = deps.registry.list_labels(
        axis=req.axis, enabled_only=req.enabled_only,
        with_description=req.with_description,
    )
    labels_out = []
    for r in rows:
        item = {"axis": r.axis, "label": r.label, "source": r.source}
        if req.with_description:
            item["description"] = r.description
        labels_out.append(item)
    return ListLabelsResult(
        labels=labels_out,
        signature=deps.registry.label_catalog_signature(),
    )


def tool_describe_label(
    deps: ToolDeps, req: DescribeLabelRequest
) -> DescribeLabelResult:
    rows = deps.registry.list_labels(
        axis=req.axis, enabled_only=False, with_description=True,
    )
    row = next(
        (r for r in rows if r.label == req.label and r.axis == req.axis), None,
    )
    description = row.description if row else None
    # sample assets — 해당 라벨이 붙은 상위 3개 asset.
    sample_rows = deps.store.conn.execute(
        "SELECT a.id, a.path, a.pack_id, p.name "
        "FROM asset_labels al JOIN assets a ON a.id = al.asset_id "
        "JOIN packs p ON p.id = a.pack_id "
        "WHERE al.axis = ? AND al.label = ? "
        "ORDER BY al.score DESC LIMIT 3",
        (req.axis, req.label),
    ).fetchall()
    samples = [
        {"asset_id": int(r[0]), "path": r[1], "pack_id": int(r[2]),
         "pack_name": r[3]}
        for r in sample_rows
    ]
    return DescribeLabelResult(
        axis=req.axis, label=req.label, description=description,
        sample_assets=samples,
    )


# ── M4: saved_searches 4 신규 도구 ───────────────────────────────────


def _resolve_project_id(deps: ToolDeps, external_id: str | None) -> int | None:
    if external_id is None:
        return None
    return deps.store.upsert_project(external_id).id


def tool_save_search(
    deps: ToolDeps, req: SaveSearchRequest
) -> SaveSearchResult:
    """SearchRequest payload 를 JSON 으로 직렬화해 saved_searches 에 저장.

    중복 (project_id, name) → IntegrityError → `400_invalid_input` 매핑.
    """
    import json as _json
    import sqlite3 as _sq

    payload: dict[str, Any] = {
        "query": req.query,
        "label_query": req.label_query,
        "kind": req.kind,
        "labels_all": [{"axis": x.axis, "label": x.label} for x in req.labels_all],
        "labels_any": [{"axis": x.axis, "label": x.label} for x in req.labels_any],
        "labels_none": [{"axis": x.axis, "label": x.label} for x in req.labels_none],
        "diversity": req.diversity,
        "diversity_lambda": req.diversity_lambda,
        "count": req.count,
        "_schema_version": 1,
    }
    filters = req.filters
    if hasattr(filters, "model_dump"):
        payload["filters"] = filters.model_dump(exclude_none=True)
    elif filters:
        payload["filters"] = dict(filters)
    pid = _resolve_project_id(deps, req.project_id)
    try:
        with deps.store.write_lock:
            sid = deps.store.save_search(pid, req.name, _json.dumps(payload))
    except _sq.IntegrityError as e:
        raise McpToolError(
            "400_invalid_input",
            f"저장된 검색 이름 '{req.name}' 중복 (project={req.project_id})",
        ) from e
    return SaveSearchResult(ok=True, saved_search_id=sid)


def tool_list_saved_searches(
    deps: ToolDeps, project_id: str | None,
) -> ListSavedSearchesResult:
    pid = _resolve_project_id(deps, project_id)
    rows = deps.store.list_saved_searches(pid)
    return ListSavedSearchesResult(
        saved_searches=[
            {
                "id": r.id, "name": r.name, "query_json": r.query_json,
                "created_at": r.created_at, "last_used_at": r.last_used_at,
            }
            for r in rows
        ],
    )


def tool_delete_saved_search(
    deps: ToolDeps, req: DeleteSavedSearchRequest,
) -> dict:
    pid = _resolve_project_id(deps, req.project_id)
    with deps.store.write_lock:
        ok = deps.store.delete_saved_search(pid, req.name)
    if not ok:
        raise McpToolError(
            "404_not_found",
            f"저장된 검색 '{req.name}' 없음 (project={req.project_id})",
        )
    return {"ok": True}


def tool_run_saved_search(
    deps: ToolDeps, req: RunSavedSearchRequest,
) -> FindAssetResult:
    """저장된 query_json 을 로드 → FindAssetRequest 재구성 → tool_find_asset 위임."""
    import json as _json

    pid = _resolve_project_id(deps, req.project_id)
    row = deps.store.get_saved_search(pid, req.name)
    if row is None:
        raise McpToolError(
            "404_not_found",
            f"저장된 검색 '{req.name}' 없음 (project={req.project_id})",
        )
    payload = _json.loads(row.query_json)
    # _schema_version 등 메타는 무시.
    payload.pop("_schema_version", None)
    payload.update(req.overrides or {})
    payload.setdefault("query", "")
    find_req = FindAssetRequest(project_id=req.project_id, **payload)
    with deps.store.write_lock:
        deps.store.update_saved_search_last_used(row.id)
    return tool_find_asset(deps, find_req)


# ── M5 Phase 4C: request_user_pick ───────────────────────────────────


def tool_request_user_pick(
    deps: ToolDeps, req: RequestUserPickRequest
) -> RequestUserPickResult:
    """후보 자산 중 사용자가 직접 선택하도록 GAH 웹 UI 에 long-poll 요청.

    흐름:
    1. `data_dir/web.port` 에서 실제 포트 읽기.
    2. `POST /internal/user-pick` 로 httpx 동기 요청 (timeout = req.timeout_seconds + 10).
    3. 200 → RequestUserPickResult 반환 + _auto_record_asset_use.
    4. 408/499/503 → McpToolError.
    5. ConnectError → 503_no_ui_available.
    """
    import httpx as _httpx

    from ..web.url import read_web_port

    if deps.paths is None:
        raise McpToolError("503_no_ui_available", "MCP server 가 AppPaths 없이 시작됨.")

    port = read_web_port(deps.paths.data_dir)
    if port is None:
        raise McpToolError(
            "503_no_ui_available",
            "GAH 웹 UI 가 떠 있지 않습니다. 트레이 모드로 GAH 를 실행해주세요.",
        )

    url = f"http://{deps.config.web_host}:{port}/internal/user-pick"
    try:
        with _httpx.Client(timeout=req.timeout_seconds + 10) as c:
            r = c.post(url, json=req.model_dump(exclude_none=False))
    except _httpx.TransportError:
        raise McpToolError("503_no_ui_available", "GAH 웹 UI 연결 실패.")

    if r.status_code == 200:
        result = RequestUserPickResult(**r.json())
        _auto_record_asset_use(deps, req, result)
        return result
    if r.status_code == 408:
        raise McpToolError("408_timeout", f"사용자가 {req.timeout_seconds}초 안에 응답하지 않았습니다.")
    if r.status_code == 499:
        raise McpToolError("499_user_cancelled", "사용자가 거부했습니다.")
    if r.status_code == 503:
        raise McpToolError("503_too_many_pending", "Pending 요청이 너무 많습니다 (max=20).")
    raise McpToolError(f"{r.status_code}_unknown", r.text)


def _auto_record_asset_use(
    deps: ToolDeps,
    req: RequestUserPickRequest,
    result: RequestUserPickResult,
) -> None:
    """request_user_pick 의 picked asset 을 source='claude_pick' 로 자동 기록."""
    if req.project_id is None:
        log.info("request_user_pick: project_id 없음 → record_asset_use 스킵")
        return
    try:
        record_req = RecordAssetUseRequest(
            asset_id=result.picked_asset_id,
            project_id=req.project_id,
            query_id=None,
            context=req.reason,
            source="claude_pick",
        )
        tool_record_asset_use(deps, record_req)
    except Exception as e:
        log.warning("자동 record_asset_use 실패: %s", e)


# ── M6 — suggest_animation_frames ─────────────────────────────────────


def tool_suggest_animation_frames(
    deps: ToolDeps, req: SuggestAnimationFramesRequest,
) -> SuggestAnimationFramesResult:
    """asset_id 시트의 animation 라벨에 해당하는 프레임 인덱스 + fps_hint.

    M6 spec §4.5. 에러:
      - 404_not_found: asset_id 없음 / sprite_meta 없음 / animation 없음 / animations_json NULL
      - 400_invalid_input: kind != spritesheet
    """
    # 자산 존재 확인 + kind 검사
    row = deps.store.conn.execute(
        "SELECT kind FROM assets WHERE id = ?", (req.asset_id,)
    ).fetchone()
    if row is None:
        raise McpToolError(
            "404_not_found", f"asset {req.asset_id} not found"
        )
    kind = str(row[0])
    if kind != "spritesheet":
        raise McpToolError(
            "400_invalid_input",
            f"asset {req.asset_id} is kind={kind}, not a spritesheet",
        )

    meta = deps.store.get_sprite_meta(req.asset_id)
    if meta is None or not meta.animations_json:
        raise McpToolError(
            "404_not_found",
            f"asset {req.asset_id} has no animations recorded",
        )

    anim_dict = meta.animations_json
    if req.animation not in anim_dict:
        available = sorted(anim_dict.keys())
        raise McpToolError(
            "404_not_found",
            f"animation '{req.animation}' not found — available: {available}",
        )

    spec = anim_dict[req.animation]
    start = int(spec.get("start_frame", 0))
    end = int(spec.get("end_frame", start))
    fps = int(spec.get("fps_hint", 12)) or 12
    indices = list(range(start, end + 1))
    return SuggestAnimationFramesResult(frame_indices=indices, fps_hint=fps)
