"""M5 Phase 3D-2 — 저장된 검색 CRUD API 검증 (Task 3.14)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gah.web.app import build_app


# ── fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def client(deps_fixture):
    with TestClient(build_app(deps_fixture)) as c:
        yield c


# ── GET /api/saved-searches — 빈 목록 ────────────────────────────────


def test_list_saved_empty(client):
    """GET /api/saved-searches → 빈 [] 반환."""
    r = client.get("/api/saved-searches")
    assert r.status_code == 200
    assert r.json() == []


# ── POST /api/saved-searches — 저장 ───────────────────────────────────


def test_save_returns_id_and_name(client):
    """POST 저장 → id + name 반환."""
    body = {"name": "내 검색", "query": {"q": "hero", "sort": "score"}}
    r = client.post("/api/saved-searches", json=body)
    assert r.status_code == 200
    data = r.json()
    assert "id" in data
    assert data["name"] == "내 검색"


def test_save_then_list_shows_item(client):
    """POST 저장 후 GET 에서 항목 반환."""
    body = {"name": "검색A", "query": {"q": "coin"}}
    client.post("/api/saved-searches", json=body)
    r = client.get("/api/saved-searches")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["name"] == "검색A"
    assert items[0]["query"]["q"] == "coin"


def test_save_multiple_items_listed(client):
    """여러 항목 저장 후 GET 에서 모두 반환."""
    client.post("/api/saved-searches", json={"name": "A", "query": {}})
    client.post("/api/saved-searches", json={"name": "B", "query": {}})
    r = client.get("/api/saved-searches")
    assert r.status_code == 200
    names = [item["name"] for item in r.json()]
    assert "A" in names
    assert "B" in names


def test_upsert_same_name_replaces_query(client):
    """동일 이름 재저장 → query 가 교체된다."""
    client.post("/api/saved-searches", json={"name": "같은이름", "query": {"q": "original"}})
    client.post("/api/saved-searches", json={"name": "같은이름", "query": {"q": "updated"}})
    r = client.get("/api/saved-searches")
    items = r.json()
    # 이름 중복이므로 1개여야 함 (upsert)
    same = [x for x in items if x["name"] == "같은이름"]
    assert len(same) == 1
    assert same[0]["query"]["q"] == "updated"


# ── DELETE /api/saved-searches/{name} ────────────────────────────────


def test_delete_existing_returns_200(client):
    """DELETE 존재하는 항목 → 200 + deleted 키."""
    client.post("/api/saved-searches", json={"name": "삭제대상", "query": {}})
    r = client.delete("/api/saved-searches/%EC%82%AD%EC%A0%9C%EB%8C%80%EC%83%81")  # URL-encoded
    assert r.status_code == 200
    assert r.json()["deleted"] == "삭제대상"


def test_delete_then_list_is_empty(client):
    """DELETE 후 GET 에서 항목 사라짐."""
    client.post("/api/saved-searches", json={"name": "임시", "query": {}})
    client.delete("/api/saved-searches/%EC%9E%84%EC%8B%9C")
    r = client.get("/api/saved-searches")
    assert r.json() == []


def test_delete_nonexistent_returns_404(client):
    """DELETE 존재하지 않는 이름 → 404."""
    r = client.delete("/api/saved-searches/notexist")
    assert r.status_code == 404


# ── POST /api/saved-searches/run/{id} ────────────────────────────────


def test_run_returns_query_dict(client):
    """POST /api/saved-searches/run/{id} → query dict 반환."""
    saved = client.post("/api/saved-searches", json={"name": "실행테스트", "query": {"q": "bgm", "sort": "score"}})
    ss_id = saved.json()["id"]
    r = client.post(f"/api/saved-searches/run/{ss_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "실행테스트"
    assert data["query"]["q"] == "bgm"


def test_run_updates_last_used_at(client):
    """POST run 후 GET 에서 last_used_at 이 갱신된다."""
    saved = client.post("/api/saved-searches", json={"name": "사용기록", "query": {}})
    ss_id = saved.json()["id"]
    # 처음엔 last_used_at = null
    items_before = client.get("/api/saved-searches").json()
    assert items_before[0]["last_used_at"] is None
    client.post(f"/api/saved-searches/run/{ss_id}")
    items_after = client.get("/api/saved-searches").json()
    assert items_after[0]["last_used_at"] is not None


def test_run_nonexistent_id_returns_404(client):
    """POST /api/saved-searches/run/9999 (미존재) → 404."""
    r = client.post("/api/saved-searches/run/9999")
    assert r.status_code == 404


# ── 라이브러리 페이지 — 저장된 검색 UI 포함 여부 ──────────────────────


def test_library_page_has_saved_searches_section(client):
    """라이브러리 페이지에 저장된 검색 섹션이 있다."""
    r = client.get("/library")
    assert r.status_code == 200
    assert "저장된 검색" in r.text


def test_library_page_has_saved_searches_alpine_component(client):
    """라이브러리 페이지에 savedSearches Alpine 컴포넌트가 있다."""
    r = client.get("/library")
    assert "savedSearches" in r.text


def test_library_page_phase3d2_placeholder_removed(client):
    """Phase 3D-2 placeholder 가 실 구현으로 교체되어 사라졌다."""
    r = client.get("/library")
    assert "Phase 3D-2" not in r.text
