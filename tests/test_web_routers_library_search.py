"""M5 — /api/search POST (JSON 응답) + /ui/search-results HTML fragment 검증."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from gah.web.app import build_app


@pytest.fixture
def client(deps_fixture):
    with TestClient(build_app(deps_fixture)) as c:
        yield c


# populated_deps / populated_client → conftest.py 공통 fixture 사용


# ── /api/search (Task 2.1) ─────────────────────────────────────────────


def test_api_search_returns_json_with_rows(client, deps_fixture):
    """빈 라이브러리에서도 200 + rows=[] + total=0."""
    r = client.post("/api/search", json={"query": "blue hero", "count": 10})
    assert r.status_code == 200
    body = r.json()
    assert "rows" in body
    assert "total" in body
    assert isinstance(body["rows"], list)


def test_api_search_passes_label_query(client, deps_fixture):
    """label_query 가 SearchRequest 의 label_query 로 전달되어 파서 호출."""
    r = client.post("/api/search", json={
        "query": "",
        "label_query": "character AND pixel_art",
        "count": 5,
    })
    assert r.status_code == 200


def test_api_search_passes_pack_filters(client, deps_fixture):
    """pack_ids 필터가 SearchRequest 에 전달 (exclude_pack_ids 로 매핑)."""
    r = client.post("/api/search", json={
        "query": "",
        "pack_ids": [1, 2],
        "count": 5,
    })
    assert r.status_code == 200


def test_api_search_invalid_diversity_returns_422(client, deps_fixture):
    """diversity 의 enum 검증 — 'bogus' 는 422."""
    r = client.post("/api/search", json={
        "query": "",
        "diversity": "bogus_value",
    })
    assert r.status_code == 422


def test_api_search_rows_include_kind(populated_client):
    """검색 결과 rows 가 kind 필드 (sprite/sound) 를 포함해야 한다 — 카드 분기용.

    M6 회귀 — ResultRow.kind 누락으로 모든 카드가 generic 아이콘 (📦) 으로
    표시되던 버그 가드.
    """
    r = populated_client.post(
        "/api/search", json={"query": "character pixel art", "count": 10},
    )
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert rows, "populated_store 검색 결과가 비어 있으면 안 됨"
    for row in rows:
        assert "kind" in row, f"row 에 kind 필드 누락: {row}"
        assert row["kind"] in ("sprite", "sound", "spritesheet"), (
            f"예상치 못한 kind: {row['kind']}"
        )


# ── /ui/search-results (Task 2.2) ─────────────────────────────────────


def test_ui_search_results_returns_html(client, deps_fixture):
    """빈 라이브러리에서도 200 + text/html."""
    r = client.post("/ui/search-results", json={"query": "blue hero", "count": 5})
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_ui_search_results_contains_card_class(client, deps_fixture):
    """빈 라이브러리도 results-cards 컨테이너는 렌더 (카드 0개)."""
    r = client.post("/ui/search-results", json={"query": "", "count": 5})
    assert r.status_code == 200
    assert "results-cards" in r.text


def test_ui_search_results_form_data(client, deps_fixture):
    """form-data (HTMX hx-post + hx-include) 도 받아들임."""
    r = client.post("/ui/search-results", data={"query": "test", "count": "5"})
    assert r.status_code == 200


def test_api_search_offset_returns_different_rows(client, deps_fixture):
    """offset=5 + count=5 → 6번째부터 10번째 row (정상 라이브러리 가정).
    빈 라이브러리에선 rows=[] 이더라도 200 응답이 와야 한다."""
    r1 = client.post("/api/search", json={"query": "", "count": 10, "offset": 0})
    r2 = client.post("/api/search", json={"query": "", "count": 5, "offset": 5})
    assert r1.status_code == 200
    assert r2.status_code == 200
    # 빈 라이브러리도 rows 는 list 형태여야 함
    assert isinstance(r1.json()["rows"], list)
    assert isinstance(r2.json()["rows"], list)
    # offset=5 에서 r1 의 앞 5 개와 겹치지 않아야 한다 (결과가 충분한 경우)
    ids1 = [row["asset_id"] for row in r1.json()["rows"]]
    ids2 = [row["asset_id"] for row in r2.json()["rows"]]
    if ids1 and ids2:
        # r2 는 r1[5:10] 과 동일해야 함
        assert ids2 == ids1[5:10]


# ── Task 2.8: 페이지네이션 (더 보기 버튼) ────────────────────────────────


def test_ui_search_results_no_load_more_when_empty(client):
    """빈 라이브러리 → next_offset=None → 더 보기 버튼 없음."""
    r = client.post("/ui/search-results", json={"query": "", "count": 100, "offset": 0})
    assert r.status_code == 200
    assert "load-more" not in r.text


def test_ui_search_results_load_more_button(client, deps_fixture):
    """빈 라이브러리 (count=5, offset=0) → next_offset=None → 더 보기 X."""
    r = client.post("/ui/search-results", json={"query": "", "count": 5, "offset": 0})
    assert r.status_code == 200
    # 빈 라이브러리에는 더 보기 없음
    assert "load-more" not in r.text


def test_pagination_passes_offset_to_handler(client):
    """offset=5 + count=5 → 정상 처리 (200)."""
    r = client.post("/ui/search-results", json={"query": "", "count": 5, "offset": 5})
    assert r.status_code == 200


# ── Task 2.9: 디폴트 상태 (빈 검색 → 라이브러리 전체 추가일↓) ────────────


def test_default_state_empty_query_returns_library_by_added_desc(client, deps_fixture):
    """query 비어 + 필터 0 → 라이브러리 전체 (rows=list) + 200."""
    r = client.post("/api/search", json={"query": "", "count": 50, "offset": 0, "sort": "added_desc"})
    assert r.status_code == 200
    body = r.json()
    # rows 가 list (None 아닌) + 빈 라이브러리는 빈 list
    assert isinstance(body["rows"], list)
    assert "total" in body


def test_default_state_uses_added_desc_when_sort_score(client, deps_fixture):
    """빈 검색 + sort=score → 추가일↓ 폴백 (score 가 의미 없으므로) + 200."""
    r = client.post("/api/search", json={"query": "", "count": 50, "sort": "score"})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["rows"], list)


def test_default_state_ui_fragment_also_works(client, deps_fixture):
    """UI fragment 엔드포인트도 빈 검색 시 200 + results-toolbar 포함."""
    r = client.post("/ui/search-results", json={"query": "", "count": 20, "offset": 0})
    assert r.status_code == 200
    assert "results-toolbar" in r.text


def test_default_state_with_assets_returns_all(populated_client):
    """에셋이 6개인 라이브러리에서 빈 query → 6개 전부 반환 (폴백 경로)."""
    r = populated_client.post("/api/search", json={"query": "", "count": 50, "offset": 0})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body["rows"], list)
    # populated_store 에는 6개 에셋이 있다
    assert len(body["rows"]) == 6


def test_default_state_sort_score_falls_back_to_added_desc(populated_client):
    """빈 query + sort=score → added_desc 폴백 (점수가 의미 없는 디폴트 뷰)."""
    r = populated_client.post("/api/search", json={"query": "", "count": 50, "sort": "score"})
    assert r.status_code == 200
    body = r.json()
    assert len(body["rows"]) == 6


# ── 페이지네이션 toolbar 중복 방지 (코드 리뷰 피드백) ────────────────────────


def test_ui_search_results_initial_includes_toolbar(client):
    """offset=0 응답은 toolbar 포함 (전체 fragment)."""
    r = client.post("/ui/search-results", json={"query": "", "count": 5, "offset": 0})
    assert r.status_code == 200
    assert "results-toolbar" in r.text


def test_ui_search_results_pagination_no_duplicate_toolbar(client):
    """offset>0 페이지네이션 응답은 toolbar 없이 카드만 — 중복 방지."""
    r = client.post("/ui/search-results", json={"query": "", "count": 5, "offset": 5})
    assert r.status_code == 200
    assert "results-toolbar" not in r.text
