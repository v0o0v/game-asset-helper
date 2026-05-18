"""M5 Phase 4A — SSE 라우터.

Task 4.3: GET /sse/notifications — EventSourceResponse (sse-starlette).
이벤트 타입: user_pick_request / user_pick_resolved / analysis_progress /
             pack_changed / ping (heartbeat 15초).
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from ..sse_bus import subscribe, unsubscribe

log = logging.getLogger(__name__)

router = APIRouter(prefix="/sse", tags=["sse"])


@router.get("/notifications")
async def sse_notifications(request: Request) -> EventSourceResponse:
    """SSE 알림 스트림.

    활성 브라우저 탭이 연결 → sse_bus 에 subscribe → 이벤트를 text/event-stream
    으로 push. 연결 해제 시 finally 에서 unsubscribe.

    이벤트 타입:
    - user_pick_request: Claude 가 사용자 선택 요청
    - user_pick_resolved: 사용자 응답/거부 완료 (다른 탭 갱신용)
    - analysis_progress: 분석 큐 진행률 (Phase 4D — Phase 4B 에서 wiring)
    - pack_changed: 팩 추가/삭제 (Phase 4D — watcher 이벤트)
    - ping: heartbeat (15초마다)
    """
    q = subscribe()

    async def event_stream():
        # 연결 즉시 ping 을 보내 headers 를 flush 하고 스트림이 live 임을 클라이언트에 알림
        yield {"event": "ping", "data": ""}
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # M7 patch: timeout 15→2초. 페이지 unload 후 빠르게
                    # is_disconnected() 체크 + ping yield 시 sse-starlette 가
                    # 끊긴 클라이언트 감지. HTTP/1.1 도메인당 6 connection
                    # 한계가 빠른 메뉴 이동 시 SSE 누적으로 채워지는 지연
                    # 회피 (M5 까지 무관했으나 M7 헤더 dropdown 추가로 노출).
                    msg = await asyncio.wait_for(q.get(), timeout=2.0)
                    yield {
                        "event": msg["event"],
                        "data": json.dumps(msg["data"], ensure_ascii=False),
                    }
                except asyncio.TimeoutError:
                    # heartbeat — 연결 유지 + 클라이언트 재연결 방지
                    yield {"event": "ping", "data": ""}
        finally:
            unsubscribe(q)
            log.debug("SSE 클라이언트 연결 해제 → unsubscribe")

    return EventSourceResponse(event_stream())
