"""M5 Phase 6A — 에러 페이지 (404/500) 검증.

전역 exception_handler:
  - /api/* 경로 → JSON {"detail": "..."}
  - 그 외 경로  → HTML 에러 페이지 (status_code + message)
  - HX-Request: true 헤더 → fragment (레이아웃 없음)
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gah.web.app import build_app


@pytest.fixture
def client(deps_fixture):
    with TestClient(build_app(deps_fixture)) as c:
        yield c


# ─── 비-API 경로 404 ────────────────────────────────────────────────────────


def test_404_unknown_html_route_returns_404(client):
    """존재하지 않는 HTML 경로 → 404 상태 코드."""
    r = client.get("/nonexistent-page")
    assert r.status_code == 404


def test_404_unknown_html_route_renders_error_page(client):
    """존재하지 않는 HTML 경로 → HTML 에러 페이지 (404 숫자 포함)."""
    r = client.get("/nonexistent-page")
    assert r.status_code == 404
    assert "text/html" in r.headers["content-type"]
    assert "404" in r.text


def test_404_html_route_contains_back_link(client):
    """에러 페이지에 라이브러리 링크가 포함된다."""
    r = client.get("/nonexistent-page")
    assert r.status_code == 404
    assert "/library" in r.text


# ─── /api/* 경로 404 — JSON 응답 유지 ──────────────────────────────────────


def test_404_api_route_returns_json(client):
    """존재하지 않는 /api/* 경로 → JSON {"detail": ...} 응답 유지."""
    r = client.get("/api/nonexistent-endpoint")
    assert r.status_code == 404
    body = r.json()
    assert "detail" in body


def test_404_known_api_route_unknown_id_returns_json(client):
    """PATCH /api/packs/9999 → JSON 404 응답 — HTML 에러 페이지로 교체되면 안 됨."""
    import json
    r = client.patch(
        "/api/packs/9999",
        content=json.dumps({"enabled": True}),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 404
    body = r.json()
    assert "detail" in body


# ─── HX-Request fragment 분기 ────────────────────────────────────────────────


def test_404_htmx_request_returns_fragment(client):
    """HX-Request: true 헤더 → 에러 fragment (base.html extend 없음)."""
    r = client.get("/nonexistent-page", headers={"HX-Request": "true"})
    assert r.status_code == 404
    assert "text/html" in r.headers["content-type"]
    assert "404" in r.text
    # HTMX fragment 는 <!DOCTYPE 또는 <html 없이 inner block 만 렌더됨
    assert "<!DOCTYPE" not in r.text
    assert "<html" not in r.text
