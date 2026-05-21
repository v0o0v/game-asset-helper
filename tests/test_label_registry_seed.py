"""M11.4 Phase 2 — LabelRegistry seed 확장 검증.

LLM #3 한계 (`crown_icon` 류 inventory item 이 character 로 잘못 분류,
`category='UI element'` 같은 whitelist 위반) 를 해소하려면 시드에
``inventory_item`` / ``ui_icon`` 카테고리, ``minimalist`` / ``neutral`` 무드
가 있어야 한다.  prompt 강화 (Phase 3) 도 이 라벨이 등록돼야 의미가 있다.
"""
from __future__ import annotations

from assetcache.core.labels import SEED_LABELS


def test_category_seed_has_inventory_item_and_ui_icon() -> None:
    """category 시드에 inventory_item / ui_icon 신규 토큰 등록 (M11.4 LLM #3)."""
    tokens = {token for token, _desc in SEED_LABELS["category"]}
    assert "inventory_item" in tokens
    assert "ui_icon" in tokens


def test_mood_seed_has_minimalist_and_neutral() -> None:
    """mood 시드에 minimalist / neutral 신규 토큰 등록 (M11.4 LLM #3)."""
    tokens = {token for token, _desc in SEED_LABELS["mood"]}
    assert "minimalist" in tokens
    assert "neutral" in tokens


def test_new_seed_tokens_have_descriptions() -> None:
    """신규 시드 4 토큰 모두 비어있지 않은 1문장 description 보유."""
    targets = {
        ("category", "inventory_item"),
        ("category", "ui_icon"),
        ("mood", "minimalist"),
        ("mood", "neutral"),
    }
    found: dict[tuple[str, str], str] = {}
    for axis, items in SEED_LABELS.items():
        for token, desc in items:
            if (axis, token) in targets:
                found[(axis, token)] = desc
    assert set(found.keys()) == targets
    for key, desc in found.items():
        assert isinstance(desc, str) and desc.strip(), f"{key} description empty"
