"""M5 — `/api/health` 엔드포인트.

MCP server 가 트레이 부팅 직후 ping 으로 가용 여부 검증 가능.
"""
from __future__ import annotations
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health(request: Request) -> dict:
    """앱 상태 + 버전 + 포트 + MCP 도구 수 + 대기 중인 pick 수 반환."""
    deps = request.app.state.deps
    # WebServer 가 실제로 bind 한 port 를 app.state.web_port 에 기록.
    # 미설정 (TestClient 직접 사용 등) 시 config 의 기본값으로 폴백.
    actual_port = getattr(request.app.state, "web_port", deps.config.web_port)
    import gah
    return {
        "status": "ok",
        "version": gah.__version__,
        "port": actual_port,
        "mcp_tools_count": 17,  # M3 12 + M4 4 + M5 1 (request_user_pick)
        "pending_picks": len(deps.pending_picks.snapshot()),
    }
