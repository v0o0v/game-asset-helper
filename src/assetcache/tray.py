"""System tray icon for AssetCacheMCP.

The icon is drawn at runtime with ``QPainter`` so we don't carry a PNG
file in the source tree.  Polished artwork lands with M6.

M10 Task 2.6: ``TrayController`` + ``_TrayBridge`` 클래스가 추가됨. PyPI
업데이트 알림을 워커 스레드 (``PollingLoop`` 등) 에서 호출하면 Qt main
thread 이벤트 루프로 마샬링해 메뉴를 동적으로 갱신한다. ``QApplication``,
``QSystemTrayIcon``, ``QMenu`` 는 ``TrayController`` 가 모듈 레벨에서 참조
가능하도록 (테스트에서 ``patch("assetcache.tray.QApplication")`` 으로 갈
수 있게) module top-level 에 import. ``qt_offscreen`` autouse fixture 가
``QT_QPA_PLATFORM=offscreen`` 을 보장하므로 headless 환경에서도 안전.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, List, Optional

from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from assetcache.platform.autostart import is_autostart_enabled, set_autostart

if TYPE_CHECKING:  # pragma: no cover
    from PySide6.QtGui import QIcon

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


# M11.1 Task 5.4 — Batch toggle 순환 테이블 (Qt-free, 단위 테스트 가능)
_BATCH_TOGGLE_CYCLE: dict[str, str] = {
    "auto": "forced_on",
    "forced_on": "forced_off",
    "forced_off": "auto",
}


def cycle_batch_toggle(cfg: Any, path: "Path") -> None:
    """cfg.batch.toggle 을 다음 상태로 순환하고 disk 에 저장한다.

    순환 순서: auto → forced_on → forced_off → auto.

    Parameters
    ----------
    cfg:
        현재 ``Config`` 인스턴스. ``cfg.batch.toggle`` 이 in-place 갱신된다.
        (``BatchConfig`` 는 dataclass 이므로 frozen=False — 직접 attr 할당 가능.)
    path:
        config.toml 경로. ``save_config(cfg, path)`` 를 통해 저장.
    """
    from assetcache.config import save_config

    next_toggle = _BATCH_TOGGLE_CYCLE.get(cfg.batch.toggle, "auto")
    cfg.batch.toggle = next_toggle
    save_config(cfg, path)
    log.debug("batch.toggle → %s (저장: %s)", next_toggle, path)


def make_tray_icon(
    qapp: "QApplication",
    *,
    on_open_main: Optional[Callable[[], None]] = None,
    cfg: Optional[Any] = None,
    cfg_path: Optional["Path"] = None,
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
                from assetcache.config import default_app_paths, load_config
            except ImportError:
                _log.debug("unity_import 모듈 없음 — 수동 스캔 skip")
                return
            try:
                paths = default_app_paths()
                cfg = load_config(paths.config_path)
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

    # M11.1 Task 5.4 — Batch mode toggle (auto / forced_on / forced_off)
    # 클릭할 때마다 다음 상태로 순환하며 라벨이 갱신된다.
    # cfg / cfg_path 가 없을 때는 action 이 no-op 로 동작 (안전).
    def _batch_action_label(toggle: str) -> str:
        return _tr("Batch: {state}").format(state=toggle)

    # cfg / cfg_path 가 caller 에서 명시 전달되면 그것을 사용 (run_tray 가 share).
    # 명시 안 되면 fallback: disk 에서 load (단 별도 instance 라 web 과 sync X — 테스트/CLI 용).
    if cfg is not None and cfg_path is not None:
        _cfg = cfg
        _cfg_path = cfg_path
        try:
            _initial_toggle = _cfg.batch.toggle
        except AttributeError:
            log.warning("tray batch toggle: cfg.batch 없음 — fallback auto")
            _initial_toggle = "auto"
    else:
        try:
            from assetcache.config import default_app_paths, load_config
            _cfg_path = default_app_paths().config_path
            _cfg = load_config(_cfg_path)
            _initial_toggle = _cfg.batch.toggle
        except Exception:
            log.exception("tray batch toggle: load_config 실패 — action 비활성")
            _cfg = None
            _cfg_path = None
            _initial_toggle = "auto"

    batch_action = QAction(_batch_action_label(_initial_toggle), menu)
    # batch_action 을 tray 오브젝트에 attribute 로 노출 → 테스트 접근 가능
    tray._batch_action = batch_action  # type: ignore[attr-defined]

    def _on_batch_toggle() -> None:
        nonlocal _cfg
        if _cfg is None or _cfg_path is None:
            return
        try:
            cycle_batch_toggle(_cfg, _cfg_path)
            batch_action.setText(_batch_action_label(_cfg.batch.toggle))
        except Exception:
            log.exception("batch toggle 저장 실패")

    batch_action.triggered.connect(_on_batch_toggle)
    menu.addAction(batch_action)
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


# ─────────────────────────────────────────────────────────────────────────────
# M10 Task 2.6 — PyPI 업데이트 알림 동적 메뉴 + Qt Signal cross-thread bridge
# ─────────────────────────────────────────────────────────────────────────────


class _TrayBridge(QObject):
    """워커 스레드 → Qt main thread 마샬링용 QObject.

    ``PollingLoop`` (asyncio) 에서 ``update_check_result(result)`` 가 호출되면
    ``update_signal.emit(result)`` 가 발생하고, Qt AutoConnection 이
    QueuedConnection 으로 격상되어 ``TrayController._apply_update_result`` 가
    main thread 이벤트 루프에서 실행된다. 따라서 GUI 위젯 조작은 안전.
    """

    update_signal = Signal(object)
    """PyPI 업데이트 확인 결과를 main thread 로 전달. payload = CheckResult."""


class TrayController:
    """PyPI 업데이트 알림 메뉴를 동적으로 관리하는 컨트롤러.

    별도 컨테이너로 분리한 이유 — 기존 ``make_tray_icon`` 은 부팅 시 1회만
    호출되는 빌더 함수이고, 업데이트 메뉴는 24h 폴링 후에 추가/제거되어야
    하므로 mutable 상태를 가진 객체가 필요. ``app`` 은 ``QApplication`` 또는
    그 모킹된 등가물 (테스트에서 ``MagicMock()`` 주입 가능).

    사용 패턴 (M10 Phase 3 통합 시)::

        controller = TrayController(app=qapp, tray_icon=tray)
        # PollingLoop 콜백에서 ─
        controller.update_check_result(check_result)
        # → signal.emit → main thread 에서 _apply_update_result
    """

    def __init__(
        self,
        app: Any,
        tray_icon: Optional["QSystemTrayIcon"] = None,
        menu: Optional["QMenu"] = None,
    ) -> None:
        self.app = app
        self.tray_icon = tray_icon
        self.menu = menu
        self.menu_actions: List[Any] = []
        self._bridge = _TrayBridge()
        # AutoConnection: 같은 스레드이면 DirectConnection, 다르면 QueuedConnection.
        self._bridge.update_signal.connect(self._apply_update_result)
        # public alias — 테스트와 외부 호출자가 cross-thread emit 검증 시 사용.
        self.update_signal = self._bridge.update_signal

    def update_check_result(self, result: Any) -> None:
        """Thread-safe: 어디서든 호출 가능. main thread 마샬링은 Signal 책임."""
        self._bridge.update_signal.emit(result)

    def _apply_update_result(self, result: Any) -> None:
        """Qt main thread 에서 실행. menu_actions 를 result 에 맞춰 동기화.

        업데이트가 가능하면 한 개의 동적 항목을 추가, 불가능하면 기존 항목을
        제거. msgid 는 영어 (M8 정책): 라벨에는 ``"update available"`` 이
        포함되어 검색/필터 가능.
        """
        # 기존 update 메뉴 항목을 모두 제거 (라벨에 'update available' 포함).
        self.menu_actions = [
            a for a in self.menu_actions if "update available" not in str(a)
        ]
        if not getattr(result, "available", False):
            self._rebuild_menu()
            return

        # lazy import — 모듈 import 시점에 updater 패키지가 로드되지 않게 한다.
        from assetcache.core.updater.pip_command import recommended_upgrade_command

        command = recommended_upgrade_command("assetcache-mcp")
        label = self._tr("v{version} update available →").format(
            version=getattr(result, "latest", "?"),
        )
        action = self._make_menu_action(label, lambda: self._on_update_clicked(command))
        self.menu_actions.append(action)
        self._rebuild_menu()

    def _on_update_clicked(self, command: str) -> None:
        """업그레이드 명령을 클립보드로 복사 + 시스템 알림 표시."""
        clipboard = QApplication.clipboard()
        clipboard.setText(command)
        if self.tray_icon is not None:
            msg = self._tr("Upgrade command copied to clipboard")
            try:
                self.tray_icon.showMessage("AssetCacheMCP", f"{msg}: {command}")
            except Exception:  # pragma: no cover — headless fallback
                log.debug("tray_icon.showMessage 실패 (headless?) — skip")

    @staticmethod
    def _make_menu_action(label: str, callback: Callable[[], None]) -> "QAction":
        """``QAction`` 을 만들어 ``triggered`` 에 callback 연결.

        실 menu (``QMenu``) 부착은 ``_rebuild_menu`` 책임. 테스트는 라벨 문자열만
        검증하므로 ``str(action)`` 이 label 을 포함하도록 ``setText`` 직후
        ``action.setObjectName(label)`` 도 세팅 → ``QAction.__repr__`` 폴백.
        실제 PyInstaller 빌드에서는 ``setText`` 만으로 충분.
        """
        action = QAction(label)
        action.setObjectName(label)
        action.triggered.connect(lambda checked=False: callback())
        return action

    def _rebuild_menu(self) -> None:
        """``self.menu`` 가 있으면 dynamic 항목들을 다시 부착.

        구체 layout (separator / 위치) 은 ``make_tray_icon`` 의 메뉴 빌더와
        Phase 3 통합 시점에 합쳐진다. Task 2.6 에서는 menu_actions list 의
        management 만 보장하면 회귀가 깨지지 않는다.
        """
        if self.menu is None:
            return
        # 기존 dynamic 액션 제거는 menu owner 가 별도로 책임 (Phase 3 통합).
        for action in self.menu_actions:
            try:
                self.menu.addAction(action)
            except Exception:  # pragma: no cover — mocked menu safety
                log.debug("menu.addAction 실패 (mock?) — skip")

    @staticmethod
    def _tr(text: str) -> str:
        return QCoreApplication.translate("Tray", text)
