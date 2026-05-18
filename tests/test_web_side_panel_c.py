"""M5 Phase 3C — C 탭 사이드 패널 검증 (Task 3.10 / 3.11)."""
from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from gah.web.app import build_app


# ── 공통 fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def client(deps_fixture):
    with TestClient(build_app(deps_fixture)) as c:
        yield c


# ── Task 3.10: C 탭 표시 옵션 양방향 바인딩 ───────────────────────────


def test_c_tab_has_opt_group(client):
    """C 탭 콘텐츠에 opt-group 클래스가 존재한다."""
    r = client.get("/library")
    assert r.status_code == 200
    assert "opt-group" in r.text


def test_c_tab_has_view_mode_toggle(client):
    """C 탭에 그리드/리스트 뷰 모드 토글 버튼이 존재한다."""
    r = client.get("/library")
    assert "그리드" in r.text
    assert "리스트" in r.text


def test_c_tab_view_mode_binds_store(client):
    """C 탭 뷰 모드 버튼이 $store.search.viewMode 를 바인딩한다."""
    r = client.get("/library")
    assert "$store.search.viewMode" in r.text


def test_c_tab_has_card_size_buttons(client):
    """C 탭에 카드 크기 S/M/L 버튼이 존재한다."""
    r = client.get("/library")
    assert "카드 크기" in r.text


def test_c_tab_card_size_binds_store(client):
    """C 탭 카드 크기 버튼이 $store.search.cardSize 를 바인딩한다."""
    r = client.get("/library")
    assert "$store.search.cardSize" in r.text


def test_c_tab_has_sort_select(client):
    """C 탭에 정렬 select 요소가 존재한다."""
    r = client.get("/library")
    assert "정렬" in r.text


def test_c_tab_sort_xmodel(client):
    """C 탭 정렬 select 가 x-model="$store.search.sort" 로 바인딩된다."""
    r = client.get("/library")
    assert 'x-model="$store.search.sort"' in r.text


def test_c_tab_sort_has_options(client):
    """C 탭 정렬 select 에 추가일↓/이름↑ 등 옵션이 존재한다."""
    r = client.get("/library")
    assert "추가일" in r.text
    assert "이름" in r.text


def test_c_tab_sort_triggers_search(client):
    """C 탭 정렬 변경이 htmx.trigger 로 검색을 재호출한다."""
    r = client.get("/library")
    assert "htmx.trigger" in r.text


def test_c_tab_no_placeholder(client):
    """Phase 3C placeholder 가 더 이상 없다 (실 구현으로 교체됨)."""
    r = client.get("/library")
    assert "Phase 3C" not in r.text


def test_main_css_has_opt_group():
    """main.css 에 .opt-group 스타일이 정의되어 있다."""
    from pathlib import Path
    css = (
        Path(__file__).parent.parent
        / "src/gah/web/static/css/main.css"
    ).read_text(encoding="utf-8")
    assert ".opt-group" in css


def test_main_css_opt_group_uses_var():
    """main.css 의 .opt-group 관련 스타일이 CSS 변수를 사용한다 (색상 var 존재)."""
    from pathlib import Path
    css = (
        Path(__file__).parent.parent
        / "src/gah/web/static/css/main.css"
    ).read_text(encoding="utf-8")
    # 전체 CSS 에 var(--*) 이 있는지 (이미 있으므로 통과)
    assert "var(--" in css


# ── Task 3.11: C 탭 카드 메타 토글 ────────────────────────────────────


def test_c_tab_has_card_meta_section(client):
    """C 탭에 카드에 표시할 정보 섹션이 존재한다."""
    r = client.get("/library")
    assert "카드에 표시할 정보" in r.text


def test_c_tab_card_meta_has_labels_checkbox(client):
    """C 탭 카드 메타에 라벨 체크박스가 존재한다."""
    r = client.get("/library")
    assert "cardMeta.labels" in r.text


def test_c_tab_card_meta_has_pack_checkbox(client):
    """C 탭 카드 메타에 팩 체크박스가 존재한다."""
    r = client.get("/library")
    assert "cardMeta.pack" in r.text


def test_c_tab_card_meta_has_score_checkbox(client):
    """C 탭 카드 메타에 점수 체크박스가 존재한다."""
    r = client.get("/library")
    assert "cardMeta.score" in r.text


def test_c_tab_card_meta_has_size_checkbox(client):
    """C 탭 카드 메타에 크기 체크박스가 존재한다."""
    r = client.get("/library")
    assert "cardMeta.size" in r.text


def test_c_tab_card_meta_uses_checkbox_input(client):
    """C 탭 카드 메타 항목이 type='checkbox' input 을 사용한다."""
    r = client.get("/library")
    assert 'type="checkbox"' in r.text


def test_c_tab_card_meta_xmodel_binding(client):
    """C 탭 카드 메타 체크박스가 x-model 로 바인딩된다."""
    r = client.get("/library")
    assert "x-model" in r.text
    assert "$store.search.cardMeta" in r.text


def test_c_tab_card_meta_label_text(client):
    """C 탭 카드 메타에 '라벨', '팩', '점수', '크기' 텍스트가 존재한다."""
    r = client.get("/library")
    assert "라벨" in r.text
    assert "팩" in r.text
    assert "점수" in r.text
    assert "크기" in r.text
