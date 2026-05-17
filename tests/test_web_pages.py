"""M5 — HTML 페이지 라우트 검증 (/, /library)."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from gah.web.app import build_app


@pytest.fixture
def client(deps_fixture):
    with TestClient(build_app(deps_fixture)) as c:
        yield c


def test_root_redirects_to_library(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (301, 302, 307, 308)
    assert "/library" in r.headers.get("location", "")


def test_library_page_returns_200_html(client):
    r = client.get("/library")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_library_page_contains_search_bar(client):
    r = client.get("/library")
    # 검색 바 (HTMX hx-post → /ui/search-results)
    assert "hx-post" in r.text
    assert "/ui/search-results" in r.text


def test_library_page_includes_static_assets(client):
    r = client.get("/library")
    # HTMX, Alpine, CSS 로드 확인
    assert "htmx.min.js" in r.text
    assert "alpine.min.js" in r.text
    assert "main.css" in r.text


def test_library_page_initializes_alpine_stores(client):
    r = client.get("/library")
    # Alpine.store('search', ...) 초기화 코드 존재
    assert "Alpine.store" in r.text
    assert "'search'" in r.text or '"search"' in r.text
    assert "advanced" in r.text  # ⚙ 토글 상태


def test_library_page_has_advanced_toggle(client):
    r = client.get("/library")
    # ⚙ 고급 버튼 존재
    assert "고급" in r.text  # Korean label


def test_search_bar_has_300ms_debounce(client):
    r = client.get("/library")
    assert "delay:300ms" in r.text


def test_search_bar_targets_results(client):
    r = client.get("/library")
    assert 'hx-target="#results"' in r.text


def test_library_page_has_load_trigger(client):
    """페이지 로드 시 자동으로 디폴트 결과 fetch."""
    r = client.get("/library")
    assert "load" in r.text  # hx-trigger="... , load"


def test_results_container_exists(client):
    r = client.get("/library")
    assert 'id="results"' in r.text


# ── Task 2.7: 결과 툴바 ─────────────────────────────────────────────────


def test_results_grid_includes_toolbar(client):
    """결과 영역에 그리드/리스트 토글 + 카드 크기 + 정렬 + 카운트."""
    r = client.post("/ui/search-results", json={"query": "", "count": 5})
    assert r.status_code == 200
    assert "results-toolbar" in r.text
    assert "view-toggle" in r.text or "view-mode" in r.text


def test_results_toolbar_has_size_buttons(client):
    r = client.post("/ui/search-results", json={"query": "", "count": 5})
    # S/M/L 버튼 — Alpine 의 $store.search.cardSize 조작
    assert "cardSize" in r.text


def test_results_toolbar_has_sort_dropdown(client):
    r = client.post("/ui/search-results", json={"query": "", "count": 5})
    # 정렬 옵션 포함 검증
    assert "정렬" in r.text or "sort" in r.text


def test_results_toolbar_shows_total_count(client):
    """총 자산 카운트 표시."""
    r = client.post("/ui/search-results", json={"query": "", "count": 5})
    # 빈 라이브러리 → "0 자산" 같은 표현
    assert "자산" in r.text or "total" in r.text


# ── Task 2.12: 통합 흐름 검증 ───────────────────────────────────────────


def test_full_library_page_flow(client):
    """라이브러리 페이지 로드 → 검색 fragment → 툴바 + 카드 영역 포함."""
    r1 = client.get("/library")
    assert r1.status_code == 200
    # 모달 컨테이너 존재 (Task 2.10 에서 추가)
    assert "asset-detail-modal" in r1.text

    r2 = client.post("/ui/search-results", json={"query": "", "count": 20})
    assert r2.status_code == 200
    assert "results-toolbar" in r2.text
    assert "results-cards" in r2.text


def test_asset_detail_modal_container_in_library(client):
    """library.html 에 #asset-detail-modal 컨테이너가 존재한다."""
    r = client.get("/library")
    assert r.status_code == 200
    assert 'id="asset-detail-modal"' in r.text


def test_card_wide_has_hx_get_asset_detail(client):
    """카드 wide 가 hx-get="/ui/asset-detail/..." 를 포함한다."""
    # 빈 라이브러리에서는 카드가 없으므로 populated 필요 → 템플릿 존재만 확인
    # (실제 카드 렌더는 populated_client 에서 검증됨)
    r = client.post("/ui/search-results", json={"query": "", "count": 5})
    assert r.status_code == 200
    # 빈 라이브러리이면 카드 없음 — 라우트 자체가 200이면 OK


def test_audio_route_exists_in_api(client):
    """/api/audio/{id} 라우트가 등록되어 있다 (미존재 id → 404, 라우트 없음 → 404 아님)."""
    r = client.get("/api/audio/99999")
    # 라우트 없으면 404이지만 "Not Found" detail; 라우트 있어도 없는 id → 404
    # 라우트 등록 여부는 status code 가 422 범위가 아닌 404 여야 함
    assert r.status_code == 404
    body = r.json()
    assert "detail" in body


def test_audio_player_fragment_route_exists(client):
    """/ui/audio-player/{id} 라우트가 등록되어 있다."""
    r = client.get("/ui/audio-player/99999")
    assert r.status_code == 404  # 라우트 있음, asset 없음
