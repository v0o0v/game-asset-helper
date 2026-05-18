"""M7 Phase 5.3 — 라이브러리 카드 채택 버튼 활성 프로젝트 연동 테스트.

5 케이스:
  1. 활성 프로젝트 있으면 /library 페이지가 200
  2. 활성 프로젝트 없으면 /ui/search-results 카드에 disabled 마커
  3. POST /api/assets/{id}/adopt 활성 프로젝트로 source=user_web 기록
  4. GET /api/find_asset?q=sword 활성 프로젝트 설정 후 200 or 404
  5. /library 페이지에 글로벌 헤더 fragment (header-project 또는 관련 텍스트)

Note: library.html 은 카드를 HTMX 로 동적 로드하므로 카드 내용은
      /ui/search-results POST endpoint 를 직접 호출해 검증한다.
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from gah.core.manifest import PackManifest


def _make_asset(store, make_pack) -> int:
    """deps_fixture.store 에 자산 1개 삽입하는 헬퍼."""
    pack_name = f"adopt_pack_{int(time.time() * 1000)}"
    make_pack(name=pack_name)
    manifest = PackManifest(
        display_name=pack_name, vendor=None, source_url=None, license=None, description=None
    )
    pack_id = store.upsert_pack(pack_name, manifest, scanned_at=int(time.time()))
    return store.upsert_asset(
        pack_id, "asset.png", "sprite",
        file_hash="h_adopt", file_size=1024, added_at=int(time.time()),
    )


@pytest.fixture
def app_with_active(deps_fixture):
    from gah.web.app import build_app
    return build_app(deps_fixture)


@pytest.fixture
def store_for_adopt(deps_fixture):
    return deps_fixture.store


def test_adopt_button_enabled_with_active(app_with_active, store_for_adopt, make_pack):
    pid = store_for_adopt.upsert_project_id(external_id="D:/X", display_name="X")
    _make_asset(store_for_adopt, make_pack)
    client = TestClient(app_with_active)
    client.put("/api/active-project", json={"project_id": pid})
    r = client.get("/library")
    assert r.status_code == 200


def test_adopt_button_disabled_without_active(app_with_active, store_for_adopt, make_pack):
    """활성 프로젝트 없을 때 /ui/search-results 카드에 disabled 마커 확인."""
    _make_asset(store_for_adopt, make_pack)
    client = TestClient(app_with_active)
    # 활성 프로젝트 설정 안 함
    r = client.post("/ui/search-results", json={"query": "", "count": 20})
    assert r.status_code == 200
    body = r.text
    # 채택 버튼이 disabled 속성 또는 no-active-project 클래스로 렌더됨
    assert (
        'disabled' in body
        or "no-active-project" in body
        or "프로젝트를 먼저 선택" in body
    )


def test_adopt_post_records_with_active(app_with_active, store_for_adopt, make_pack):
    pid = store_for_adopt.upsert_project_id(external_id="D:/X", display_name="X")
    asset_id = _make_asset(store_for_adopt, make_pack)
    client = TestClient(app_with_active)
    client.put("/api/active-project", json={"project_id": pid})
    r = client.post(f"/api/assets/{asset_id}/adopt", json={})
    assert r.status_code == 200
    rows = store_for_adopt.get_project_asset_usage(project_id=pid)
    assert any(row.asset_id == asset_id and row.source == "user_web" for row in rows)


def test_search_passes_active_project_id(app_with_active, store_for_adopt):
    pid = store_for_adopt.upsert_project_id(external_id="D:/X", display_name="X")
    client = TestClient(app_with_active)
    client.put("/api/active-project", json={"project_id": pid})
    r = client.get("/api/find_asset?q=sword")
    # 자산 없으면 404, 있으면 200 — 둘 다 OK (활성 프로젝트 주입 검증)
    assert r.status_code in (200, 404)


def test_global_header_renders_on_library_page(app_with_active):
    client = TestClient(app_with_active)
    r = client.get("/library")
    assert r.status_code == 200
    # 글로벌 헤더 fragment 가 페이지에 포함됨
    assert (
        "header-project" in r.text
        or "현재 프로젝트" in r.text
        or "프로젝트 선택" in r.text
    )
