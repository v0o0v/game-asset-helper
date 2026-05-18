"""M7 — UnityImporter 추출 + pack.json + state 머신 회귀."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from gah.core.unity_import.importer import UnityImporter
from gah.core.unity_import.scanner import UnityAssetStoreScanner
from tests.fixtures.unity.make_unitypackage import make_fixture_unitypackage


@pytest.fixture
def cache_with_pkg(tmp_path):
    pub = tmp_path / "Pixel Studios" / "Sprites"
    pub.mkdir(parents=True)
    make_fixture_unitypackage(pub / "Mega Platformer Pack.unitypackage", include_psd=False)
    return tmp_path


@pytest.fixture
def library_dir(tmp_path):
    lib = tmp_path / "library"
    lib.mkdir()
    return lib


def _discover_and_get_id(store, cache_dir):
    scanner = UnityAssetStoreScanner(store=store)
    scanner.run_once(cache_path=cache_dir)
    return store.list_unity_imports()[0].id


def test_import_physical_copy_to_library(cache_with_pkg, library_dir, store):
    uid = _discover_and_get_id(store, cache_with_pkg)
    importer = UnityImporter(store=store, library_root=library_dir)
    result = importer.import_package(uid)
    assert result.state == "imported"
    pack_dir = library_dir / "mega_platformer_pack"
    assert (pack_dir / "Assets" / "Sprites" / "idle.png").is_file()
    assert (pack_dir / "Assets" / "Sounds" / "jump.wav").is_file()


def test_pack_json_auto_generated(cache_with_pkg, library_dir, store):
    uid = _discover_and_get_id(store, cache_with_pkg)
    importer = UnityImporter(store=store, library_root=library_dir)
    importer.import_package(uid)
    manifest = library_dir / "mega_platformer_pack" / "pack.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["vendor"] == "Pixel Studios"
    assert data["license"] == "Unity Asset Store EULA"
    assert data["source"] == "unity_asset_store_cache"


def test_state_imported_after_success(cache_with_pkg, library_dir, store):
    uid = _discover_and_get_id(store, cache_with_pkg)
    importer = UnityImporter(store=store, library_root=library_dir)
    importer.import_package(uid)
    row = store.get_unity_import_by_id(uid)
    assert row.import_state == "imported"
    assert row.imported_at is not None


def test_state_failed_on_error(cache_with_pkg, library_dir, store, monkeypatch):
    uid = _discover_and_get_id(store, cache_with_pkg)
    importer = UnityImporter(store=store, library_root=library_dir)
    def raise_oops(*a, **kw):
        raise OSError("disk full")
    monkeypatch.setattr("gah.core.unity_import.importer.extract_targets", raise_oops)
    result = importer.import_package(uid)
    assert result.state == "failed"
    row = store.get_unity_import_by_id(uid)
    assert row.import_state == "failed"
    assert row.import_error is not None


def test_pack_name_normalization(cache_with_pkg, library_dir, store):
    uid = _discover_and_get_id(store, cache_with_pkg)
    importer = UnityImporter(store=store, library_root=library_dir)
    importer.import_package(uid)
    # "Mega Platformer Pack" → "mega_platformer_pack"
    assert (library_dir / "mega_platformer_pack").is_dir()


def test_import_pending_state_then_imported(cache_with_pkg, library_dir, store):
    uid = _discover_and_get_id(store, cache_with_pkg)
    store.update_unity_state(uid, "import_pending")
    importer = UnityImporter(store=store, library_root=library_dir)
    result = importer.import_package(uid)
    assert result.state == "imported"


def test_idempotent_import(cache_with_pkg, library_dir, store):
    """이미 imported 인 row 를 다시 import 호출해도 noop."""
    uid = _discover_and_get_id(store, cache_with_pkg)
    importer = UnityImporter(store=store, library_root=library_dir)
    r1 = importer.import_package(uid)
    # 첫 번째 호출은 pack_id=None 으로 imported (워처가 pack_id 를 채움)
    # 두 번째 호출은 row.pack_id 가 None 이면 다시 추출 시도
    # 이 테스트는 단순히 두 번 호출해도 state=imported 유지 검증
    r2 = importer.import_package(uid)
    assert r1.state == "imported"
    assert r2.state == "imported"


def test_imported_at_recorded(cache_with_pkg, library_dir, store):
    uid = _discover_and_get_id(store, cache_with_pkg)
    importer = UnityImporter(store=store, library_root=library_dir)
    before = int(time.time())
    importer.import_package(uid)
    after = int(time.time())
    row = store.get_unity_import_by_id(uid)
    assert before <= row.imported_at <= after
