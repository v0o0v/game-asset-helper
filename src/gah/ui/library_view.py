"""Library tab — QSplitter 3 분할 (좌 칩+필터 / 중 검색박스+테이블 / 우 슬라이더+저장).

M2 surfaces ``라벨`` (top-3 labels) and ``설명``.  M3 adds a debounced search
input on top: typing fires ``HybridSearcher.hybrid()`` after a 250 ms quiet
period (M2.1 pattern) and replaces the grid rows with the ranked results.
M4 wraps everything in a horizontal QSplitter — left/right panels are lazily
populated when ``set_label_registry`` / ``set_config`` get called (so the
M3 minimal mode without those setters still works).

신호 흐름:
    search_input.textChanged → 250ms debounce → _run_search()
    LabelChipPanel.selectionChanged → 250ms debounce → _run_search()
    FilterBar.filterChanged → 250ms debounce → _run_search()
    SearchSidePanel.weightsChanged → 250ms debounce → _run_search()
    SearchSidePanel.savedSearchActivated(name) → _on_saved_search_activated
    SearchSidePanel.saveCurrentRequested(name) → _on_save_current_requested
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtWidgets import (
    QHeaderView,
    QLineEdit,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Config
    from ..core.labels import LabelRegistry
    from ..core.search import HybridSearcher
    from ..core.store import Store


log = logging.getLogger(__name__)


_DEFAULT_LIMIT = 1000
_SEARCH_DEBOUNCE_MS = 250


def _tr(text: str) -> str:
    return QCoreApplication.translate("LibraryView", text)


class LibraryView(QWidget):
    """좌·중·우 QSplitter — 풍부 위젯은 setter 호출 시 lazy 생성."""

    def __init__(self, store: "Store", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._store = store
        self._searcher: "HybridSearcher | None" = None
        self._config: "Config | None" = None
        self._registry: "LabelRegistry | None" = None
        self._in_search_mode: bool = False
        # M4 lazy 위젯들 — setter 호출 후에만 생성/노출.
        self._chip_panel = None
        self._filter_bar = None
        self._side_panel = None

        # debounce timer (single-shot) — M2.1 _flush_progress 패턴
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(_SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._run_search)

        # ── 레이아웃 — QSplitter Horizontal 3 분할 ─────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self._splitter = QSplitter(Qt.Horizontal, self)

        # 좌측 패널 — set_label_registry 시 LabelChipPanel + FilterBar 추가.
        self._left_panel = QWidget(self._splitter)
        self._left_layout = QVBoxLayout(self._left_panel)
        self._left_layout.setContentsMargins(0, 0, 0, 0)
        self._splitter.addWidget(self._left_panel)

        # 중앙 패널 — 검색 박스 + 결과 테이블 (M3 와 동일).
        center = QWidget(self._splitter)
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        self.search_input = QLineEdit(center)
        self.search_input.setPlaceholderText(_tr("자연어 검색…"))
        self.search_input.textChanged.connect(self._on_search_text_changed)
        center_layout.addWidget(self.search_input)
        headers = (
            _tr("경로"),
            _tr("종류"),
            _tr("파일 크기"),
            _tr("분석 상태"),
            _tr("라벨"),
            _tr("설명"),
            _tr("점수"),
        )
        self.table = QTableWidget(0, len(headers), center)
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        center_layout.addWidget(self.table)
        self._splitter.addWidget(center)

        # 우측 패널 — set_config 시 SearchSidePanel 추가.
        self._right_panel = QWidget(self._splitter)
        self._right_layout = QVBoxLayout(self._right_panel)
        self._right_layout.setContentsMargins(0, 0, 0, 0)
        self._splitter.addWidget(self._right_panel)

        # 스트레치: 좌 1 · 중 4 · 우 1.
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 4)
        self._splitter.setStretchFactor(2, 1)
        root.addWidget(self._splitter)

    # -- setter (app.py 가 부팅 시 호출) ----------------------------------

    def set_searcher(self, searcher: "HybridSearcher") -> None:
        """``app.py`` 가 부팅 시 1회 호출 — HybridSearcher 주입."""
        self._searcher = searcher

    def set_config(self, config: "Config") -> None:
        """M4 — Config 주입 + 우측 SearchSidePanel lazy 생성."""
        self._config = config
        if self._side_panel is None:
            from .search_side_panel import SearchSidePanel

            self._side_panel = SearchSidePanel(config, self._store, self._right_panel)
            self._side_panel.weightsChanged.connect(self._on_filter_changed)
            self._side_panel.savedSearchActivated.connect(self._on_saved_search_activated)
            self._side_panel.saveCurrentRequested.connect(self._on_save_current_requested)
            self._right_layout.addWidget(self._side_panel)
            # 저장된 검색 초기 로드 (global = project_id None).
            self._side_panel.reload_saved_searches(None)

    def set_label_registry(self, registry: "LabelRegistry") -> None:
        """M4 — LabelRegistry 주입 + 좌측 LabelChipPanel + FilterBar lazy 생성."""
        self._registry = registry
        if self._chip_panel is None:
            from .label_chip_panel import LabelChipPanel

            self._chip_panel = LabelChipPanel(registry, self._left_panel)
            self._chip_panel.selectionChanged.connect(self._on_filter_changed)
            self._left_layout.addWidget(self._chip_panel)
        if self._filter_bar is None:
            from .filter_bar import FilterBar

            self._filter_bar = FilterBar(self._store, self._left_panel)
            self._filter_bar.filterChanged.connect(self._on_filter_changed)
            self._left_layout.addWidget(self._filter_bar)

    @property
    def is_in_search_mode(self) -> bool:
        return self._in_search_mode

    # -- 입력 이벤트 → 디바운스 → _run_search ---------------------------

    def _on_search_text_changed(self, _text: str) -> None:
        # 텍스트 + 칩 둘 다 비면 즉시 기본 모드로 복귀 (디바운스 없이).
        if not self._has_any_input():
            self._search_timer.stop()
            if self._in_search_mode:
                self._in_search_mode = False
                self.refresh()
            return
        self._search_timer.start()

    def _on_filter_changed(self) -> None:
        """칩·필터·슬라이더 변경 → 디바운스 후 검색 재호출 (입력 있을 때만)."""
        if not self._has_any_input():
            self._search_timer.stop()
            if self._in_search_mode:
                self._in_search_mode = False
                self.refresh()
            return
        self._search_timer.start()

    def _has_any_input(self) -> bool:
        if self.search_input.text().strip():
            return True
        if self._chip_panel is not None:
            _, filters = self._chip_panel.selected()
            if filters:
                return True
        return False

    # -- 핵심 검색 ----------------------------------------------------------

    def _run_search(self) -> None:
        if self._searcher is None:
            return
        text = self.search_input.text().strip()
        if not self._has_any_input():
            return

        from ..core.search import LabelFilter, SearchRequest

        # 칩 선택 → labels_all/any/none (모드 라디오 단일 단위).
        labels_all: list[LabelFilter] = []
        labels_any: list[LabelFilter] = []
        labels_none: list[LabelFilter] = []
        if self._chip_panel is not None:
            mode, chip_filters = self._chip_panel.selected()
            cf = [LabelFilter(axis=f.axis, label=f.label) for f in chip_filters]
            if mode == "all":
                labels_all = cf
            elif mode == "any":
                labels_any = cf
            elif mode == "none":
                labels_none = cf

        # FilterBar — kind + force_pack_id (단일 선택만 v1).
        fb_kind = None
        fb_force_pack = None
        if self._filter_bar is not None:
            fb = self._filter_bar.current_filters()
            fb_kind = fb.get("kind")
            packs = fb.get("pack_ids") or []
            if len(packs) == 1:
                fb_force_pack = packs[0]

        # 텍스트는 query + (registry 있으면 label_query) 둘 다로 전달.
        # 파서가 axis:label/AND/OR/NOT 토큰을 자동 추출 + 미지 토큰은 free_text 로
        # 분리되어 effective_query 에 합쳐진다.  파서 예외 (모호/혼합) 는 캐치 후
        # label_query 없이 재시도.
        use_label_query = bool(text) and self._registry is not None

        try:
            request = SearchRequest(
                query=text,
                label_query=text if use_label_query else None,
                kind=fb_kind,
                force_pack_id=fb_force_pack,
                labels_all=labels_all,
                labels_any=labels_any,
                labels_none=labels_none,
                count=20,
            )
            results = self._searcher.hybrid(request)
        except Exception:
            log.exception(
                "library search failed for query=%r; retrying without label_query",
                text,
            )
            try:
                results = self._searcher.hybrid(SearchRequest(
                    query=text,
                    kind=fb_kind,
                    force_pack_id=fb_force_pack,
                    labels_all=labels_all,
                    labels_any=labels_any,
                    labels_none=labels_none,
                    count=20,
                ))
            except Exception:
                log.exception("library search fallback also failed")
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

    # -- 저장된 검색 핸들러 ---------------------------------------------------

    def _on_saved_search_activated(self, name: str) -> None:
        """우측 패널 저장된 검색 더블클릭 → 저장된 query_json 로드 → 검색박스 채움."""
        try:
            row = self._store.get_saved_search(None, name)
        except Exception:
            log.exception("get_saved_search failed: %s", name)
            return
        if row is None:
            log.warning("saved_search not found: %s", name)
            return
        try:
            payload = json.loads(row.query_json)
        except (ValueError, TypeError):
            log.exception("saved_search query_json malformed: %s", name)
            return
        # v1: 텍스트 쿼리만 복원 (칩/필터 복원은 follow-up).
        text = payload.get("query") or ""
        self.search_input.setText(text)
        # last_used 갱신.
        try:
            self._store.update_saved_search_last_used(row.id)
        except Exception:
            log.exception("update_saved_search_last_used failed: %s", row.id)
        # 즉시 한 번 검색 (디바운스 우회).
        self._run_search()

    def _on_save_current_requested(self, name: str) -> None:
        """우측 패널 "현재 검색 저장…" 클릭 → 현재 SearchRequest 핵심만 JSON 직렬화."""
        text = self.search_input.text().strip()
        chip_mode = "all"
        chip_dump: list[dict] = []
        if self._chip_panel is not None:
            chip_mode, chip_filters = self._chip_panel.selected()
            chip_dump = [{"axis": f.axis, "label": f.label} for f in chip_filters]
        fb_kind = None
        if self._filter_bar is not None:
            fb_kind = self._filter_bar.current_filters().get("kind")
        # MCP save_search 와 같은 JSON 포맷 (project_id 제외, _schema_version=1).
        payload: dict = {
            "query": text,
            "label_query": text if (text and self._registry is not None) else None,
            "kind": fb_kind,
            "labels_all": chip_dump if chip_mode == "all" else [],
            "labels_any": chip_dump if chip_mode == "any" else [],
            "labels_none": chip_dump if chip_mode == "none" else [],
            "count": 20,
            "_schema_version": 1,
        }
        try:
            self._store.save_search(None, name, json.dumps(payload))
        except Exception:
            log.exception("save_search failed: %s", name)
            return
        if self._side_panel is not None:
            self._side_panel.reload_saved_searches(None)

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
