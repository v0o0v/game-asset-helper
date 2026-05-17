"""MainWindow.update_progress debounce — at 4Hz, 100 rapid snapshots
should collapse to at most 2 actual widget refreshes per 250ms window:
the leading-edge one (so the user sees something *immediately*) and a
trailing flush.

We monkey-patch :py:meth:`MainWindow._flush_progress` with a counting
wrapper rather than poking at QLabel internals.
"""

from __future__ import annotations

import time

import pytest
from PySide6.QtCore import QCoreApplication

from gah.core.analysis_queue import AnalysisProgress


def _snap(done: int, pending: int, *, path: str | None = "kenney/x.png") -> AnalysisProgress:
    return AnalysisProgress(
        completed_in_session=done,
        pending=pending,
        in_flight_path=path,
        eta_seconds=10.0,
        avg_duration_seconds=2.0,
    )


def _qwait(ms: int) -> None:
    """Process Qt events for ~ms milliseconds without QTest dependency."""
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        QCoreApplication.processEvents()
        time.sleep(0.005)


def _attach_counter(win) -> dict:
    state = {"count": 0}
    original = win._flush_progress

    def counted() -> None:
        state["count"] += 1
        original()

    win._flush_progress = counted  # type: ignore[assignment]
    return state


def test_first_update_renders_immediately(qapp, store) -> None:
    from gah.ui.main_window import MainWindow

    win = MainWindow(store)
    state = _attach_counter(win)

    win.update_progress(_snap(1, 5))

    # leading-edge 정책: 첫 호출은 타이머를 기다리지 않고 즉시 한 번 그려준다.
    assert state["count"] == 1
    win.close()


def test_rapid_updates_collapse_to_at_most_two_renders_per_window(qapp, store) -> None:
    from gah.ui.main_window import MainWindow

    win = MainWindow(store)
    state = _attach_counter(win)

    # 100회 빠르게 쏟아붓는다 — 디바운스 창이 250ms 라 모두 그 안에 들어와야 한다.
    for i in range(100):
        win.update_progress(_snap(i, 100 - i))

    # 200ms 만 기다리면 trailing flush 가 아직 안 떨어졌다 — 최대 1회(leading) 만
    _qwait(200)
    assert state["count"] <= 1, f"too many renders within window: {state['count']}"

    # 350ms 더 기다리면 trailing flush 가 떨어져서 총 2회 이내
    _qwait(350)
    assert state["count"] <= 2, f"too many renders after trailing flush: {state['count']}"
    win.close()


def test_final_snapshot_eventually_rendered_after_window(qapp, store) -> None:
    from gah.ui.main_window import MainWindow

    win = MainWindow(store)
    _attach_counter(win)  # we don't assert on count here

    win.update_progress(_snap(1, 9))
    final = _snap(9, 1, path="kenney/final.png")
    win.update_progress(final)

    # leading-edge 가 처음 snapshot 으로 그려졌더라도, 디바운스 창이 끝나면
    # 마지막 snapshot 이 라벨에 반영되어 있어야 한다.
    _qwait(400)

    text = win.progress_label.text()
    assert "final.png" in text or "9" in text  # 최종 값 반영
    win.close()
