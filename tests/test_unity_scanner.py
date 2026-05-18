"""M7 — UnityAssetStoreScanner state 머신 + walk 회귀."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from gah.core.unity_import.scanner import UnityAssetStoreScanner
from tests.fixtures.unity.make_unitypackage import make_fixture_unitypackage


@pytest.fixture
def cache_dir(tmp_path):
    """가짜 캐시 디렉터리 구조: <Publisher>/<Category>/<AssetName>.unitypackage"""
    pub = tmp_path / "Pixel Studios" / "Sprites"
    pub.mkdir(parents=True)
    make_fixture_unitypackage(pub / "Mega Platformer Pack.unitypackage")
    pub2 = tmp_path / "Kenney" / "Sounds"
    pub2.mkdir(parents=True)
    make_fixture_unitypackage(pub2 / "UI Sound Pack.unitypackage")
    return tmp_path


def test_walk_picks_up_unitypackage_only(cache_dir, store):
    (cache_dir / "NotAPackage.zip").write_bytes(b"x")
    scanner = UnityAssetStoreScanner(store=store)
    result = scanner.run_once(cache_path=cache_dir)
    assert result.scanned == 2


def test_first_scan_marks_new_discovered(cache_dir, store):
    scanner = UnityAssetStoreScanner(store=store)
    result = scanner.run_once(cache_path=cache_dir)
    assert result.new == 2
    rows = store.list_unity_imports()
    assert all(r.import_state == "discovered" for r in rows)


def test_second_scan_unchanged(cache_dir, store):
    scanner = UnityAssetStoreScanner(store=store)
    scanner.run_once(cache_path=cache_dir)
    result2 = scanner.run_once(cache_path=cache_dir)
    assert result2.new == 0
    assert result2.unchanged == 2


def test_mtime_change_reverts_imported_to_discovered(cache_dir, store):
    scanner = UnityAssetStoreScanner(store=store)
    scanner.run_once(cache_path=cache_dir)
    rows = store.list_unity_imports()
    # 첫 번째 row 를 imported 로 강제 — pack_id FK 위반 방지를 위해 실제 팩 먼저 만듦
    # (store.upsert_pack 가 있다고 가정 — Phase 2A.2 패턴 참고)
    target_pkg = rows[0].package_path
    # pack_id 없이도 update_unity_state 가 동작하므로 (pack_id 옵션) — 일단 imported 만
    store.update_unity_state(rows[0].id, "imported", imported_at=int(time.time()))
    # mtime 변경 시뮬
    new_mtime = target_pkg.stat().st_mtime + 100
    os.utime(target_pkg, (new_mtime, new_mtime))
    result = scanner.run_once(cache_path=cache_dir)
    assert result.updated >= 1
    refreshed = store.get_unity_import_by_path(target_pkg)
    assert refreshed.import_state == "discovered"
    assert refreshed.preview_asset_count is None


def test_mtime_change_reverts_skipped_to_discovered(cache_dir, store):
    scanner = UnityAssetStoreScanner(store=store)
    scanner.run_once(cache_path=cache_dir)
    rows = store.list_unity_imports()
    store.update_unity_state(rows[0].id, "skipped")
    pkg = rows[0].package_path
    new_mtime = pkg.stat().st_mtime + 100
    os.utime(pkg, (new_mtime, new_mtime))
    scanner.run_once(cache_path=cache_dir)
    refreshed = store.get_unity_import_by_path(pkg)
    assert refreshed.import_state == "discovered"


def test_removed_file_counted(cache_dir, store):
    scanner = UnityAssetStoreScanner(store=store)
    scanner.run_once(cache_path=cache_dir)
    for p in cache_dir.rglob("*.unitypackage"):
        p.unlink()
        break
    result2 = scanner.run_once(cache_path=cache_dir)
    assert result2.removed == 1


def test_publisher_glob_filter(cache_dir, store):
    scanner = UnityAssetStoreScanner(store=store)
    result = scanner.run_once(cache_path=cache_dir, publisher_glob="Pixel*")
    assert result.scanned == 1


def test_asset_name_glob_filter(cache_dir, store):
    scanner = UnityAssetStoreScanner(store=store)
    result = scanner.run_once(cache_path=cache_dir, asset_name_glob="*Sound*")
    assert result.scanned == 1


def test_empty_cache_directory(tmp_path, store):
    empty = tmp_path / "empty"
    empty.mkdir()
    scanner = UnityAssetStoreScanner(store=store)
    result = scanner.run_once(cache_path=empty)
    assert result.scanned == 0


def test_missing_cache_directory(tmp_path, store):
    """존재하지 않는 디렉터리 → warnings 에 메시지."""
    scanner = UnityAssetStoreScanner(store=store)
    result = scanner.run_once(cache_path=tmp_path / "nonexistent")
    assert result.scanned == 0
    assert any("cache" in w.lower() or "missing" in w.lower() for w in result.warnings)
