"""M7 Phase 0 — unity_import.types 7 frozen dataclass 단위 테스트.

TDD red phase: types.py 구현 전 모두 실패해야 한다.
"""

from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError
from pathlib import Path


# ── 1. UnityPackagePath ──────────────────────────────────────────────


def test_unity_package_path_frozen():
    from gah.core.unity_import.types import UnityPackagePath

    p = UnityPackagePath(
        abs_path=Path("/cache/Assets/hero.unitypackage"),
        publisher="Kenney",
        category="2D",
        asset_name="hero",
        size=1024,
        mtime=1700000000,
    )
    p2 = UnityPackagePath(
        abs_path=Path("/cache/Assets/hero.unitypackage"),
        publisher="Kenney",
        category="2D",
        asset_name="hero",
        size=1024,
        mtime=1700000000,
    )
    # frozen — 동등성 확인
    assert p == p2
    # frozen — 변경 시 FrozenInstanceError
    with pytest.raises(FrozenInstanceError):
        p.asset_name = "changed"  # type: ignore[misc]


# ── 2. UnityPackageEntry ─────────────────────────────────────────────


def test_unity_package_entry_kind_enum():
    from gah.core.unity_import.types import UnityPackageEntry

    img_entry = UnityPackageEntry(
        guid="abc123",
        pathname="Assets/Sprites/idle.png",
        internal_kind="image",
        size=512,
    )
    snd_entry = UnityPackageEntry(
        guid="def456",
        pathname="Assets/Sounds/jump.wav",
        internal_kind="sound",
        size=256,
    )
    assert img_entry.internal_kind in ("image", "sound")
    assert snd_entry.internal_kind in ("image", "sound")
    assert img_entry.internal_kind == "image"
    assert snd_entry.internal_kind == "sound"


# ── 3. UnityPackagePreview ───────────────────────────────────────────


def test_unity_package_preview_zero_default():
    from gah.core.unity_import.types import UnityPackagePreview

    preview = UnityPackagePreview(asset_count=0, image_count=0, sound_count=0)
    assert preview.sample_pathnames == ()
    assert isinstance(preview.sample_pathnames, tuple)


# ── 4. UnityScanResult ───────────────────────────────────────────────


def test_unity_scan_result_sum_invariant():
    from gah.core.unity_import.types import UnityScanResult

    result = UnityScanResult(
        scanned=10,
        new=3,
        updated=2,
        unchanged=4,
        removed=1,
        cache_path=Path("/cache"),
    )
    assert result.new + result.updated + result.unchanged + result.removed == result.scanned


# ── 5. UnityImportResult ─────────────────────────────────────────────


def test_unity_import_result_states():
    from gah.core.unity_import.types import UnityImportResult

    ok = UnityImportResult(pack_id=1, pack_name="Kenney", asset_count=5, state="imported")
    fail = UnityImportResult(
        pack_id=None, pack_name="Bad", asset_count=0, state="failed", error="파싱 오류"
    )
    assert ok.state in ("imported", "failed")
    assert fail.state in ("imported", "failed")
    assert ok.error is None
    assert fail.error == "파싱 오류"


# ── 6. ExtractResult ─────────────────────────────────────────────────


def test_extract_result_counts():
    from gah.core.unity_import.types import ExtractResult

    r = ExtractResult(files_extracted=7, bytes_written=204800)
    assert r.files_extracted == 7
    assert r.bytes_written == 204800


# ── 7. UnityImportRecord ─────────────────────────────────────────────


def test_unity_import_record_mirrors_db():
    from gah.core.unity_import.types import UnityImportRecord

    rec = UnityImportRecord(
        id=1,
        package_path=Path("/cache/hero.unitypackage"),
        publisher="Kenney",
        category="2D",
        asset_name="hero",
        package_size=2048,
        package_mtime=1700000000,
        preview_asset_count=None,
        preview_image_count=None,
        preview_sound_count=None,
        preview_inspected_at=None,
        pack_id=None,
        import_state="discovered",
        import_error=None,
        imported_at=None,
        first_seen_at=1700000000,
        last_scanned_at=1700000001,
    )
    assert rec.import_state == "discovered"
    assert rec.import_state in (
        "discovered",
        "previewed",
        "import_pending",
        "imported",
        "failed",
        "skipped",
    )
    assert rec.pack_id is None
    assert rec.import_error is None
