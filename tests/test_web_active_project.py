"""M7 Phase 5.1 — 활성 프로젝트 API 회귀 테스트.

5 케이스 (라이브러리 카드 채택 흐름 제거 후):
  1. GET /api/active-project → active: None (기본 상태)
  2. PUT /api/active-project → config 갱신 후 GET 에서 확인
  3. PUT /api/active-project null → active: None 으로 해제
  4. POST /api/projects → 새 프로젝트 생성
  5. PUT /api/active-project 존재하지 않는 id → 404

이전 8 케이스 중 adopt 관련 3건 (test_post_adopt_*) 은 사용자 의도와 안 맞아
제거 (라이브러리 카드 직접 채택 흐름은 의미 없음 — Claude pending-pick 만 의미).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_for_projects(deps_fixture):
    """deps_fixture 기반 build_app."""
    from gah.web.app import build_app
    return build_app(deps_fixture)


@pytest.fixture
def store_for_projects(deps_fixture):
    return deps_fixture.store


def test_get_active_project_none(app_for_projects):
    client = TestClient(app_for_projects)
    r = client.get("/api/active-project")
    assert r.status_code == 200
    assert r.json() == {"active": None}


def test_put_active_project_sets_config(app_for_projects, store_for_projects):
    pid = store_for_projects.upsert_project_id(external_id="D:/X", display_name="X")
    client = TestClient(app_for_projects)
    r = client.put("/api/active-project", json={"project_id": pid})
    assert r.status_code == 200
    r2 = client.get("/api/active-project")
    assert r2.json()["active"]["id"] == pid


def test_put_active_project_clear(app_for_projects, store_for_projects):
    pid = store_for_projects.upsert_project_id(external_id="D:/X", display_name="X")
    client = TestClient(app_for_projects)
    client.put("/api/active-project", json={"project_id": pid})
    r = client.put("/api/active-project", json={"project_id": None})
    assert r.status_code == 200
    r2 = client.get("/api/active-project")
    assert r2.json() == {"active": None}


def test_post_projects_creates(app_for_projects):
    client = TestClient(app_for_projects)
    r = client.post("/api/projects", json={
        "external_id": "D:/Unity/MyGame",
        "display_name": "MyGame",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["id"] > 0


def test_put_active_project_not_found(app_for_projects):
    client = TestClient(app_for_projects)
    r = client.put("/api/active-project", json={"project_id": 99999})
    assert r.status_code == 404
