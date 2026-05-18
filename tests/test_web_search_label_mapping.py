"""M5 Phase 3B-2 — Task 3.9: /api/search 라벨/매칭모드/pack_ids 통합 검증."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from gah.web.app import build_app


# ── 공통 fixtures ──────────────────────────────────────────────────────
# populated_deps / populated_client → conftest.py 공통 fixture 사용

@pytest.fixture
def client(deps_fixture):
    with TestClient(build_app(deps_fixture)) as c:
        yield c


# ── helpers ────────────────────────────────────────────────────────────

def _get_label_ids_by_axis(populated_deps, axis: str) -> list[int]:
    """store 에서 특정 axis 의 label id 목록 반환."""
    rows = populated_deps.store.list_labels_raw(axis=axis, enabled_only=True)
    return [r.id for r in rows]


# ── Task 3.9: labels + match_mode → SearchRequest 매핑 ────────────────


def test_api_search_with_labels_all_returns_200(populated_client, populated_deps):
    """labels=[id1] + match_mode='all' → 200."""
    ids = _get_label_ids_by_axis(populated_deps, "category")
    if not ids:
        pytest.skip("category 라벨 없음")
    r = populated_client.post("/api/search", json={
        "query": "sprite",
        "labels": [ids[0]],
        "match_mode": "all",
        "count": 10,
    })
    assert r.status_code == 200
    body = r.json()
    assert "rows" in body


def test_api_search_with_labels_any_returns_200(populated_client, populated_deps):
    """labels=[id1, id2] + match_mode='any' → 200."""
    ids = _get_label_ids_by_axis(populated_deps, "style")
    if not ids:
        pytest.skip("style 라벨 없음")
    r = populated_client.post("/api/search", json={
        "query": "hero",
        "labels": ids[:2],
        "match_mode": "any",
        "count": 10,
    })
    assert r.status_code == 200
    assert "rows" in r.json()


def test_api_search_with_labels_none_returns_200(populated_client, populated_deps):
    """labels=[id] + match_mode='none' → 200."""
    ids = _get_label_ids_by_axis(populated_deps, "sound_category")
    if not ids:
        pytest.skip("sound_category 라벨 없음")
    r = populated_client.post("/api/search", json={
        "query": "audio",
        "labels": [ids[0]],
        "match_mode": "none",
        "count": 10,
    })
    assert r.status_code == 200
    assert "rows" in r.json()


def test_api_search_nonexistent_label_id_ignored(populated_client):
    """존재하지 않는 label id → labels_all/any/none 모두 빈 list → 200."""
    r = populated_client.post("/api/search", json={
        "query": "hero",
        "labels": [99999],
        "match_mode": "all",
        "count": 10,
    })
    assert r.status_code == 200
    assert "rows" in r.json()


def test_api_search_empty_labels_list(populated_client):
    """labels=[] → 라벨 필터 없음 → 정상 검색 결과."""
    r = populated_client.post("/api/search", json={
        "query": "sprite",
        "labels": [],
        "match_mode": "all",
        "count": 10,
    })
    assert r.status_code == 200


def test_api_search_pack_ids_filter(populated_client, populated_deps):
    """pack_ids=[pack_a_id] → pack_a 소속 자산만 반환 (Python 후처리)."""
    # pack_a 의 id 조회
    packs = populated_deps.store.list_packs(include_disabled=True)
    pack_a = next((p for p in packs if p.name == "pack_a"), None)
    if pack_a is None:
        pytest.skip("pack_a 없음")
    r = populated_client.post("/api/search", json={
        "query": "sprite hero coin",
        "pack_ids": [pack_a.id],
        "count": 20,
    })
    assert r.status_code == 200
    body = r.json()
    # 반환된 모든 row 의 pack_id 가 pack_a.id 여야 함
    for row in body["rows"]:
        assert row["pack_id"] == pack_a.id, (
            f"pack_id {row['pack_id']} 가 pack_a.id {pack_a.id} 와 다름"
        )


def test_api_search_empty_pack_ids_no_filter(populated_client):
    """pack_ids=[] → 후처리 필터 없음 → 전체 결과."""
    r = populated_client.post("/api/search", json={
        "query": "sprite",
        "pack_ids": [],
        "count": 20,
    })
    assert r.status_code == 200
    assert "rows" in r.json()


# ── Task 3.9: form-data JSON parse ────────────────────────────────────


def test_ui_search_results_json_labels_string(populated_client, populated_deps):
    """/ui/search-results form-data 로 labels='[id]' 문자열 → 정상 파싱 + 200."""
    ids = _get_label_ids_by_axis(populated_deps, "category")
    if not ids:
        pytest.skip("category 라벨 없음")
    import json
    r = populated_client.post("/ui/search-results", data={
        "query": "sprite",
        "labels": json.dumps([ids[0]]),
        "match_mode": "all",
        "count": "10",
    })
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_ui_search_results_json_labels_empty_array(populated_client):
    """/ui/search-results labels='[]' 빈 JSON 배열 → 필터 없음 + 200."""
    r = populated_client.post("/ui/search-results", data={
        "query": "sprite",
        "labels": "[]",
        "count": "10",
    })
    assert r.status_code == 200


def test_ui_search_results_json_pack_ids_string(populated_client, populated_deps):
    """/ui/search-results pack_ids='[1]' 문자열 → 정상 파싱 + 200."""
    packs = populated_deps.store.list_packs(include_disabled=True)
    pack_a = next((p for p in packs if p.name == "pack_a"), None)
    if pack_a is None:
        pytest.skip("pack_a 없음")
    import json
    r = populated_client.post("/ui/search-results", data={
        "query": "sprite",
        "pack_ids": json.dumps([pack_a.id]),
        "count": "10",
    })
    assert r.status_code == 200


def test_ui_search_results_invalid_labels_json_ignored(populated_client):
    """labels 가 유효하지 않은 JSON 문자열 → 무시하고 200."""
    r = populated_client.post("/ui/search-results", data={
        "query": "sprite",
        "labels": "not_json",
        "count": "10",
    })
    assert r.status_code == 200


def test_ui_search_results_labels_empty_string(populated_client):
    """labels='' 빈 문자열 → 무시 → 200."""
    r = populated_client.post("/ui/search-results", data={
        "query": "sprite",
        "labels": "",
        "count": "10",
    })
    assert r.status_code == 200


# ── Task 3.9: library.html hidden input 3개 ───────────────────────────


def test_library_html_has_hidden_match_mode(client):
    """library.html form 에 name='match_mode' hidden input 이 존재한다."""
    r = client.get("/library")
    assert r.status_code == 200
    assert 'name="match_mode"' in r.text


def test_library_html_has_hidden_labels(client):
    """library.html form 에 name='labels' hidden input 이 존재한다."""
    r = client.get("/library")
    assert 'name="labels"' in r.text


def test_library_html_has_hidden_pack_ids(client):
    """library.html form 에 name='pack_ids' hidden input 이 존재한다."""
    r = client.get("/library")
    assert 'name="pack_ids"' in r.text


def test_library_html_match_mode_binds_to_store(client):
    """match_mode hidden input 이 $store.search.matchMode 에 바인딩된다."""
    r = client.get("/library")
    assert "$store.search.matchMode" in r.text


def test_library_html_labels_uses_json_stringify(client):
    """labels hidden input 이 JSON.stringify($store.b.selectedLabels) 를 사용한다."""
    r = client.get("/library")
    assert "JSON.stringify($store.b.selectedLabels)" in r.text


def test_library_html_pack_ids_uses_json_stringify(client):
    """pack_ids hidden input 이 JSON.stringify($store.b.selectedPackIds) 를 사용한다."""
    r = client.get("/library")
    assert "JSON.stringify($store.b.selectedPackIds)" in r.text
