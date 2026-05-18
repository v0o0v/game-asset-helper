"""M5 — PendingPickQueue (Claude request_user_pick 의 in-process 큐) 검증."""
from __future__ import annotations
import asyncio
import pytest

from gah.web.pending import (
    PendingPick,
    PendingPickQueue,
    MaxPendingExceeded,
    UserCancelledError,
)


@pytest.fixture
def empty_queue() -> PendingPickQueue:
    return PendingPickQueue(max_pending=20)


@pytest.mark.asyncio
async def test_register_returns_pending_with_request_id(empty_queue: PendingPickQueue) -> None:
    p = empty_queue.register([1, 2, 3], reason="test", project_id=None)
    assert isinstance(p, PendingPick)
    assert isinstance(p.request_id, str)
    assert len(p.request_id) >= 16  # hex uuid4 = 32
    assert p.status == "pending"
    assert p.candidates == [1, 2, 3]
    assert p.reason == "test"
    assert p.project_id is None


@pytest.mark.asyncio
async def test_resolve_sets_future_result(empty_queue: PendingPickQueue) -> None:
    p = empty_queue.register([1, 2], reason=None, project_id="proj")
    ok = empty_queue.resolve(p.request_id, picked_asset_id=2, user_note="nice")
    assert ok is True
    assert p.status == "resolved"
    result = await asyncio.wait_for(p.future, timeout=0.1)
    assert result["picked_asset_id"] == 2
    assert result["user_note"] == "nice"
    assert "picked_at" in result and isinstance(result["picked_at"], int)


@pytest.mark.asyncio
async def test_resolve_unknown_rid_returns_false(empty_queue: PendingPickQueue) -> None:
    assert empty_queue.resolve("nonexistent", 1, None) is False


@pytest.mark.asyncio
async def test_cancel_raises_user_cancelled(empty_queue: PendingPickQueue) -> None:
    p = empty_queue.register([1], reason=None, project_id=None)
    assert empty_queue.cancel(p.request_id, reason="user_cancelled") is True
    assert p.status == "cancelled"
    with pytest.raises(UserCancelledError):
        await asyncio.wait_for(p.future, timeout=0.1)


@pytest.mark.asyncio
async def test_double_resolve_returns_false(empty_queue: PendingPickQueue) -> None:
    p = empty_queue.register([1, 2], reason=None, project_id=None)
    empty_queue.resolve(p.request_id, 1, None)
    assert empty_queue.resolve(p.request_id, 2, None) is False


@pytest.mark.asyncio
async def test_max_pending_raises(empty_queue: PendingPickQueue) -> None:
    q = PendingPickQueue(max_pending=2)
    q.register([1], reason=None, project_id=None)
    q.register([1], reason=None, project_id=None)
    with pytest.raises(MaxPendingExceeded):
        q.register([1], reason=None, project_id=None)


@pytest.mark.asyncio
async def test_snapshot_is_lifo(empty_queue: PendingPickQueue) -> None:
    a = empty_queue.register([1], reason="A", project_id=None)
    b = empty_queue.register([2], reason="B", project_id=None)
    c = empty_queue.register([3], reason="C", project_id=None)
    snap = empty_queue.snapshot()
    assert len(snap) == 3
    # LIFO: 최신 (c) 먼저
    assert snap[0]["request_id"] == c.request_id
    assert snap[1]["request_id"] == b.request_id
    assert snap[2]["request_id"] == a.request_id


@pytest.mark.asyncio
async def test_cleanup_expired_cancels_old_entries(empty_queue: PendingPickQueue) -> None:
    p = empty_queue.register([1], reason=None, project_id=None)
    # created_at 직접 강제로 오래된 시간으로
    p.created_at = 0.0
    removed = empty_queue.cleanup_expired(now=10_000.0, ttl=300.0)
    assert removed == 1
    assert p.status == "expired"
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(p.future, timeout=0.1)


@pytest.mark.asyncio
async def test_cleanup_expired_skips_recent(empty_queue: PendingPickQueue) -> None:
    p = empty_queue.register([1], reason=None, project_id=None)
    p.created_at = 9_900.0  # 100s 전
    removed = empty_queue.cleanup_expired(now=10_000.0, ttl=300.0)
    assert removed == 0
    assert p.status == "pending"


@pytest.mark.asyncio
async def test_resolved_entries_excluded_from_snapshot_after_cancel(empty_queue: PendingPickQueue) -> None:
    a = empty_queue.register([1], reason=None, project_id=None)
    b = empty_queue.register([2], reason=None, project_id=None)
    empty_queue.cancel(a.request_id, "user_cancelled")
    snap = empty_queue.snapshot()
    # snapshot 은 모든 status 포함 (cancelled 도) — UI 에서 회색 처리용
    rids = [s["request_id"] for s in snap]
    assert a.request_id in rids
    assert b.request_id in rids
    a_snap = next(s for s in snap if s["request_id"] == a.request_id)
    assert a_snap["status"] == "cancelled"
