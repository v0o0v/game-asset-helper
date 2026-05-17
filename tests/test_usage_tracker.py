"""M3 — UsageTracker (explicit + implicit top-1 + summary)."""

from __future__ import annotations

from dataclasses import replace

import pytest


@pytest.fixture
def tracker(store):
    from gah.config import Config
    from gah.core.usage_tracker import UsageTracker

    return UsageTracker(store, Config())


@pytest.fixture
def tracker_implicit_on(store):
    from gah.config import Config
    from gah.core.usage_tracker import UsageTracker

    cfg = Config(implicit_top1_enabled=True)
    return UsageTracker(store, cfg)


def test_record_explicit_returns_usage_id(populated_store, tracker):
    store, ids = populated_store
    p = store.upsert_project("proj1")
    uid = tracker.record_explicit(p.id, ids["hero"], query_id=None, context="test")
    assert isinstance(uid, int)
    assert uid > 0


def test_record_explicit_with_query_id_sets_source_explicit(populated_store, tracker):
    store, ids = populated_store
    p = store.upsert_project("proj1")
    qid = store.insert_search_query(p.id, "hero", [(ids["hero"], 0.9)])
    uid = tracker.record_explicit(p.id, ids["hero"], query_id=qid, context=None)
    row = store.conn.execute(
        "SELECT source FROM asset_usage WHERE id=?", (uid,)
    ).fetchone()
    assert row[0] == "explicit"


def test_implicit_off_returns_none(populated_store, tracker):
    store, ids = populated_store
    p = store.upsert_project("proj1")
    qid = store.insert_search_query(p.id, "hero", [(ids["hero"], 0.9)])
    result = tracker.record_implicit_top1(p.id, qid)
    assert result is None
    # No row was created.
    n = store.conn.execute(
        "SELECT COUNT(*) FROM asset_usage WHERE project_id=?", (p.id,)
    ).fetchone()[0]
    assert n == 0


def test_implicit_on_records_top1_of_last_query(populated_store, tracker_implicit_on):
    store, ids = populated_store
    p = store.upsert_project("proj1")
    qid = store.insert_search_query(p.id, "hero", [(ids["hero"], 0.9)])
    uid = tracker_implicit_on.record_implicit_top1(p.id, qid)
    assert uid is not None
    row = store.conn.execute(
        "SELECT asset_id, source FROM asset_usage WHERE id=?", (uid,)
    ).fetchone()
    assert row[0] == ids["hero"]
    assert row[1] == "implicit_top1"


def test_implicit_does_not_duplicate_for_same_query_id(populated_store, tracker_implicit_on):
    store, ids = populated_store
    p = store.upsert_project("proj1")
    qid = store.insert_search_query(p.id, "hero", [(ids["hero"], 0.9)])
    uid1 = tracker_implicit_on.record_implicit_top1(p.id, qid)
    uid2 = tracker_implicit_on.record_implicit_top1(p.id, qid)
    assert uid1 is not None
    assert uid2 is None  # second call is a no-op


def test_summary_empty_project_has_zero_total(populated_store, tracker):
    store, _ = populated_store
    p = store.upsert_project("proj_empty")
    summary = tracker.summary(p.id)
    assert summary.total_uses == 0


def test_summary_aggregates_correctly_after_two_uses(populated_store, tracker):
    store, ids = populated_store
    p = store.upsert_project("proj1")
    tracker.record_explicit(p.id, ids["hero"], query_id=None, context=None)
    tracker.record_explicit(p.id, ids["coin"], query_id=None, context=None)
    summary = tracker.summary(p.id)
    assert summary.total_uses == 2
    assert summary.pack_uses[ids["pack_a"]] == 2


def test_summary_dominant_style_picks_most_used_packs_style(populated_store, tracker):
    store, ids = populated_store
    p = store.upsert_project("proj1")
    # pack_a used 2×, pack_b used 1× → dominant = pack_a's main_style = pixel_art
    tracker.record_explicit(p.id, ids["hero"], query_id=None, context=None)
    tracker.record_explicit(p.id, ids["coin"], query_id=None, context=None)
    tracker.record_explicit(p.id, ids["menu_bg"], query_id=None, context=None)
    summary = tracker.summary(p.id)
    assert summary.dominant_style == "pixel_art"
