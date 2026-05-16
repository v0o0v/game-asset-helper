"""Shared pytest fixtures for GAH tests."""

from __future__ import annotations

import os
from pathlib import Path

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
