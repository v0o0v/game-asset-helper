"""M11.7 A2 — category 별 mood 차단 가이드.

M11.6 LIVE 에서 crown_icon (category=inventory_item) 응답에
mood=heroic/playful 가 합산.  inventory item / UI icon / tile / background
는 정적 객체라 감정 라벨이 의미 없음 — prompt Guidance 에 명시적 차단
가이드 추가.
"""
from __future__ import annotations

from assetcache.core.analyzer.messages import (
    BATCH_IMAGE_PROMPT,
    BATCH_SPRITESHEET_PROMPT,
)


def _has_category_mood_exclusion(prompt: str) -> bool:
    """4 정적 category 모두 + mood 차단 키워드 동시 명시 확인."""
    lower = prompt.lower()
    # 4 정적 category 모두 등장
    static_categories = ("inventory_item", "ui_icon", "tile", "background")
    if not all(cat in lower for cat in static_categories):
        return False
    # 'do NOT include mood' 또는 'mood as []' 같은 차단 시그널
    return (
        "do not include mood" in lower
        or "do not include any mood" in lower
        or ("mood" in lower and "leave" in lower and "[]" in prompt)
    )


def test_image_prompt_excludes_mood_for_static_categories() -> None:
    """BATCH_IMAGE_PROMPT 가 4 정적 category 에 mood 차단 가이드 명시."""
    assert _has_category_mood_exclusion(BATCH_IMAGE_PROMPT), (
        "BATCH_IMAGE_PROMPT must exclude mood for inventory_item/ui_icon/tile/background"
    )


def test_spritesheet_prompt_excludes_mood_for_static_categories() -> None:
    """BATCH_SPRITESHEET_PROMPT 도 동일 가이드 노출.

    spritesheet 는 대부분 character 지만, 회전 coin / tile sheet 같은
    경계 케이스도 있으니 동일 가이드 적용.
    """
    assert _has_category_mood_exclusion(BATCH_SPRITESHEET_PROMPT), (
        "BATCH_SPRITESHEET_PROMPT must exclude mood for inventory_item/ui_icon/tile/background"
    )
