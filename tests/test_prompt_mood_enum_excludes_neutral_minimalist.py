"""M11.8 — BATCH_*_PROMPT mood enum 동기화.

M11.7 의 두 prompt 가이드는 mood enum 에 `neutral` / `minimalist` 토큰을
catch-all 로 노출하고 있어 LLM 응답에서 그대로 떨어진다 (M11.7 LIVE
시트 5/5 자산: mood=['neutral'] 4건 + ['minimalist'] 1건).  시드 단계
비활성화 (`DISABLED_BY_DEFAULT`) 와 동기화해 prompt enum 에서도 두 토큰
제거.  나머지 mood 토큰 (heroic / dark / playful / calm / mysterious /
intense) 은 보존.
"""
from __future__ import annotations

import re

from assetcache.core.analyzer.messages import (
    BATCH_IMAGE_PROMPT,
    BATCH_SPRITESHEET_PROMPT,
)


# 두 prompt 모두 동일하게 `mood (...): ... pick from heroic, dark, ...` 형태로
# mood 토큰 enum 을 한 줄에 나열한다.  enum 만 추출하기 위해 "pick from" 다음
# 부터 다음 큰 섹션 (`palette` 또는 `confidence` 등) 직전까지 슬라이스.


def _extract_mood_enum_block(prompt: str) -> str:
    """mood 관련 가이드 라인만 잘라내 반환.

    BATCH_IMAGE_PROMPT 와 BATCH_SPRITESHEET_PROMPT 두 형태 모두 호환되는
    가벼운 텍스트 추출.  내부 newline 까지 포함하지만 mood 다음의 다른
    field (palette / confidence) 는 제외.
    """
    match = re.search(
        r"-\s*mood\b.*?(?=\n-\s*\w+\b|\n\n)", prompt, re.DOTALL
    )
    assert match is not None, f"mood 줄을 찾지 못함:\n{prompt[:400]}"
    return match.group(0)


def test_batch_image_prompt_mood_enum_excludes_neutral_and_minimalist() -> None:
    """BATCH_IMAGE_PROMPT 의 mood enum 에 `neutral`/`minimalist` 부재."""
    enum_block = _extract_mood_enum_block(BATCH_IMAGE_PROMPT)
    assert "neutral" not in enum_block, (
        "M11.8: BATCH_IMAGE_PROMPT mood enum 의 'neutral' 제거 필요"
    )
    assert "minimalist" not in enum_block, (
        "M11.8: BATCH_IMAGE_PROMPT mood enum 의 'minimalist' 제거 필요"
    )


def test_batch_spritesheet_prompt_mood_enum_excludes_neutral_and_minimalist() -> None:
    """BATCH_SPRITESHEET_PROMPT 의 mood enum 에 `neutral`/`minimalist` 부재."""
    enum_block = _extract_mood_enum_block(BATCH_SPRITESHEET_PROMPT)
    assert "neutral" not in enum_block, (
        "M11.8: BATCH_SPRITESHEET_PROMPT mood enum 의 'neutral' 제거 필요"
    )
    assert "minimalist" not in enum_block, (
        "M11.8: BATCH_SPRITESHEET_PROMPT mood enum 의 'minimalist' 제거 필요"
    )


def test_batch_image_prompt_mood_enum_keeps_other_tokens() -> None:
    """BATCH_IMAGE_PROMPT mood enum 의 다른 토큰 6 개 보존."""
    enum_block = _extract_mood_enum_block(BATCH_IMAGE_PROMPT)
    for token in ("heroic", "dark", "playful", "calm", "mysterious", "intense"):
        assert token in enum_block, (
            f"M11.8: BATCH_IMAGE_PROMPT mood enum 에 '{token}' 누락"
        )


def test_batch_spritesheet_prompt_mood_enum_keeps_other_tokens() -> None:
    """BATCH_SPRITESHEET_PROMPT mood enum 의 다른 토큰 6 개 보존."""
    enum_block = _extract_mood_enum_block(BATCH_SPRITESHEET_PROMPT)
    for token in ("heroic", "dark", "playful", "calm", "mysterious", "intense"):
        assert token in enum_block, (
            f"M11.8: BATCH_SPRITESHEET_PROMPT mood enum 에 '{token}' 누락"
        )
