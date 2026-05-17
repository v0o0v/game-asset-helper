"""MCP 12 도구 함수 — store/search/usage/registry/queue 위 얇은 어댑터.

Write 도구는 ``store.write_lock`` 안에서 실행 (M2.1 패턴). 워커가 없는
환경(``deps.queue is None``)에서 ``request_rescan`` 은 mark_pending 만
하고 OK + warnings 응답.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..config import Config
from ..core.labels import LabelRegistry
from ..core.search import HybridSearcher, LabelFilter, SearchRequest
from ..core.store import Store
from ..core.usage_tracker import UsageTracker
from .models import (
    AxisLabel,
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
    RecordAssetUseRequest,
    RecordAssetUseResult,
    ReportFeedbackRequest,
    RequestRescanRequest,
    SetProjectPinRequest,
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
            for r in sorted(items, key=lambda x: x.score, reverse=True)[:3]:
                samples.append({
                    "asset_id": r.asset_id, "path": r.path, "score": r.score,
                })
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
    # v1: 로그만 + search_queries 검색 가능. 페널티 학습은 M4.
    log.info(
        "feedback: query_id=%s asset_id=%s reason=%s",
        req.query_id, req.asset_id, req.reason,
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
