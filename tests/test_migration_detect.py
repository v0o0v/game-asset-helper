"""마이그레이션 candidate 감지 테스트."""
from __future__ import annotations

from pathlib import Path

import pytest

from assetcache.config import AppPaths, default_app_paths
from assetcache.core.migration import (
    MigrationCandidate,
    detect_v001_candidate,
    is_already_migrated,
)


def _make_app_paths(tmp_path: Path, new_app: str = "AssetCacheMCP", old_app: str = "GameAssetHelper") -> AppPaths:
    """tmp 디렉터리에 가짜 %APPDATA%/AppName 두 폴더의 부모를 둔다.

    AppPaths 의 frozen dataclass 모든 필드를 채우려면 default_app_paths(tmp_path/new_app) 활용 +
    legacy_data_dir 만 override.
    """
    # AppPaths 가 frozen 이므로 dataclasses.replace 또는 직접 생성
    new_root = tmp_path / new_app
    old_root = tmp_path / old_app
    base = default_app_paths(new_root)
    from dataclasses import replace
    return replace(base, legacy_data_dir=old_root)


def test_detect_no_candidate_when_both_empty(tmp_path):
    """신규 사용자 — 두 폴더 모두 비어있거나 없음."""
    paths = _make_app_paths(tmp_path)
    assert detect_v001_candidate(paths) is None


def test_detect_candidate_when_legacy_has_db_and_library(tmp_path):
    """v0.0.1 사용자 — 구 폴더에 metadata.db + library/ 존재."""
    paths = _make_app_paths(tmp_path)
    paths.legacy_data_dir.mkdir(parents=True)
    (paths.legacy_data_dir / "metadata.db").write_text("fake db")
    (paths.legacy_data_dir / "library").mkdir()
    (paths.legacy_data_dir / "library" / "asset.png").write_bytes(b"\x00" * 100)

    candidate = detect_v001_candidate(paths)

    assert candidate is not None
    assert candidate.source == paths.legacy_data_dir
    assert candidate.target == paths.data_dir
    assert candidate.has_db is True
    assert candidate.has_library is True
    assert candidate.total_files >= 2
    assert candidate.total_bytes >= 100


def test_detect_no_candidate_when_new_folder_has_data(tmp_path):
    """새 사용자가 이미 새 폴더 사용 중 — 마이그레이션 X."""
    paths = _make_app_paths(tmp_path)
    paths.data_dir.mkdir(parents=True)
    (paths.data_dir / "metadata.db").write_text("fake db")

    paths.legacy_data_dir.mkdir(parents=True)
    (paths.legacy_data_dir / "metadata.db").write_text("fake old db")

    assert detect_v001_candidate(paths) is None


def test_detect_no_candidate_when_already_migrated(tmp_path):
    """마이그레이션 완료 마커가 있으면 다시 candidate 안 됨."""
    paths = _make_app_paths(tmp_path)
    paths.data_dir.mkdir(parents=True)
    (paths.data_dir / ".migrated_from_v001").write_text("2026-05-19")

    paths.legacy_data_dir.mkdir(parents=True)
    (paths.legacy_data_dir / "metadata.db").write_text("fake db")

    assert detect_v001_candidate(paths) is None


def test_is_already_migrated_marker(tmp_path):
    target = tmp_path / "new"
    target.mkdir()
    assert is_already_migrated(target) is False

    (target / ".migrated_from_v001").write_text("ok")
    assert is_already_migrated(target) is True
