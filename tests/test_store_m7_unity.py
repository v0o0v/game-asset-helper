"""M7 — Store unity_imports CRUD + state 머신 invariant."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from gah.core.unity_import.types import UnityPackagePath


@pytest.fixture
def unity_path(tmp_path):
    pkg = tmp_path / "A.unitypackage"
    pkg.write_bytes(b"dummy")
    return UnityPackagePath(
        abs_path=pkg, publisher="A", category="B",
        asset_name="A", size=5, mtime=1700000000,
    )


def test_unity_imports_create_table_idempotent(store):
    store.initialize()  # 또는 store fixture 가 이미 initialized 일 수도
    store.initialize()  # 두 번 호출해도 OK


def test_insert_unity_import(store, unity_path):
    store.insert_unity_import(unity_path, first_seen_at=1, last_scanned_at=1)
    rows = store.list_unity_imports()
    assert len(rows) == 1
    assert rows[0].import_state == "discovered"


def test_upsert_unity_import(store, unity_path):
    store.insert_unity_import(unity_path, first_seen_at=1, last_scanned_at=1)
    new = UnityPackagePath(
        abs_path=unity_path.abs_path, publisher="A", category="B",
        asset_name="A", size=999, mtime=1800000000,
    )
    store.upsert_unity_import(new, last_scanned_at=2)
    row = store.get_unity_import_by_path(unity_path.abs_path)
    assert row.package_mtime == 1800000000
    assert row.package_size == 999


def test_update_unity_state_to_imported(store, unity_path):
    import time
    from gah.core.manifest import PackManifest

    # 실제 pack row 삽입 (FK 제약 충족)
    real_pack_id = store.upsert_pack(
        "test_pack_import",
        PackManifest(display_name=None, vendor=None, source_url=None, license=None, description=None),
        scanned_at=int(time.time()),
    )
    store.insert_unity_import(unity_path, first_seen_at=1, last_scanned_at=1)
    rows = store.list_unity_imports()
    store.update_unity_state(rows[0].id, "imported", pack_id=real_pack_id, imported_at=2)
    row = store.get_unity_import_by_id(rows[0].id)
    assert row.import_state == "imported"
    assert row.pack_id == real_pack_id
    assert row.imported_at == 2


def test_update_unity_state_resets_preview(store, unity_path):
    store.insert_unity_import(unity_path, first_seen_at=1, last_scanned_at=1)
    rows = store.list_unity_imports()
    store.update_unity_preview(rows[0].id, asset_count=10, image_count=8, sound_count=2)
    store.update_unity_state(rows[0].id, "discovered", reset_preview=True)
    row = store.get_unity_import_by_id(rows[0].id)
    assert row.preview_asset_count is None


def test_list_unity_imports_filter_state(store, unity_path, tmp_path):
    store.insert_unity_import(unity_path, first_seen_at=1, last_scanned_at=1)
    pkg2 = tmp_path / "B.unitypackage"
    pkg2.write_bytes(b"x")
    up2 = UnityPackagePath(
        abs_path=pkg2, publisher="A", category="B",
        asset_name="B", size=1, mtime=1700000000,
    )
    store.insert_unity_import(up2, first_seen_at=1, last_scanned_at=1)
    rows = store.list_unity_imports()
    store.update_unity_state(rows[0].id, "skipped")
    filt = store.list_unity_imports(state="skipped")
    assert len(filt) == 1


def test_list_unity_imports_offset_limit(store, tmp_path):
    for i in range(5):
        pkg = tmp_path / f"P{i}.unitypackage"
        pkg.write_bytes(b"x")
        up = UnityPackagePath(
            abs_path=pkg, publisher="X", category="Y",
            asset_name=f"P{i}", size=1, mtime=1700000000+i,
        )
        store.insert_unity_import(up, first_seen_at=1, last_scanned_at=1)
    page1 = store.list_unity_imports(offset=0, limit=2)
    page2 = store.list_unity_imports(offset=2, limit=2)
    assert len(page1) == 2 and len(page2) == 2
    assert page1[0].id != page2[0].id


def test_get_unity_import_by_path(store, unity_path):
    store.insert_unity_import(unity_path, first_seen_at=1, last_scanned_at=1)
    row = store.get_unity_import_by_path(unity_path.abs_path)
    assert row is not None
    assert row.asset_name == "A"


def test_get_unity_import_by_id_missing(store):
    assert store.get_unity_import_by_id(9999) is None


def test_touch_unity_import_updates_last_scanned(store, unity_path):
    store.insert_unity_import(unity_path, first_seen_at=1, last_scanned_at=1)
    rows = store.list_unity_imports()
    store.touch_unity_import(rows[0].id, last_scanned_at=999)
    row = store.get_unity_import_by_id(rows[0].id)
    assert row.last_scanned_at == 999
