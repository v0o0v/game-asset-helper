"""M5 Phase 6+ — Playwright e2e smoke (의존성 검증).

스테이지 1 — 인프라가 동작하는지 최소 2 케이스로 검증.
스테이지 2 가 M5_verification §4 36 단계 자동화 매핑 + 확장 예정.
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.e2e


def test_library_page_loads_and_renders_title(page, e2e_url):
    """페이지 진입 → <title> 에 'AssetCacheMCP' 포함."""
    page.goto(f"{e2e_url}/library")
    assert "AssetCacheMCP" in page.title()


def test_search_bar_submits_on_button_click(page, e2e_url):
    """검색 바에 텍스트 입력 → 🔍 버튼 클릭 → HTMX 검색 결과 응답 수신."""
    page.goto(f"{e2e_url}/library")
    # 초기 load trigger 결과 대기 — #results 가 렌더될 때까지
    page.wait_for_selector("#results")
    page.fill('input[name="query"]', "hero")
    # 검색 버튼 클릭 + HTMX POST /ui/search-results 응답 대기
    with page.expect_response("**/ui/search-results"):
        page.click("button.search-submit")
    # 응답 수신 후 #results 영역이 여전히 존재하는지 확인
    assert page.query_selector("#results") is not None
