"""M4 — LabelChipPanel: axis 별 라벨 칩 다중 선택 + AND/OR/NOT 모드 라디오.

LibraryView 좌측 사이드 패널에 들어간다.  ``selectionChanged`` 시그널이
모든 칩 토글 + 모드 변경에서 발화 — 상위 위젯이 받아 검색 재호출.

v1 한계: 모드는 패널 전체 단위 (axis 별 모드 다르게 못 잡음).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..core.label_query import LabelFilter


if TYPE_CHECKING:  # pragma: no cover
    from ..core.labels import LabelRegistry


def _tr(text: str) -> str:
    return QCoreApplication.translate("LabelChipPanel", text)


_MODES = ("all", "any", "none")


class LabelChipPanel(QWidget):
    """축별 라벨 체크박스 패널 + 매칭 모드 라디오 (AND/OR/NOT)."""

    selectionChanged = Signal()

    def __init__(
        self, registry: "LabelRegistry", parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._registry = registry
        self._checks: dict[tuple[str, str], QCheckBox] = {}
        self._mode_radios: dict[str, QRadioButton] = {}
        self._mode_group = QButtonGroup(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)

        # 매칭 모드 — 상단 라디오 1행.
        mode_box = QGroupBox(_tr("매칭 모드"))
        mb = QHBoxLayout(mode_box)
        for key, label in (("all", "AND"), ("any", "OR"), ("none", "NOT")):
            r = QRadioButton(label)
            self._mode_radios[key] = r
            self._mode_group.addButton(r)
            r.toggled.connect(self._on_radio_toggled)
            mb.addWidget(r)
        self._mode_radios["all"].setChecked(True)
        root.addWidget(mode_box)

        # axis 별 그룹 박스 (스크롤 가능)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        host = QWidget()
        self._host_layout = QVBoxLayout(host)
        self.populate(registry)
        scroll.setWidget(host)
        root.addWidget(scroll)

    # -- public API ---------------------------------------------------

    def populate(self, registry: "LabelRegistry") -> None:
        """등록된 axis/label 로 칩 그리드 빌드 (재호출 시 clear + rebuild)."""
        # 기존 그룹 박스 모두 제거.
        while self._host_layout.count():
            it = self._host_layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        self._checks.clear()
        for axis in registry.list_axes():
            labels = registry.list_labels(axis=axis, enabled_only=True)
            if not labels:
                continue
            group = QGroupBox(axis)
            hl = QHBoxLayout(group)
            for label in labels:
                cb = QCheckBox(label)
                cb.toggled.connect(self._on_check_toggled)
                self._checks[(axis, label)] = cb
                hl.addWidget(cb)
            self._host_layout.addWidget(group)
        self._host_layout.addStretch(1)

    def selected(self) -> tuple[str, list[LabelFilter]]:
        """현재 선택 — `(mode, [LabelFilter, ...])`. mode ∈ {'all','any','none'}."""
        mode = self.mode()
        chosen = [
            LabelFilter(axis=ax, label=lbl)
            for (ax, lbl), cb in self._checks.items()
            if cb.isChecked()
        ]
        return mode, chosen

    def mode(self) -> str:
        for key, r in self._mode_radios.items():
            if r.isChecked():
                return key
        return "all"

    def set_mode(self, mode: str) -> None:
        if mode not in _MODES:
            return
        self._mode_radios[mode].setChecked(True)

    # -- internal -----------------------------------------------------

    def _on_check_toggled(self, _checked: bool) -> None:
        self.selectionChanged.emit()

    def _on_radio_toggled(self, _checked: bool) -> None:
        # 두 라디오가 toggled 시그널을 동시에 보내지만 (one ON, one OFF) —
        # 중복 발화 방지를 위해 ON 케이스만.
        if not _checked:
            return
        self.selectionChanged.emit()
