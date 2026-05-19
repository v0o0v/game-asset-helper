"""System tray icon for AssetCacheMCP.

The icon is drawn at runtime with ``QPainter`` so we don't carry a PNG
file in the source tree.  Polished artwork lands with M6.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

from assetcache.platform.autostart import is_autostart_enabled, set_autostart

if TYPE_CHECKING:  # pragma: no cover
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication, QSystemTrayIcon

    from .core.analysis_queue import AnalysisProgress

log = logging.getLogger(__name__)


def _build_app_icon() -> "QIcon":
    """Return a coloured GAH icon as a :class:`QIcon`.

    The pixmap is 64×64 (Windows scales this down to 16×16 / 24×24 in
    the system tray, so starting larger keeps anti-aliasing crisp).
    The palette is one of DESIGN.md's dominant-colour samples — dark
    teal background, warm orange initial.
    """
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QBrush, QColor, QFont, QIcon, QPainter, QPixmap

    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor("#264653")))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRect(0, 0, size, size), 12, 12)

        painter.setPen(QColor("#f4a261"))
        font = QFont("Arial", int(size * 0.55))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "G")
    finally:
        painter.end()

    return QIcon(pixmap)


def _handle_tray_activation(reason, on_open_main: Optional[Callable[[], None]]) -> None:
    """Route the tray's ``activated`` signal to :func:`on_open_main`.

    Only ``DoubleClick`` triggers the callback: a left single-click on
    Windows does nothing in most apps, and right-click is reserved for
    the context menu.
    """
    from PySide6.QtWidgets import QSystemTrayIcon

    if reason == QSystemTrayIcon.DoubleClick and on_open_main is not None:
        on_open_main()


def make_tray_icon(
    qapp: "QApplication",
    *,
    on_open_main: Optional[Callable[[], None]] = None,
) -> "QSystemTrayIcon":
    """Build a tray icon and return it.

    Parameters
    ----------
    qapp : QApplication
        The application instance that will own menu actions.
    on_open_main : callable, optional
        Invoked when the user picks "메인 창 열기" *or* double-clicks
        the tray icon.  ``None`` hides the menu entry and disables the
        double-click handler, which is convenient for tests that don't
        have a window to raise.

    M5: ``on_open_labels`` 매개변수 제거. 라벨 관리는 웹 페이지
    ``/labels/admin`` 으로 이전.

    Imports of PySide6 are deferred to function scope so that simply
    importing ``assetcache.tray`` (e.g. from the test suite) doesn't drag in
    the Qt platform plugin.
    """
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMenu, QSystemTrayIcon

    def _tr(text: str) -> str:
        return QCoreApplication.translate("Tray", text)

    icon = _build_app_icon()

    tray = QSystemTrayIcon(icon, qapp)
    tray.setToolTip(_tr("AssetCacheMCP"))

    menu = QMenu()

    if on_open_main is not None:
        open_action = QAction(_tr("메인 창 열기"), menu)
        open_action.triggered.connect(on_open_main)
        menu.addAction(open_action)
        menu.addSeparator()

    # M7: Unity 캐시 스캔 메뉴
    unity_scan_action = QAction(_tr("Unity 캐시 스캔"), menu)

    def _on_unity_scan() -> None:
        """트레이에서 Unity 캐시 수동 스캔 (별도 스레드)."""
        import threading
        import logging as _logging

        _log = _logging.getLogger(__name__)

        def _run() -> None:
            try:
                from assetcache.core.unity_import.cache_paths import detect_cache_path
                from assetcache.core.unity_import.scanner import UnityAssetStoreScanner
                from assetcache.config import load_config
                from assetcache.platform.single_instance import get_app_paths
            except ImportError:
                _log.debug("unity_import 모듈 없음 — 수동 스캔 skip")
                return
            try:
                paths, cfg = get_app_paths(), load_config()
                from assetcache.core.store import Store
                store = Store(paths.db_path)
                store.initialize()
                cache = detect_cache_path(cfg)
                if cache is None:
                    _log.info("Unity 캐시 경로 없음 — 스캔 skip")
                    store.close()
                    return
                scanner = UnityAssetStoreScanner(store=store)
                result = scanner.run_once(cache_path=cache)
                _log.info("트레이 Unity 스캔: 새 %d개", result.new)
                store.close()
            except Exception:
                _log.exception("트레이 Unity 수동 스캔 오류")

        threading.Thread(target=_run, daemon=True).start()

    unity_scan_action.triggered.connect(_on_unity_scan)
    menu.addAction(unity_scan_action)
    menu.addSeparator()

    # M8: 자동 시작 토글 체크박스
    autostart_action = QAction(_tr("자동 시작 (Windows)"), menu)
    autostart_action.setCheckable(True)
    autostart_action.setChecked(is_autostart_enabled())

    def _toggle_autostart(checked: bool) -> None:
        """자동 시작 레지스트리 키를 토글. OSError 시 롤백."""
        try:
            set_autostart(checked)
        except OSError as e:
            log.warning("자동 시작 토글 실패: %s", e)
            # 레지스트리 실제 상태로 체크박스 롤백 (무한 루프 방지: setChecked 는 toggled 재발사 안 함)
            autostart_action.setChecked(is_autostart_enabled())

    autostart_action.toggled.connect(_toggle_autostart)
    menu.addAction(autostart_action)
    menu.addSeparator()

    quit_action = QAction(_tr("종료"), menu)
    quit_action.triggered.connect(qapp.quit)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)

    tray.activated.connect(lambda reason: _handle_tray_activation(reason, on_open_main))

    tray.show()
    log.info("Tray icon initialised")
    return tray


def update_tray_tooltip(
    tray: "QSystemTrayIcon", snapshot: "AnalysisProgress"
) -> None:
    """Reflect analysis progress in the tray icon's hover tooltip."""
    from PySide6.QtCore import QCoreApplication

    from .core.analysis_queue import _format_duration_kor

    def _tr(text: str) -> str:
        return QCoreApplication.translate("Tray", text)

    completed = int(snapshot.completed_in_session)
    pending = int(snapshot.pending)
    total = completed + pending
    if pending == 0 and snapshot.in_flight_path is None:
        tray.setToolTip(_tr("AssetCacheMCP — 분석 대기 중"))
        return
    eta = _format_duration_kor(snapshot.eta_seconds)
    tray.setToolTip(
        _tr("분석 중 {done}/{total} — 약 {eta} 남음").format(
            done=completed, total=total, eta=eta,
        )
    )


def notify_user_pick_request(
    tray: "QSystemTrayIcon", count: int,
) -> None:
    """Claude 요청 카운트 변경 시 트레이 툴팁 갱신 + property 기록.

    ``count > 0`` 시 "AssetCacheMCP — Claude 요청 N건" 툴팁.
    ``count == 0`` 시 디폴트 툴팁 복원. ``_pick_count`` property 가 정수로
    기록됨 (테스트 + 디버그용).

    Qt 시그널은 본 함수 호출자가 main thread 마샬링 책임 (Phase 4 에서
    QObject signal bridge 추가). 본 함수 자체는 GUI 호출이라 main thread
    에서만 호출되어야 한다.
    """
    from PySide6.QtCore import QCoreApplication

    def _tr(text: str) -> str:
        return QCoreApplication.translate("Tray", text)

    if count > 0:
        tray.setToolTip(_tr("AssetCacheMCP — Claude 요청 {n}건").format(n=count))
        tray.setProperty("_pick_count", count)
    else:
        tray.setToolTip(_tr("AssetCacheMCP"))
        tray.setProperty("_pick_count", 0)
