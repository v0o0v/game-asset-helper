"""Main application window — packs / library tabs.

M1 ships only two tabs because the data we have to show is still
minimal.  Detail / projects / settings / logs land in M6.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import QMainWindow, QTabWidget, QWidget

from ..core.pack_manager import ingest_pack
from ..core.scanner import reconcile_library
from .library_view import LibraryView
from .pack_view import PackView

if TYPE_CHECKING:  # pragma: no cover
    from ..core.store import Store

log = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Top-level window backed by a :class:`gah.core.store.Store`.

    The :attr:`packChanged` signal is the bridge between the background
    watcher thread and the GUI thread.  Emitting it from any thread
    causes :meth:`_on_pack_changed` to run inside the Qt event loop.
    """

    packChanged = Signal(str)

    def __init__(self, store: "Store", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Game Asset Helper")
        self.resize(900, 600)
        self.setWindowFlag(Qt.Window)

        self._store = store
        self._library_root: Optional[Path] = None

        tabs = QTabWidget(self)
        self.pack_view = PackView(store, tabs)
        self.library_view = LibraryView(store, tabs)

        tabs.addTab(self.pack_view, "팩")
        tabs.addTab(self.library_view, "라이브러리")
        self.setCentralWidget(tabs)

        self.packChanged.connect(self._on_pack_changed)

    def set_library_root(self, path: Path) -> None:
        """Tell the window where ``library/`` lives so it can re-ingest on events."""
        self._library_root = Path(path)

    def refresh(self) -> None:
        """Re-query the store and repaint both tabs."""
        self.pack_view.refresh()
        self.library_view.refresh()

    def show_and_raise(self) -> None:
        """Bring the window to the foreground (used by the tray menu)."""
        self.show()
        self.raise_()
        self.activateWindow()

    @Slot(str)
    def _on_pack_changed(self, pack_name: str) -> None:
        if self._library_root is None:
            self.refresh()
            return
        pack_dir = self._library_root / pack_name
        try:
            if pack_dir.is_dir():
                ingest_pack(self._store, pack_dir, self._library_root)
            else:
                # The pack folder disappeared (rename / delete) — fall back to a full reconcile.
                reconcile_library(self._store, self._library_root)
        except Exception:
            log.exception("failed to ingest pack %r", pack_name)
        self.refresh()
