"""Main application window — packs / library tabs + status bar.

M2 additions: status-bar progress widget showing ``현재 분석 N/M — 약 X 남음``,
a ``Ctrl+L`` shortcut to open the labels admin dialog, and a slot to
absorb :class:`AnalysisQueue` progress snapshots without blocking the
GUI thread.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QCoreApplication, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QProgressBar,
    QStatusBar,
    QTabWidget,
    QWidget,
)

from ..core.pack_manager import ingest_pack
from ..core.scanner import reconcile_library
from .library_view import LibraryView
from .pack_view import PackView

if TYPE_CHECKING:  # pragma: no cover
    from ..core.analysis_queue import AnalysisProgress
    from ..core.labels import LabelRegistry
    from ..core.store import Store

log = logging.getLogger(__name__)


def _tr(text: str) -> str:
    return QCoreApplication.translate("MainWindow", text)


class MainWindow(QMainWindow):
    """Top-level window backed by a :class:`gah.core.store.Store`."""

    packChanged = Signal(str)

    def __init__(self, store: "Store", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_tr("Game Asset Helper"))
        self.resize(900, 600)
        self.setWindowFlag(Qt.Window)

        self._store = store
        self._library_root: Optional[Path] = None
        self._label_registry: Optional["LabelRegistry"] = None
        # M2.1: 분석 큐 동시성 3 일 때 progressChanged 가 N 배로 emit 된다.
        # 250ms 디바운스로 4Hz cap — leading-edge 즉시 표시 + trailing flush.
        self._pending_snapshot: "AnalysisProgress | None" = None
        self._progress_flush_timer: QTimer | None = None
        self._progress_debounce_ms: int = 250

        self.tab_widget = QTabWidget(self)
        self.pack_view = PackView(store, self.tab_widget)
        self.library_view = LibraryView(store, self.tab_widget)

        self.tab_widget.addTab(self.pack_view, _tr("팩"))
        self.tab_widget.addTab(self.library_view, _tr("라이브러리"))
        self.setCentralWidget(self.tab_widget)

        # ── 상태바 — 분석 진행 표시 ─────────────────────────────────
        bar = QStatusBar(self)
        self.setStatusBar(bar)
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.progress_bar.setMaximumWidth(180)
        self.progress_label = QLabel(_tr("분석 대기 중"))
        bar.addPermanentWidget(self.progress_bar)
        bar.addPermanentWidget(self.progress_label, 1)

        self.packChanged.connect(self._on_pack_changed)

        self._labels_shortcut = QShortcut(
            QKeySequence("Ctrl+L"), self
        )
        self._labels_shortcut.activated.connect(self.open_labels_admin)

    # -- wiring -------------------------------------------------------

    def set_library_root(self, path: Path) -> None:
        self._library_root = Path(path)

    def set_label_registry(self, registry: "LabelRegistry") -> None:
        self._label_registry = registry

    def open_labels_admin(self) -> None:
        if self._label_registry is None:
            log.warning("label registry not set; cannot open admin dialog")
            return
        # 지연 import: 다이얼로그가 매번 살아 있을 필요는 없음
        from .labels_admin import LabelsAdminDialog

        dlg = LabelsAdminDialog(self._label_registry, parent=self)
        dlg.exec()

    def refresh(self) -> None:
        self.pack_view.refresh()
        self.library_view.refresh()

    def show_and_raise(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    # -- M2 progress slot --------------------------------------------

    @Slot(object)
    def update_progress(self, snapshot: "AnalysisProgress") -> None:
        """Receive a progress snapshot — debounced at 4Hz.

        Leading-edge: 첫 호출(또는 직전 창이 끝난 직후의 첫 호출) 은 즉시 그린다.
        그 다음 250ms 창 안에 들어오는 추가 호출은 마지막 snapshot 만 누적되어
        창이 끝날 때 한 번 더 그려진다. 사용자 체감 lag 없이 refresh 폭주를 막는다.
        """
        self._pending_snapshot = snapshot
        if self._progress_flush_timer is None:
            # leading-edge — 즉시 한 번 그린다.
            self._flush_progress()
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._on_progress_window_end)
            self._progress_flush_timer = timer
            timer.start(self._progress_debounce_ms)
        # else: 이미 창이 열려 있어 trailing flush 가 마지막 snapshot 을 처리한다.

    def _on_progress_window_end(self) -> None:
        # 창이 끝났다 — 마지막에 쌓인 snapshot 을 그려주고 타이머를 비운다.
        self._flush_progress()
        self._progress_flush_timer = None

    def _flush_progress(self) -> None:
        snapshot = self._pending_snapshot
        if snapshot is None:
            return
        # 지연 import — 모듈 결합 줄이기 위해
        from ..core.analysis_queue import _format_duration_kor

        completed = int(snapshot.completed_in_session)
        pending = int(snapshot.pending)
        total = completed + pending
        if total <= 0:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)
        else:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(completed)

        if pending == 0 and snapshot.in_flight_path is None:
            self.progress_label.setText(_tr("분석 완료"))
            return

        eta = _format_duration_kor(snapshot.eta_seconds)
        path_segment = ""
        if snapshot.in_flight_path:
            path_segment = f" — {self._shorten_path(snapshot.in_flight_path)}"
        self.progress_label.setText(
            _tr("분석 중 {done}/{total}{path} — 약 {eta} 남음").format(
                done=completed, total=total,
                path=path_segment, eta=eta,
            )
        )

    @Slot(int)
    def on_asset_analyzed(self, asset_id: int) -> None:
        # 단순 새로고침 — M3 풍부 UX 가 부분 갱신을 도입
        self.refresh()

    # -- pack ingest event flow --------------------------------------

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
                reconcile_library(self._store, self._library_root)
        except Exception:
            log.exception("failed to ingest pack %r", pack_name)
        self.refresh()

    # -- helpers ------------------------------------------------------

    @staticmethod
    def _shorten_path(path: str, *, max_len: int = 48) -> str:
        if len(path) <= max_len:
            return path
        return "…" + path[-(max_len - 1):]
