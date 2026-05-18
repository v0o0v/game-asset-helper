"""M5 Stage 2 — Playwright e2e: 404 / 다크모드 / 반응형 검증.

M5_verification.md §4 step 33-35 에 해당.

* 404 에러 페이지 + "라이브러리로 돌아가기" 링크
* 다크 모드 emulate → CSS variable --bg 변화
* 반응형 ≤768px → 사이드 패널 자동 닫힘
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.e2e


# ─────────────────────────────────────────────────────────────────────
# 404 에러 페이지 (step 33)
# ─────────────────────────────────────────────────────────────────────


def test_404_page_rendered_for_unknown_route(page, e2e_url):
    """존재하지 않는 경로 → 커스텀 404 페이지 + 홈 링크."""
    resp = page.goto(f"{e2e_url}/nonexistent-route-xyz")
    assert resp is not None
    assert resp.status == 404

    # 커스텀 에러 페이지 컨텐츠
    page.wait_for_selector(".error-page", timeout=3000)
    error_code = page.locator(".error-code")
    assert "404" in error_code.inner_text()

    # "라이브러리로 돌아가기" 링크 존재
    back_link = page.locator(".btn-back, a[href='/library']")
    assert back_link.count() >= 1
    href = back_link.first.get_attribute("href")
    assert href == "/library"


def test_404_page_back_link_navigates_to_library(page, e2e_url):
    """404 페이지의 '라이브러리로 돌아가기' 클릭 → /library 로 이동."""
    page.goto(f"{e2e_url}/nonexistent-route-xyz")
    page.wait_for_selector(".btn-back, a[href='/library']", timeout=3000)

    back_link = page.locator(".btn-back, a[href='/library']").first
    back_link.click()

    page.wait_for_url(f"{e2e_url}/library", timeout=5000)
    assert "/library" in page.url


# ─────────────────────────────────────────────────────────────────────
# 다크 모드 (step 34)
# ─────────────────────────────────────────────────────────────────────


def test_dark_mode_css_variable_bg_changes(page, e2e_url):
    """다크 모드 emulate → CSS variable --bg 가 light 와 다른 값."""
    # 라이트 모드에서 --bg 읽기
    page.emulate_media(color_scheme="light")
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")

    bg_light = page.evaluate(
        "getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()"
    )

    # 다크 모드로 전환 후 재로드
    page.emulate_media(color_scheme="dark")
    page.reload()
    page.wait_for_selector("#results")

    bg_dark = page.evaluate(
        "getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()"
    )

    assert bg_light != bg_dark, (
        f"다크/라이트 --bg 가 동일함: light={bg_light!r}, dark={bg_dark!r}"
    )
    # themes.css 기준: 다크 --bg = #1a1a1a, 라이트 --bg = #fafafa
    assert bg_dark == "#1a1a1a"
    assert bg_light == "#fafafa"


def test_dark_mode_css_variable_fg_changes(page, e2e_url):
    """다크 모드에서 --fg 색상이 라이트와 반전된다."""
    page.emulate_media(color_scheme="light")
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")
    fg_light = page.evaluate(
        "getComputedStyle(document.documentElement).getPropertyValue('--fg').trim()"
    )

    page.emulate_media(color_scheme="dark")
    page.reload()
    page.wait_for_selector("#results")
    fg_dark = page.evaluate(
        "getComputedStyle(document.documentElement).getPropertyValue('--fg').trim()"
    )

    assert fg_light != fg_dark
    assert fg_dark == "#fafafa"
    assert fg_light == "#1a1a1a"


# ─────────────────────────────────────────────────────────────────────
# 반응형 ≤768px (step 35)
# ─────────────────────────────────────────────────────────────────────


def test_responsive_side_panel_auto_closes_at_small_viewport(page, e2e_url):
    """≤768px 뷰포트 설정 시 사이드 패널이 자동으로 닫힌다."""
    # 먼저 넓은 뷰포트에서 패널 열기
    page.set_viewport_size({"width": 1200, "height": 800})
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")

    # ⚙ 토글로 패널 열기
    page.click("button.advanced-toggle")
    page.wait_for_selector(".side-panel", state="visible")
    assert page.evaluate("Alpine.store('advanced').open") is True

    # 뷰포트를 768px 이하로 축소 → resize 이벤트 발생
    page.set_viewport_size({"width": 600, "height": 800})

    # resize listener 가 Alpine store 를 닫아야 함 (최대 1초 대기)
    page.wait_for_function(
        "Alpine.store('advanced').open === false",
        timeout=2000,
    )
    assert page.evaluate("Alpine.store('advanced').open") is False


def test_responsive_side_panel_reopens_at_small_viewport(page, e2e_url):
    """≤768px 에서 ⚙ 재클릭 → 패널 다시 열림."""
    page.set_viewport_size({"width": 600, "height": 800})
    page.goto(f"{e2e_url}/library")
    page.wait_for_selector("#results")

    # 작은 뷰포트에서는 처음에 닫혀있어야 함
    assert page.evaluate("Alpine.store('advanced').open") is False

    # ⚙ 클릭 → 패널 열림
    page.click("button.advanced-toggle")
    page.wait_for_selector(".side-panel", state="visible")
    assert page.evaluate("Alpine.store('advanced').open") is True
