"""Tests for gah.core.store — SQLite schema + pack/asset CRUD."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _all_table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {r[0] for r in rows}


def test_initialize_creates_required_tables(store) -> None:
    names = _all_table_names(store.conn)
    assert {"packs", "assets", "tags", "asset_tags"}.issubset(names)
    # M7 — unity_imports 테이블이 initialize() 에서 생성되어야 한다.
    assert "unity_imports" in names, "unity_imports 테이블이 M7 에서 추가되어야 함"


def test_pragma_journal_mode_is_wal(store) -> None:
    mode = store.conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert str(mode).lower() == "wal"


def test_initialize_is_idempotent(tmp_appdata: Path) -> None:
    from gah.core.store import Store

    s = Store(tmp_appdata / "x.db")
    s.initialize()
    s.initialize()  # must not raise
    names = _all_table_names(s.conn)
    assert {"packs", "assets"}.issubset(names)
    s.close()


def test_upsert_pack_inserts_then_updates(store) -> None:
    from gah.core.manifest import PackManifest

    m1 = PackManifest(display_name="Demo", vendor="kenney", source_url=None, license="CC0", description=None)
    pid = store.upsert_pack("kenney_demo", m1, scanned_at=100)
    assert isinstance(pid, int)

    m2 = PackManifest(display_name="Demo Renamed", vendor="kenney", source_url="https://x", license="CC0", description="new")
    pid_again = store.upsert_pack("kenney_demo", m2, scanned_at=200)
    assert pid_again == pid

    packs = store.list_packs()
    assert len(packs) == 1
    only = packs[0]
    assert only.name == "kenney_demo"
    assert only.display_name == "Demo Renamed"
    assert only.source_url == "https://x"
    assert only.scanned_at == 200


def test_upsert_pack_returns_stable_id(store) -> None:
    from gah.core.manifest import PackManifest

    m = PackManifest(None, None, None, None, None)
    pid_a = store.upsert_pack("alpha", m, scanned_at=0)
    pid_b = store.upsert_pack("beta", m, scanned_at=0)
    pid_a2 = store.upsert_pack("alpha", m, scanned_at=1)
    assert pid_a == pid_a2
    assert pid_a != pid_b


def test_delete_pack_cascades_assets(store) -> None:
    from gah.core.manifest import PackManifest

    pid = store.upsert_pack("p", PackManifest(None, None, None, None, None), scanned_at=0)
    store.upsert_asset(pid, "p/a.png", "sprite", "h1", 10, added_at=0)
    store.upsert_asset(pid, "p/b.wav", "sound", "h2", 20, added_at=0)

    store.delete_pack(pid)
    rows = store.conn.execute("SELECT COUNT(*) FROM assets").fetchone()
    assert rows[0] == 0, "asset rows should cascade away with the pack"


def test_upsert_asset_sets_pending_state(store) -> None:
    from gah.core.manifest import PackManifest

    pid = store.upsert_pack("p", PackManifest(None, None, None, None, None), scanned_at=0)
    aid = store.upsert_asset(pid, "p/a.png", "sprite", "deadbeef", 100, added_at=0)
    row = store.conn.execute(
        "SELECT analysis_state, analyzed_at, kind FROM assets WHERE id=?", (aid,)
    ).fetchone()
    assert row[0] == "pending"
    assert row[1] is None
    assert row[2] == "sprite"


def test_upsert_asset_with_same_hash_is_noop(store) -> None:
    from gah.core.manifest import PackManifest

    pid = store.upsert_pack("p", PackManifest(None, None, None, None, None), scanned_at=0)
    aid = store.upsert_asset(pid, "p/a.png", "sprite", "hash-A", 100, added_at=0)

    # pretend M2 analysed it
    store.conn.execute(
        "UPDATE assets SET analysis_state='ok', analyzed_at=42 WHERE id=?", (aid,)
    )

    aid2 = store.upsert_asset(pid, "p/a.png", "sprite", "hash-A", 100, added_at=999)
    assert aid2 == aid
    row = store.conn.execute(
        "SELECT analysis_state, analyzed_at FROM assets WHERE id=?", (aid,)
    ).fetchone()
    assert row[0] == "ok"
    assert row[1] == 42


def test_upsert_asset_with_changed_hash_resets_analysis(store) -> None:
    from gah.core.manifest import PackManifest

    pid = store.upsert_pack("p", PackManifest(None, None, None, None, None), scanned_at=0)
    aid = store.upsert_asset(pid, "p/a.png", "sprite", "hash-A", 100, added_at=0)
    store.conn.execute(
        "UPDATE assets SET analysis_state='ok', analyzed_at=42 WHERE id=?", (aid,)
    )

    store.upsert_asset(pid, "p/a.png", "sprite", "hash-B", 200, added_at=0)
    row = store.conn.execute(
        "SELECT analysis_state, analyzed_at, file_hash, file_size FROM assets WHERE id=?", (aid,)
    ).fetchone()
    assert row[0] == "pending"
    assert row[1] is None
    assert row[2] == "hash-B"
    assert row[3] == 200


def test_delete_assets_outside_removes_missing_only(store) -> None:
    from gah.core.manifest import PackManifest

    pid = store.upsert_pack("p", PackManifest(None, None, None, None, None), scanned_at=0)
    store.upsert_asset(pid, "p/keep.png", "sprite", "h1", 1, added_at=0)
    store.upsert_asset(pid, "p/gone.png", "sprite", "h2", 1, added_at=0)
    store.upsert_asset(pid, "p/also_keep.wav", "sound", "h3", 1, added_at=0)

    store.delete_assets_outside(pid, kept_rel_paths={"p/keep.png", "p/also_keep.wav"})

    remaining = {r.path for r in store.assets_for_pack(pid)}
    assert remaining == {"p/keep.png", "p/also_keep.wav"}


def test_list_packs_returns_dataclasses(store) -> None:
    from gah.core.manifest import PackManifest
    from gah.core.store import PackRow

    store.upsert_pack(
        "p1",
        PackManifest(display_name="Pack One", vendor="kenney", source_url=None, license="CC0", description=None),
        scanned_at=10,
    )
    packs = store.list_packs()
    assert len(packs) == 1
    assert isinstance(packs[0], PackRow)
    assert packs[0].name == "p1"
    assert packs[0].vendor == "kenney"


def test_assets_for_pack_returns_in_path_order(store) -> None:
    from gah.core.manifest import PackManifest

    pid = store.upsert_pack("p", PackManifest(None, None, None, None, None), scanned_at=0)
    for rel in ("p/zeta.png", "p/alpha.png", "p/mu.wav"):
        store.upsert_asset(pid, rel, "sprite" if rel.endswith(".png") else "sound", "h", 1, added_at=0)

    paths = [r.path for r in store.assets_for_pack(pid)]
    assert paths == sorted(paths)


# ─── get_pack_by_id (Phase 3 cleanup 항목 1) ─────────────────────────────


def test_get_pack_by_id_returns_pack_row(store) -> None:
    """존재하는 pack_id → PackRow 반환."""
    from gah.core.manifest import PackManifest
    from gah.core.store import PackRow

    pid = store.upsert_pack(
        "kenney_demo",
        PackManifest(display_name="Kenney Demo", vendor="kenney", source_url=None, license="CC0", description=None),
        scanned_at=5,
    )
    row = store.get_pack_by_id(pid)
    assert row is not None
    assert isinstance(row, PackRow)
    assert row.id == pid
    assert row.name == "kenney_demo"
    assert row.vendor == "kenney"


def test_get_pack_by_id_returns_none_for_missing(store) -> None:
    """존재하지 않는 pack_id → None."""
    assert store.get_pack_by_id(99999) is None


# ─── get_saved_search_by_id (Phase 3 cleanup 항목 2) ─────────────────────


def test_get_saved_search_by_id_returns_row(store) -> None:
    """존재하는 saved_search id → SavedSearchRow 반환."""
    import json
    from gah.core.store import SavedSearchRow

    store.upsert_saved_search(
        project_id=None,
        name="my_search",
        query_json=json.dumps({"query": "hero", "count": 10}),
    )
    # id 는 list_saved_searches 로 조회
    rows = store.list_saved_searches(project_id=None)
    assert len(rows) == 1
    ss_id = rows[0].id

    result = store.get_saved_search_by_id(ss_id)
    assert result is not None
    assert isinstance(result, SavedSearchRow)
    assert result.id == ss_id
    assert result.name == "my_search"


def test_get_saved_search_by_id_returns_none_for_missing(store) -> None:
    """존재하지 않는 id → None."""
    assert store.get_saved_search_by_id(99999) is None
