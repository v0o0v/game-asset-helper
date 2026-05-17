"""UsageTracker — 명시 + 암묵 채택 이력 기록.

ProjectUsageSummary 는 ``store.py`` 가 source of truth — usage_tracker 는
re-export 한다. 그래서 ``from gah.core.usage_tracker import ProjectUsageSummary``
와 ``from gah.core.store import ProjectUsageSummary`` 둘 다 같은 객체.
"""

from __future__ import annotations

import logging

from .store import ProjectUsageSummary, Store

log = logging.getLogger(__name__)


__all__ = ["UsageTracker", "ProjectUsageSummary"]


class UsageTracker:
    def __init__(self, store: Store, config) -> None:
        self.store = store
        self.config = config

    # ----- 명시 채택 -----------------------------------------------

    def record_explicit(
        self,
        project_id: int,
        asset_id: int,
        *,
        query_id: int | None = None,
        context: str | None = None,
    ) -> int:
        pack_id = self._pack_id_for_asset(asset_id)
        if pack_id is None:
            # asset 이 사라졌을 가능성 — 안전하게 0으로 폴백.
            log.warning("record_explicit: asset_id=%s has no pack row", asset_id)
            pack_id = 0
        return self.store.record_asset_use(
            project_id, asset_id, pack_id, source="explicit", context=context,
        )

    # ----- 암묵 top1 추정 ------------------------------------------

    def record_implicit_top1(self, project_id: int, query_id: int) -> int | None:
        if not bool(getattr(self.config, "implicit_top1_enabled", False)):
            return None
        pair = self.store.last_query_top1_for_project(project_id)
        if pair is None:
            return None
        last_qid, asset_id = pair
        if last_qid != query_id:
            # 다른 쿼리에 대한 호출 — 동일 query_id 만 처리.
            return None
        # 같은 query_id 로 이미 implicit_top1 행이 있으면 중복 방지.
        existing = self.store.conn.execute(
            "SELECT 1 FROM asset_usage "
            "WHERE project_id = ? AND asset_id = ? AND source = 'implicit_top1' "
            "LIMIT 1",
            (project_id, asset_id),
        ).fetchone()
        if existing:
            return None
        pack_id = self._pack_id_for_asset(asset_id) or 0
        return self.store.record_asset_use(
            project_id, asset_id, pack_id, source="implicit_top1", context=None,
        )

    # ----- 요약 -----------------------------------------------------

    def summary(self, project_id: int) -> ProjectUsageSummary:
        return self.store.project_usage_summary(project_id)

    # ----- 내부 헬퍼 ------------------------------------------------

    def _pack_id_for_asset(self, asset_id: int) -> int | None:
        row = self.store.conn.execute(
            "SELECT pack_id FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
        return int(row[0]) if row else None
