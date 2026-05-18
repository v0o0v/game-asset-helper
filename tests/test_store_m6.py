"""M6 — Store animations_json 컬럼 + get_sprite_meta + update_asset_kind."""
from __future__ import annotations

import json

import pytest

from gah.core.manifest import PackManifest
from gah.core.store import SpriteMeta, Store


@pytest.fixture()
def store(tmp_path):
    s = Store(tmp_path / "metadata.db")
    s.initialize()
    yield s
    s.close()


def _seed_pack_and_asset(store: Store) -> int:
    pid = store.upsert_pack(
        "pack1",
        PackManifest(None, "kenney", None, None, None),
        scanned_at=1,
    )
    aid = store.upsert_asset(
        pid, "pack1/hero.png", "sprite", "h1", 1024,
        added_at=1,
    )
    return aid


def test_animations_json_column_exists(store):
    rows = store.conn.execute("PRAGMA table_info(sprite_meta)").fetchall()
    cols = {r[1] for r in rows}
    assert "animations_json" in cols


def test_save_sprite_meta_round_trip_animations(store):
    aid = _seed_pack_and_asset(store)
    anim = {"walk": {"start_frame": 0, "end_frame": 7,
                     "fps_hint": 12, "source": "json_tag"}}
    meta = SpriteMeta(
        width=256, height=32, has_alpha=True, is_pixel_art=False,
        dominant_colors=["#000000"],
        frame_w=32, frame_h=32, frame_count=8,
        animation_tags=["walk"], animations_json=anim,
    )
    store.save_sprite_meta(aid, meta)
    got = store.get_sprite_meta(aid)
    assert got is not None
    assert got.animations_json == anim
    assert got.frame_count == 8


def test_save_sprite_meta_animations_none(store):
    aid = _seed_pack_and_asset(store)
    meta = SpriteMeta(
        width=32, height=32, has_alpha=True, is_pixel_art=True,
        dominant_colors=["#000000"],
    )
    store.save_sprite_meta(aid, meta)
    got = store.get_sprite_meta(aid)
    assert got is not None
    assert got.animations_json is None
    assert got.frame_count is None


def test_get_sprite_meta_missing_asset(store):
    assert store.get_sprite_meta(999_999) is None


def test_update_asset_kind(store):
    aid = _seed_pack_and_asset(store)
    store.update_asset_kind(aid, "spritesheet")
    row = store.conn.execute(
        "SELECT kind FROM assets WHERE id = ?", (aid,)
    ).fetchone()
    assert row[0] == "spritesheet"


def test_migration_idempotent(tmp_path):
    s = Store(tmp_path / "metadata.db")
    s.initialize()
    s.initialize()  # 두 번 호출도 OK
    rows = s.conn.execute("PRAGMA table_info(sprite_meta)").fetchall()
    cols = {r[1] for r in rows}
    assert "animations_json" in cols
    s.close()


def test_legacy_db_without_animations_column(tmp_path):
    # 컬럼이 없던 옛 DB 를 시뮬레이션 — initialize() 가 컬럼 추가
    import sqlite3
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE sprite_meta (
        asset_id INTEGER PRIMARY KEY, width INTEGER, height INTEGER,
        has_alpha INTEGER, is_pixel_art INTEGER, dominant_colors TEXT,
        frame_w INTEGER, frame_h INTEGER, frame_count INTEGER,
        animation_tags TEXT
    )""")
    conn.commit()
    conn.close()
    s = Store(db)
    s.initialize()  # ADD COLUMN
    rows = s.conn.execute("PRAGMA table_info(sprite_meta)").fetchall()
    cols = {r[1] for r in rows}
    assert "animations_json" in cols
    s.close()


def test_animations_json_dict_serialization(store):
    aid = _seed_pack_and_asset(store)
    payload = {
        "walk": {"start_frame": 0, "end_frame": 3, "fps_hint": 12, "source": "gemma_inferred"},
        "idle": {"start_frame": 4, "end_frame": 7, "fps_hint": 8, "source": "gemma_inferred"},
    }
    meta = SpriteMeta(
        width=128, height=32, has_alpha=True, is_pixel_art=False,
        dominant_colors=[],
        frame_w=16, frame_h=32, frame_count=8,
        animation_tags=["walk", "idle"], animations_json=payload,
    )
    store.save_sprite_meta(aid, meta)
    raw = store.conn.execute(
        "SELECT animations_json FROM sprite_meta WHERE asset_id = ?",
        (aid,)
    ).fetchone()[0]
    assert json.loads(raw) == payload
