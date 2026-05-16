"""QApplication wiring for tray mode.

PySide6 imports are deferred to function scope so importing ``gah.app``
in a non-GUI context (e.g. CLI ``--version``, unit tests) does not
require a Qt platform plugin.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Sequence

from .config import AppPaths, Config
from .core.scanner import reconcile_library
from .core.store import Store
from .core.watcher import LibraryWatcher

log = logging.getLogger(__name__)


def _resolve_library_root(paths: AppPaths, config: Config) -> Path:
    if config.library_dir_override:
        return Path(config.library_dir_override).expanduser().resolve()
    return paths.library_dir


def run_tray(paths: AppPaths, config: Config, argv: Sequence[str] | None = None) -> int:
    """Boot the tray application. Returns the QApplication exit code."""
    from PySide6.QtWidgets import QApplication

    from .tray import make_tray_icon
    from .ui.main_window import MainWindow

    qapp = QApplication(list(argv or sys.argv))
    qapp.setQuitOnLastWindowClosed(False)

    library_root = _resolve_library_root(paths, config)
    library_root.mkdir(parents=True, exist_ok=True)

    store = Store(paths.db_path)
    store.initialize()

    report = reconcile_library(store, library_root)
    log.info(
        "library reconciled: +%d / -%d / =%d",
        len(report.added),
        len(report.removed),
        len(report.rescanned),
    )

    main_window = MainWindow(store)
    main_window.set_library_root(library_root)
    main_window.refresh()

    watcher = LibraryWatcher(
        window_seconds=config.watch_debounce_seconds,
        on_pack_changed=main_window.packChanged.emit,
    )
    watcher.start(library_root)

    tray = make_tray_icon(qapp, on_open_main=main_window.show_and_raise)
    qapp._gah_tray = tray  # type: ignore[attr-defined]
    qapp._gah_store = store  # type: ignore[attr-defined]
    qapp._gah_watcher = watcher  # type: ignore[attr-defined]
    qapp._gah_main_window = main_window  # type: ignore[attr-defined]

    log.info("GAH tray ready (data_dir=%s, library=%s)", paths.data_dir, library_root)
    rc = qapp.exec()

    watcher.stop()
    store.close()
    return rc
