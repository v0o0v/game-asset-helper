"""M5 — Claude `request_user_pick` 의 in-process 큐.

MCP server (별 프로세스) 가 `/internal/user-pick` POST 로 등록하면
FastAPI 측의 본 큐에 PendingPick 가 박히고, asyncio.Future 가 사용자
응답을 기다린다. 사용자가 브라우저에서 채택/거부하면 `/api/user-pick/{rid}`
POST 가 `resolve`/`cancel` 을 호출 → Future 가 결과를 set → MCP server
의 long-poll 이 깨어남.

Thread safety: FastAPI 가 uvicorn[standard] 의 별 스레드에서 ASGI worker
를 돌리고, Qt 시그널이 main thread 에서 발화하므로 lock 필수.
`asyncio.Future.set_result` 는 future 의 own loop 에서만 호출해야 하므로
`call_soon_threadsafe` 로 마샬링.
"""
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any


class UserCancelledError(Exception):
    """사용자가 [✕ 거부] 를 눌러 future 가 cancel 됐을 때."""


class MaxPendingExceeded(Exception):
    """동시 pending pick 한도를 초과."""


@dataclass
class PendingPick:
    request_id: str
    candidates: list[int]
    reason: str | None
    project_id: str | None
    created_at: float
    status: str  # "pending" | "resolved" | "cancelled" | "expired"
    future: asyncio.Future = field(repr=False)
    _loop: asyncio.AbstractEventLoop = field(repr=False)
    # ^ register() 시점의 asyncio.get_running_loop() — future 의 own loop 여야 함.
    #   call_soon_threadsafe 는 반드시 이 loop 로 호출해야 thread-safe 하게 future 에 접근.
    _seq: int = field(default=0, repr=False)
    # ^ 삽입 순서 — LIFO 정렬 동점 해소용. self._lock 보호 하에서만 읽고 씀.


class PendingPickQueue:
    """thread-safe in-process queue of pending picks."""

    def __init__(self, max_pending: int = 20) -> None:
        self._items: dict[str, PendingPick] = {}
        self._lock = threading.RLock()
        self._max = max_pending
        self._seq = 0  # 단조 증가 삽입 순번

    def register(
        self, candidates: list[int], reason: str | None, project_id: str | None,
    ) -> PendingPick:
        """asyncio 컨텍스트 안에서 호출 — 현재 loop 의 future 를 만든다."""
        with self._lock:
            if len(self._items) >= self._max:
                raise MaxPendingExceeded(
                    f"동시 pending pick 한도 ({self._max}) 초과"
                )
            rid = uuid.uuid4().hex
            loop = asyncio.get_running_loop()
            fut: asyncio.Future = loop.create_future()
            self._seq += 1
            p = PendingPick(
                request_id=rid,
                candidates=list(candidates),
                reason=reason,
                project_id=project_id,
                created_at=time.time(),
                status="pending",
                future=fut,
                _loop=loop,
                _seq=self._seq,
            )
            self._items[rid] = p
            return p

    def resolve(
        self, rid: str, picked_asset_id: int, user_note: str | None,
    ) -> bool:
        """사용자 응답 → future.set_result. 이미 결정된 항목은 False.

        call_soon_threadsafe 를 lock 안에서 호출한다.
        - 원본 코드도 이미 안전했다: RLock 의 happens-before 보장으로
          Thread B 가 lock 을 획득하는 시점에는 Thread A 의 status 쓰기가
          이미 가시(visible)하므로, "pending" → 두 번 통과하는 경로가 없다.
        - 그러나 lock 안에서 호출하면 추론이 단순해지고, future 상태 변경이
          항상 status 변경과 원자적으로 묶인다.
        - call_soon_threadsafe 자체는 lock 친화적 (내부에서 lock-free 큐 사용).
        """
        with self._lock:
            p = self._items.get(rid)
            if p is None or p.status != "pending":
                return False
            p.status = "resolved"
            result = {
                "picked_asset_id": picked_asset_id,
                "user_note": user_note,
                "picked_at": int(time.time()),
            }
            p._loop.call_soon_threadsafe(p.future.set_result, result)
        return True

    def cancel(self, rid: str, reason: str) -> bool:
        """사용자 거부 → future.set_exception(UserCancelledError).

        call_soon_threadsafe 를 lock 안에서 호출 — resolve/expire 와 동일 불변식.
        """
        with self._lock:
            p = self._items.get(rid)
            if p is None or p.status != "pending":
                return False
            p.status = "cancelled"
            p._loop.call_soon_threadsafe(
                p.future.set_exception, UserCancelledError(reason),
            )
        return True

    def expire(self, rid: str) -> bool:
        """TTL 초과 → future.cancel.

        call_soon_threadsafe 를 lock 안에서 호출 — resolve/cancel 과 동일 불변식.
        """
        with self._lock:
            p = self._items.get(rid)
            if p is None or p.status != "pending":
                return False
            p.status = "expired"
            p._loop.call_soon_threadsafe(p.future.cancel)
        return True

    def cleanup_expired(self, now: float, ttl: float) -> int:
        """`created_at + ttl < now` 인 pending 항목 모두 expire. 카운트 반환."""
        to_expire: list[str] = []
        with self._lock:
            for rid, p in self._items.items():
                if p.status == "pending" and p.created_at + ttl < now:
                    to_expire.append(rid)
        for rid in to_expire:
            self.expire(rid)
        return len(to_expire)

    def snapshot(self) -> list[dict[str, Any]]:
        """LIFO (최신순) 으로 모든 항목의 메타 dict 반환."""
        with self._lock:
            items = sorted(
                self._items.values(),
                key=lambda p: p._seq,
                reverse=True,
            )
            return [
                {
                    "request_id": p.request_id,
                    "candidates": list(p.candidates),
                    "reason": p.reason,
                    "project_id": p.project_id,
                    "created_at": p.created_at,
                    "status": p.status,
                }
                for p in items
            ]
