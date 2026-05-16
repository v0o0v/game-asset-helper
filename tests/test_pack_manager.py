"""Tests for gah.core.pack_manager — pack ingestion end-to-end."""

from __future__ import annotations

from pathlib import Path


def test_ingest_creates_pack_and_assets_from_manifest(store, library_root: Path, make_pack) -> None:
    from gah.core.pack_manager import ingest_pack

    pack_dir = make_pack(
        "kenney_demo",
        files={
            "PNG/Characters/hero.png": b"\x89PNG-fake-bytes-1",
            "PNG/Tiles/grass.png": b"\x89PNG-fake-bytes-2",
            "Sounds/jump.wav": b"RIFF-fake-bytes",
        },
        manifest={
            "name": "Kenney Demo",
            "vendor": "kenney",
            "license": "CC0",
            "description": "데모용",
        },
    )

    pid = ingest_pack(store, pack_dir, library_root)

    packs = store.list_packs()
    assert len(packs) == 1
    assert packs[0].id == pid
    assert packs[0].name == "kenney_demo"
    assert packs[0].display_name == "Kenney Demo"
    assert packs[0].vendor == "kenney"
    assert packs[0].license == "CC0"

    assets = store.assets_for_pack(pid)
    assert len(assets) == 3
    kinds = {a.path: a.kind for a in assets}
    assert kinds == {
        "kenney_demo/PNG/Characters/hero.png": "sprite",
        "kenney_demo/PNG/Tiles/grass.png": "sprite",
        "kenney_demo/Sounds/jump.wav": "sound",
    }


def test_ingest_without_manifest_uses_folder_heuristic(store, library_root: Path, make_pack) -> None:
    from gah.core.pack_manager import ingest_pack

    pack_dir = make_pack(
        "kenney_no_manifest",
        files={"hero.png": b"\x89PNG-bytes"},
    )

    ingest_pack(store, pack_dir, library_root)
    packs = store.list_packs()
    assert packs[0].vendor == "kenney"
    assert packs[0].display_name is None


def test_ingest_skips_unsupported_files(store, library_root: Path, make_pack) -> None:
    from gah.core.pack_manager import ingest_pack

    pack_dir = make_pack(
        "mix",
        files={
            "hero.png": b"png-bytes",
            "readme.txt": b"hi",
            "config.gd": b"extends Node",
            "icon.meta": b"meta",
        },
    )

    pid = ingest_pack(store, pack_dir, library_root)
    assets = store.assets_for_pack(pid)
    paths = {a.path for a in assets}
    assert paths == {"mix/hero.png"}


def test_reingest_is_noop_when_unchanged(store, library_root: Path, make_pack) -> None:
    from gah.core.pack_manager import ingest_pack

    pack_dir = make_pack(
        "p",
        files={"a.png": b"AAA"},
    )

    pid = ingest_pack(store, pack_dir, library_root)
    asset = store.assets_for_pack(pid)[0]
    # simulate M2: mark it analysed
    store.conn.execute(
        "UPDATE assets SET analysis_state='ok', analyzed_at=42 WHERE id=?", (asset.id,)
    )

    ingest_pack(store, pack_dir, library_root)
    after = store.assets_for_pack(pid)[0]
    assert after.analysis_state == "ok"
    assert after.analyzed_at == 42


def test_reingest_updates_hash_when_bytes_change(store, library_root: Path, make_pack) -> None:
    from gah.core.pack_manager import ingest_pack

    pack_dir = make_pack(
        "p",
        files={"a.png": b"AAA"},
    )
    pid = ingest_pack(store, pack_dir, library_root)
    asset = store.assets_for_pack(pid)[0]
    store.conn.execute(
        "UPDATE assets SET analysis_state='ok', analyzed_at=42 WHERE id=?", (asset.id,)
    )
    h0 = asset.file_hash

    (pack_dir / "a.png").write_bytes(b"BBBBBBBB")

    ingest_pack(store, pack_dir, library_root)
    refreshed = store.assets_for_pack(pid)[0]
    assert refreshed.file_hash != h0
    assert refreshed.analysis_state == "pending"
    assert refreshed.analyzed_at is None


def test_reingest_removes_deleted_files(store, library_root: Path, make_pack) -> None:
    from gah.core.pack_manager import ingest_pack

    pack_dir = make_pack(
        "p",
        files={"a.png": b"AAA", "b.png": b"BBB"},
    )
    pid = ingest_pack(store, pack_dir, library_root)
    assert len(store.assets_for_pack(pid)) == 2

    (pack_dir / "b.png").unlink()
    ingest_pack(store, pack_dir, library_root)
    remaining = {a.path for a in store.assets_for_pack(pid)}
    assert remaining == {"p/a.png"}


def test_ingest_handles_empty_pack(store, library_root: Path, make_pack) -> None:
    from gah.core.pack_manager import ingest_pack

    pack_dir = make_pack("empty_pack", files={})

    pid = ingest_pack(store, pack_dir, library_root)
    packs = store.list_packs()
    assert any(p.id == pid and p.name == "empty_pack" for p in packs)
    assert store.assets_for_pack(pid) == []


def test_ingest_normalizes_relative_path_to_posix(store, library_root: Path, make_pack) -> None:
    from gah.core.pack_manager import ingest_pack

    pack_dir = make_pack(
        "p",
        files={"sub/dir/leaf.png": b"x"},
    )
    pid = ingest_pack(store, pack_dir, library_root)
    paths = [a.path for a in store.assets_for_pack(pid)]
    # forward slashes regardless of platform
    assert paths == ["p/sub/dir/leaf.png"]
    assert "\\" not in paths[0]
