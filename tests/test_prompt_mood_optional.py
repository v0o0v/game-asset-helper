"""M11.7 A1 — mood OPTIONAL 가이드.

M11.6 LIVE 의 mood 노이즈 (시트 5/5 가 일률적으로 mood=minimalist/neutral
응답 + crown_icon 같은 inventory item 에 mood=heroic/playful 응답) 는
prompt 가 mood 를 "array of strings" 로만 명시해 Gemini 가 catch-all
mood 토큰을 강제 채우는 패턴이 원인.  M11.7 A1 — 두 prompt 의 mood
줄에 "leave [] if no clear mood" 같은 OPTIONAL 시그널을 명시.
"""
from __future__ import annotations

from assetcache.core.analyzer.messages import (
    BATCH_IMAGE_PROMPT,
    BATCH_SPRITESHEET_PROMPT,
)


def _has_mood_optional_signal(prompt: str) -> bool:
    """mood 가 빈 배열 응답 허용된다는 시그널 — leave/empty/optional + [] 패턴."""
    lower = prompt.lower()
    # 'leave [] if no clear mood' / 'or [] if no clear mood' / 'mood is optional'
    has_empty_marker = "[]" in prompt or "empty" in lower or "optional" in lower
    has_no_mood_phrase = (
        "no clear mood" in lower
        or "no mood" in lower
        or "if no clear" in lower
    )
    return has_empty_marker and has_no_mood_phrase


def test_image_prompt_marks_mood_as_optional() -> None:
    """BATCH_IMAGE_PROMPT 의 mood 줄에 OPTIONAL 시그널 명시."""
    assert _has_mood_optional_signal(BATCH_IMAGE_PROMPT), (
        "BATCH_IMAGE_PROMPT must mark mood as optional with empty/[] guidance"
    )


def test_spritesheet_prompt_marks_mood_as_optional() -> None:
    """BATCH_SPRITESHEET_PROMPT 의 mood 줄에 OPTIONAL 시그널 명시."""
    assert _has_mood_optional_signal(BATCH_SPRITESHEET_PROMPT), (
        "BATCH_SPRITESHEET_PROMPT must mark mood as optional with empty/[] guidance"
    )
