"""M5 Phase 4D — Qt thread-safe 트레이 시그널 브리지.

`TrayBridge` 는 uvicorn worker thread (비-Qt 스레드) 에서 `pickCountChanged.emit(n)`
을 호출하면 Qt `AutoConnection` 에 의해 main thread 이벤트 루프에서 슬롯이 실행되도록
마샬링해 준다.

`gah.web` 패키지의 다른 모듈이 PySide6 에 직접 의존하지 않도록, PySide6 import 는
이 모듈 내에서만 일어난다. `WebDeps.tray_bridge` 는 `Any | None` 으로 타입 선언되어
있어 `gah.web` → Qt 트랜지티브 의존성이 생기지 않는다.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class TrayBridge(QObject):
    """Qt main thread 에 pending pick 카운트 변경을 안전하게 전달하는 브리지.

    uvicorn worker thread 에서 `pickCountChanged.emit(n)` 을 호출하면
    Qt AutoConnection 이 QueuedConnection 으로 격상되어 main thread 의 이벤트
    루프에서 슬롯이 호출된다. 따라서 호출자는 스레드 안전성을 별도로 보장할
    필요가 없다.

    사용 패턴 (app.py)::

        bridge = TrayBridge()
        bridge.pickCountChanged.connect(lambda n: notify_user_pick_request(tray, n))
        # → WebDeps(tray_bridge=bridge, ...) 로 주입
    """

    pickCountChanged = Signal(int)
    """pending pick 카운트가 변경될 때 emit. 값은 새 카운트 (0 이상 정수)."""
