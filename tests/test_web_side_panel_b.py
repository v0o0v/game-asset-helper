"""M5 Phase 3B — B 탭 사이드 패널 검증 (Task 3.4 / 3.5 / 3.6)."""
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


# ── Task 3.4: 매칭 모드 라디오 ─────────────────────────────────────────


def test_b_tab_has_match_mode_fieldset(client):
    """B 탭 콘텐츠에 match-mode fieldset 이 존재한다."""
    r = client.get("/library")
    assert r.status_code == 200
    assert "match-mode" in r.text


def test_b_tab_match_mode_has_and(client):
    """매칭 모드 AND 라디오가 존재한다."""
    r = client.get("/library")
    assert "AND" in r.text


def test_b_tab_match_mode_has_or(client):
    """매칭 모드 OR 라디오가 존재한다."""
    r = client.get("/library")
    assert "OR" in r.text


def test_b_tab_match_mode_has_not(client):
    """매칭 모드 NOT 라디오가 존재한다."""
    r = client.get("/library")
    assert "NOT" in r.text


def test_b_tab_match_mode_xmodel(client):
    """라디오가 $store.search.matchMode 를 x-model 로 바인딩한다."""
    r = client.get("/library")
    assert "$store.search.matchMode" in r.text


def test_b_tab_match_mode_triggers_search(client):
    """라디오 @change 가 검색을 트리거한다 (htmx.trigger 또는 Alpine watcher)."""
    r = client.get("/library")
    # htmx.trigger 또는 $watch 방식 중 하나
    assert "htmx.trigger" in r.text or "$watch" in r.text


# ── Task 3.5: 라벨 검색 input + 매칭 칩 CSS ───────────────────────────


def test_b_tab_has_label_filter_input(client):
    """B 탭에 type='search' 라벨 검색 input 이 존재한다."""
    r = client.get("/library")
    assert 'type="search"' in r.text


def test_b_tab_label_filter_xmodel(client):
    """라벨 검색 input 이 $store.b.labelFilter 를 x-model 로 바인딩한다."""
    r = client.get("/library")
    assert "$store.b.labelFilter" in r.text


def test_b_tab_label_filter_placeholder(client):
    """라벨 검색 input 에 placeholder 가 있다."""
    r = client.get("/library")
    assert "라벨 검색" in r.text


def test_main_css_has_chip_matched():
    """main.css 에 .chip.matched 스타일이 정의되어 있다."""
    from pathlib import Path
    css = (
        Path(__file__).parent.parent
        / "src/gah/web/static/css/main.css"
    ).read_text(encoding="utf-8")
    assert ".chip.matched" in css


def test_main_css_chip_matched_uses_var(client):
    """main.css 의 .chip.matched 가 CSS 변수를 사용한다."""
    from pathlib import Path
    css = (
        Path(__file__).parent.parent
        / "src/gah/web/static/css/main.css"
    ).read_text(encoding="utf-8")
    # --chip-matched 변수 참조
    assert "--chip-matched" in css


# ── Task 3.6: 종류 탭 (sprite/sheet/sound) ────────────────────────────


def test_b_tab_has_kind_tabs_nav(client):
    """B 탭에 class='kind-tabs' nav 가 존재한다."""
    r = client.get("/library")
    assert "kind-tabs" in r.text


def test_b_tab_kind_tab_sprite(client):
    """종류 탭에 스프라이트 버튼이 존재한다."""
    r = client.get("/library")
    assert "스프라이트" in r.text


def test_b_tab_kind_tab_sheet(client):
    """종류 탭에 시트 버튼이 존재한다."""
    r = client.get("/library")
    assert "시트" in r.text


def test_b_tab_kind_tab_sound(client):
    """종류 탭에 사운드 버튼이 존재한다."""
    r = client.get("/library")
    assert "사운드" in r.text


def test_b_tab_kind_tab_xclick_binding(client):
    """종류 탭 버튼이 $store.b.kindTab 을 @click 으로 변경한다."""
    r = client.get("/library")
    assert "$store.b.kindTab" in r.text


def test_kind_tabs_has_active_class_binding(client):
    """종류 탭 버튼에 :class='{active: ...}' 바인딩이 존재한다."""
    r = client.get("/library")
    assert "active" in r.text and "kindTab" in r.text


def test_main_css_has_kind_tabs():
    """main.css 에 .kind-tabs 스타일이 정의되어 있다."""
    from pathlib import Path
    css = (
        Path(__file__).parent.parent
        / "src/gah/web/static/css/main.css"
    ).read_text(encoding="utf-8")
    assert ".kind-tabs" in css


# ── Task 3.6: _classify_axis 단위 테스트 ─────────────────────────────


def test_classify_axis_sound_category():
    from gah.web.routers.filters import _classify_axis
    assert _classify_axis("sound_category") == "sound"


def test_classify_axis_sound_tempo():
    from gah.web.routers.filters import _classify_axis
    assert _classify_axis("sound_tempo") == "sound"


def test_classify_axis_sheet_grid():
    from gah.web.routers.filters import _classify_axis
    assert _classify_axis("sheet_grid") == "sheet"


def test_classify_axis_category_is_sprite():
    from gah.web.routers.filters import _classify_axis
    assert _classify_axis("category") == "sprite"


def test_classify_axis_style_is_sprite():
    from gah.web.routers.filters import _classify_axis
    assert _classify_axis("style") == "sprite"


# ── Task 3.6: /api/filters/labels 엔드포인트 ──────────────────────────


def test_filters_labels_returns_200(populated_client):
    """/api/filters/labels GET → 200."""
    r = populated_client.get("/api/filters/labels")
    assert r.status_code == 200


def test_filters_labels_has_three_keys(populated_client):
    """/api/filters/labels 응답에 sprite/sheet/sound 키가 있다."""
    r = populated_client.get("/api/filters/labels")
    body = r.json()
    assert "sprite" in body
    assert "sheet" in body
    assert "sound" in body


def test_filters_labels_sprite_is_list(populated_client):
    """sprite 키 값이 list 다."""
    r = populated_client.get("/api/filters/labels")
    assert isinstance(r.json()["sprite"], list)


def test_filters_labels_sheet_is_empty_list(populated_client):
    """SEED 에 sheet_* axis 없음 → sheet 는 빈 list."""
    r = populated_client.get("/api/filters/labels")
    assert r.json()["sheet"] == []


def test_filters_labels_sprite_has_category_axis(populated_client):
    """sprite 버킷에 'category' axis 가 존재한다."""
    r = populated_client.get("/api/filters/labels")
    sprite = r.json()["sprite"]
    axes = [g["axis"] for g in sprite]
    assert "category" in axes


def test_filters_labels_sprite_has_style_axis(populated_client):
    """sprite 버킷에 'style' axis 가 존재한다."""
    r = populated_client.get("/api/filters/labels")
    sprite = r.json()["sprite"]
    axes = [g["axis"] for g in sprite]
    assert "style" in axes


def test_filters_labels_sound_has_sound_category_axis(populated_client):
    """sound 버킷에 'sound_category' axis 가 존재한다."""
    r = populated_client.get("/api/filters/labels")
    sound = r.json()["sound"]
    axes = [g["axis"] for g in sound]
    assert "sound_category" in axes


def test_filters_labels_group_has_labels_list(populated_client):
    """각 axis 그룹에 'labels' 리스트가 있다."""
    r = populated_client.get("/api/filters/labels")
    sprite = r.json()["sprite"]
    assert len(sprite) > 0
    for group in sprite:
        assert "axis" in group
        assert "labels" in group
        assert isinstance(group["labels"], list)


def test_filters_labels_empty_store(client):
    """/api/filters/labels — 빈 DB (bootstrap 없음) → 빈 버킷 3개."""
    r = client.get("/api/filters/labels")
    assert r.status_code == 200
    body = r.json()
    assert body["sprite"] == []
    assert body["sheet"] == []
    assert body["sound"] == []


# ── Task 3.7: axis 칩 FlowLayout + toggleLabel ────────────────────────


def test_b_tab_axis_chips_area_exists(client):
    """B 탭에 axis-chips-area 영역이 존재한다."""
    r = client.get("/library")
    assert r.status_code == 200
    assert "axis-chips-area" in r.text


def test_b_tab_axis_chips_uses_x_for_axis(client):
    """axis 칩이 x-for loop 로 axis 를 순회한다."""
    r = client.get("/library")
    assert "x-for" in r.text
    assert "labelsByKind" in r.text


def test_b_tab_axis_chip_has_active_class_binding(client):
    """axis 칩 버튼에 :class active 바인딩이 존재한다."""
    r = client.get("/library")
    assert "selectedLabels" in r.text
    assert "active" in r.text


def test_b_tab_axis_chip_has_matched_class_binding(client):
    """axis 칩 버튼에 :class matched 바인딩이 존재한다."""
    r = client.get("/library")
    assert "matched" in r.text
    assert "labelFilter" in r.text


def test_b_tab_toggle_label_function_in_html(client):
    """toggleLabel 함수가 라이브러리 페이지에 존재한다."""
    r = client.get("/library")
    assert "toggleLabel" in r.text


def test_b_tab_toggle_label_triggers_search(client):
    """toggleLabel 이 htmx.trigger 로 검색을 재호출한다."""
    r = client.get("/library")
    # toggleLabel 함수 안에서 htmx.trigger 사용
    assert "htmx.trigger" in r.text


def test_main_css_has_chip_class():
    """main.css 에 .chip 스타일이 정의되어 있다."""
    from pathlib import Path
    css = (
        Path(__file__).parent.parent
        / "src/gah/web/static/css/main.css"
    ).read_text(encoding="utf-8")
    assert ".chip" in css


def test_main_css_chip_matched_box_shadow_only():
    """.chip.matched 는 box-shadow 만 사용하고 background 는 없다 (정정됨)."""
    from pathlib import Path
    css = (
        Path(__file__).parent.parent
        / "src/gah/web/static/css/main.css"
    ).read_text(encoding="utf-8")
    idx = css.find(".chip.matched")
    assert idx >= 0, ".chip.matched 스타일 없음"
    # 닫는 } 까지만 추출해 해당 CSS 블록만 검사
    end = css.find("}", idx)
    block = css[idx: end + 1] if end >= 0 else css[idx: idx + 200]
    # box-shadow 는 있어야 함
    assert "box-shadow" in block
    # background 가 그 블록에 없어야 함 (정정 확인)
    assert "background" not in block


def test_main_css_has_axis_group():
    """main.css 에 .axis-group 스타일이 정의되어 있다."""
    from pathlib import Path
    css = (
        Path(__file__).parent.parent
        / "src/gah/web/static/css/main.css"
    ).read_text(encoding="utf-8")
    assert ".axis-group" in css


def test_main_css_has_chip_flow():
    """main.css 에 .chip-flow 스타일이 정의되어 있다 (flex-wrap)."""
    from pathlib import Path
    css = (
        Path(__file__).parent.parent
        / "src/gah/web/static/css/main.css"
    ).read_text(encoding="utf-8")
    assert ".chip-flow" in css


def test_b_tab_axis_chips_fetch_on_init(client):
    """B 탭 패널에 /api/filters/labels 를 x-init 으로 fetch 하는 코드가 있다."""
    r = client.get("/library")
    assert "/api/filters/labels" in r.text
    assert "x-init" in r.text
