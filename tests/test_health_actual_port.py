"""M5 — /api/health 가 WebServer actual_port 를 반환 (Phase 1B fix)."""
from __future__ import annotations
import pytest


def test_health_returns_app_state_web_port(deps_fixture):
    from fastapi.testclient import TestClient
    from gah.web.app import build_app
    app = build_app(deps_fixture)
    app.state.web_port = 9881  # 강제로 폴백 port 시뮬레이션
    with TestClient(app) as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        assert r.json()["port"] == 9881


def test_health_falls_back_to_config_port_if_app_state_unset(deps_fixture):
    from fastapi.testclient import TestClient
    from gah.web.app import build_app
    app = build_app(deps_fixture)
    # app.state.web_port 미설정 — config.web_port 로 폴백
    with TestClient(app) as c:
        r = c.get("/api/health")
        assert r.json()["port"] == deps_fixture.config.web_port
