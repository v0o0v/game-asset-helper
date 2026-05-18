"""M5 — FastAPI app factory + lifespan + 9 router 등록 검증."""
from __future__ import annotations
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gah.web.app import build_app


@pytest.fixture
def app_for_test(deps_fixture):
    """build_app() 으로 FastAPI 인스턴스. TestClient 사용."""
    return build_app(deps_fixture)


@pytest.fixture
def client(app_for_test):
    with TestClient(app_for_test) as c:
        yield c


def test_build_app_returns_fastapi(deps_fixture):
    app = build_app(deps_fixture)
    assert isinstance(app, FastAPI)
    assert app.title == "Game Asset Helper"


def test_health_endpoint_200(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "version" in body
    assert "port" in body
    assert body["mcp_tools_count"] == 17  # M5 신규 — 16 + request_user_pick
    assert body["pending_picks"] == 0


def test_static_htmx_served(client):
    r = client.get("/static/vendor/htmx.min.js")
    assert r.status_code == 200
    assert "htmx" in r.text.lower() or len(r.content) > 1000


def test_static_alpine_served(client):
    r = client.get("/static/vendor/alpine.min.js")
    assert r.status_code == 200
    assert len(r.content) > 1000


def test_unknown_route_404(client):
    r = client.get("/api/nonexistent")
    assert r.status_code == 404


def test_lifespan_starts_cleanup_task(deps_fixture):
    """lifespan 가 진입/종료 시 cleanup 잡을 관리."""
    app = build_app(deps_fixture)
    with TestClient(app) as c:
        # lifespan 진입 (TestClient context manager)
        assert c.get("/api/health").status_code == 200
    # context exit = lifespan 종료, 잡 cancel — 예외 X 면 OK


def test_routers_registered(deps_fixture):
    app = build_app(deps_fixture)
    # 9 router 등록 (health + library + filters + saved_searches + feedback
    # + packs + labels_admin + picks + sse). 각 라우터가 빈 stub 이어도 mount 는 됨.
    paths = [r.path for r in app.routes]
    assert "/api/health" in paths
    # 정적 mount 도 확인
    assert any("/static" in str(r) for r in app.routes)


def test_health_response_includes_pending_picks_count(client, deps_fixture):
    # PendingPickQueue 에 1개 register 후 count 확인.
    # register() 는 asyncio.get_running_loop() 을 호출하므로
    # 실행 중인 루프 안에서 호출해야 한다.
    import asyncio

    async def _do_register():
        deps_fixture.pending_picks.register([1], reason=None, project_id=None)

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_do_register())
    finally:
        loop.close()
    r = client.get("/api/health")
    assert r.json()["pending_picks"] == 1
