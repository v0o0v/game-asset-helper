"""M5 Phase 4A — /internal/user-pick POST + /api/user-pick/{rid} POST + /cancel 검증.

Task 4.1: /internal/user-pick (MCP loopback long-poll)
Task 4.2: /api/user-pick/{rid} (사용자 응답) + /cancel (사용자 거부)
"""
from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio
import httpx
from httpx import ASGITransport

from gah.web.app import build_app
from gah.web.pending import PendingPickQueue, UserCancelledError


# ─── helpers ────────────────────────────────────────────────────────────────


def _app(deps_fixture):
    return build_app(deps_fixture)


# ─── Task 4.1 — /internal/user-pick POST (long-poll) ────────────────────────


@pytest.mark.asyncio
async def test_internal_user_pick_resolved(deps_fixture):
    """별도 asyncio task 가 0.1초 뒤 resolve → 200 + 올바른 결과 dict."""
    app = _app(deps_fixture)
    response_holder: dict = {}

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async def _resolver():
            # 요청이 pending queue 에 들어갈 때까지 조금 기다림
            await asyncio.sleep(0.1)
            snap = deps_fixture.pending_picks.snapshot()
            if snap:
                rid = snap[0]["request_id"]
                deps_fixture.pending_picks.resolve(rid, picked_asset_id=42, user_note="great")

        resolver_task = asyncio.create_task(_resolver())
        try:
            r = await client.post(
                "/internal/user-pick",
                json={"candidates": [42, 99], "reason": "choose one", "timeout_seconds": 10},
            )
        finally:
            await resolver_task

    assert r.status_code == 200
    body = r.json()
    assert body["picked_asset_id"] == 42
    assert body["user_note"] == "great"
    assert "picked_at" in body
    assert isinstance(body["picked_at"], int)


@pytest.mark.asyncio
async def test_internal_user_pick_timeout(deps_fixture):
    """timeout_seconds=1, resolver 없음 → 408 + code='408_timeout'."""
    app = _app(deps_fixture)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=10.0
    ) as client:
        r = await client.post(
            "/internal/user-pick",
            json={"candidates": [1, 2], "timeout_seconds": 1},
        )

    assert r.status_code == 408
    assert r.json()["detail"]["code"] == "408_timeout"

    # 만료된 항목이 snapshot 에 expired 상태로 남아야 함
    snap = deps_fixture.pending_picks.snapshot()
    assert any(p["status"] == "expired" for p in snap)


@pytest.mark.asyncio
async def test_internal_user_pick_cancelled(deps_fixture):
    """별도 task 가 cancel → 499 + code='499_user_cancelled'."""
    app = _app(deps_fixture)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=15.0
    ) as client:
        async def _canceller():
            await asyncio.sleep(0.1)
            snap = deps_fixture.pending_picks.snapshot()
            if snap:
                rid = snap[0]["request_id"]
                deps_fixture.pending_picks.cancel(rid, "test_cancel")

        cancel_task = asyncio.create_task(_canceller())
        try:
            r = await client.post(
                "/internal/user-pick",
                json={"candidates": [1], "timeout_seconds": 10},
            )
        finally:
            await cancel_task

    assert r.status_code == 499
    assert r.json()["detail"]["code"] == "499_user_cancelled"


@pytest.mark.asyncio
async def test_internal_user_pick_max_pending(deps_fixture):
    """queue 가 max_pending 에 도달하면 503 + code='503_too_many_pending'."""
    from gah.web.deps import WebDeps

    # max_pending=2 짜리 큐로 WebDeps 생성
    small_queue = PendingPickQueue(max_pending=2)
    small_deps = WebDeps(
        store=deps_fixture.store,
        search=deps_fixture.search,
        usage=deps_fixture.usage,
        registry=deps_fixture.registry,
        queue=deps_fixture.queue,
        config=deps_fixture.config,
        paths=deps_fixture.paths,
        pending_picks=small_queue,
    )
    small_app = build_app(small_deps)

    # 큐를 직접 register 로 채워서 HTTP 경유 없이 확실히 max 에 도달시킴
    fill_1 = small_queue.register([1], reason=None, project_id=None)
    fill_2 = small_queue.register([2], reason=None, project_id=None)

    try:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=small_app), base_url="http://test", timeout=5.0
        ) as client:
            # 큐가 꽉 찬 상태에서 POST → 503 이어야 함
            r = await client.post(
                "/internal/user-pick",
                json={"candidates": [1], "timeout_seconds": 1},
            )
    finally:
        # 정리: fill 항목들 expire
        small_queue.expire(fill_1.request_id)
        small_queue.expire(fill_2.request_id)

    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "503_too_many_pending"


@pytest.mark.asyncio
async def test_internal_user_pick_validation_too_many_candidates(deps_fixture):
    """candidates 가 11개이면 422 (max_length=10)."""
    app = _app(deps_fixture)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/internal/user-pick",
            json={"candidates": list(range(11))},
        )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_internal_user_pick_validation_empty_candidates(deps_fixture):
    """candidates 가 빈 리스트이면 422 (min_length=1)."""
    app = _app(deps_fixture)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/internal/user-pick",
            json={"candidates": []},
        )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_internal_user_pick_null_project_id(deps_fixture):
    """project_id=None 이어도 정상 등록 + resolve 가능."""
    app = _app(deps_fixture)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", timeout=10.0
    ) as client:
        async def _resolver():
            await asyncio.sleep(0.1)
            snap = deps_fixture.pending_picks.snapshot()
            if snap:
                rid = snap[0]["request_id"]
                deps_fixture.pending_picks.resolve(rid, picked_asset_id=7, user_note=None)

        resolver_task = asyncio.create_task(_resolver())
        try:
            r = await client.post(
                "/internal/user-pick",
                json={"candidates": [7], "project_id": None, "timeout_seconds": 10},
            )
        finally:
            await resolver_task

    assert r.status_code == 200
    assert r.json()["picked_asset_id"] == 7


@pytest.mark.asyncio
async def test_internal_user_pick_broadcasts_sse_event(deps_fixture):
    """POST 시 SSE bus 에 user_pick_request 이벤트가 broadcast 된다."""
    from gah.web import sse_bus

    # 먼저 subscribe
    loop = asyncio.get_event_loop()
    q = sse_bus.subscribe()

    app = _app(deps_fixture)

    try:
        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", timeout=10.0
        ) as client:
            async def _resolver():
                await asyncio.sleep(0.15)
                snap = deps_fixture.pending_picks.snapshot()
                if snap:
                    rid = snap[0]["request_id"]
                    deps_fixture.pending_picks.resolve(rid, picked_asset_id=5, user_note=None)

            resolver_task = asyncio.create_task(_resolver())
            try:
                r = await client.post(
                    "/internal/user-pick",
                    json={"candidates": [5, 6], "reason": "sse_test", "timeout_seconds": 10},
                )
            finally:
                await resolver_task

        assert r.status_code == 200

        # broadcast 는 call_soon_threadsafe 이므로 잠깐 yield
        await asyncio.sleep(0.05)

        # 큐에 user_pick_request 이벤트가 있어야 함
        events = []
        while not q.empty():
            events.append(q.get_nowait())

        pick_events = [e for e in events if e["event"] == "user_pick_request"]
        assert len(pick_events) >= 1
        data = pick_events[0]["data"]
        assert "request_id" in data
        assert data["candidates"] == [5, 6]
        assert data["reason"] == "sse_test"
    finally:
        sse_bus.unsubscribe(q)


# ─── Task 4.2 — /api/user-pick/{rid} + /cancel ──────────────────────────────


@pytest.mark.asyncio
async def test_api_user_pick_resolves(deps_fixture):
    """register → POST /api/user-pick/{rid} → future 완성 + SSE user_pick_resolved."""
    from gah.web import sse_bus

    q = sse_bus.subscribe()
    try:
        app = _app(deps_fixture)

        # pending pick 등록
        pending = deps_fixture.pending_picks.register([10, 20], reason=None, project_id=None)
        rid = pending.request_id

        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(
                f"/api/user-pick/{rid}",
                json={"picked_asset_id": 20, "user_note": "perfect"},
            )

        assert r.status_code == 200
        assert r.json()["ok"] is True

        # future 가 결과를 갖고 있어야 함
        result = await asyncio.wait_for(pending.future, timeout=1.0)
        assert result["picked_asset_id"] == 20
        assert result["user_note"] == "perfect"

        # SSE broadcast 확인
        await asyncio.sleep(0.05)
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        resolved_events = [e for e in events if e["event"] == "user_pick_resolved"]
        assert len(resolved_events) >= 1
        assert resolved_events[0]["data"]["request_id"] == rid
        assert resolved_events[0]["data"]["picked_asset_id"] == 20
    finally:
        sse_bus.unsubscribe(q)


@pytest.mark.asyncio
async def test_api_user_pick_unknown_rid(deps_fixture):
    """존재하지 않는 rid → 404."""
    app = _app(deps_fixture)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/api/user-pick/nonexistent-rid-xyz",
            json={"picked_asset_id": 1},
        )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_api_user_pick_already_resolved(deps_fixture):
    """두 번째 resolve 시도 → 409 + code='409_already_resolved'."""
    app = _app(deps_fixture)

    pending = deps_fixture.pending_picks.register([1], reason=None, project_id=None)
    rid = pending.request_id

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post(
            f"/api/user-pick/{rid}",
            json={"picked_asset_id": 1},
        )
        assert r1.status_code == 200

        r2 = await client.post(
            f"/api/user-pick/{rid}",
            json={"picked_asset_id": 1},
        )

    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == "409_already_resolved"


@pytest.mark.asyncio
async def test_api_user_pick_cancel(deps_fixture):
    """cancel → future raises UserCancelledError + SSE user_pick_resolved(cancelled=True)."""
    from gah.web import sse_bus

    q = sse_bus.subscribe()
    try:
        app = _app(deps_fixture)

        pending = deps_fixture.pending_picks.register([3, 4], reason=None, project_id=None)
        rid = pending.request_id

        async with httpx.AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.post(f"/api/user-pick/{rid}/cancel")

        assert r.status_code == 200
        assert r.json()["ok"] is True

        # future 가 UserCancelledError 를 담고 있어야 함
        with pytest.raises(UserCancelledError):
            await asyncio.wait_for(pending.future, timeout=1.0)

        # SSE broadcast 확인
        await asyncio.sleep(0.05)
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        resolved_events = [e for e in events if e["event"] == "user_pick_resolved"]
        assert len(resolved_events) >= 1
        assert resolved_events[0]["data"]["cancelled"] is True
    finally:
        sse_bus.unsubscribe(q)


@pytest.mark.asyncio
async def test_api_user_pick_cancel_unknown(deps_fixture):
    """존재하지 않는 rid 취소 → 404."""
    app = _app(deps_fixture)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/user-pick/no-such-rid/cancel")
    assert r.status_code == 404
