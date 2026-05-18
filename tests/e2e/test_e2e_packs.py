"""M5 Stage 2 — Playwright e2e: 팩 관리 페이지 검증.

M5_verification.md §4 step 27-28 에 해당.

* /packs 진입 → 팩 카드 그리드 렌더
* 팩 토글 버튼 → PATCH → outerHTML 교체 + 상태 변화
"""
from __future__ import annotations

import pytest


pytestmark = pytest.mark.e2e


def test_packs_page_loads_and_shows_pack_grid(page, e2e_url):
    """/packs 진입 → 팩 카드 그리드 + 자산 수 + kind 분포 렌더."""
    page.goto(f"{e2e_url}/packs")
    assert "팩 관리" in page.title()

    # 팩 카드 그리드 컨테이너 존재
    page.wait_for_selector("#packs-container", timeout=5000)

    # e2e DB 에는 test_pack 1개가 들어있어야 함
    pack_cards = page.locator(".pack-card")
    assert pack_cards.count() >= 1, "최소 1개 팩 카드가 있어야 함"

    # 첫 번째 카드에 이름 + asset_count 표시
    first_card = pack_cards.first
    # 팩 이름 존재
    assert first_card.locator(".pack-card-name").count() >= 1
    # 에셋 수 표시 (N개)
    count_text = first_card.locator(".pack-asset-count").inner_text()
    assert "개" in count_text


def test_packs_page_toggle_button_present(page, e2e_url):
    """/packs 팩 카드에 활성/비활성 토글 버튼 존재."""
    page.goto(f"{e2e_url}/packs")
    page.wait_for_selector(".pack-card", timeout=5000)

    toggle_btn = page.locator(".pack-toggle-btn").first
    assert toggle_btn.count() == 1 or toggle_btn.is_visible()
    # 버튼 텍스트가 '활성' 또는 '비활성' 포함
    btn_text = toggle_btn.inner_text()
    assert "활성" in btn_text or "비활성" in btn_text


def test_packs_page_toggle_changes_enabled_state(page, e2e_url):
    """팩 토글 버튼 클릭 → PATCH /api/packs/{id} → outerHTML 교체 + 상태 반전."""
    page.goto(f"{e2e_url}/packs")
    page.wait_for_selector(".pack-card", timeout=5000)

    first_card = page.locator(".pack-card").first
    initial_enabled = first_card.get_attribute("data-enabled")
    assert initial_enabled in ("true", "false")

    # 토글 버튼 클릭 — HTMX PATCH 응답 대기
    toggle_btn = first_card.locator(".pack-toggle-btn")
    with page.expect_response("**/api/packs/**"):
        toggle_btn.click()

    # outerHTML 교체 후 새 카드의 data-enabled 값이 반전되어야 함
    new_card = page.locator(".pack-card").first
    new_enabled = new_card.get_attribute("data-enabled")
    expected = "false" if initial_enabled == "true" else "true"
    assert new_enabled == expected
