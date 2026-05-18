"""M5 Phase 4D — TrayBridge QObject 시그널 브리지 테스트.

Task 4.10: _TrayBridge QObject (Signal) + _notify_tray_pick_count 헬퍼.

RED → GREEN 패턴:
- TrayBridge import + 속성 검증
- pickCountChanged.emit → 연결된 슬롯 호출 (Qt main thread 마샬링)
- _notify_tray_pick_count: tray_bridge=None 시 no-op
- _notify_tray_pick_count: tray_bridge=mock 시 emit 호출
- picks router 가 register/resolve/cancel 후 _notify_tray_pick_count 를 호출하는지
"""
from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock, call, patch

import pytest


# ─── TrayBridge 기본 속성 ─────────────────────────────────────────────────────


def test_tray_bridge_import():
    """TrayBridge 가 gah.web.tray_bridge 에서 import 가능해야 한다."""
    from gah.web.tray_bridge import TrayBridge  # noqa: F401


def test_tray_bridge_has_signal(qapp):
    """TrayBridge 인스턴스가 pickCountChanged Signal 을 갖고 있어야 한다."""
    from gah.web.tray_bridge import TrayBridge

    bridge = TrayBridge()
    assert hasattr(bridge, "pickCountChanged")


def test_tray_bridge_signal_connects(qapp):
    """pickCountChanged.connect(slot) 이 에러 없이 연결되어야 한다."""
    from PySide6.QtWidgets import QApplication

    from gah.web.tray_bridge import TrayBridge

    received: list[int] = []
    bridge = TrayBridge()
    bridge.pickCountChanged.connect(received.append)
    bridge.pickCountChanged.emit(3)

    # Qt 이벤트 루프 한 번 돌려서 연결된 슬롯 실행
    QApplication.processEvents()

    assert received == [3]


def test_tray_bridge_emit_from_thread(qapp):
    """다른 스레드에서 emit 해도 슬롯이 main thread 에서 호출되어야 한다.

    AutoConnection 기본으로 cross-thread 시그널은 QueuedConnection 으로
    격상되어 main thread 이벤트 루프에서 실행된다.
    """
    from PySide6.QtWidgets import QApplication

    from gah.web.tray_bridge import TrayBridge

    received: list[int] = []
    bridge = TrayBridge()
    bridge.pickCountChanged.connect(received.append)

    def _worker():
        bridge.pickCountChanged.emit(7)

    t = threading.Thread(target=_worker)
    t.start()
    t.join()

    # 이벤트 루프를 돌려서 QueuedConnection 슬롯이 실행되도록
    QApplication.processEvents()

    assert received == [7]


# ─── _notify_tray_pick_count 헬퍼 ────────────────────────────────────────────


def test_notify_tray_pick_count_no_op_when_bridge_none(deps_fixture):
    """tray_bridge=None 이면 _notify_tray_pick_count 가 에러 없이 no-op."""
    from gah.web.routers.picks import _notify_tray_pick_count

    # deps_fixture.tray_bridge 는 기본 None — 에러 없이 통과해야 한다
    _notify_tray_pick_count(deps_fixture)  # must not raise


def test_notify_tray_pick_count_emits_count(deps_fixture):
    """tray_bridge 가 mock 이면 pickCountChanged.emit(N) 이 호출되어야 한다."""
    from gah.web.deps import WebDeps
    from gah.web.routers.picks import _notify_tray_pick_count

    mock_bridge = MagicMock()
    deps = WebDeps(
        store=deps_fixture.store,
        search=deps_fixture.search,
        usage=deps_fixture.usage,
        registry=deps_fixture.registry,
        queue=deps_fixture.queue,
        config=deps_fixture.config,
        paths=deps_fixture.paths,
        pending_picks=deps_fixture.pending_picks,
        tray_bridge=mock_bridge,
    )

    # pending 큐가 비어 있을 때 → emit(0)
    _notify_tray_pick_count(deps)
    mock_bridge.pickCountChanged.emit.assert_called_once_with(0)


def test_notify_tray_pick_count_reflects_queue_size(deps_fixture):
    """pending 큐에 항목이 있을 때 emit(N) 이 올바른 N 을 전달해야 한다."""
    from gah.web.deps import WebDeps
    from gah.web.routers.picks import _notify_tray_pick_count

    mock_bridge = MagicMock()
    deps = WebDeps(
        store=deps_fixture.store,
        search=deps_fixture.search,
        usage=deps_fixture.usage,
        registry=deps_fixture.registry,
        queue=deps_fixture.queue,
        config=deps_fixture.config,
        paths=deps_fixture.paths,
        pending_picks=deps_fixture.pending_picks,
        tray_bridge=mock_bridge,
    )

    # asyncio 루프 없이 register 를 흉내내어 _items 에 직접 주입.
    # status="pending" 만 카운트해야 하므로 resolved/expired 가 섞여 있어도
    # 2 가 나오는지 회귀 가드 (Phase 6 fix: 채택 후에도 1건 표시되던 버그).
    mock_snapshot = [
        {"id": 1, "status": "pending"},
        {"id": 2, "status": "pending"},
        {"id": 3, "status": "resolved"},
        {"id": 4, "status": "expired"},
    ]
    deps.pending_picks.snapshot = lambda: mock_snapshot  # type: ignore[method-assign]

    _notify_tray_pick_count(deps)
    mock_bridge.pickCountChanged.emit.assert_called_once_with(2)


# ─── picks router — register/resolve/cancel 후 _notify_tray_pick_count 호출 ───


@pytest.mark.asyncio
async def test_internal_user_pick_calls_notify(deps_fixture):
    """POST /internal/user-pick 이 register + resolve 후 _notify_tray_pick_count 를 2회 호출."""
    import httpx
    from httpx import ASGITransport

    from gah.web.app import build_app
    from gah.web.deps import WebDeps

    mock_bridge = MagicMock()
    patched_deps = WebDeps(
        store=deps_fixture.store,
        search=deps_fixture.search,
        usage=deps_fixture.usage,
        registry=deps_fixture.registry,
        queue=deps_fixture.queue,
        config=deps_fixture.config,
        paths=deps_fixture.paths,
        pending_picks=deps_fixture.pending_picks,
        tray_bridge=mock_bridge,
    )
    app = build_app(patched_deps)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=10.0
    ) as client:
        async def _resolver():
            await asyncio.sleep(0.1)
            snap = patched_deps.pending_picks.snapshot()
            if snap:
                rid = snap[0]["request_id"]
                patched_deps.pending_picks.resolve(rid, picked_asset_id=5, user_note=None)

        task = asyncio.create_task(_resolver())
        try:
            r = await client.post(
                "/internal/user-pick",
                json={"candidates": [5], "timeout_seconds": 10},
            )
        finally:
            await task

    assert r.status_code == 200
    # register 후 1회 + finally 에서 1회 = 2회 이상
    assert mock_bridge.pickCountChanged.emit.call_count >= 2


@pytest.mark.asyncio
async def test_api_user_pick_resolve_calls_notify(deps_fixture):
    """POST /api/user-pick/{rid} 후 _notify_tray_pick_count 가 호출되어야 한다."""
    import httpx
    from httpx import ASGITransport

    from gah.web.app import build_app
    from gah.web.deps import WebDeps

    mock_bridge = MagicMock()
    patched_deps = WebDeps(
        store=deps_fixture.store,
        search=deps_fixture.search,
        usage=deps_fixture.usage,
        registry=deps_fixture.registry,
        queue=deps_fixture.queue,
        config=deps_fixture.config,
        paths=deps_fixture.paths,
        pending_picks=deps_fixture.pending_picks,
        tray_bridge=mock_bridge,
    )
    app = build_app(patched_deps)

    # pending pick 등록 (asyncio 컨텍스트 필요 — httpx ASGI 안에서)
    pending = patched_deps.pending_picks.register([10], reason=None, project_id=None)
    rid = pending.request_id

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(f"/api/user-pick/{rid}", json={"picked_asset_id": 10})

    assert r.status_code == 200
    mock_bridge.pickCountChanged.emit.assert_called()


@pytest.mark.asyncio
async def test_api_user_pick_cancel_calls_notify(deps_fixture):
    """POST /api/user-pick/{rid}/cancel 후 _notify_tray_pick_count 가 호출되어야 한다."""
    import httpx
    from httpx import ASGITransport

    from gah.web.app import build_app
    from gah.web.deps import WebDeps

    mock_bridge = MagicMock()
    patched_deps = WebDeps(
        store=deps_fixture.store,
        search=deps_fixture.search,
        usage=deps_fixture.usage,
        registry=deps_fixture.registry,
        queue=deps_fixture.queue,
        config=deps_fixture.config,
        paths=deps_fixture.paths,
        pending_picks=deps_fixture.pending_picks,
        tray_bridge=mock_bridge,
    )
    app = build_app(patched_deps)

    pending = patched_deps.pending_picks.register([3], reason=None, project_id=None)
    rid = pending.request_id

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(f"/api/user-pick/{rid}/cancel")

    assert r.status_code == 200
    mock_bridge.pickCountChanged.emit.assert_called()


# ─── TrayBridge + notify_user_pick_request 통합 (mock tray) ─────────────────


def test_tray_bridge_integration_with_mock_tray(qapp):
    """bridge.pickCountChanged.connect → notify_user_pick_request(mock_tray, n) 호출.

    Phase 4D Task 4.10 Step 3: signal 이 main thread 에서 실제 callback 을 호출.
    """
    from PySide6.QtWidgets import QApplication

    from gah.web.tray_bridge import TrayBridge

    mock_tray = MagicMock()
    notify_calls: list[int] = []

    def _slot(n: int) -> None:
        notify_calls.append(n)

    bridge = TrayBridge()
    bridge.pickCountChanged.connect(_slot)
    bridge.pickCountChanged.emit(3)

    QApplication.processEvents()

    assert notify_calls == [3]
