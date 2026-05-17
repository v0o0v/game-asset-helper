"""M3 — 라이브러리 탭 검색 박스 (디바운스 + Searcher 호출 + 그리드 갱신)."""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QCoreApplication


def _qwait(ms: int) -> None:
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.005)


class _FakeSearcher:
    def __init__(self):
        self.calls: list[str] = []
        self._results = []  # list of SearchResults-shaped objects

    def hybrid(self, req):
        self.calls.append(req.query)

        class _Row:
            def __init__(self, asset_id, score):
                self.asset_id = asset_id
                self.pack_id = 1
                self.pack_name = "pack_a"
                self.path = "/tmp/x.png"
                self.score = score
                self.score_breakdown = {
                    "semantic": score, "keyword": 0, "label_match": 0,
                    "consistency": 0, "recency": 0,
                }
                self.matched_labels = []
                self.why = "fake"
                self.meta = {}

        class _Res:
            def __init__(self, rows):
                self.query_id = 1
                self.results = rows

        return _Res([_Row(1, 0.9), _Row(2, 0.8)])


@pytest.fixture
def view(qapp, store):
    from gah.ui.library_view import LibraryView

    v = LibraryView(store)
    yield v
    v.deleteLater()


def test_empty_input_shows_default_library_model(view):
    searcher = _FakeSearcher()
    view.set_searcher(searcher)
    view.search_input.setText("")
    _qwait(300)
    assert searcher.calls == []
    assert view.is_in_search_mode is False


def test_input_debounce_does_not_call_searcher_within_250ms(view):
    searcher = _FakeSearcher()
    view.set_searcher(searcher)
    view.search_input.setText("hero")
    _qwait(100)  # 100 ms < 250 ms debounce → searcher not called yet
    assert searcher.calls == []


def test_input_calls_searcher_once_after_250ms(view):
    searcher = _FakeSearcher()
    view.set_searcher(searcher)
    view.search_input.setText("hero pixel")
    _qwait(400)
    assert searcher.calls == ["hero pixel"]


def test_search_result_replaces_grid_model(view):
    searcher = _FakeSearcher()
    view.set_searcher(searcher)
    view.search_input.setText("anything")
    _qwait(400)
    # After search fires, rowCount reflects the 2 fake rows + view enters
    # search mode (default library is hidden until input cleared).
    assert view.is_in_search_mode is True
    assert view.table.rowCount() == 2


def test_clearing_input_restores_default_model(view):
    searcher = _FakeSearcher()
    view.set_searcher(searcher)
    view.search_input.setText("hero")
    _qwait(400)
    assert view.is_in_search_mode is True

    view.search_input.setText("")
    _qwait(400)
    assert view.is_in_search_mode is False
