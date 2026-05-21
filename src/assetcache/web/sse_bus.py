"""M5 — SSE broadcast bus (Qt main thread → uvicorn-loop subscribers).

발화자 (analysis_progress, pack_changed 시그널 등) 는 Qt main thread.
수신자 (SSE GET /sse/notifications 의 EventSourceResponse) 는 uvicorn
별도 스레드 + 별도 asyncio 루프. 둘 사이를 thread-safe 하게 잇기 위해
각 subscriber 가 자기 loop 와 asyncio.Queue 를 보관하고, broadcast 가
``call_soon_threadsafe`` 로 이벤트를 push 한다.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from typing import Any

log = logging.getLogger(__name__)

_subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
_lock = threading.RLock()


def broadcast(event: str, data: Any) -> None:
    """모든 subscriber 에게 (event, data) push. 어느 thread 에서든 호출 OK."""
    with _lock:
        subs = list(_subscribers)
    for loop, q in subs:
        def _put(q=q, event=event, data=data):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait({"event": event, "data": data})
        try:
            loop.call_soon_threadsafe(_put)
        except RuntimeError as e:
            log.debug("SSE broadcast subscriber dead (loop closed?): %s", e)


def subscribe() -> asyncio.Queue:
    """현재 asyncio 루프에 묶인 새 Queue 를 반환. SSE 핸들러가 호출."""
    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    with _lock:
        _subscribers.append((loop, q))
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    """subscriber 목록에서 q 를 제거한다."""
    with _lock:
        _subscribers[:] = [(l, qq) for (l, qq) in _subscribers if qq is not q]


def subscriber_count() -> int:
    """현재 연결된 SSE subscriber 수를 반환한다."""
    with _lock:
        return len(_subscribers)
