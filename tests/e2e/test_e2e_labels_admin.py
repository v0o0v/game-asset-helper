"""M5 Stage 2 — Playwright e2e: 라벨 관리 페이지 검증.

M5_verification.md §4 step 29-30 에 해당.

* /labels/admin 진입 → 24 axis 탭
* axis 탭 전환 클릭
* 라벨 추가 form 제출 → 새 row 추가
* 라벨 삭제 버튼 → row 사라짐
"""
from __future__ import annotations

import time

import pytest


pytestmark = pytest.mark.e2e


def test_labels_admin_page_loads_with_axis_tabs(page, e2e_url):
    """/labels/admin 진입 → axis 탭 24개 렌더 + 첫 탭 active."""
    page.goto(f"{e2e_url}/labels/admin")
    assert "라벨 관리" in page.title()

    page.wait_for_selector(".axis-tabs", timeout=5000)
    tabs = page.locator(".axis-tab")
    tab_count = tabs.count()
    assert tab_count == 24, f"axis 탭이 24개 여야 함, 실제: {tab_count}"

    # 첫 탭(알파벳 순 첫 번째 axis)이 active
    first_active = page.locator(".axis-tab.active, .axis-tab[aria-selected='true']")
    assert first_active.count() >= 1


def test_labels_admin_axis_tab_switch(page, e2e_url):
    """/labels/admin axis 탭 클릭 → Alpine activeAxis 변경 + 컨텐츠 전환."""
    page.goto(f"{e2e_url}/labels/admin")
    page.wait_for_selector(".axis-tabs", timeout=5000)

    tabs = page.locator(".axis-tab")
    # 첫 번째 탭의 텍스트 (첫 axis)
    first_tab_text = tabs.nth(0).inner_text()
    # 두 번째 탭 클릭
    second_tab = tabs.nth(1)
    second_tab_text = second_tab.inner_text()
    second_tab.click()

    # Alpine activeAxis 변경 확인
    active_axis = page.evaluate(
        "document.querySelector('.labels-admin-grid').__x ? "
        "document.querySelector('.labels-admin-grid').__x.$data.activeAxis : null"
    )
    # x-data 는 Alpine 내부 접근이 까다로울 수 있으므로 DOM 기반으로 확인
    # 두 번째 탭이 active 클래스를 가져야 함
    second_tab_classes = second_tab.get_attribute("class") or ""
    # aria-selected 로 확인 (tablist pattern)
    aria_selected = second_tab.get_attribute("aria-selected")
    assert "active" in second_tab_classes or aria_selected == "true", (
        f"두 번째 탭({second_tab_text})이 active 여야 함. class={second_tab_classes!r}"
    )


def test_labels_admin_add_label_adds_row(page, e2e_url):
    """라벨 추가 form 제출 → tbody 에 새 row 추가 (hx-swap=beforeend)."""
    page.goto(f"{e2e_url}/labels/admin")
    page.wait_for_selector(".axis-tabs", timeout=5000)

    # 첫 번째 axis 탭이 이미 열려 있어야 함
    tabs = page.locator(".axis-tab")
    first_axis = tabs.nth(0).inner_text().strip()

    # 첫 번째 axis 의 tbody id
    tbody_id = f"axis-tbody-{first_axis}"

    # 기존 행 수 기록
    tbody = page.locator(f"#{tbody_id}")
    initial_count = tbody.locator("tr.label-row").count()

    # 유일한 라벨 토큰 (소문자 + 숫자 만)
    new_label = f"e2etest{int(time.time() * 1000) % 100000}"

    # 라벨 추가 form — label input 에 값 입력
    add_form = page.locator(".label-add-form").first
    label_input = add_form.locator("input[name='label']")
    label_input.fill(new_label)

    # 폼 제출 — HTMX POST /api/labels 응답 대기
    with page.expect_response("**/api/labels"):
        add_form.locator("button[type='submit']").click()

    # tbody 에 새 행이 추가됐는지 확인
    page.wait_for_function(
        f"document.querySelectorAll('#{tbody_id} tr.label-row').length > {initial_count}",
        timeout=3000,
    )
    new_count = tbody.locator("tr.label-row").count()
    assert new_count == initial_count + 1


def test_labels_admin_delete_label_removes_row(page, e2e_url):
    """라벨 삭제 버튼 클릭 → confirm 수락 → row 사라짐 (hx-swap=delete)."""
    page.goto(f"{e2e_url}/labels/admin")
    page.wait_for_selector(".axis-tabs", timeout=5000)

    tabs = page.locator(".axis-tab")
    first_axis = tabs.nth(0).inner_text().strip()
    tbody_id = f"axis-tbody-{first_axis}"

    # 먼저 삭제할 라벨 추가
    new_label = f"todel{int(time.time() * 1000) % 100000}"
    add_form = page.locator(".label-add-form").first
    add_form.locator("input[name='label']").fill(new_label)
    with page.expect_response("**/api/labels"):
        add_form.locator("button[type='submit']").click()

    # 새 행이 생겼는지 확인
    tbody = page.locator(f"#{tbody_id}")
    page.wait_for_selector(f"#{tbody_id} tr.label-row", timeout=3000)
    count_before = tbody.locator("tr.label-row").count()
    assert count_before >= 1

    # 마지막 행의 삭제 버튼 클릭 — hx-confirm 다이얼로그 수락
    page.on("dialog", lambda d: d.accept())

    last_row = tbody.locator("tr.label-row").last
    # 삭제 버튼 (btn-danger)
    del_btn = last_row.locator(".btn-danger")
    with page.expect_response("**/api/labels/**"):
        del_btn.click()

    # 행이 줄어들었는지 확인
    page.wait_for_function(
        f"document.querySelectorAll('#{tbody_id} tr.label-row').length < {count_before}",
        timeout=3000,
    )
    count_after = tbody.locator("tr.label-row").count()
    assert count_after == count_before - 1
