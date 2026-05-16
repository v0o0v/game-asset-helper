"""Library tab — read-only table of all indexed assets.

M1 shows only the columns the indexer populates.  Filters, search and
preview thumbnails arrive with M3/M6.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

if TYPE_CHECKING:  # pragma: no cover
    from ..core.store import Store


_HEADERS = ("경로", "종류", "파일 크기", "분석 상태")
_DEFAULT_LIMIT = 1000


class LibraryView(QWidget):
    """A flat list of all assets — pagination/filtering is for later milestones."""

    def __init__(self, store: "Store", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.table = QTableWidget(0, len(_HEADERS), self)
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)

        layout.addWidget(self.table)

    def refresh(self) -> None:
        rows = self._store.list_assets(limit=_DEFAULT_LIMIT, offset=0)
        self.table.setRowCount(len(rows))
        for r, asset in enumerate(rows):
            cells = (asset.path, asset.kind, str(asset.file_size), asset.analysis_state)
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, item)
