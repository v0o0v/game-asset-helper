"""System tray icon for Game Asset Helper.

The icon is drawn at runtime with ``QPainter`` so we don't carry a PNG
file in the source tree.  Polished artwork lands with M6.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:  # pragma: no cover
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

log = logging.getLogger(__name__)


def _build_app_icon() -> "QIcon":
    """Return a coloured GAH icon as a :class:`QIcon`.

    The pixmap is 64×64 (Windows scales this down to 16×16 / 24×24 in
    the system tray, so starting larger keeps anti-aliasing crisp).
    The palette is one of DESIGN.md's dominant-colour samples — dark
    teal background, warm orange initial.
    """
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap

    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor("#264653")))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRect(0, 0, size, size), 12, 12)

        painter.setPen(QColor("#f4a261"))
        font = QFont("Arial", int(size * 0.55))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "G")
    finally:
        painter.end()

    return QIcon(pixmap)


def _handle_tray_activation(reason, on_open_main: Optional[Callable[[], None]]) -> None:
    """Route the tray's ``activated`` signal to :func:`on_open_main`.

    Only ``DoubleClick`` triggers the callback: a left single-click on
    Windows does nothing in most apps, and right-click is reserved for
    the context menu.
    """
    from PySide6.QtWidgets import QSystemTrayIcon

    if reason == QSystemTrayIcon.DoubleClick and on_open_main is not None:
        on_open_main()


def make_tray_icon(
    qapp: "QApplication",
    *,
    on_open_main: Optional[Callable[[], None]] = None,
) -> "QSystemTrayIcon":
    """Build a tray icon and return it.

    Parameters
    ----------
    qapp : QApplication
        The application instance that will own menu actions.
    on_open_main : callable, optional
        Invoked when the user picks "메인 창 열기" *or* double-clicks
        the tray icon.  ``None`` hides the menu entry and disables the
        double-click handler, which is convenient for tests that don't
        have a window to raise.

    Imports of PySide6 are deferred to function scope so that simply
    importing ``gah.tray`` (e.g. from the test suite) doesn't drag in
    the Qt platform plugin.
    """
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMenu, QSystemTrayIcon

    icon = _build_app_icon()

    tray = QSystemTrayIcon(icon, qapp)
    tray.setToolTip("Game Asset Helper")

    menu = QMenu()

    if on_open_main is not None:
        open_action = QAction("메인 창 열기", menu)
        open_action.triggered.connect(on_open_main)
        menu.addAction(open_action)
        menu.addSeparator()

    quit_action = QAction("종료", menu)
    quit_action.triggered.connect(qapp.quit)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)

    tray.activated.connect(lambda reason: _handle_tray_activation(reason, on_open_main))

    tray.show()
    log.info("Tray icon initialised")
    return tray
