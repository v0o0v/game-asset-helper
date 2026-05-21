"""GeminiBackend integration — inventory_item / ui_icon 분류 정확도 (M11.4 + M11.6).

M11.4 LLM #3 검증 — 실 Gemini 호출로 BATCH_IMAGE_PROMPT 가이드가 crown
같은 inventory item 을 character 가 아닌 inventory_item 으로 분류하도록
유도되는지 확인한다.  M11.6 — BATCH_SPRITESHEET_PROMPT palette enum 효과
+ 두 prompt 의 'other' 금지 가이드 효과 확인.  기본 `pytest -q` 에서는
`llm_integration` marker deselect 로 제외.

옵트인:

    $env:GEMINI_API_KEY = "AIza..."
    pytest -m llm_integration tests/test_llm_backend_gemini_inventory_item_integration.py
"""
from __future__ import annotations

import base64
import io
import os

import pytest
from PIL import Image, ImageDraw

from assetcache.core.analyzer.messages import (
    BATCH_IMAGE_PROMPT,
    BATCH_SPRITESHEET_PROMPT,
)
from assetcache.core.llm.backends.gemini import GeminiBackend
from assetcache.core.llm.base import ChatMessage


pytestmark = pytest.mark.llm_integration


@pytest.fixture
def gemini() -> GeminiBackend:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY env not set")
    return GeminiBackend(
        api_key=api_key,
        model_image="gemini-2.5-flash",
        model_audio="gemini-2.5-flash",
        model_embed="gemini-embedding-001",
        timeout=60.0,
    )


def _make_crown_icon_png() -> str:
    """단순한 노란색 왕관 아이콘 (inventory_item 후보)."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 왕관 본체 (사다리꼴 + 봉우리 3개)
    draw.polygon(
        [(10, 50), (54, 50), (50, 30), (40, 40),
         (32, 20), (24, 40), (14, 30)],
        fill=(255, 215, 0, 255),  # gold
        outline=(140, 100, 0, 255),
    )
    # 보석
    draw.ellipse((28, 36, 36, 44), fill=(220, 0, 80, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _make_ui_button_png() -> str:
    """단순한 UI 설정 톱니바퀴 아이콘 (ui_icon 후보)."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 톱니바퀴 모양 (8 spoke)
    draw.ellipse((10, 10, 54, 54), fill=(120, 120, 130, 255))
    draw.ellipse((22, 22, 42, 42), fill=(40, 40, 50, 255))
    for x in (4, 28, 52):
        draw.rectangle((x, 28, x + 8, 36), fill=(120, 120, 130, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_crown_classified_as_inventory_item_not_character(gemini) -> None:
    """crown_icon → category=inventory_item (M11.4 LLM #3 핵심 검증)."""
    img_b64 = _make_crown_icon_png()
    out = gemini.chat(
        [ChatMessage("user", BATCH_IMAGE_PROMPT, images_b64=[img_b64])],
        force_json=True,
    )
    category = (out.get("category") or "").lower()
    # 핵심: M11.3 에서 character 로 잘못 분류되던 것을 inventory_item 으로 분류
    assert category != "character", (
        f"crown_icon 이 여전히 character 로 분류됨: {out!r}"
    )
    # M11.5 Phase 5 — strict.  M11.4 의 acceptable set 에서 icon/ui_icon/other
    # 를 제거 (LIVE 검증에서 inventory_item 직응답 확인 — verification.md §3).
    acceptable = {"inventory_item", "item"}
    assert category in acceptable, (
        f"crown_icon category {category!r} 이 strict acceptable set 밖: {out!r}"
    )


def test_ui_button_classified_as_ui_icon_not_character(gemini) -> None:
    """settings cog → category=ui_icon (M11.4 신규 카테고리 검증)."""
    img_b64 = _make_ui_button_png()
    out = gemini.chat(
        [ChatMessage("user", BATCH_IMAGE_PROMPT, images_b64=[img_b64])],
        force_json=True,
    )
    category = (out.get("category") or "").lower()
    assert category != "character", (
        f"ui_button 이 character 로 잘못 분류됨: {out!r}"
    )
    # M11.5 Phase 5 — strict.  M11.4 의 acceptable set 에서 icon/inventory_item/other
    # 를 제거.  ui_icon 카테고리가 시드에 등록됐고 (M11.4 Phase 2) prompt 도
    # ui_icon 을 명시 → Gemini 가 정확히 ui_icon/ui 로 응답하는지 strict 확인.
    acceptable = {"ui_icon", "ui"}
    assert category in acceptable, (
        f"ui_button category {category!r} 이 strict acceptable set 밖: {out!r}"
    )


# === M11.6 — BATCH_SPRITESHEET_PROMPT palette + 'other' 금지 ============

_TONE_GROUP_ENUM = frozenset(
    {"warm", "cool", "monochrome", "high_contrast", "pastel", "neutral"}
)


def _make_warrior_strip_png() -> str:
    """4-frame 가로 strip — 검 든 캐릭터 (warm tone)."""
    img = Image.new("RGBA", (256, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for i in range(4):
        ox = i * 64
        # 몸통 (red)
        draw.rectangle((ox + 24, 20, ox + 40, 50), fill=(180, 40, 30, 255))
        # 머리 (gold)
        draw.ellipse((ox + 24, 8, ox + 40, 24), fill=(255, 200, 80, 255))
        # 칼 (silver) — frame 마다 각도 다르게 = 움직임 hint
        x_off = i * 3
        draw.line(
            (ox + 40 + x_off, 30, ox + 56 + x_off, 14),
            fill=(220, 220, 230, 255),
            width=3,
        )
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_spritesheet_response_has_palette_label_from_tone_group(gemini) -> None:
    """M11.6 A1 — composite strip 응답에 palette tone group 토큰 ≥ 1건.

    M11.5 LIVE 의 별도 발견 #1 (시트 5/5 palette 0건) 가 M11.6 A1 (palette
    enum + tone group 가이드) 로 해소되는지 직접 단언.  LIVE driver 결과는
    `M11_6_verification.md §3` 에 5/5 통과 기록.
    """
    img_b64 = _make_warrior_strip_png()
    system_prompt = BATCH_SPRITESHEET_PROMPT.format(
        anim_enum="idle, walk, attack, hurt"
    )
    out = gemini.chat(
        [
            ChatMessage("system", system_prompt),
            ChatMessage(
                "user",
                "Identify the animation in this strip.",
                images_b64=[img_b64],
            ),
        ],
        force_json=True,
    )
    palette = out.get("palette") or []
    assert isinstance(palette, list) and palette, (
        f"BATCH_SPRITESHEET_PROMPT 응답에 palette 라벨 없음: {out!r}"
    )
    # 모든 palette 토큰이 tone group enum 안 + hex 금지
    for tok in palette:
        assert isinstance(tok, str)
        assert not tok.startswith("#"), (
            f"palette 응답이 hex 코드 {tok!r}: prompt hex 금지 위반"
        )
        assert tok.lower() in _TONE_GROUP_ENUM, (
            f"palette token {tok!r} 이 tone group enum 밖: {out!r}"
        )


def test_spritesheet_response_does_not_use_other_fallback(gemini) -> None:
    """M11.6 A2-prompt — BATCH_SPRITESHEET_PROMPT 응답에 'other' 0건.

    M11.5 LIVE 의 별도 발견 #2 (animation='other' 가 4 자산에 합산) 가
    M11.6 A2-prompt ("do NOT use 'other'" 가이드) 로 해소되는지 직접 단언.
    LIVE driver 결과는 `M11_6_verification.md §3` 에 0/6 통과 기록.
    """
    img_b64 = _make_warrior_strip_png()
    system_prompt = BATCH_SPRITESHEET_PROMPT.format(
        anim_enum="idle, walk, attack, hurt"
    )
    out = gemini.chat(
        [
            ChatMessage("system", system_prompt),
            ChatMessage(
                "user",
                "Identify the animation in this strip.",
                images_b64=[img_b64],
            ),
        ],
        force_json=True,
    )
    # 모든 axis 응답에 'other' literal 0건
    for axis in ("animation_hint", "category", "style", "mood", "palette"):
        value = out.get(axis)
        if isinstance(value, list):
            assert "other" not in [
                (v or "").lower() if isinstance(v, str) else v for v in value
            ], f"{axis} 응답에 'other' 포함: {value!r} (full={out!r})"
        elif isinstance(value, str):
            assert value.lower() != "other", (
                f"{axis} 응답이 'other': {out!r}"
            )
