"""M4 — FilterBar: 다축 필터 (pack 다중 + kind/state/license/vendor + sort).

LibraryView 상단 (검색 박스 옆) 에 들어간다.  ``filterChanged`` 시그널 +
``current_filters() -> dict`` 두 면.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QWidget,
)


if TYPE_CHECKING:  # pragma: no cover
    from ..core.store import Store


def _tr(text: str) -> str:
    return QCoreApplication.translate("FilterBar", text)


_KIND_VALUES = ("", "sprite", "spritesheet", "sound")
_STATE_VALUES = ("", "ok", "partial", "pending", "failed", "skipped")
_SORT_KEYS = (
    ("score_desc", "점수 내림차순"),
    ("score_asc", "점수 오름차순"),
    ("added_desc", "추가일 최신"),
    ("added_asc", "추가일 오래된"),
    ("name_asc", "이름 오름차순"),
    ("name_desc", "이름 내림차순"),
    ("size_desc", "크기 큰 순"),
    ("size_asc", "크기 작은 순"),
)


class FilterBar(QWidget):
    """pack 다중 선택 + kind/state/license/vendor 콤보 + 정렬 드롭다운."""

    filterChanged = Signal()

    def __init__(self, store: "Store", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store

        root = QHBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)

        # pack 다중 선택 — 작은 리스트.
        root.addWidget(QLabel(_tr("팩")))
        self._pack_list = QListWidget(self)
        self._pack_list.setSelectionMode(QListWidget.MultiSelection)
        self._pack_list.setMaximumHeight(80)
        self._pack_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._populate_packs()
        self._pack_list.itemSelectionChanged.connect(self._emit)
        root.addWidget(self._pack_list)

        # kind 콤보.
        root.addWidget(QLabel(_tr("종류")))
        self._kind = QComboBox(self)
        for k in _KIND_VALUES:
            self._kind.addItem(k or _tr("(전체)"), k)
        self._kind.currentIndexChanged.connect(self._emit)
        root.addWidget(self._kind)

        # 분석 상태 콤보.
        root.addWidget(QLabel(_tr("상태")))
        self._state = QComboBox(self)
        for s in _STATE_VALUES:
            self._state.addItem(s or _tr("(전체)"), s)
        self._state.currentIndexChanged.connect(self._emit)
        root.addWidget(self._state)

        # license / vendor — store 에 분포가 있으면 채움. 없으면 빈 콤보.
        root.addWidget(QLabel(_tr("라이선스")))
        self._license = QComboBox(self)
        self._license.addItem(_tr("(전체)"), "")
        for lic in self._distinct_licenses():
            self._license.addItem(lic, lic)
        self._license.currentIndexChanged.connect(self._emit)
        root.addWidget(self._license)

        root.addWidget(QLabel(_tr("벤더")))
        self._vendor = QComboBox(self)
        self._vendor.addItem(_tr("(전체)"), "")
        for ven in self._distinct_vendors():
            self._vendor.addItem(ven, ven)
        self._vendor.currentIndexChanged.connect(self._emit)
        root.addWidget(self._vendor)

        # 정렬 드롭다운.
        root.addWidget(QLabel(_tr("정렬")))
        self._sort = QComboBox(self)
        for key, label in _SORT_KEYS:
            self._sort.addItem(_tr(label), key)
        self._sort.currentIndexChanged.connect(self._emit)
        root.addWidget(self._sort)

    # -- public API ---------------------------------------------------

    def set_pack_selection(self, pack_ids: list[int]) -> None:
        wanted = set(int(p) for p in pack_ids)
        for i in range(self._pack_list.count()):
            it = self._pack_list.item(i)
            it.setSelected(it.data(0x0100) in wanted)  # Qt.UserRole = 0x0100

    def set_kind(self, kind: str | None) -> None:
        idx = self._kind.findData(kind or "")
        if idx >= 0:
            self._kind.setCurrentIndex(idx)

    def set_sort_key(self, key: str) -> None:
        # 정확 매칭 우선, 그 다음 prefix 매칭 (예: "name" → "name_asc").
        idx = self._sort.findData(key)
        if idx < 0:
            for i in range(self._sort.count()):
                data = self._sort.itemData(i) or ""
                if data == key or data.startswith(key + "_"):
                    idx = i
                    break
        if idx >= 0 and idx != self._sort.currentIndex():
            self._sort.setCurrentIndex(idx)
        elif idx >= 0:
            # 같은 인덱스로 설정한 경우 — currentIndexChanged 가 안 떠서 수동 발화.
            self._emit()

    def current_filters(self) -> dict:
        packs = [
            int(self._pack_list.item(i).data(0x0100))
            for i in range(self._pack_list.count())
            if self._pack_list.item(i).isSelected()
        ]
        kind = self._kind.currentData() or None
        state = self._state.currentData() or None
        license_ = self._license.currentData() or None
        vendor = self._vendor.currentData() or None
        return {
            "pack_ids": packs,
            "kind": kind,
            "analysis_state": state,
            "license": license_,
            "vendor": vendor,
            "sort_key": self._sort.currentData(),
        }

    # -- internal -----------------------------------------------------

    def _populate_packs(self) -> None:
        rows = self._store.conn.execute(
            "SELECT id, COALESCE(display_name, name) FROM packs "
            "WHERE enabled = 1 ORDER BY name"
        ).fetchall()
        for pid, name in rows:
            it = QListWidgetItem(str(name))
            it.setData(0x0100, int(pid))
            self._pack_list.addItem(it)

    def _distinct_licenses(self) -> list[str]:
        rows = self._store.conn.execute(
            "SELECT DISTINCT license FROM packs WHERE license IS NOT NULL "
            "AND license != '' ORDER BY license"
        ).fetchall()
        return [r[0] for r in rows]

    def _distinct_vendors(self) -> list[str]:
        rows = self._store.conn.execute(
            "SELECT DISTINCT vendor FROM packs WHERE vendor IS NOT NULL "
            "AND vendor != '' ORDER BY vendor"
        ).fetchall()
        return [r[0] for r in rows]

    def _emit(self, *_args) -> None:
        self.filterChanged.emit()
