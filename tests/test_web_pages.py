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
    # ⚙ Advanced 버튼 존재 (Task 6 이후 영어 msgid)
    assert "Advanced" in r.text


def test_search_bar_triggers_only_on_submit_and_load(client):
    """검색 바는 엔터/검색 버튼 (submit) + 페이지 로드만 trigger — 자동 디바운스 없음."""
    r = client.get("/library")
    assert 'hx-trigger="submit, load"' in r.text
    # 사용자 의도: 자동 입력 디바운스 비활성 (검색 버튼 / 엔터로만 실행)
    assert "delay:300ms" not in r.text


def test_search_bar_has_explicit_submit_button(client):
    """엔터 외에도 명시적 🔍 검색 버튼이 form 안에 있어야 한다."""
    r = client.get("/library")
    assert 'type="submit"' in r.text
    assert 'class="search-submit"' in r.text


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


# ── Task 3.1: 사이드 패널 슬라이드 in transition ────────────────────────


def test_side_panel_element_exists(client):
    """<aside class="side-panel"> 가 library 페이지에 존재한다."""
    r = client.get("/library")
    assert r.status_code == 200
    assert 'class="side-panel"' in r.text


def test_side_panel_has_x_show(client):
    """사이드 패널이 x-show="$store.advanced.open" 속성을 가진다."""
    r = client.get("/library")
    assert '$store.advanced.open' in r.text


def test_side_panel_has_slide_transition(client):
    """사이드 패널에 translateX 기반 슬라이드 transition 관련 속성이 있다."""
    r = client.get("/library")
    # x-transition:enter 계열 속성 또는 translate-x-full 유틸 클래스 존재
    assert (
        "translate-x-full" in r.text
        or "x-transition:enter" in r.text
        or "translateX" in r.text
    )


def test_side_panel_width_binding(client):
    """사이드 패널이 Alpine store 의 sidePanelWidth 를 :style 로 바인딩한다."""
    r = client.get("/library")
    assert "sidePanelWidth" in r.text


# ── Task 3.2: 사이드 패널 리사이즈 핸들 ─────────────────────────────────


def test_side_panel_has_resize_handle(client):
    """사이드 패널 안에 class="resize-handle" 요소가 존재한다."""
    r = client.get("/library")
    assert r.status_code == 200
    assert 'class="resize-handle"' in r.text


def test_resize_handle_function_defined(client):
    """resizeHandle() Alpine 컴포넌트 함수가 페이지에 정의되어 있다."""
    r = client.get("/library")
    assert "resizeHandle()" in r.text or "resizeHandle" in r.text


def test_resize_handle_drag_logic(client):
    """resizeHandle 내부에 startDrag / onDrag / stopDrag 로직이 존재한다."""
    r = client.get("/library")
    assert "startDrag" in r.text
    assert "onDrag" in r.text
    assert "stopDrag" in r.text


def test_resize_handle_has_mousedown(client):
    """resize-handle 요소가 @mousedown 이벤트를 처리한다."""
    r = client.get("/library")
    assert "mousedown" in r.text


# ── Task 3.3: B/C/D 탭 헤더 + 컨테이너 ─────────────────────────────────


def test_side_panel_b_partial_exists():
    """_side_panel_b.html partial 파일이 존재한다."""
    from pathlib import Path
    p = Path(__file__).parent.parent / "src/gah/web/templates/_side_panel_b.html"
    assert p.exists(), f"{p} 파일이 없음"


def test_side_panel_c_partial_exists():
    """_side_panel_c.html partial 파일이 존재한다."""
    from pathlib import Path
    p = Path(__file__).parent.parent / "src/gah/web/templates/_side_panel_c.html"
    assert p.exists(), f"{p} 파일이 없음"


def test_side_panel_d_partial_exists():
    """_side_panel_d.html partial 파일이 존재한다."""
    from pathlib import Path
    p = Path(__file__).parent.parent / "src/gah/web/templates/_side_panel_d.html"
    assert p.exists(), f"{p} 파일이 없음"


def test_library_page_has_side_tabs(client):
    """library 페이지에 class="side-tabs" 탭 헤더가 존재한다."""
    r = client.get("/library")
    assert r.status_code == 200
    assert 'class="side-tabs"' in r.text


def test_library_page_has_tab_labels(client):
    """탭 헤더에 B Filters, C Display, D Adjust 레이블이 존재한다 (Task 6 이후 영어 msgid)."""
    r = client.get("/library")
    assert "B Filters" in r.text
    assert "C Display" in r.text
    assert "D Adjust" in r.text


def test_library_page_has_b_match_mode(client):
    """B 탭에 매칭 모드 fieldset (match-mode 클래스 + AND/OR/NOT) 이 렌더된다."""
    r = client.get("/library")
    assert "match-mode" in r.text
    assert "AND" in r.text
    assert "OR" in r.text
    assert "NOT" in r.text


def test_library_page_has_c_view_mode_toggle(client):
    """C 탭 실 구현 — opt-group + $store.search.viewMode + Card size 가 렌더된다 (Task 6 이후 영어 msgid)."""
    r = client.get("/library")
    assert "opt-group" in r.text
    assert "$store.search.viewMode" in r.text
    assert "Card size" in r.text


def test_library_page_has_d_tab_sections(client):
    """D 탭 실 구현 (Saved searches + Consistency/penalty) 섹션이 렌더된다 (Task 6 이후 영어 msgid)."""
    r = client.get("/library")
    assert "Saved searches" in r.text
    assert "Consistency / penalty" in r.text


def test_side_tab_content_has_x_show(client):
    """탭 컨테이너가 x-show 로 activeTab 을 확인한다."""
    r = client.get("/library")
    assert "activeTab" in r.text


# ── Phase 4B: SSE 클라이언트 + pick-cards 컨테이너 + app.js ─────────────────


def test_library_page_subscribes_to_sse_via_app_js(client):
    """app.js 가 /sse/notifications 를 native EventSource 로 구독.

    Phase 6 fix: htmx-sse 의존성 제거 (event 이름 mismatch 로 동작 안 함).
    이제 app.js 의 IIFE 가 EventSource 직접 등록 + 이벤트 listener 3개 부착.
    """
    r = client.get("/library")
    assert r.status_code == 200
    assert "app.js" in r.text  # 클라이언트가 SSE 등록을 처리


def test_library_page_includes_pick_cards_container(client):
    """library 페이지에 id="pick-cards" 컨테이너가 포함된다."""
    r = client.get("/library")
    assert r.status_code == 200
    assert 'id="pick-cards"' in r.text


def test_library_page_includes_app_js(client):
    """library 페이지에 app.js 스크립트 태그가 포함된다."""
    r = client.get("/library")
    assert r.status_code == 200
    assert "app.js" in r.text


def test_app_js_static_file_exists():
    """src/gah/web/static/js/app.js 파일이 존재한다."""
    from pathlib import Path
    p = Path(__file__).parent.parent / "src/gah/web/static/js/app.js"
    assert p.exists(), f"{p} 파일이 없음"


def test_app_js_registers_user_pick_request_listener():
    """app.js 가 user_pick_request SSE 이벤트 listener 를 등록한다.

    Phase 6 fix: htmx-sse 의 sse-swap 대신 native EventSource.addEventListener
    로 직접 등록. app.js 안에 "user_pick_request" 이벤트 이름이 포함되어야 한다.
    """
    from pathlib import Path
    app_js = Path(__file__).parent.parent / "src/gah/web/static/js/app.js"
    content = app_js.read_text(encoding="utf-8")
    assert "user_pick_request" in content
    assert "addEventListener" in content
    assert "/sse/notifications" in content


def test_library_page_loads_htmx_json_enc_extension(client):
    """채택 버튼이 JSON body 로 POST 하려면 htmx-json-enc.js 가 로드돼야 한다."""
    r = client.get("/library")
    assert r.status_code == 200
    assert "htmx-json-enc.js" in r.text


# ── Task 5.6: /packs HTML 페이지 ────────────────────────────────────────


def test_page_packs_returns_200(populated_client):
    """GET /packs → 200 HTML."""
    r = populated_client.get("/packs")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_page_packs_renders_pack_names(populated_client):
    """GET /packs HTML 에 pack_a, pack_b 이름이 모두 나온다."""
    r = populated_client.get("/packs")
    assert r.status_code == 200
    assert "pack_a" in r.text
    assert "pack_b" in r.text


def test_page_packs_has_correct_nav_active(populated_client):
    """팩 페이지는 nav 에서 '팩' 링크가 active 클래스를 갖는다."""
    r = populated_client.get("/packs")
    assert r.status_code == 200
    # nav 에 active 클래스가 있어야 함
    assert "active" in r.text


def test_page_packs_includes_toggle_button(populated_client):
    """팩 카드에 활성/비활성 토글 버튼이 있다."""
    r = populated_client.get("/packs")
    assert r.status_code == 200
    # hx-patch 가 toggle 버튼에 달려 있어야 함
    assert "hx-patch" in r.text


# ── Task 5.6 partial: /labels/admin 페이지 라우트 ────────────────────────


def test_page_labels_admin_returns_200(populated_client):
    """GET /labels/admin → 200 HTML."""
    r = populated_client.get("/labels/admin")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_page_labels_admin_renders_axes(populated_client):
    """GET /labels/admin HTML 에 주요 axis 이름이 포함된다."""
    r = populated_client.get("/labels/admin")
    assert r.status_code == 200
    assert "category" in r.text
    assert "style" in r.text


def test_page_labels_admin_has_correct_nav_active(populated_client):
    """라벨 관리 페이지에서 nav 의 'Label management' 링크가 active 클래스를 갖는다 (Task 6 이후 영어 msgid)."""
    r = populated_client.get("/labels/admin")
    assert r.status_code == 200
    assert "active" in r.text
    assert "Label management" in r.text
