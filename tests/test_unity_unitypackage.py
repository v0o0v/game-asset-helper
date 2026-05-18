"""M7 — .unitypackage 파서 + 추출 회귀."""
from __future__ import annotations

from pathlib import Path

import pytest

from gah.core.unity_import.unitypackage import parse_pathnames, extract_targets
from tests.fixtures.unity.make_unitypackage import make_fixture_unitypackage


@pytest.fixture
def fixture_pkg(tmp_path):
    pkg = tmp_path / "MegaPack.unitypackage"
    return make_fixture_unitypackage(pkg)


@pytest.fixture
def fixture_pkg_no_psd(tmp_path):
    pkg = tmp_path / "MegaPackNoPSD.unitypackage"
    return make_fixture_unitypackage(pkg, include_psd=False)


# ── parse_pathnames ───────────────────────────────────────────────────


def test_parse_pathnames_returns_dict(fixture_pkg):
    entries = parse_pathnames(fixture_pkg)
    assert isinstance(entries, dict)


def test_parse_filters_image_extensions(fixture_pkg):
    entries = parse_pathnames(fixture_pkg)
    assert "abc123" in entries
    assert entries["abc123"].pathname == "Assets/Sprites/idle.png"
    assert entries["abc123"].internal_kind == "image"


def test_parse_filters_sound_extensions(fixture_pkg):
    entries = parse_pathnames(fixture_pkg)
    assert "def456" in entries
    assert entries["def456"].pathname == "Assets/Sounds/jump.wav"
    assert entries["def456"].internal_kind == "sound"


def test_parse_excludes_psd(fixture_pkg):
    entries = parse_pathnames(fixture_pkg)
    assert "psd789" not in entries


def test_parse_empty_package(tmp_path):
    import tarfile
    pkg = tmp_path / "empty.unitypackage"
    with tarfile.open(pkg, mode="w:gz") as tar:
        pass
    entries = parse_pathnames(pkg)
    assert entries == {}


def test_parse_broken_unitypackage(tmp_path):
    pkg = tmp_path / "broken.unitypackage"
    pkg.write_bytes(b"not a gzip file")
    with pytest.raises(Exception):
        parse_pathnames(pkg)


# ── extract_targets ───────────────────────────────────────────────────


def test_extract_targets_physical_copy(fixture_pkg_no_psd, tmp_path):
    dest = tmp_path / "library" / "mega"
    result = extract_targets(fixture_pkg_no_psd, dest, target_guids=["abc123", "def456"])
    assert (dest / "Assets" / "Sprites" / "idle.png").is_file()
    assert (dest / "Assets" / "Sounds" / "jump.wav").is_file()
    assert result.files_extracted == 2
    assert result.bytes_written > 0


def test_extract_preserves_directory_structure(fixture_pkg, tmp_path):
    dest = tmp_path / "library" / "mega"
    extract_targets(fixture_pkg, dest, target_guids=["abc123"])
    assert (dest / "Assets" / "Sprites" / "idle.png").exists()
    assert not (dest / "Assets" / "Sounds").exists()


def test_extract_creates_destination(fixture_pkg_no_psd, tmp_path):
    dest = tmp_path / "deep" / "library" / "mega"
    extract_targets(fixture_pkg_no_psd, dest, target_guids=["abc123"])
    assert dest.is_dir()


def test_extract_skips_psd_even_if_target(fixture_pkg, tmp_path):
    dest = tmp_path / "library" / "mega"
    result = extract_targets(
        fixture_pkg, dest, target_guids=["abc123", "psd789"],
    )
    assert (dest / "Assets" / "Sprites" / "idle.png").is_file()
    assert not (dest / "Assets" / "Sprites" / "source.psd").exists()
    assert result.files_extracted == 1


def test_extract_empty_targets(fixture_pkg_no_psd, tmp_path):
    dest = tmp_path / "library" / "mega"
    result = extract_targets(fixture_pkg_no_psd, dest, target_guids=[])
    assert result.files_extracted == 0


def test_parse_unicode_pathname(tmp_path):
    import io
    import tarfile
    pkg = tmp_path / "unicode.unitypackage"
    with tarfile.open(pkg, mode="w:gz") as tar:
        def add(name, data):
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        add("xyz/asset", b"PNG")
        add("xyz/pathname", "Assets/한글경로/이미지.png".encode("utf-8"))
    entries = parse_pathnames(pkg)
    assert "xyz" in entries
    assert "한글" in entries["xyz"].pathname
