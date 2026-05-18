"""M5 — 트레이 메뉴 + Claude 요청 알림 검증.

PySide6 의존성 때문에 offscreen QApplication 필요.
conftest.py 의 qt_offscreen autouse fixture 가 이미 QT_QPA_PLATFORM=offscreen
을 설정하므로 여기서는 qapp fixture 만 추가.
"""
from __future__ import annotations
import pytest


@pytest.fixture
def qapp(monkeypatch):
    """offscreen QApplication 인스턴스."""
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_open_main_invokes_callback(qapp):
    from gah.tray import make_tray_icon
    called = []
    tray = make_tray_icon(qapp, on_open_main=lambda: called.append(1))
    try:
        actions = tray.contextMenu().actions()
        open_action = next(a for a in actions if "메인 창" in a.text())
        open_action.trigger()
        assert called == [1]
    finally:
        tray.hide()


def test_make_tray_icon_no_open_labels_param(qapp):
    """on_open_labels 매개변수가 더 이상 존재하지 않는다 (M5 폐기)."""
    from gah.tray import make_tray_icon
    import inspect
    sig = inspect.signature(make_tray_icon)
    assert "on_open_labels" not in sig.parameters


def test_menu_has_no_labels_admin_entry(qapp):
    """트레이 메뉴에 '라벨 관리' 항목 없음 (웹 페이지 /labels/admin 으로 대체)."""
    from gah.tray import make_tray_icon
    tray = make_tray_icon(qapp, on_open_main=lambda: None)
    try:
        actions = tray.contextMenu().actions()
        labels = [a.text() for a in actions]
        assert not any("라벨" in t for t in labels)
    finally:
        tray.hide()


def test_notify_user_pick_request_with_count(qapp):
    from gah.tray import make_tray_icon, notify_user_pick_request
    tray = make_tray_icon(qapp, on_open_main=lambda: None)
    try:
        notify_user_pick_request(tray, count=3)
        tooltip = tray.toolTip()
        assert "Claude" in tooltip
        assert "3" in tooltip
        assert tray.property("_pick_count") == 3
    finally:
        tray.hide()


def test_notify_user_pick_request_zero_resets_tooltip(qapp):
    from gah.tray import make_tray_icon, notify_user_pick_request
    tray = make_tray_icon(qapp, on_open_main=lambda: None)
    try:
        notify_user_pick_request(tray, count=3)
        notify_user_pick_request(tray, count=0)
        tooltip = tray.toolTip()
        assert "Claude" not in tooltip
        assert tray.property("_pick_count") == 0
    finally:
        tray.hide()
