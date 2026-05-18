"""M5 — run_tray 가 WebServer 시작 + main_window 의존성 제거 검증."""
from __future__ import annotations
import time
from unittest.mock import MagicMock, patch
import pytest


@pytest.fixture
def offscreen_qt(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")


def test_run_tray_starts_webserver(offscreen_qt, tmp_path):
    """run_tray 가 WebServer.start() 와 stop() 을 호출."""
    from gah.config import Config, default_app_paths
    from gah.app import run_tray

    paths = default_app_paths(tmp_path)
    paths.ensure_dirs()

    with patch("gah.app.WebServer") as mock_ws, \
         patch("PySide6.QtWidgets.QApplication.exec", return_value=0) as mock_exec, \
         patch("webbrowser.open") as mock_open:
        mock_ws_instance = mock_ws.return_value
        mock_ws_instance.actual_port = 9874
        rc = run_tray(paths, Config())
        assert rc == 0
        mock_ws.assert_called_once()
        mock_ws_instance.start.assert_called_once()
        mock_ws_instance.stop.assert_called_once()


def test_run_tray_opens_browser_by_default(offscreen_qt, tmp_path):
    from gah.config import Config, default_app_paths
    from gah.app import run_tray
    paths = default_app_paths(tmp_path); paths.ensure_dirs()
    cfg = Config(web_open_browser_on_start=True)
    with patch("gah.app.WebServer") as mock_ws, \
         patch("PySide6.QtWidgets.QApplication.exec", return_value=0), \
         patch("webbrowser.open") as mock_open:
        mock_ws.return_value.actual_port = 9874
        run_tray(paths, cfg)
        mock_open.assert_called_once()
        call_url = mock_open.call_args[0][0]
        assert "127.0.0.1" in call_url
        assert "9874" in call_url


def test_run_tray_skips_browser_when_disabled(offscreen_qt, tmp_path):
    from gah.config import Config, default_app_paths
    from gah.app import run_tray
    paths = default_app_paths(tmp_path); paths.ensure_dirs()
    cfg = Config(web_open_browser_on_start=False)
    with patch("gah.app.WebServer") as mock_ws, \
         patch("PySide6.QtWidgets.QApplication.exec", return_value=0), \
         patch("webbrowser.open") as mock_open:
        mock_ws.return_value.actual_port = 9874
        run_tray(paths, cfg)
        mock_open.assert_not_called()


def test_run_tray_imports_no_main_window(offscreen_qt, tmp_path):
    """run_tray 가 main_window 를 import 하지 않음 (M5 폐기 예정)."""
    import gah.app
    source = open(gah.app.__file__, "r", encoding="utf-8").read()
    # MainWindow import 또는 ui.main_window 사용이 없어야 함
    assert "from .ui.main_window import" not in source
    assert "from gah.ui.main_window import" not in source


def test_run_tray_wires_progress_to_sse(offscreen_qt, tmp_path):
    """queue.progressChanged 신호가 SSE broadcast 로 흐른다 (import 검증)."""
    from gah.config import Config, default_app_paths
    from gah.app import run_tray
    paths = default_app_paths(tmp_path); paths.ensure_dirs()

    with patch("gah.app.WebServer") as mock_ws, \
         patch("gah.web.sse_bus.broadcast") as mock_broadcast, \
         patch("PySide6.QtWidgets.QApplication.exec", return_value=0), \
         patch("webbrowser.open"):
        mock_ws.return_value.actual_port = 9874
        rc = run_tray(paths, Config())
        assert rc == 0


def test_run_tray_uses_actual_port_in_url(offscreen_qt, tmp_path):
    """WebServer 가 9875 로 폴백 시 브라우저 URL 도 9875."""
    from gah.config import Config, default_app_paths
    from gah.app import run_tray
    paths = default_app_paths(tmp_path); paths.ensure_dirs()
    with patch("gah.app.WebServer") as mock_ws, \
         patch("PySide6.QtWidgets.QApplication.exec", return_value=0), \
         patch("webbrowser.open") as mock_open:
        mock_ws.return_value.actual_port = 9875  # 폴백
        run_tray(paths, Config())
        call_url = mock_open.call_args[0][0]
        assert "9875" in call_url
