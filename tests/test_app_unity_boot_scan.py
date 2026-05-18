"""M7 Task 2.5 — 부팅 자동 스캔 + 트레이 메뉴 smoke 테스트."""
from __future__ import annotations

import importlib


def test_boot_unity_scan_import():
    """_boot_unity_scan 함수가 app.py 에서 import 가능한지 확인."""
    import gah.app as app_mod
    assert hasattr(app_mod, "_boot_unity_scan")


def test_boot_unity_scan_skips_when_no_cache(tmp_path):
    """캐시 경로가 없을 때 _boot_unity_scan 은 예외 없이 silently skip."""
    from gah.app import _boot_unity_scan
    from gah.config import Config

    cfg = Config()
    cfg.unity_asset_store_cache_path = None  # 캐시 없음

    # store가 없어도 캐시 없으면 return 되어야 함
    class _FakeStore:
        pass

    _boot_unity_scan(cfg, _FakeStore())  # 예외 없이 통과해야 함


def test_tray_unity_scan_action_exists():
    """make_tray_icon 이 반환하는 QSystemTrayIcon 의 메뉴에
    'Unity 캐시 스캔' 액션이 있는지 확인.

    Qt 플랫폼 플러그인이 없는 headless CI 환경에서는 skip.
    """
    pytest = importlib.import_module("pytest")
    try:
        from PySide6.QtWidgets import QApplication
        qapp = QApplication.instance() or QApplication([])
    except Exception:
        pytest.skip("Qt platform plugin not available")
    from gah.tray import make_tray_icon
    tray = make_tray_icon(qapp)
    menu = tray.contextMenu()
    action_texts = [a.text() for a in menu.actions()]
    assert "Unity 캐시 스캔" in action_texts, (
        f"'Unity 캐시 스캔' not in tray menu. Found: {action_texts}"
    )
