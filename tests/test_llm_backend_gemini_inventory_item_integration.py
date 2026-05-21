"""GeminiBackend integration — inventory_item / ui_icon 분류 정확도 (M11.4).

M11.4 LLM #3 검증 — 실 Gemini 호출로 BATCH_IMAGE_PROMPT 가이드가 crown
같은 inventory item 을 character 가 아닌 inventory_item 으로 분류하도록
유도되는지 확인한다.  기본 `pytest -q` 에서는 `llm_integration` marker
deselect 로 제외.

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

from assetcache.core.analyzer.messages import BATCH_IMAGE_PROMPT
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
    # 이상적 결과: inventory_item (or 최소한 item-adjacent 카테고리)
    acceptable = {"inventory_item", "item", "icon", "ui_icon", "other"}
    assert category in acceptable, (
        f"crown_icon category {category!r} 이 acceptable set 밖: {out!r}"
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
    acceptable = {"ui_icon", "ui", "icon", "inventory_item", "other"}
    assert category in acceptable, (
        f"ui_button category {category!r} 이 acceptable set 밖: {out!r}"
    )
