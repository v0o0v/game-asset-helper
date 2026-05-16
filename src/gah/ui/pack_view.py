"""Pack tab — read-only table of registered packs.

Rich metadata columns (style summary, palette, asset breakdown) land
in M3/M6 once the analyzer and consistency scorer fill them in.  M1
just lists what the watcher found.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

if TYPE_CHECKING:  # pragma: no cover
    from ..core.store import Store


_HEADERS = ("이름", "표시명", "벤더", "라이선스", "에셋 수", "활성", "최근 스캔")


class PackView(QWidget):
    """A simple QTableWidget bound to ``store.list_packs()``."""

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
        packs = self._store.list_packs(include_disabled=True)
        self.table.setRowCount(len(packs))
        for row, pack in enumerate(packs):
            asset_count = self._store.count_assets_in_pack(pack.id)
            cells = (
                pack.name,
                pack.display_name or "",
                pack.vendor or "",
                pack.license or "",
                str(asset_count),
                "✓" if pack.enabled else "—",
                str(pack.scanned_at) if pack.scanned_at is not None else "",
            )
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, col, item)
