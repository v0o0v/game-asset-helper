"""M7 Phase 6 — /projects 목록 + /projects/<id> 상세 + 자산별 선호도 패널."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ── fixture: app_for_projects ─────────────────────────────────────────


@pytest.fixture
def app_for_projects(deps_fixture):
    """deps_fixture 기반 FastAPI 앱 (Phase 6 프로젝트 페이지 전용)."""
    from gah.web.app import build_app

    return build_app(deps_fixture)


@pytest.fixture
def store(deps_fixture):
    """deps_fixture 의 store 를 직접 접근."""
    return deps_fixture.store


# ═══════════════════════════════════════════════════════════════════════
# Phase 6A — /projects 목록 페이지 (4 케이스)
# ═══════════════════════════════════════════════════════════════════════


def test_projects_page_renders_empty(app_for_projects):
    """/projects 페이지 — 프로젝트 없어도 200 반환."""
    client = TestClient(app_for_projects)
    r = client.get("/projects")
    assert r.status_code == 200


def test_projects_page_lists_projects(app_for_projects, store):
    """/projects 페이지 — 등록된 프로젝트 이름이 HTML 에 포함된다."""
    store.upsert_project_id(external_id="D:/A", display_name="GameA")
    store.upsert_project_id(external_id="D:/B", display_name="GameB")
    client = TestClient(app_for_projects)
    r = client.get("/projects")
    assert "GameA" in r.text
    assert "GameB" in r.text


def test_projects_page_highlights_active(app_for_projects, store):
    """/projects 페이지 — 활성 프로젝트 행에 강조 마커가 포함된다."""
    pid = store.upsert_project_id(external_id="D:/A", display_name="GameA")
    client = TestClient(app_for_projects)
    client.put("/api/active-project", json={"project_id": pid})
    r = client.get("/projects")
    assert f'data-active="{pid}"' in r.text or "row-active" in r.text


def test_projects_page_has_new_button(app_for_projects):
    """/projects 페이지 — '새 프로젝트' 버튼이 존재한다."""
    client = TestClient(app_for_projects)
    r = client.get("/projects")
    assert "새 프로젝트" in r.text or "new project" in r.text.lower()


# ═══════════════════════════════════════════════════════════════════════
# Phase 6B — /projects/<id> 상세 페이지 (4 케이스)
# ═══════════════════════════════════════════════════════════════════════


def test_project_detail_renders(app_for_projects, store):
    """/projects/<id> — 200 + 프로젝트 이름 포함."""
    pid = store.upsert_project_id(external_id="D:/A", display_name="GameA")
    client = TestClient(app_for_projects)
    r = client.get(f"/projects/{pid}")
    assert r.status_code == 200
    assert "GameA" in r.text


def test_project_detail_404(app_for_projects):
    """/projects/9999 — 존재하지 않는 프로젝트 → 404."""
    client = TestClient(app_for_projects)
    r = client.get("/projects/9999")
    assert r.status_code == 404


def test_project_detail_shows_usage_table(app_for_projects, store, asset_factory):
    """/projects/<id> — 자산 사용 이력 context 가 HTML 에 표시된다."""
    pid = store.upsert_project_id(external_id="D:/A", display_name="GameA")
    aid = asset_factory()
    asset = store.get_asset_by_id(aid)
    store.record_asset_use(
        project_id=pid,
        asset_id=aid,
        pack_id=asset.pack_id,
        source="explicit",
        used_at=1,
        context="lvl1",
    )
    client = TestClient(app_for_projects)
    r = client.get(f"/projects/{pid}")
    assert "lvl1" in r.text


def test_project_detail_pack_distribution(app_for_projects, store, asset_factory):
    """/projects/<id> — 채택 팩 분포 섹션이 HTML 에 있다."""
    pid = store.upsert_project_id(external_id="D:/A", display_name="GameA")
    aid = asset_factory()
    asset = store.get_asset_by_id(aid)
    for _ in range(3):
        store.record_asset_use(
            project_id=pid,
            asset_id=aid,
            pack_id=asset.pack_id,
            source="explicit",
            used_at=1,
        )
    client = TestClient(app_for_projects)
    r = client.get(f"/projects/{pid}")
    assert "pack-distribution" in r.text or "채택 팩 분포" in r.text


# ═══════════════════════════════════════════════════════════════════════
# Phase 6C — 자산별 선호도 패널 (5 케이스)
# ═══════════════════════════════════════════════════════════════════════


def test_preference_panel_in_detail(app_for_projects, store, asset_factory):
    """/projects/<id> HTML — preference-panel 섹션이 렌더된다."""
    pid = store.upsert_project_id(external_id="D:/A", display_name="GameA")
    aid = asset_factory()
    store.insert_feedback_record(
        project_id=pid,
        asset_id=aid,
        query_id=None,
        reason="positive",
        weight=0.3,
    )
    client = TestClient(app_for_projects)
    r = client.get(f"/projects/{pid}")
    assert "preference-panel" in r.text


def test_preference_sort_query(app_for_projects, store):
    """/projects/<id>/preferences.json?sort=usage_desc — 200 반환."""
    pid = store.upsert_project_id(external_id="D:/A", display_name="GameA")
    client = TestClient(app_for_projects)
    r = client.get(f"/projects/{pid}/preferences.json?sort=usage_desc")
    assert r.status_code == 200


def test_preference_search_query(app_for_projects, store, asset_factory):
    """/projects/<id>/preferences.json?search=hero — 200 반환."""
    pid = store.upsert_project_id(external_id="D:/A", display_name="GameA")
    aid = asset_factory(path="hero.png")
    asset = store.get_asset_by_id(aid)
    store.record_asset_use(
        project_id=pid,
        asset_id=aid,
        pack_id=asset.pack_id,
        source="explicit",
        used_at=1,
    )
    client = TestClient(app_for_projects)
    r = client.get(f"/projects/{pid}/preferences.json?search=hero")
    assert r.status_code == 200


def test_preference_pagination(app_for_projects, store):
    """/projects/<id>/preferences.json?offset=0&limit=5 — 200 반환."""
    pid = store.upsert_project_id(external_id="D:/A", display_name="GameA")
    client = TestClient(app_for_projects)
    r = client.get(f"/projects/{pid}/preferences.json?offset=0&limit=5")
    assert r.status_code == 200


def test_preference_score_bar_clamping(app_for_projects, store, asset_factory):
    """bar_value 는 -2~+2 로 클램프된다."""
    pid = store.upsert_project_id(external_id="D:/A", display_name="GameA")
    aid = asset_factory()
    # 매우 큰 negative weight → composite_score 가 -2 이하
    for _ in range(20):
        store.insert_feedback_record(
            project_id=pid,
            asset_id=aid,
            query_id=None,
            reason="negative",
            weight=-0.5,
        )
    client = TestClient(app_for_projects)
    r = client.get(f"/projects/{pid}/preferences.json")
    body = r.json()
    item = next((i for i in body["items"] if i["asset_id"] == aid), None)
    assert item is not None
    assert item["bar_value"] == -2
