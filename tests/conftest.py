"""Shared pytest fixtures for GAH tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Iterator

import pytest


@pytest.fixture(autouse=True)
def qt_offscreen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force Qt to use the offscreen platform plugin so PySide6 can import
    without a display server in CI/sandbox environments."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def tmp_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Override GAH's data root to a fresh temp directory for the test."""
    monkeypatch.setenv("GAH_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def library_root(tmp_appdata: Path) -> Path:
    """A fresh, empty library directory inside the temporary AppData root."""
    root = tmp_appdata / "library"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def make_pack(library_root: Path) -> Callable[..., Path]:
    """Factory for building a pack directory under ``library_root``.

    Usage::

        pack_dir = make_pack(
            "kenney_demo",
            files={"PNG/hero.png": b"\\x89PNG...", "Sounds/jump.wav": b"RIFF..."},
            manifest={"name": "Kenney Demo", "vendor": "kenney"},
        )
    """

    def _make_pack(
        name: str,
        *,
        files: dict[str, bytes] | None = None,
        manifest: dict | None = None,
        manifest_format: str = "json",
    ) -> Path:
        pack_dir = library_root / name
        pack_dir.mkdir(parents=True, exist_ok=True)
        for rel, payload in (files or {}).items():
            file_path = pack_dir / rel
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(payload)
        if manifest is not None:
            if manifest_format == "json":
                (pack_dir / "pack.json").write_text(
                    json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
                )
            elif manifest_format == "toml":
                import tomli_w

                (pack_dir / "pack.toml").write_bytes(tomli_w.dumps(manifest).encode("utf-8"))
            else:  # pragma: no cover - defensive
                raise ValueError(f"unknown manifest_format: {manifest_format!r}")
        return pack_dir

    return _make_pack


@pytest.fixture
def store(tmp_appdata: Path) -> Iterator["object"]:
    """Initialised on-disk Store at ``tmp_appdata/test.db``.

    Returns the live Store object; callers can use ``store.conn`` if they
    need raw SQL access for assertions.
    """
    from gah.core.store import Store

    s = Store(tmp_appdata / "test.db")
    s.initialize()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def clean_root_logger():
    """Snapshot and restore the root logger so logging tests don't bleed."""
    import logging

    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    for h in list(root.handlers):
        root.removeHandler(h)
    try:
        yield root
    finally:
        for h in list(root.handlers):
            try:
                h.close()
            except Exception:
                pass
            root.removeHandler(h)
        for h in saved_handlers:
            root.addHandler(h)
        root.setLevel(saved_level)
