"""M7 Phase 5.1 — 활성 프로젝트 API + 채택 endpoint 회귀 테스트.

8 케이스:
  1. GET /api/active-project → active: None (기본 상태)
  2. PUT /api/active-project → config 갱신 후 GET 에서 확인
  3. PUT /api/active-project null → active: None 으로 해제
  4. POST /api/projects → 새 프로젝트 생성
  5. POST /api/assets/{id}/adopt → 활성 프로젝트로 기록
  6. POST /api/assets/{id}/adopt 활성 프로젝트 없으면 400
  7. adopt source="user_web" 확인
  8. PUT /api/active-project 존재하지 않는 id → 404

Note: app_for_projects 와 asset_factory_for_projects 는 동일한 deps_fixture.store 를 공유.
      conftest 의 asset_factory 는 별도 store fixture 를 사용하므로 여기서는 직접 구현.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from gah.core.manifest import PackManifest


def _make_asset(store, make_pack) -> int:
    """deps_fixture.store 에 자산 1개 삽입하는 헬퍼."""
    pack_name = f"test_pack_{int(time.time() * 1000)}"
    make_pack(name=pack_name)
    manifest = PackManifest(
        display_name=pack_name, vendor=None, source_url=None, license=None, description=None
    )
    pack_id = store.upsert_pack(pack_name, manifest, scanned_at=int(time.time()))
    return store.upsert_asset(
        pack_id, "asset.png", "sprite",
        file_hash="h1", file_size=1024, added_at=int(time.time()),
    )


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


def test_post_adopt_active_project(app_for_projects, store_for_projects, make_pack):
    pid = store_for_projects.upsert_project_id(external_id="D:/A", display_name="A")
    client = TestClient(app_for_projects)
    client.put("/api/active-project", json={"project_id": pid})
    asset_id = _make_asset(store_for_projects, make_pack)
    r = client.post(f"/api/assets/{asset_id}/adopt", json={"context": "x"})
    assert r.status_code == 200


def test_post_adopt_without_active_project(app_for_projects, store_for_projects, make_pack):
    client = TestClient(app_for_projects)
    asset_id = _make_asset(store_for_projects, make_pack)
    r = client.post(f"/api/assets/{asset_id}/adopt", json={"context": "x"})
    assert r.status_code == 400


def test_adopt_records_source_user_web(app_for_projects, store_for_projects, make_pack):
    pid = store_for_projects.upsert_project_id(external_id="D:/A", display_name="A")
    client = TestClient(app_for_projects)
    client.put("/api/active-project", json={"project_id": pid})
    asset_id = _make_asset(store_for_projects, make_pack)
    client.post(f"/api/assets/{asset_id}/adopt", json={})
    rows = store_for_projects.get_project_asset_usage(project_id=pid)
    assert any(r.source == "user_web" for r in rows)


def test_put_active_project_not_found(app_for_projects):
    client = TestClient(app_for_projects)
    r = client.put("/api/active-project", json={"project_id": 99999})
    assert r.status_code == 404
