"""QApplication wiring for tray mode.

PySide6 imports are deferred to function scope so importing ``gah.app``
in a non-GUI context (e.g. CLI ``--version``, unit tests) does not
require a Qt platform plugin.
"""

from __future__ import annotations

import logging
import sys
from typing import Sequence

from .config import AppPaths, Config

log = logging.getLogger(__name__)


def run_tray(paths: AppPaths, config: Config, argv: Sequence[str] | None = None) -> int:
    """Boot the tray application. Returns the QApplication exit code."""
    from PySide6.QtWidgets import QApplication

    from .tray import make_tray_icon

    qapp = QApplication(list(argv or sys.argv))
    qapp.setQuitOnLastWindowClosed(False)

    tray = make_tray_icon(qapp)
    # keep a strong reference on the QApplication so the icon isn't GC'd
    qapp._gah_tray = tray  # type: ignore[attr-defined]

    log.info("GAH tray ready (data_dir=%s)", paths.data_dir)
    return qapp.exec()
