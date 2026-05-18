"""M7 — Store 프로젝트 / 사용 이력 / 분포 / 선호도 + I-5 격리."""
from __future__ import annotations

import time

import pytest


def _make_project(store, ext_id="D:/Unity/A", display="A"):
    return store.upsert_project_id(external_id=ext_id, display_name=display)


def test_upsert_project_new(store):
    pid = _make_project(store)
    assert pid > 0


def test_upsert_project_existing_updates_display(store):
    pid1 = _make_project(store, "D:/X", "Old")
    pid2 = _make_project(store, "D:/X", "New")
    assert pid1 == pid2
    rows = store.list_projects_with_summary()
    assert any(r.display_name == "New" for r in rows)


def test_list_projects_with_summary(store):
    pid = _make_project(store)
    rows = store.list_projects_with_summary()
    assert len(rows) >= 1
    assert rows[0].asset_count >= 0


def test_get_project_asset_usage_empty(store):
    pid = _make_project(store)
    items = store.get_project_asset_usage(project_id=pid)
    assert items == []


def test_get_project_pack_distribution_top_n(store):
    pid = _make_project(store)
    dist = store.get_project_pack_distribution(project_id=pid, top_n=5)
    assert dist == []


def test_get_project_asset_preferences_default_sort(store):
    pid = _make_project(store)
    rows = store.get_project_asset_preferences(project_id=pid)
    assert isinstance(rows, list)


def test_preference_score_formula(store, asset_factory):
    """asset_X 에 positive feedback (weight=+0.3) 2회 + usage 3회
    composite = 0.6 + 0.1 * 3 = 0.9"""
    pid = _make_project(store)
    asset_id = asset_factory()
    asset_row = store.get_asset_by_id(asset_id)
    # feedback 2 회 (weight=+0.3 each)
    store.insert_feedback_record(
        project_id=pid, asset_id=asset_id, query_id=None,
        reason="positive", weight=0.3,
    )
    store.insert_feedback_record(
        project_id=pid, asset_id=asset_id, query_id=None,
        reason="positive", weight=0.3,
    )
    # usage 3 회
    for i in range(3):
        store.record_asset_use(
            project_id=pid, asset_id=asset_id,
            pack_id=asset_row.pack_id,
            source="explicit",
            used_at=int(time.time()) + i,
        )
    rows = store.get_project_asset_preferences(project_id=pid, sort="score_desc")
    row = next(r for r in rows if r.asset_id == asset_id)
    assert abs(row.composite_score - 0.9) < 1e-9


def test_preference_isolation_i5(store, asset_factory):
    """I-5: project_A 의 weight 가 project_B 의 점수에 미반영."""
    pa = _make_project(store, "D:/A", "A")
    pb = _make_project(store, "D:/B", "B")
    asset_id = asset_factory()
    store.insert_feedback_record(
        project_id=pa, asset_id=asset_id, query_id=None,
        reason="negative", weight=-0.5,
    )
    rows_b = store.get_project_asset_preferences(project_id=pb)
    matching_b = [r for r in rows_b if r.asset_id == asset_id]
    if matching_b:
        assert matching_b[0].composite_score == 0


def test_preference_sort_options(store):
    pid = _make_project(store)
    for s in ("score_desc", "score_asc", "usage_desc", "recent_desc"):
        rows = store.get_project_asset_preferences(project_id=pid, sort=s)
        assert isinstance(rows, list)


def test_preference_pagination(store, asset_factory):
    pid = _make_project(store)
    for i in range(5):
        aid = asset_factory(path=f"asset{i}.png")
        asset_row = store.get_asset_by_id(aid)
        store.record_asset_use(
            project_id=pid, asset_id=aid,
            pack_id=asset_row.pack_id,
            source="explicit", used_at=int(time.time()) + i,
        )
    page = store.get_project_asset_preferences(project_id=pid, offset=0, limit=3)
    assert len(page) <= 3


def test_record_asset_use_source_user_web(store, asset_factory):
    """Task 2.3: source='user_web' 으로 INSERT 후 조회 시 'user_web' 반환."""
    pid = _make_project(store, "D:/Test", "Test")
    asset_id = asset_factory()
    asset_row = store.get_asset_by_id(asset_id)
    uid = store.record_asset_use(
        project_id=pid, asset_id=asset_id,
        pack_id=asset_row.pack_id,
        source="user_web",
    )
    row = store.conn.execute(
        "SELECT source FROM asset_usage WHERE id = ?", (uid,)
    ).fetchone()
    assert row is not None
    assert row[0] == "user_web"
