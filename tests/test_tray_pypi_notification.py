"""M10 Task 2.6 — 트레이 PyPI 알림 메뉴 + 클립보드 복사 + Qt Signal cross-thread.

`TrayController` 는 워커 스레드 (예: `PollingLoop`) 에서 `update_check_result(result)`
가 호출되어도 Qt main thread 에서 메뉴를 갱신하도록 `_TrayBridge` (QObject) +
`Signal(object)` 으로 cross-thread 마샬링을 보장한다.

테스트 패턴:
- `fake_qapp` fixture 가 `assetcache.tray.QApplication / QSystemTrayIcon / QMenu` 를
  patch — TrayController 가 모듈 레벨 이름을 참조하기 때문에 patch 가능해야 한다.
- update 가 있는 경우 동적 메뉴 항목 추가, 없으면 미추가.
- 메뉴 클릭 → `QApplication.clipboard().setText(command)`.
- `update_signal` 속성 노출 → cross-thread emit 검증은 별도 한 줄.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def fake_qapp():
    """PySide6 클래스 3개를 patch — TrayController 가 모듈 namespace 참조.

    실제 Qt 위젯이 생성되지 않으므로 헤드리스 / CI 환경에서도 안전. QObject /
    Signal 자체는 patch 하지 않는다 — `_TrayBridge` 가 진짜 QObject 를 상속해
    main thread 마샬링 동작이 살아 있어야 한다.
    """
    with patch("assetcache.tray.QApplication") as qa, patch(
        "assetcache.tray.QSystemTrayIcon"
    ) as qsti, patch("assetcache.tray.QMenu") as qm:
        yield {"QApplication": qa, "QSystemTrayIcon": qsti, "QMenu": qm}


def test_tray_adds_update_menu_when_available(fake_qapp, qapp):
    """update.available=True → menu_actions 에 "v0.2.0" 라벨 항목 추가."""
    from assetcache.tray import TrayController
    from assetcache.core.updater.checker import CheckResult
    from assetcache.core.updater.version import Version

    controller = TrayController(app=MagicMock())
    result = CheckResult(
        current=Version.parse("0.1.0"),
        latest=Version.parse("0.2.0"),
        available=True,
        release_notes_url="https://github.com/v0o0v/assetcache-mcp/releases",
    )

    controller.update_check_result(result)
    # cross-thread Signal 이 connection 을 통해 슬롯을 호출하도록 이벤트 루프 펌프
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()

    assert any("v0.2.0" in str(c) for c in controller.menu_actions)


def test_tray_no_update_menu_when_not_available(fake_qapp, qapp):
    """available=False → "update available" 라벨 항목 없음."""
    from assetcache.tray import TrayController
    from assetcache.core.updater.checker import CheckResult
    from assetcache.core.updater.version import Version

    controller = TrayController(app=MagicMock())
    result = CheckResult(
        current=Version.parse("0.1.0"),
        latest=Version.parse("0.1.0"),
        available=False,
    )
    controller.update_check_result(result)
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()

    # msgid 는 영어 (M8 정책): "update available"
    assert not any("update available" in str(c) for c in controller.menu_actions)


def test_tray_click_update_copies_command(fake_qapp):
    """업데이트 메뉴 클릭 → QApplication.clipboard().setText(command) 호출."""
    from assetcache.tray import TrayController

    fake_clipboard = MagicMock()
    fake_qapp["QApplication"].clipboard.return_value = fake_clipboard

    controller = TrayController(app=MagicMock())
    controller._on_update_clicked("pipx upgrade assetcache-mcp")

    fake_clipboard.setText.assert_called_with("pipx upgrade assetcache-mcp")


def test_tray_signal_for_cross_thread_update(fake_qapp):
    """TrayController.update_signal 속성이 노출되어 cross-thread emit 가능해야 한다."""
    from assetcache.tray import TrayController

    controller = TrayController(app=MagicMock())
    assert hasattr(controller, "update_signal")
