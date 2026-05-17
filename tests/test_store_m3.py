"""M3 — Store 마이그레이션 (projects / asset_usage / search_queries) + 신규 메서드."""

from __future__ import annotations

import json
import time

import numpy as np
import pytest


# ─────────────────────────────────────────────────────────────────────
# Schema migration
# ─────────────────────────────────────────────────────────────────────


def _table_names(store) -> set[str]:
    cur = store.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {row[0] for row in cur.fetchall()}


def test_initialize_creates_m3_tables(store):
    tables = _table_names(store)
    assert {"projects", "asset_usage", "search_queries"} <= tables


def test_initialize_is_idempotent_with_m1_m2_tables(store):
    store.initialize()  # second call must not raise
    tables = _table_names(store)
    assert {"packs", "assets", "labels", "projects", "asset_usage"} <= tables


# ─────────────────────────────────────────────────────────────────────
# projects (upsert / pin / blocked)
# ─────────────────────────────────────────────────────────────────────


def test_upsert_project_returns_row_with_id(store):
    row = store.upsert_project("D:/Unity/MyGame", display_name="My Game")
    assert row.id > 0
    assert row.external_id == "D:/Unity/MyGame"
    assert row.display_name == "My Game"
    assert row.first_seen > 0


def test_upsert_project_updates_last_seen_on_second_call(store):
    row1 = store.upsert_project("D:/Unity/MyGame", display_name="A")
    time.sleep(0.01)
    row2 = store.upsert_project("D:/Unity/MyGame", display_name="A")
    assert row1.id == row2.id
    assert row2.last_seen >= row1.last_seen


def test_upsert_project_preserves_display_name_when_arg_none(store):
    store.upsert_project("D:/Unity/MyGame", display_name="Original")
    row = store.upsert_project("D:/Unity/MyGame", display_name=None)
    assert row.display_name == "Original"


def test_set_project_pin_persists(populated_store):
    store, ids = populated_store
    p = store.upsert_project("proj1")
    store.set_project_pin(p.id, ids["pack_a"])
    row = store.get_project("proj1")
    assert row.pinned_pack_id == ids["pack_a"]


def test_set_blocked_packs_json_roundtrip(populated_store):
    store, ids = populated_store
    p = store.upsert_project("proj1")
    store.set_blocked_packs(p.id, [ids["pack_b"]])
    row = store.get_project("proj1")
    assert row.blocked_packs == [ids["pack_b"]]


# ─────────────────────────────────────────────────────────────────────
# asset_usage
# ─────────────────────────────────────────────────────────────────────


def test_record_asset_use_increments_usage_count(populated_store):
    store, ids = populated_store
    p = store.upsert_project("proj1")
    uid1 = store.record_asset_use(p.id, ids["hero"], ids["pack_a"], source="explicit")
    uid2 = store.record_asset_use(p.id, ids["coin"], ids["pack_a"], source="explicit")
    assert uid1 != uid2
    cur = store.conn.execute(
        "SELECT COUNT(*) FROM asset_usage WHERE project_id=?", (p.id,)
    )
    assert cur.fetchone()[0] == 2


def test_project_usage_summary_aggregates_pack_and_vendor(populated_store):
    store, ids = populated_store
    p = store.upsert_project("proj1")
    store.record_asset_use(p.id, ids["hero"], ids["pack_a"], source="explicit")
    store.record_asset_use(p.id, ids["coin"], ids["pack_a"], source="explicit")
    store.record_asset_use(p.id, ids["menu_bg"], ids["pack_b"], source="explicit")

    summary = store.project_usage_summary(p.id)
    assert summary.pack_uses[ids["pack_a"]] == 2
    assert summary.pack_uses[ids["pack_b"]] == 1
    assert summary.vendor_uses["kenney"] == 2
    assert summary.vendor_uses["craftpix"] == 1
    assert summary.total_uses == 3
    assert summary.distinct_packs == 2


def test_project_usage_summary_empty_project_returns_defaults(store):
    p = store.upsert_project("proj_empty")
    summary = store.project_usage_summary(p.id)
    assert summary.pack_uses == {}
    assert summary.vendor_uses == {}
    assert summary.total_uses == 0
    assert summary.distinct_packs == 0
    assert summary.dominant_style is None
    assert summary.dominant_palette == []


# ─────────────────────────────────────────────────────────────────────
# search_queries
# ─────────────────────────────────────────────────────────────────────


def test_last_query_top1_returns_none_when_no_query(store):
    p = store.upsert_project("proj_no_query")
    assert store.last_query_top1_for_project(p.id, within_seconds=3600) is None


def test_last_query_top1_returns_recent_only(populated_store):
    store, ids = populated_store
    p = store.upsert_project("proj1")
    qid = store.insert_search_query(p.id, "dark cave bgm", [(ids["bgm_loop"], 0.91)])
    # immediate fetch — within 3600s window
    pair = store.last_query_top1_for_project(p.id, within_seconds=3600)
    assert pair == (qid, ids["bgm_loop"])
    # tiny window — same call should now return None
    assert store.last_query_top1_for_project(p.id, within_seconds=0) is None


def test_insert_search_query_persists_json(populated_store):
    store, ids = populated_store
    p = store.upsert_project("proj1")
    qid = store.insert_search_query(
        p.id, "hero", [(ids["hero"], 0.91), (ids["coin"], 0.75)]
    )
    row = store.conn.execute(
        "SELECT query_text, results_json FROM search_queries WHERE id=?", (qid,)
    ).fetchone()
    assert row[0] == "hero"
    data = json.loads(row[1])
    assert data == [[ids["hero"], 0.91], [ids["coin"], 0.75]]


# ─────────────────────────────────────────────────────────────────────
# fts_search + semantic_candidates_load + asset_labels_for + pack_aggregate
# ─────────────────────────────────────────────────────────────────────


def test_fts_search_matches_label_prefix(populated_store):
    store, ids = populated_store
    hits = store.fts_search("label:pixel_art", kind=None, pack_id=None,
                            exclude_pack_ids=[], k=20)
    hit_ids = {row[0] for row in hits}
    assert ids["hero"] in hit_ids
    assert ids["coin"] in hit_ids


def test_fts_search_excludes_blocked_packs(populated_store):
    store, ids = populated_store
    hits = store.fts_search(
        "label:pixel_art", kind=None, pack_id=None,
        exclude_pack_ids=[ids["pack_a"]], k=20,
    )
    hit_ids = {row[0] for row in hits}
    assert ids["hero"] not in hit_ids
    assert ids["coin"] not in hit_ids


def test_fts_search_filters_by_kind(populated_store):
    store, ids = populated_store
    hits = store.fts_search("category:character", kind="sprite", pack_id=None,
                            exclude_pack_ids=[], k=20)
    hit_ids = {row[0] for row in hits}
    assert ids["hero"] in hit_ids
    # sound asset (jump.wav) has no 'character' label, must not appear
    assert ids["jump"] not in hit_ids


def test_semantic_candidates_load_blob_roundtrip(populated_store):
    store, ids = populated_store
    asset_ids, matrix, model_id = store.semantic_candidates_load()
    assert len(asset_ids) == 6  # 2 packs × 3 assets
    assert matrix.shape == (6, 768)
    assert matrix.dtype == np.float32
    # round-trip stability: pulling a subset returns the same vectors row-wise.
    subset_ids, sub_matrix, _ = store.semantic_candidates_load(asset_ids=[ids["hero"]])
    assert subset_ids == [ids["hero"]]
    hero_row = matrix[asset_ids.index(ids["hero"])]
    np.testing.assert_array_equal(sub_matrix[0], hero_row)


def test_asset_labels_for_returns_all_axes_per_asset(populated_store):
    store, ids = populated_store
    labels = store.asset_labels_for([ids["hero"], ids["coin"]])
    assert {label.axis for label in labels[ids["hero"]]} == {"category", "style"}
    assert {label.axis for label in labels[ids["coin"]]} == {"category", "style"}


def test_pack_aggregate_decodes_json(populated_store):
    store, ids = populated_store
    agg = store.pack_aggregate(ids["pack_a"])
    assert agg is not None
    assert agg["main_style"] == "pixel_art"
    assert "#aa1122" in agg["palette"]


def test_recent_assets_score_within_zero_one_using_analyzed_at(populated_store):
    store, ids = populated_store
    scores = store.recent_assets_score(
        [ids["hero"], ids["coin"]], window_seconds=30 * 24 * 3600
    )
    assert all(0.0 <= s <= 1.0 for s in scores.values())
    assert set(scores.keys()) == {ids["hero"], ids["coin"]}


def test_delete_project_cascades_usage_and_queries(populated_store):
    store, ids = populated_store
    p = store.upsert_project("proj_doomed")
    store.record_asset_use(p.id, ids["hero"], ids["pack_a"], source="explicit")
    store.insert_search_query(p.id, "hero", [(ids["hero"], 0.9)])

    with store.write_lock:
        store.conn.execute("DELETE FROM projects WHERE id=?", (p.id,))
        store.conn.commit()

    n_usage = store.conn.execute(
        "SELECT COUNT(*) FROM asset_usage WHERE project_id=?", (p.id,)
    ).fetchone()[0]
    n_queries = store.conn.execute(
        "SELECT COUNT(*) FROM search_queries WHERE project_id=?", (p.id,)
    ).fetchone()[0]
    assert n_usage == 0
    assert n_queries == 0
