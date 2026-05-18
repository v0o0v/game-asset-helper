"""M5 Stage 2 — Playwright e2e: 라이브러리 페이지 검증.

M5_verification.md §4 기준 step 1-21 중 자동화 가능한 항목을 커버한다.

* ⚙ 토글 + 사이드 패널 슬라이드
* B/C/D 탭 전환 + 각 탭 내부 인터랙션
* 자산 상세 모달 (카드 클릭 / ESC 닫힘 / 키보드 Enter)
"""
from __future__ import annotations

import time

import pytest


pytestmark = pytest.mark.e2e


# ─────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────


def _open_side_panel(page):
    """⚙ 토글 버튼 클릭 후 패널이 visible 될 때까지 대기."""
    page.click("button.advanced-toggle")
    page.wait_for_selector(".side-panel", state="visible")


def _activate_tab(page, tab: str):
    """side-tabs 안에서 탭 버튼(B/C/D)을 클릭한다.

    tab: 'b' | 'c' | 'd'
    """
    texts = {"b": "B 필터", "c": "C 표시", "d": "D 조정"}
    page.locator(".side-tabs button", has_text=texts[tab]).click()


# ─────────────────────────────────────────────────────────────────────
# ⚙ 토글 + 사이드 패널 (step 4)
# ─────────────────────────────────────────────────────────────────────


def test_gear_toggle_opens_and_closes_side_panel(page, e2e_url):
    """⚙ 클릭 → 사이드 패널 슬라이드 인 (visible) → 다시 클릭 → 슬라이드 아웃."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")

    # 최초에는 닫혀있어야 함
    panel = page.locator(".side-panel")
    # Alpine x-show 로 숨겨진 상태 — display:none 또는 hidden
    assert panel.is_hidden()

    # 열기
    _open_side_panel(page)
    assert panel.is_visible()

    # 닫기
    page.click("button.advanced-toggle")
    panel.wait_for(state="hidden")
    assert panel.is_hidden()


def test_gear_toggle_state_in_alpine_store(page, e2e_url):
    """⚙ 클릭 후 Alpine store('advanced').open 값이 True 로 변한다."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")

    # 패널 열기
    _open_side_panel(page)
    # Alpine 스토어 상태 직접 확인
    open_state = page.evaluate("Alpine.store('advanced').open")
    assert open_state is True


# ─────────────────────────────────────────────────────────────────────
# B/C/D 탭 전환 (step 6)
# ─────────────────────────────────────────────────────────────────────


def test_side_panel_tab_switching(page, e2e_url):
    """B/C/D 탭 클릭 → activeTab store 변경 + 활성 탭 버튼 active 클래스."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    _open_side_panel(page)

    # 기본은 b 탭
    assert page.evaluate("Alpine.store('advanced').activeTab") == "b"

    # C 탭으로 전환
    _activate_tab(page, "c")
    assert page.evaluate("Alpine.store('advanced').activeTab") == "c"
    # C 탭 버튼이 active 클래스를 가져야 함
    c_btn = page.locator(".side-tabs button", has_text="C 표시")
    assert "active" in (c_btn.get_attribute("class") or "")

    # D 탭으로 전환
    _activate_tab(page, "d")
    assert page.evaluate("Alpine.store('advanced').activeTab") == "d"

    # 다시 B 탭
    _activate_tab(page, "b")
    assert page.evaluate("Alpine.store('advanced').activeTab") == "b"


# ─────────────────────────────────────────────────────────────────────
# B 탭 — 매칭 모드 (step 7)
# ─────────────────────────────────────────────────────────────────────


def test_b_tab_match_mode_radio_changes_store(page, e2e_url):
    """AND/OR/NOT 라디오 변경 → $store.search.matchMode 갱신."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    _open_side_panel(page)

    # 기본값 all (AND)
    assert page.evaluate("Alpine.store('search').matchMode") == "all"

    # OR 선택
    page.locator(".match-mode input[value='any']").click()
    assert page.evaluate("Alpine.store('search').matchMode") == "any"

    # NOT 선택
    page.locator(".match-mode input[value='none']").click()
    assert page.evaluate("Alpine.store('search').matchMode") == "none"

    # 다시 AND
    page.locator(".match-mode input[value='all']").click()
    assert page.evaluate("Alpine.store('search').matchMode") == "all"


def test_b_tab_match_mode_updates_hidden_input(page, e2e_url):
    """매칭 모드 변경 → form 의 hidden input[name='match_mode'] 값 동기화."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    _open_side_panel(page)

    page.locator(".match-mode input[value='any']").click()
    # Alpine :value 바인딩이 hidden input 에 반영되었는지 확인
    val = page.evaluate(
        "document.querySelector('input[name=\"match_mode\"]').value"
    )
    assert val == "any"


# ─────────────────────────────────────────────────────────────────────
# B 탭 — 라벨 검색 + matched 클래스 (step 8)
# ─────────────────────────────────────────────────────────────────────


def test_b_tab_label_filter_sets_store(page, e2e_url):
    """라벨 검색 input 입력 → $store.b.labelFilter 갱신."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    _open_side_panel(page)

    page.fill(".label-filter-input", "hero")
    val = page.evaluate("Alpine.store('b').labelFilter")
    assert val == "hero"


def test_b_tab_label_filter_shows_matched_chips(page, e2e_url):
    """라벨 검색 입력 → 매칭 axis 칩에 .matched 클래스 출현.

    /api/filters/labels 응답 대기 후 chip 존재하면 필터 입력하고 matched 확인.
    chips 없으면 xfail (라벨 없는 e2e DB 가능).
    """
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    _open_side_panel(page)

    # B 탭 패널이 /api/filters/labels fetch 완료될 때까지 대기 (최대 3s)
    page.wait_for_function(
        "Alpine.store('b').labelsByKind.sprite && Alpine.store('b').labelsByKind.sprite.length > 0",
        timeout=3000,
    )
    chips = page.locator(".chip-flow .chip")
    count = chips.count()
    if count == 0:
        pytest.skip("라벨 칩 없음 — e2e DB 에 sprite 라벨 없음")

    # 첫 번째 칩의 텍스트로 검색
    first_chip_text = chips.nth(0).inner_text()
    page.fill(".label-filter-input", first_chip_text[:3])
    # matched 클래스를 가진 칩이 1개 이상
    matched = page.locator(".chip-flow .chip.matched")
    matched.first.wait_for(timeout=2000)
    assert matched.count() >= 1


# ─────────────────────────────────────────────────────────────────────
# B 탭 — 종류 탭 (step 9)
# ─────────────────────────────────────────────────────────────────────


def test_b_tab_kind_tabs_switch_store(page, e2e_url):
    """스프라이트/시트/사운드 탭 클릭 → $store.b.kindTab 변경."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    _open_side_panel(page)

    assert page.evaluate("Alpine.store('b').kindTab") == "sprite"

    page.locator(".kind-tabs button", has_text="시트").click()
    assert page.evaluate("Alpine.store('b').kindTab") == "sheet"

    page.locator(".kind-tabs button", has_text="사운드").click()
    assert page.evaluate("Alpine.store('b').kindTab") == "sound"

    page.locator(".kind-tabs button", has_text="스프라이트").click()
    assert page.evaluate("Alpine.store('b').kindTab") == "sprite"


# ─────────────────────────────────────────────────────────────────────
# B 탭 — axis 칩 클릭 + selectedLabels (step 10)
# ─────────────────────────────────────────────────────────────────────


def test_b_tab_axis_chip_click_updates_selected_labels(page, e2e_url):
    """axis 칩 클릭 → $store.b.selectedLabels 에 id 추가 / 다시 클릭 → 제거."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    _open_side_panel(page)

    page.wait_for_function(
        "Alpine.store('b').labelsByKind.sprite && Alpine.store('b').labelsByKind.sprite.length > 0",
        timeout=3000,
    )

    chips = page.locator(".chip-flow .chip")
    if chips.count() == 0:
        pytest.skip("라벨 칩 없음")

    # 처음에는 비어있음
    assert page.evaluate("Alpine.store('b').selectedLabels") == []

    # 첫 칩 클릭 → selectedLabels 에 추가
    chips.nth(0).click()
    selected = page.evaluate("Alpine.store('b').selectedLabels")
    assert len(selected) == 1

    # 같은 칩 다시 클릭 → 제거
    chips.nth(0).click()
    selected = page.evaluate("Alpine.store('b').selectedLabels")
    assert len(selected) == 0


# ─────────────────────────────────────────────────────────────────────
# B 탭 — 다축 필터 details 열림 (step 11)
# ─────────────────────────────────────────────────────────────────────


def test_b_tab_multi_filter_details_expand(page, e2e_url):
    """팩/벤더/라이선스/상태 details summary 클릭 → 펼침."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    _open_side_panel(page)

    details_list = page.locator(".filter-group")
    count = details_list.count()
    assert count >= 4  # 팩/벤더/라이선스/상태 4개 이상

    first_details = details_list.nth(0)
    summary_el = first_details.locator("summary")
    # 닫혀있는지 확인 (open attribute 없음)
    assert first_details.get_attribute("open") is None

    summary_el.click()
    # 열렸는지 확인
    assert first_details.get_attribute("open") is not None


# ─────────────────────────────────────────────────────────────────────
# C 탭 — 그리드/리스트 토글 (step 12)
# ─────────────────────────────────────────────────────────────────────


def test_c_tab_grid_list_toggle(page, e2e_url):
    """C 탭 그리드/리스트 버튼 클릭 → $store.search.viewMode 변경."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    _open_side_panel(page)
    _activate_tab(page, "c")

    # 기본은 grid
    assert page.evaluate("Alpine.store('search').viewMode") == "grid"

    # C 탭 패널 내 버튼만 (결과 툴바와 구분 — aside.side-panel 내부로 범위 제한)
    panel = page.locator("aside.side-panel")
    panel.locator(".view-btn", has_text="리스트").click()
    assert page.evaluate("Alpine.store('search').viewMode") == "list"

    panel.locator(".view-btn", has_text="그리드").click()
    assert page.evaluate("Alpine.store('search').viewMode") == "grid"


# ─────────────────────────────────────────────────────────────────────
# C 탭 — 카드 크기 S/M/L (step 13)
# ─────────────────────────────────────────────────────────────────────


def test_c_tab_card_size_buttons(page, e2e_url):
    """C 탭 S/M/L 버튼 클릭 → $store.search.cardSize 변경."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    _open_side_panel(page)
    _activate_tab(page, "c")

    assert page.evaluate("Alpine.store('search').cardSize") == "m"

    # C 탭 패널 내 버튼만 (결과 툴바와 구분)
    panel = page.locator("aside.side-panel")
    panel.locator(".size-btn", has_text="S").click()
    assert page.evaluate("Alpine.store('search').cardSize") == "s"

    panel.locator(".size-btn", has_text="L").click()
    assert page.evaluate("Alpine.store('search').cardSize") == "l"

    panel.locator(".size-btn", has_text="M").click()
    assert page.evaluate("Alpine.store('search').cardSize") == "m"


# ─────────────────────────────────────────────────────────────────────
# C 탭 — 카드 메타 4 체크박스 (step 14)
# ─────────────────────────────────────────────────────────────────────


def test_c_tab_card_meta_checkboxes(page, e2e_url):
    """C 탭 라벨/팩/점수/크기 체크박스 토글 → $store.search.cardMeta 갱신."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    _open_side_panel(page)
    _activate_tab(page, "c")

    # 기본 상태 확인
    meta = page.evaluate("Alpine.store('search').cardMeta")
    assert meta["labels"] is True
    assert meta["pack"] is True
    assert meta["score"] is False
    assert meta["size"] is False

    # 점수 체크박스 켜기 (기본 off → on)
    score_checkbox = page.locator(".opt-check input[type=checkbox]").nth(2)  # 3번째: 점수
    score_checkbox.check()
    meta2 = page.evaluate("Alpine.store('search').cardMeta")
    assert meta2["score"] is True

    # 라벨 체크박스 끄기
    labels_checkbox = page.locator(".opt-check input[type=checkbox]").nth(0)
    labels_checkbox.uncheck()
    meta3 = page.evaluate("Alpine.store('search').cardMeta")
    assert meta3["labels"] is False


# ─────────────────────────────────────────────────────────────────────
# D 탭 — 프리셋 3개 (step 15)
# ─────────────────────────────────────────────────────────────────────


def test_d_tab_presets_change_active_preset(page, e2e_url):
    """D 탭 프리셋 버튼 클릭 → $store.d.activePreset + weights store 갱신."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    _open_side_panel(page)
    _activate_tab(page, "d")

    # 기본 balanced
    assert page.evaluate("Alpine.store('d').activePreset") == "balanced"

    # 통일성 우선 프리셋 클릭
    with page.expect_response("**/api/preset/consistency"):
        page.locator(".preset-btn", has_text="통일성 우선").click()

    assert page.evaluate("Alpine.store('d').activePreset") == "consistency"
    # weights store 에서 consistency 가 높아졌는지 확인
    consistency_weight = page.evaluate("Alpine.store('weights').consistency")
    assert consistency_weight > 0

    # 참신성 프리셋
    with page.expect_response("**/api/preset/novelty"):
        page.locator(".preset-btn", has_text="참신성").click()
    assert page.evaluate("Alpine.store('d').activePreset") == "novelty"

    # 균형 프리셋 복원
    with page.expect_response("**/api/preset/balanced"):
        page.locator(".preset-btn", has_text="균형").click()
    assert page.evaluate("Alpine.store('d').activePreset") == "balanced"


# ─────────────────────────────────────────────────────────────────────
# D 탭 — 슬라이더 (step 16)
# ─────────────────────────────────────────────────────────────────────


def test_d_tab_sliders_update_weights_store(page, e2e_url):
    """D 탭 슬라이더 조작 → $store.weights 갱신."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    _open_side_panel(page)
    _activate_tab(page, "d")

    # sliders details 펼치기
    page.locator(".weights-section summary").click()

    sliders = page.locator(".sliders input[type=range]")
    assert sliders.count() == 6

    # Alpine x-model.number 는 input 이벤트로 바인딩됨.
    # DOM input.value 직접 설정 + input 이벤트 dispatch 로 Alpine 상태 갱신.
    first_slider = sliders.nth(0)
    first_slider.evaluate(
        "el => {"
        "  el.value = '50';"
        "  el.dispatchEvent(new Event('input', {bubbles: true}));"
        "}"
    )
    semantic_val = page.evaluate("Alpine.store('weights').semantic")
    assert semantic_val == 50


def test_d_tab_slider_change_clears_active_preset(page, e2e_url):
    """슬라이더 변경 후 activePreset 이 null 이 된다."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    _open_side_panel(page)
    _activate_tab(page, "d")

    # 먼저 프리셋 적용
    with page.expect_response("**/api/preset/balanced"):
        page.locator(".preset-btn", has_text="균형").click()
    assert page.evaluate("Alpine.store('d').activePreset") == "balanced"

    # 슬라이더 펼치고 값 변경
    page.locator(".weights-section summary").click()
    first_slider = page.locator(".sliders input[type=range]").nth(0)

    with page.expect_response("**/api/weights"):
        first_slider.evaluate(
            "el => { el.value = 60; el.dispatchEvent(new Event('change', {bubbles: true})); }"
        )

    preset_val = page.evaluate("Alpine.store('d').activePreset")
    assert preset_val is None


# ─────────────────────────────────────────────────────────────────────
# D 탭 — 저장된 검색 CRUD (step 17)
# ─────────────────────────────────────────────────────────────────────


def test_d_tab_saved_search_crud(page, e2e_url):
    """저장된 검색 이름 입력 → 저장 → 목록에 추가 → 항목 클릭(복원) → 삭제."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    _open_side_panel(page)
    _activate_tab(page, "d")

    # 저장할 검색 이름 (유일하게 식별할 수 있는 이름)
    saved_name = f"e2e_test_search_{int(time.time() * 1000) % 100000}"

    # 이름 입력 후 저장
    page.fill(".save-name-input", saved_name)
    with page.expect_response("**/api/saved-searches"):
        page.locator(".save-btn").click()

    # 목록에 새 항목이 추가됐는지 확인
    page.wait_for_selector(f".saved-item .saved-name:text-is('{saved_name}')")
    assert page.locator(f".saved-item .saved-name", has_text=saved_name).count() >= 1

    # 항목 클릭 → 복원 (run saved search)
    saved_item = page.locator(".saved-item", has_text=saved_name)
    with page.expect_response("**/api/saved-searches/run/**"):
        saved_item.click()

    # 삭제 — confirm 다이얼로그 자동 수락
    page.on("dialog", lambda d: d.accept())
    saved_item2 = page.locator(".saved-item", has_text=saved_name)
    del_btn = saved_item2.locator(".saved-del-btn")
    with page.expect_response("**/api/saved-searches/**"):
        del_btn.click()

    # 목록에서 사라졌는지 확인
    page.wait_for_function(
        f"document.querySelectorAll('.saved-item .saved-name').length === 0 || "
        f"!Array.from(document.querySelectorAll('.saved-item .saved-name')).some(el => el.textContent.trim() === '{saved_name}')",
        timeout=3000,
    )


# ─────────────────────────────────────────────────────────────────────
# D 탭 — 통일성 요약 모달 (step 18 유사)
# ─────────────────────────────────────────────────────────────────────


def test_d_tab_usage_detail_modal_opens(page, e2e_url):
    """D 탭 '상세 보기' 클릭 → #usage-modal 에 innerHTML 채워짐."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    _open_side_panel(page)
    _activate_tab(page, "d")

    with page.expect_response("**/ui/usage/detail"):
        page.locator(".usage-detail-btn").click()

    modal = page.locator("#usage-modal")
    # innerHTML 이 채워져야 함
    assert modal.inner_html().strip() != ""


def test_d_tab_usage_detail_modal_closes_on_close_button(page, e2e_url):
    """통일성 모달 열린 상태에서 닫기(✕) 버튼 클릭 → 모달 닫힘(innerHTML 빔)."""
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    _open_side_panel(page)
    _activate_tab(page, "d")

    with page.expect_response("**/ui/usage/detail"):
        page.locator(".usage-detail-btn").click()

    usage_modal = page.locator("#usage-modal")
    assert usage_modal.inner_html().strip() != ""

    # 닫기 버튼(✕) 클릭으로 모달 닫기.
    # Alpine @click 핸들러가 innerHTML = '' 설정.
    page.locator("#usage-modal .modal-close").click()

    page.wait_for_function(
        "document.getElementById('usage-modal').innerHTML.trim() === ''",
        timeout=2000,
    )
    assert usage_modal.inner_html().strip() == ""


# ─────────────────────────────────────────────────────────────────────
# 자산 상세 모달 (step 20 / 21)
# ─────────────────────────────────────────────────────────────────────


def _wait_for_cards(page, e2e_url) -> bool:
    """라이브러리 페이지 진입 후 카드가 렌더될 때까지 대기.

    hx-trigger="load" 가 페이지 로드 직후 발화하므로
    expect_response 는 page.goto 이전에 시작해야 함.
    카드가 없으면 False 반환.
    """
    with page.expect_response(f"*{e2e_url.replace('http://', '//')}/ui/search-results",
                               timeout=10000) as _:
        page.goto(f"{e2e_url}/library")

    # Alpine x-if 가 .grid-container 를 렌더할 때까지 (최대 5s)
    try:
        page.wait_for_selector(".grid-container, .list-container", timeout=5000)
    except Exception:
        return False

    return page.locator("[data-asset-id]").count() > 0


def test_asset_card_click_opens_detail_modal(page, e2e_url):
    """자산 카드 클릭 → #asset-detail-modal innerHTML 채워짐 (모달 열림)."""
    has_cards = _wait_for_cards(page, e2e_url)
    if not has_cards:
        pytest.skip("검색 결과 카드 없음 — pending 자산만 있는 e2e DB")

    cards = page.locator("[data-asset-id]")

    # 첫 번째 카드 클릭 — HTMX GET /ui/asset-detail/{id} 응답 대기
    with page.expect_response("**/ui/asset-detail/**") as resp_info:
        cards.first.click()

    assert resp_info.value.status == 200
    modal = page.locator("#asset-detail-modal")
    page.wait_for_function(
        "document.getElementById('asset-detail-modal').innerHTML.trim() !== ''",
        timeout=3000,
    )
    assert modal.inner_html().strip() != ""


def test_asset_detail_modal_closes_on_esc(page, e2e_url):
    """자산 상세 모달 열린 상태에서 ESC → 모달 닫힘 (innerHTML 비워짐)."""
    has_cards = _wait_for_cards(page, e2e_url)
    if not has_cards:
        pytest.skip("검색 결과 카드 없음")

    cards = page.locator("[data-asset-id]")
    with page.expect_response("**/ui/asset-detail/**"):
        cards.first.click()

    modal = page.locator("#asset-detail-modal")
    page.wait_for_function(
        "document.getElementById('asset-detail-modal').innerHTML.trim() !== ''",
        timeout=3000,
    )
    assert modal.inner_html().strip() != ""

    # ESC 키 — app.js keydown 핸들러가 innerHTML = "" 설정
    page.keyboard.press("Escape")
    page.wait_for_function(
        "document.getElementById('asset-detail-modal').innerHTML.trim() === ''",
        timeout=2000,
    )
    assert modal.inner_html().strip() == ""
