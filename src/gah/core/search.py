"""HybridSearcher — FTS5 키워드 + numpy 코사인 + 라벨 매칭 + 통일성 가중합.

가중합 공식 (Config 기본값):
  final = 0.40·semantic + 0.15·keyword + 0.20·label_match + 0.20·consistency + 0.05·recency

`label_match=0` (자유 쿼리, 라벨 필터 미지정) 인 경우에도 다른 채널을
재정규화하지 않는다 — 라벨 필터 명시 안 한 검색은 의도적으로 max 0.80.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .consistency import ConsistencyResult, ConsistencyScorer
from .labels import LabelRegistry
from .searchable import build_query_text
from .store import LabelScore, Store

log = logging.getLogger(__name__)


# ── data classes ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class LabelFilter:
    axis: str
    label: str


@dataclass(frozen=True)
class SearchRequest:
    query: str
    kind: str | None = None
    count: int = 5
    project_id: str | None = None
    prefer_pack_id: int | None = None
    force_pack_id: int | None = None
    exclude_pack_ids: list[int] = field(default_factory=list)
    consistency_weight_override: float | None = None
    label_match_weight_override: float | None = None
    filters: dict = field(default_factory=dict)
    labels_all: list[LabelFilter] = field(default_factory=list)
    labels_any: list[LabelFilter] = field(default_factory=list)
    labels_none: list[LabelFilter] = field(default_factory=list)


@dataclass(frozen=True)
class ResultRow:
    asset_id: int
    pack_id: int
    pack_name: str
    path: str
    score: float
    score_breakdown: dict[str, float]
    matched_labels: list[dict]
    why: str
    meta: dict


@dataclass(frozen=True)
class SearchResults:
    query_id: int
    results: list[ResultRow]


# ── helpers ──────────────────────────────────────────────────────────


def _normalize_minmax(values: dict[int, float]) -> dict[int, float]:
    if not values:
        return {}
    vs = list(values.values())
    lo, hi = min(vs), max(vs)
    span = hi - lo
    if span <= 1e-9:
        return {k: 0.0 for k in values}
    return {k: (v - lo) / span for k, v in values.items()}


def _label_match_score(
    asset_labels: list[LabelScore],
    labels_all: list[LabelFilter],
    labels_any: list[LabelFilter],
    labels_none: list[LabelFilter],
) -> float:
    if not (labels_all or labels_any or labels_none):
        return 0.0
    present = {(l.axis, l.label) for l in asset_labels}

    # labels_all: 하나라도 빠지면 0.
    if labels_all:
        all_ok = all((f.axis, f.label) in present for f in labels_all)
        if not all_ok:
            return 0.0

    # labels_none: 하나라도 포함되면 0.
    if labels_none and any((f.axis, f.label) in present for f in labels_none):
        return 0.0

    score = 0.0
    if labels_all:
        score += 0.5  # AND 만족
    if labels_any:
        hit = sum(1 for f in labels_any if (f.axis, f.label) in present)
        if hit:
            score += 0.4 * (hit / len(labels_any))
    if labels_none:
        score += 0.1  # NOT 만족
    return min(1.0, score)


def _labels_match_filter(
    labels_by_aid: dict[int, list[LabelScore]],
    labels_all: list[LabelFilter],
    labels_any: list[LabelFilter],
    labels_none: list[LabelFilter],
) -> set[int]:
    """labels_all/any/none 모두 만족하는 asset_id 집합."""
    out = set()
    for aid, labels in labels_by_aid.items():
        present = {(l.axis, l.label) for l in labels}
        if labels_all and not all((f.axis, f.label) in present for f in labels_all):
            continue
        if labels_none and any((f.axis, f.label) in present for f in labels_none):
            continue
        if labels_any and not any((f.axis, f.label) in present for f in labels_any):
            continue
        out.add(aid)
    return out


def _apply_filters(meta: dict, filters: dict) -> bool:
    """SearchRequest.filters (DESIGN §6.1) 적용. meta 는 asset 의 sound_meta dict 등."""
    if not filters:
        return True
    duration_ms = meta.get("duration_ms")
    if duration_ms is not None:
        if "min_duration_ms" in filters and duration_ms < filters["min_duration_ms"]:
            return False
        if "max_duration_ms" in filters and duration_ms > filters["max_duration_ms"]:
            return False
    if "loopable" in filters:
        if meta.get("loopable") != filters["loopable"]:
            return False
    if "tags_any" in filters and filters["tags_any"]:
        tags = set(meta.get("tags") or [])
        if not (set(filters["tags_any"]) & tags):
            return False
    return True


def _cosine_scores(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    if matrix.size == 0:
        return np.zeros(0, dtype="<f4")
    qn = np.linalg.norm(query_vec)
    mn = np.linalg.norm(matrix, axis=1)
    denom = qn * mn
    denom[denom == 0] = 1e-9
    raw = (matrix @ query_vec) / denom
    # 음수 클램프 → [0, 1]
    return np.clip(raw, 0.0, 1.0).astype("<f4")


# ── HybridSearcher ───────────────────────────────────────────────────


class HybridSearcher:
    def __init__(
        self,
        store: Store,
        embedder,
        consistency: ConsistencyScorer,
        registry: LabelRegistry,
        config,
    ) -> None:
        self.store = store
        self.embedder = embedder
        self.consistency = consistency
        self.registry = registry
        self.config = config

    # ─── public entry ─────────────────────────────────────────────────

    def hybrid(self, req: SearchRequest) -> SearchResults:
        # 1) project upsert + summary
        project_row = None
        summary = None
        if req.project_id:
            project_row = self.store.upsert_project(req.project_id)
            summary = self.store.project_usage_summary(project_row.id)
        blocked_packs = set(req.exclude_pack_ids or [])
        pinned_pack_id = None
        if project_row is not None:
            pinned_pack_id = project_row.pinned_pack_id
            blocked_packs |= set(project_row.blocked_packs)

        # 2) 후보 추출 — FTS + semantic 합집합
        fts_hits = self.store.fts_search(
            req.query, kind=req.kind, pack_id=req.force_pack_id,
            exclude_pack_ids=list(blocked_packs), k=200,
        )
        fts_ids = [aid for aid, _ in fts_hits]
        fts_raw = {aid: bm for aid, bm in fts_hits}

        all_ids, all_matrix, _ = self.store.semantic_candidates_load()
        if all_matrix.size == 0:
            return SearchResults(query_id=self._log_query(project_row, req, []),
                                 results=[])

        query_blob, dim = self.embedder.encode_text(build_query_text(req.query, req.kind))
        query_vec = self.embedder.decode_vector(query_blob, dim)
        cosine_all = _cosine_scores(query_vec, all_matrix)

        # 상위 K coarse 단계 (200) — 통일성/라벨 계산 비용 절감
        if len(all_ids) > 200:
            top_idx = np.argpartition(-cosine_all, 199)[:200]
            sem_top_ids = [all_ids[i] for i in top_idx]
        else:
            sem_top_ids = list(all_ids)

        candidate_ids = set(fts_ids) | set(sem_top_ids)

        # 3) scope 필터 (force_pack_id / blocked / kind)
        asset_meta = self._load_asset_meta(list(candidate_ids), kind=req.kind)
        candidate_ids &= set(asset_meta.keys())
        if req.force_pack_id is not None:
            candidate_ids = {a for a in candidate_ids
                             if asset_meta[a]["pack_id"] == req.force_pack_id}
        if blocked_packs:
            candidate_ids = {a for a in candidate_ids
                             if asset_meta[a]["pack_id"] not in blocked_packs}

        # 4) 라벨 필터
        labels_by_aid = self.store.asset_labels_for(list(candidate_ids))
        if req.labels_all or req.labels_any or req.labels_none:
            candidate_ids &= _labels_match_filter(
                labels_by_aid, req.labels_all, req.labels_any, req.labels_none,
            )

        # filters (duration / loopable / tags)
        candidate_ids = {a for a in candidate_ids
                         if _apply_filters(asset_meta[a].get("kind_meta", {}), req.filters)}

        if not candidate_ids:
            return SearchResults(query_id=self._log_query(project_row, req, []),
                                 results=[])

        # 5) 채널 점수 산출
        ordered = list(candidate_ids)
        id_to_idx = {aid: i for i, aid in enumerate(all_ids)}
        sem_raw = {a: float(cosine_all[id_to_idx[a]]) for a in ordered if a in id_to_idx}
        # 후보 중 임베딩 없는 경우는 0 처리
        for a in ordered:
            sem_raw.setdefault(a, 0.0)

        kw_raw_neg = {a: fts_raw.get(a, 0.0) for a in ordered}
        # bm25 는 낮을수록 좋음 — 부호 뒤집기
        kw_raw = {a: -v for a, v in kw_raw_neg.items()}
        # FTS 후보 아닌 행은 keyword 0 (정규화 후 자동 처리되지만 명시)
        kw_present_ids = set(fts_ids)
        kw_raw_filtered = {a: kw_raw[a] for a in ordered if a in kw_present_ids}
        kw_normalized = _normalize_minmax(kw_raw_filtered)
        kw_score = {a: kw_normalized.get(a, 0.0) for a in ordered}

        sem_normalized = _normalize_minmax(sem_raw)

        label_match = {
            a: _label_match_score(labels_by_aid.get(a, []),
                                  req.labels_all, req.labels_any, req.labels_none)
            for a in ordered
        }

        recency_raw = self.store.recent_assets_score(
            ordered, window_seconds=int(self.config.recency_window_seconds),
        )
        recency = {a: float(recency_raw.get(a, 0.0)) for a in ordered}

        # consistency
        consistency_results: dict[int, ConsistencyResult] = {}
        for a in ordered:
            pack_id = asset_meta[a]["pack_id"]
            pack_row = asset_meta[a]["pack_row"]
            agg = asset_meta[a]["pack_aggregate"]
            if summary is None:
                consistency_results[a] = ConsistencyResult(score=0.0)
            else:
                consistency_results[a] = self.consistency.score_asset(
                    project_id=project_row.id if project_row else 0,
                    asset=None,
                    pack_aggregate=agg or {},
                    summary=summary,
                    blocked_packs=blocked_packs,
                    pinned_pack_id=pinned_pack_id,
                    pack=pack_row,
                )

        # 6) 가중합
        w_sem = float(self.config.weight_semantic)
        w_kw = float(self.config.weight_keyword)
        w_label = (
            float(req.label_match_weight_override)
            if req.label_match_weight_override is not None
            else float(self.config.weight_label_match)
        )
        w_cons = (
            float(req.consistency_weight_override)
            if req.consistency_weight_override is not None
            else float(self.config.weight_consistency)
        )
        w_rec = float(self.config.weight_recency)

        final: dict[int, float] = {}
        breakdown: dict[int, dict[str, float]] = {}
        for a in ordered:
            s_sem = sem_normalized.get(a, 0.0) * w_sem
            s_kw = kw_score.get(a, 0.0) * w_kw
            s_label = label_match.get(a, 0.0) * w_label
            s_cons = consistency_results[a].score * w_cons
            s_rec = recency.get(a, 0.0) * w_rec
            # prefer_pack_id 보너스 +0.3 (스코프 안에서만)
            bonus = 0.0
            if req.prefer_pack_id is not None and asset_meta[a]["pack_id"] == req.prefer_pack_id:
                bonus = 0.3
            total = s_sem + s_kw + s_label + s_cons + s_rec + bonus
            final[a] = total
            breakdown[a] = {
                "semantic": s_sem,
                "keyword": s_kw,
                "label_match": s_label,
                "consistency": s_cons,
                "recency": s_rec,
            }
            if bonus:
                breakdown[a]["prefer_bonus"] = bonus

        # pinned_pack_id → 무조건 1순위 (consistency 1.0 으로 이미 끌어올림 + 보장)
        if pinned_pack_id is not None:
            for a in ordered:
                if asset_meta[a]["pack_id"] == pinned_pack_id:
                    final[a] = max(final[a], 1.0)

        # 7) 정렬 + top-N + 응답 빌드
        sorted_ids = sorted(ordered, key=lambda a: final[a], reverse=True)[:req.count]
        result_rows: list[ResultRow] = []
        for a in sorted_ids:
            cresult = consistency_results[a]
            matched = self._matched_labels(labels_by_aid.get(a, []), req)
            why = self._build_why(cresult, matched, asset_meta[a], summary)
            result_rows.append(ResultRow(
                asset_id=a,
                pack_id=asset_meta[a]["pack_id"],
                pack_name=asset_meta[a]["pack_name"],
                path=asset_meta[a]["path"],
                score=float(final[a]),
                score_breakdown=breakdown[a],
                matched_labels=matched,
                why=why,
                meta=asset_meta[a].get("kind_meta", {}),
            ))

        qid = self._log_query(project_row, req,
                              [(r.asset_id, r.score) for r in result_rows])
        return SearchResults(query_id=qid, results=result_rows)

    # ─── helpers ──────────────────────────────────────────────────────

    def _load_asset_meta(self, asset_ids: list[int], *, kind: str | None) -> dict[int, dict]:
        if not asset_ids:
            return {}
        placeholders = ",".join("?" * len(asset_ids))
        params: list = [int(x) for x in asset_ids]
        sql = (
            f"SELECT a.id, a.pack_id, a.path, a.kind, p.name, p.vendor, p.aggregate_meta "
            f"FROM assets a JOIN packs p ON p.id = a.pack_id "
            f"WHERE a.id IN ({placeholders})"
        )
        if kind is not None:
            sql += " AND a.kind = ?"
            params.append(kind)
        rows = self.store.conn.execute(sql, params).fetchall()
        import json as _json

        from .store import PackRow

        out: dict[int, dict] = {}
        for aid, pack_id, path, k, pname, pvendor, pagg in rows:
            try:
                agg = _json.loads(pagg) if pagg else {}
            except (ValueError, TypeError):
                agg = {}
            pack_row = PackRow(
                id=int(pack_id), name=pname, display_name=pname, vendor=pvendor,
                source_url=None, license=None, description=None,
                enabled=True, added_at=0, scanned_at=None,
            )
            # kind-specific meta (sound_meta for sound assets)
            kind_meta: dict[str, Any] = {}
            if k == "sound":
                srow = self.store.conn.execute(
                    "SELECT duration_ms, loopable FROM sound_meta WHERE asset_id = ?",
                    (int(aid),),
                ).fetchone()
                if srow:
                    kind_meta["duration_ms"] = int(srow[0])
                    kind_meta["loopable"] = bool(srow[1]) if srow[1] is not None else None
            out[int(aid)] = {
                "pack_id": int(pack_id),
                "pack_name": pname,
                "pack_row": pack_row,
                "path": path,
                "kind": k,
                "pack_aggregate": agg,
                "kind_meta": kind_meta,
            }
        return out

    def _matched_labels(
        self, asset_labels: list[LabelScore], req: SearchRequest
    ) -> list[dict]:
        all_filters = list(req.labels_all) + list(req.labels_any)
        if not all_filters:
            # 명시 필터 없으면 상위 3개 라벨을 근거로 노출
            top = sorted(asset_labels, key=lambda l: l.score, reverse=True)[:3]
            return [{"axis": l.axis, "label": l.label, "source": l.source,
                     "score": l.score} for l in top]
        requested = {(f.axis, f.label) for f in all_filters}
        matched = [l for l in asset_labels if (l.axis, l.label) in requested]
        return [{"axis": l.axis, "label": l.label, "source": l.source,
                 "score": l.score} for l in matched]

    def _build_why(
        self,
        cresult: ConsistencyResult,
        matched_labels: list[dict],
        asset_meta_one: dict,
        summary,
    ) -> str:
        parts: list[str] = []
        cwhy = self.consistency.format_why(cresult, asset_meta_one["pack_name"])
        if cwhy:
            parts.append(cwhy)
        elif summary is None or summary.total_uses == 0:
            parts.append("이 프로젝트의 첫 검색 — 통일성 가중치는 다음 채택 이후 적용됩니다")
        if matched_labels:
            label_str = ", ".join(
                f"{m['axis']}={m['label']}" for m in matched_labels[:4]
            )
            parts.append(f"매칭 라벨: {label_str}")
        return " · ".join(parts) if parts else ""

    def _log_query(
        self,
        project_row,
        req: SearchRequest,
        results: list[tuple[int, float]],
    ) -> int:
        pid = project_row.id if project_row else None
        return self.store.insert_search_query(pid, req.query, results)
