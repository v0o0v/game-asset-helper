"""Smoke tests for gah.ui — main window + table views construct under offscreen Qt."""

from __future__ import annotations

from pathlib import Path

import pytest


def _make_qapplication():
    """Reuse the singleton QApplication across tests so PySide6 doesn't error.

    PySide6 forbids constructing more than one QApplication per process; the
    offscreen plugin set in conftest still requires at least one instance.
    """
    from PySide6.QtWidgets import QApplication

    qapp = QApplication.instance() or QApplication([])
    return qapp


def test_main_window_can_be_constructed(store) -> None:
    _make_qapplication()
    from gah.ui.main_window import MainWindow

    win = MainWindow(store)
    win.refresh()  # empty store — should not raise
    win.deleteLater()


def test_pack_view_populates_from_store(store) -> None:
    _make_qapplication()
    from gah.core.manifest import PackManifest
    from gah.ui.pack_view import PackView

    store.upsert_pack(
        "kenney_demo",
        PackManifest(
            display_name="Kenney Demo",
            vendor="kenney",
            source_url=None,
            license="CC0",
            description=None,
        ),
        scanned_at=42,
    )

    view = PackView(store)
    view.refresh()
    table = view.table  # implementation exposes the QTableWidget for tests
    assert table.rowCount() == 1
    assert table.item(0, 0).text() == "kenney_demo"
    view.deleteLater()


def test_library_view_populates_from_store(store) -> None:
    _make_qapplication()
    from gah.core.manifest import PackManifest
    from gah.ui.library_view import LibraryView

    pid = store.upsert_pack(
        "p",
        PackManifest(None, None, None, None, None),
        scanned_at=0,
    )
    store.upsert_asset(pid, "p/hero.png", "sprite", "h", 100, added_at=0)
    store.upsert_asset(pid, "p/jump.wav", "sound", "h2", 200, added_at=0)

    view = LibraryView(store)
    view.refresh()
    table = view.table
    assert table.rowCount() == 2
    view.deleteLater()
