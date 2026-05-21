"""M11.4 Phase 3 — BATCH_IMAGE_PROMPT enum + tone group + inventory_item 가이드.

M11.3 LIVE 검증 v2 에서 `crown_icon` 류 inventory item 이 character 로
잘못 분류되고, palette 가 `#FDD835` 같은 hex 로 응답돼 whitelist 위반
'other' 강등되는 한계를 해소한다.  prompt 자체가 enum 을 명시해 Gemini
batch 응답의 정확도를 끌어올린다.
"""
from __future__ import annotations

from assetcache.core.analyzer.messages import BATCH_IMAGE_PROMPT


def test_prompt_lists_category_enum_with_inventory_item_and_ui_icon() -> None:
    """category enum 에 inventory_item / ui_icon 신규 토큰 명시."""
    assert "inventory_item" in BATCH_IMAGE_PROMPT
    assert "ui_icon" in BATCH_IMAGE_PROMPT


def test_prompt_lists_palette_tone_groups_and_rejects_hex() -> None:
    """palette 가 hex 대신 tone group set 으로 응답하도록 enum 명시."""
    for tone in (
        "warm", "cool", "monochrome", "high_contrast", "pastel", "neutral",
    ):
        assert tone in BATCH_IMAGE_PROMPT, f"missing tone group {tone!r}"
    # hex 사용 금지 가이드
    assert "hex" in BATCH_IMAGE_PROMPT.lower()


def test_prompt_inventory_item_guidance_with_concrete_examples() -> None:
    """crown / sword / potion 같은 구체 예시로 inventory_item 분류 유도."""
    lower = BATCH_IMAGE_PROMPT.lower()
    examples = ("crown", "sword", "potion", "gem", "scroll")
    assert any(e in lower for e in examples), \
        "prompt should reference at least one inventory item example"


def test_prompt_still_requests_json_only_response() -> None:
    """기존 'JSON only' 제약 보존 — prompt 강화로 인한 형식 regression 방지."""
    lower = BATCH_IMAGE_PROMPT.lower()
    assert "json" in lower
    # category / mood / palette / confidence 필수 필드 모두 보존
    for field in ("category", "mood", "palette", "confidence"):
        assert field in lower
