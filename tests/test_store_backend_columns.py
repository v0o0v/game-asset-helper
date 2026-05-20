"""M11 Phase 6 Task 6.1 — assets.backend_image/audio/embed 컬럼.

분석에 사용된 backend 이름을 per-asset 메타데이터로 저장. MCP find_asset
응답 + 검색 카드 배지에서 사용.

회귀 보호: 기존 row 는 backend_* = NULL 로 마이그레이션. SELECT 결과의
신규 필드는 AssetRow.backend_image/audio/embed 에 노출.
"""

from __future__ import annotations

from assetcache.core.store import Store


def _open_store(tmp_path) -> Store:
    store = Store(tmp_path / "test.db")
    store.initialize()
    return store


def _seed_pack_and_asset(store: Store) -> tuple[int, int]:
    """간단한 pack + asset 시드. (pack_id, asset_id) 반환."""
    from assetcache.core.manifest import PackManifest

    manifest = PackManifest(
        display_name="P", vendor="V", description="", source_url=None, license=None,
    )
    pack_id = store.upsert_pack("pack1", manifest, scanned_at=100)
    cur = store.conn.execute(
        "INSERT INTO assets (pack_id, path, kind, file_hash, file_size,"
        "                    added_at, analysis_state)"
        " VALUES (?, ?, 'sprite', 'h', 1, 100, 'pending')",
        (pack_id, "pack1/asset.png"),
    )
    asset_id = int(cur.lastrowid)
    return pack_id, asset_id


def test_migrate_m11_backend_columns_added(tmp_path):
    """initialize 후 assets 테이블에 backend_image/audio/embed 컬럼 존재."""
    store = _open_store(tmp_path)
    cur = store.conn.execute("PRAGMA table_info(assets)")
    cols = {r[1] for r in cur.fetchall()}
    assert "backend_image" in cols
    assert "backend_audio" in cols
    assert "backend_embed" in cols


def test_migrate_m11_backend_columns_idempotent(tmp_path):
    """initialize 를 두 번 호출해도 ALTER TABLE 중복 에러 없음."""
    store = _open_store(tmp_path)
    # 두 번째 initialize — 이미 컬럼 존재, ALTER 건너뛰어야
    store.initialize()
    cur = store.conn.execute("PRAGMA table_info(assets)")
    cols = [r[1] for r in cur.fetchall()]
    assert cols.count("backend_image") == 1
    assert cols.count("backend_audio") == 1
    assert cols.count("backend_embed") == 1


def test_legacy_row_has_null_backend_fields(tmp_path):
    """마이그레이션 직후 기존 row 의 backend_* 컬럼은 NULL → AssetRow 의 None."""
    store = _open_store(tmp_path)
    _, asset_id = _seed_pack_and_asset(store)
    row = store.get_asset_by_id(asset_id)
    assert row is not None
    assert row.backend_image is None
    assert row.backend_audio is None
    assert row.backend_embed is None


def test_mark_asset_backends_saves_all_three(tmp_path):
    """mark_asset_backends 가 3 필드 모두 저장 + 조회 가능."""
    store = _open_store(tmp_path)
    _, asset_id = _seed_pack_and_asset(store)
    store.mark_asset_backends(
        asset_id, image="gemini", audio="ollama", embed="openai"
    )
    row = store.get_asset_by_id(asset_id)
    assert row.backend_image == "gemini"
    assert row.backend_audio == "ollama"
    assert row.backend_embed == "openai"


def test_mark_asset_backends_partial_update(tmp_path):
    """일부만 명시 → 미명시 필드는 기존 값 유지."""
    store = _open_store(tmp_path)
    _, asset_id = _seed_pack_and_asset(store)
    # 1차: 3개 모두 셋
    store.mark_asset_backends(
        asset_id, image="ollama", audio="ollama", embed="ollama"
    )
    # 2차: image 만 gemini 로 변경 — 다른 두 개는 유지돼야
    store.mark_asset_backends(asset_id, image="gemini")
    row = store.get_asset_by_id(asset_id)
    assert row.backend_image == "gemini"
    assert row.backend_audio == "ollama"
    assert row.backend_embed == "ollama"


def test_mark_asset_backends_nonexistent_asset_no_crash(tmp_path):
    """없는 asset_id 호출도 silent — UPDATE 가 0 rows 영향."""
    store = _open_store(tmp_path)
    # 존재하지 않는 asset_id — 예외 없이 통과
    store.mark_asset_backends(99999, image="gemini")


def test_list_assets_includes_backend_fields(tmp_path):
    """list_assets 가 신규 backend_* 필드를 채워 반환."""
    store = _open_store(tmp_path)
    _, asset_id = _seed_pack_and_asset(store)
    store.mark_asset_backends(asset_id, image="claude")
    rows = store.list_assets()
    assert len(rows) >= 1
    found = next(r for r in rows if r.id == asset_id)
    assert found.backend_image == "claude"
    assert found.backend_audio is None


def test_assets_for_pack_includes_backend_fields(tmp_path):
    """assets_for_pack 도 동일."""
    store = _open_store(tmp_path)
    pack_id, asset_id = _seed_pack_and_asset(store)
    store.mark_asset_backends(asset_id, embed="openai")
    rows = store.assets_for_pack(pack_id)
    assert len(rows) == 1
    assert rows[0].backend_embed == "openai"
