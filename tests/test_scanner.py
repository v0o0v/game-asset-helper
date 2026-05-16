"""Tests for gah.core.scanner — boot-time full-scan reconciliation."""

from __future__ import annotations

from pathlib import Path


def test_reconcile_adds_new_packs(store, library_root: Path, make_pack) -> None:
    from gah.core.scanner import reconcile_library

    make_pack("alpha", files={"a.png": b"x"})
    make_pack("beta", files={"b.wav": b"y"})

    report = reconcile_library(store, library_root)
    names = {p.name for p in store.list_packs()}
    assert names == {"alpha", "beta"}
    assert sorted(report.added) == ["alpha", "beta"]
    assert report.removed == []


def test_reconcile_removes_vanished_packs(store, library_root: Path, make_pack) -> None:
    from gah.core.scanner import reconcile_library

    make_pack("ghost", files={"g.png": b"g"})
    reconcile_library(store, library_root)
    assert any(p.name == "ghost" for p in store.list_packs())

    # delete the pack folder, then reconcile again
    import shutil

    shutil.rmtree(library_root / "ghost")
    report = reconcile_library(store, library_root)
    assert report.removed == ["ghost"]
    assert all(p.name != "ghost" for p in store.list_packs())


def test_reconcile_no_changes_is_noop_report(store, library_root: Path, make_pack) -> None:
    from gah.core.scanner import reconcile_library

    make_pack("steady", files={"a.png": b"x"})
    reconcile_library(store, library_root)

    report = reconcile_library(store, library_root)
    assert report.added == []
    assert report.removed == []
    assert report.rescanned == ["steady"]


def test_reconcile_ignores_files_at_library_root(store, library_root: Path) -> None:
    from gah.core.scanner import reconcile_library

    # a stray file directly in library/ — not a pack
    (library_root / "stray.png").write_bytes(b"x")

    report = reconcile_library(store, library_root)
    assert report.added == []
    assert report.removed == []
    assert report.rescanned == []
    assert store.list_packs() == []


def test_reconcile_runs_on_empty_library(store, library_root: Path) -> None:
    from gah.core.scanner import reconcile_library

    report = reconcile_library(store, library_root)
    assert report.added == []
    assert report.removed == []
    assert report.rescanned == []
