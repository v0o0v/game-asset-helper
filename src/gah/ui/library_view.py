"""Library tab — flat table of all indexed assets + M3 search box.

M2 surfaces ``라벨`` (top-3 labels) and ``설명``.  M3 adds a debounced
search input on top: typing fires ``HybridSearcher.hybrid()`` after a
250 ms quiet period (M2.1 pattern) and replaces the grid rows with the
ranked results.  Clearing the input restores the default library view.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtWidgets import (
    QHeaderView,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..core.search import HybridSearcher
    from ..core.store import Store


log = logging.getLogger(__name__)


_DEFAULT_LIMIT = 1000
_SEARCH_DEBOUNCE_MS = 250


def _tr(text: str) -> str:
    return QCoreApplication.translate("LibraryView", text)


class LibraryView(QWidget):
    """A flat list of all assets — pagination/filtering arrives in M4."""

    def __init__(self, store: "Store", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._searcher: "HybridSearcher | None" = None
        self._config = None
        self._in_search_mode: bool = False
        # debounce timer (single-shot) — M2.1 _flush_progress 패턴
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(_SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._run_search)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # M3: 검색 박스
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText(_tr("자연어 검색…"))
        self.search_input.textChanged.connect(self._on_search_text_changed)
        layout.addWidget(self.search_input)

        headers = (
            _tr("경로"),
            _tr("종류"),
            _tr("파일 크기"),
            _tr("분석 상태"),
            _tr("라벨"),
            _tr("설명"),
            _tr("점수"),
        )
        self.table = QTableWidget(0, len(headers), self)
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)

        layout.addWidget(self.table)

    # -- M3 search wiring --------------------------------------------

    def set_searcher(self, searcher: "HybridSearcher") -> None:
        """``app.py`` 가 부팅 시 1회 호출 — HybridSearcher 주입."""
        self._searcher = searcher

    def set_config(self, config) -> None:
        """M4: ``app.py`` 가 부팅 시 1회 호출 — Config 주입.

        SearchSidePanel 의 슬라이더 양방향 바인딩 및 현재 검색 저장 기능이
        같은 인스턴스를 참조하기 위해 필요.
        """
        self._config = config

    def set_label_registry(self, registry) -> None:
        """M4: ``app.py`` 가 부팅 시 1회 호출 — LabelRegistry 주입."""
        self._registry = registry

    @property
    def is_in_search_mode(self) -> bool:
        return self._in_search_mode

    def _on_search_text_changed(self, _text: str) -> None:
        # 빈 입력은 즉시 기본 모드로 복귀 (디바운스 없이).
        if not self.search_input.text().strip():
            self._search_timer.stop()
            if self._in_search_mode:
                self._in_search_mode = False
                self.refresh()
            return
        self._search_timer.start()

    def _run_search(self) -> None:
        if self._searcher is None:
            return
        query = self.search_input.text().strip()
        if not query:
            return
        from ..core.search import SearchRequest

        try:
            results = self._searcher.hybrid(SearchRequest(query=query, count=20))
        except Exception:  # noqa: BLE001 — UI 안에서 검색 실패가 트레이를 죽이면 안 됨
            # 단, 로그에는 traceback 을 박는다 — silent 으로 삼키면 사용자가
            # "결과가 안 보인다"는 증상만 보고 원인을 추적할 수 없음.
            log.exception("library search failed for query=%r", query)
            return
        self._show_search_results(results.results)

    def _show_search_results(self, rows) -> None:
        self._in_search_mode = True
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            matched = " · ".join(
                f"{m['axis']}={m['label']}" for m in (row.matched_labels or [])[:3]
            )
            cells = (
                row.path,
                "",  # kind — search result row 는 fast path 라 비움 (M4 풍부화)
                "",
                "",
                matched,
                row.why,
                f"{row.score:.3f}",
            )
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, item)

    def refresh(self) -> None:
        # 검색 모드 중일 때는 외부 refresh 호출 무시 (사용자 입력 우선).
        if self._in_search_mode:
            return
        rows = self._store.list_assets(limit=_DEFAULT_LIMIT, offset=0)
        # M2: 라벨/설명을 배치 조회로 채운다 (N+1 회피).
        labels_by_asset, description_by_asset = self._collect_extras(rows)

        self.table.setRowCount(len(rows))
        for r, asset in enumerate(rows):
            labels_text = self._top_labels_text(labels_by_asset.get(asset.id, []))
            desc_text = description_by_asset.get(asset.id, "")
            cells = (
                asset.path,
                asset.kind,
                str(asset.file_size),
                asset.analysis_state,
                labels_text,
                desc_text,
                "",  # M3 점수 컬럼 — 기본 모드에선 비어 있음
            )
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(r, c, item)

    # -- helpers ------------------------------------------------------

    def _collect_extras(self, rows) -> tuple[dict, dict]:
        if not rows:
            return {}, {}
        ids = [a.id for a in rows]
        placeholders = ",".join("?" * len(ids))

        labels_by_asset: dict[int, list[tuple[str, str, float, str]]] = {}
        for asset_id, axis, label, score, source in self._store.conn.execute(
            f"SELECT asset_id, axis, label, score, source FROM asset_labels"
            f" WHERE asset_id IN ({placeholders})"
            f" ORDER BY asset_id, score DESC",
            ids,
        ).fetchall():
            labels_by_asset.setdefault(int(asset_id), []).append(
                (axis, label, score, source)
            )

        description_by_asset: dict[int, str] = {}
        # Gemma description 은 분석 결과 자체 — assets_fts 의 searchable_text
        # 마지막 토큰들에서 자연어 description 을 발췌하기는 부정확해서
        # 별도 컬럼이 없는 한 빈 문자열로 둔다.  M3 에서 별도 컬럼/뷰 도입.
        # 단, sound_meta.audio_path_used / sprite_meta.dominant_colors 같은
        # 보조 정보가 필요하면 같은 쿼리에 합칠 수 있음.
        return labels_by_asset, description_by_asset

    @staticmethod
    def _top_labels_text(label_rows) -> str:
        # 상위 3개 (axis=label) 만 join — 'source' 가 다른 경우 중복은 한 번만.
        seen: set[tuple[str, str]] = set()
        picks: list[str] = []
        for axis, label, _score, _source in label_rows:
            key = (axis, label)
            if key in seen:
                continue
            seen.add(key)
            picks.append(f"{axis}={label}")
            if len(picks) >= 3:
                break
        return " · ".join(picks)
