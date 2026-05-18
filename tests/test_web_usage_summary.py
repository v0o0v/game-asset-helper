"""M5 Phase 3D-2 — 통일성/페널티 요약 API + 상세 모달 검증 (Task 3.15)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gah.web.app import build_app


# ── fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def client(deps_fixture):
    with TestClient(build_app(deps_fixture)) as c:
        yield c


# ── GET /api/usage/summary (project_id 없음 — 글로벌) ─────────────────


def test_usage_summary_no_project_returns_default(client):
    """GET /api/usage/summary (project_id 없음) → 기본 dict 반환."""
    r = client.get("/api/usage/summary")
    assert r.status_code == 200
    data = r.json()
    assert "top_packs" in data
    assert "rejected_count" in data
    assert "window_seconds" in data
    assert isinstance(data["top_packs"], list)
    assert isinstance(data["rejected_count"], int)


def test_usage_summary_no_project_has_empty_top_packs(client):
    """project_id 없으면 top_packs = [] (v1 글로벌 단순화)."""
    r = client.get("/api/usage/summary")
    data = r.json()
    assert data["top_packs"] == []
    assert data["rejected_count"] == 0


def test_usage_summary_window_seconds_is_positive(client):
    """window_seconds 가 양수 (30일 = 2_592_000)."""
    r = client.get("/api/usage/summary")
    data = r.json()
    assert data["window_seconds"] > 0


# ── GET /api/usage/summary?project_id=... ─────────────────────────────


def test_usage_summary_with_project_id_returns_dict(client, deps_fixture):
    """project_id=1 → project_usage_summary 결과 반환."""
    # project_id=1 에 대해 asset_usage 가 없으므로 빈 pack_uses
    r = client.get("/api/usage/summary?project_id=1")
    assert r.status_code == 200
    data = r.json()
    assert "top_packs" in data
    assert isinstance(data["top_packs"], list)


def test_usage_summary_with_project_id_has_required_fields(client):
    """project_id 있는 응답도 top_packs/rejected_count/window_seconds 포함."""
    r = client.get("/api/usage/summary?project_id=1")
    data = r.json()
    assert "top_packs" in data
    assert "rejected_count" in data
    assert "window_seconds" in data


# ── GET /ui/usage/detail ─────────────────────────────────────────────


def test_usage_detail_returns_html(client):
    """GET /ui/usage/detail → HTML 응답."""
    r = client.get("/ui/usage/detail")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_usage_detail_has_modal_overlay(client):
    """GET /ui/usage/detail → modal-overlay 클래스 포함."""
    r = client.get("/ui/usage/detail")
    assert "modal-overlay" in r.text


def test_usage_detail_has_title(client):
    """GET /ui/usage/detail → 통일성/페널티 상세 타이틀 포함."""
    r = client.get("/ui/usage/detail")
    assert "통일성" in r.text


def test_usage_detail_has_close_button(client):
    """GET /ui/usage/detail → 닫기 버튼 존재."""
    r = client.get("/ui/usage/detail")
    assert "modal-close" in r.text


def test_usage_detail_with_project_id(client):
    """GET /ui/usage/detail?project_id=1 → 200 + HTML."""
    r = client.get("/ui/usage/detail?project_id=1")
    assert r.status_code == 200
    assert "modal-overlay" in r.text


# ── D 탭에 통일성 요약 섹션 + 상세 보기 버튼 존재 ───────────────────────


def test_library_page_has_usage_section(client):
    """라이브러리 페이지 D 탭에 통일성/페널티 섹션이 있다."""
    r = client.get("/library")
    assert r.status_code == 200
    assert "통일성 / 페널티" in r.text


def test_library_page_has_usage_detail_button(client):
    """라이브러리 페이지에 상세 보기 버튼이 있다."""
    r = client.get("/library")
    assert "상세 보기" in r.text
    assert "/ui/usage/detail" in r.text


def test_library_page_has_usage_modal_target(client):
    """라이브러리 페이지에 usage-modal 타겟이 있다."""
    r = client.get("/library")
    assert "usage-modal" in r.text
