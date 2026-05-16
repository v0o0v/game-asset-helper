"""Minimal system tray skeleton for M0.

The real menu items (re-scan, open library, Ollama health, Unity sync, ...)
live in later milestones — M0 only proves that PySide6 can be wired up
and that the tray icon appears with a working "종료" action.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

log = logging.getLogger(__name__)


def make_tray_icon(qapp: "QApplication") -> "QSystemTrayIcon":
    """Build a tray icon with a single 'Quit' action and return it.

    Imports of PySide6 are deferred to function scope so that simply
    importing ``gah.tray`` (e.g. from the test suite) doesn't drag in
    the Qt platform plugin.
    """
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QAction, QIcon, QPixmap
    from PySide6.QtWidgets import QMenu, QSystemTrayIcon

    # Empty 16x16 transparent pixmap — proper artwork in M6.
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.transparent)
    icon = QIcon(pixmap)

    tray = QSystemTrayIcon(icon, qapp)
    tray.setToolTip("Game Asset Helper")

    menu = QMenu()
    quit_action = QAction("종료", menu)
    quit_action.triggered.connect(qapp.quit)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)

    tray.show()
    log.info("Tray icon initialised")
    return tray
