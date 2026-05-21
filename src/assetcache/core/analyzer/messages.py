"""Shared message builders for analyzers + batch.

SpriteAnalyzer / SoundAnalyzer / SpritesheetAnalyzer 의 interactive 경로는
리샘플·멜스펙트로그램 등 복잡한 전처리를 수행하므로 그대로 유지한다.
이 모듈은 **batch 경로 전용** — 원본 파일 바이트를 그대로 base64 인코딩해
ChatMessage 를 구성한다.

BatchManager._build_chat_requests 가 사용한다.
interactive 와 batch 가 동일 prompt 구조(단순화) + payload 를 공유하여
정확도 일관성을 유지한다.
"""

from __future__ import annotations

import base64
from pathlib import Path

from ..llm.base import ChatMessage


_AUDIO_MIME_BY_SUFFIX: dict[str, str] = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
}

# batch 경로 전용 프롬프트 — interactive 의 registry-driven enum 과 달리
# 범용 JSON metadata 요청.  분석 이후 BatchPoller 에서 enum 정규화 수행.
# M11.4 Phase 3: category enum + palette tone group 을 prompt 에 직접 명시
# 해 inventory_item / ui_icon / hex 거부 정확도를 끌어올린다.
BATCH_IMAGE_PROMPT = (
    "You are a game asset metadata generator. Respond ONLY with valid JSON.\n"
    "Fields:\n"
    "- category (string): pick exactly one of "
    "[character, tile, effect, background, inventory_item, ui_icon, other]\n"
    "- style (string): short style label such as pixel_art or cartoon\n"
    "- mood (array of strings): pick from heroic, dark, playful, neutral, "
    "minimalist, calm, mysterious, intense, or similar\n"
    "- palette (array of strings): pick tone group names from "
    "[warm, cool, monochrome, high_contrast, pastel, neutral] — "
    "do NOT use hex codes like #FDD835\n"
    "- subject (short noun phrase)\n"
    "- description (one sentence)\n"
    "- confidence (float 0..1)\n"
    "\n"
    "Guidance:\n"
    "- Use 'inventory_item' for crown, sword, potion, gem, scroll, key, "
    "or other carry-and-use objects — NOT 'character'.\n"
    "- Use 'ui_icon' for HUD buttons, settings cog, heart counter, or "
    "stand-alone interface graphics — NOT 'icon' or 'ui'."
)

BATCH_AUDIO_PROMPT = (
    "You are a game audio metadata generator. "
    "Respond ONLY with valid JSON with fields: "
    "category (string), mood (array of strings), instruments (array of strings), "
    "tempo (string or null), intensity (string), loopable (boolean), "
    "description (one sentence), confidence (float 0..1)."
)

# M11.2 — Spritesheet batch 전용 prompt.  sync SpritesheetAnalyzer._call_gemma 의
# system prompt 와 동일한 schema — animation_hint enum 은 호출 시점에 builder
# 가 동적 주입한다.  ``{anim_enum}`` placeholder 는 build_spritesheet_chat_messages
# 가 ``.format(anim_enum=...)`` 로 치환.
BATCH_SPRITESHEET_PROMPT = (
    "You are a game animation labeler. Respond ONLY with valid JSON.\n\n"
    "Input is a horizontal strip of sprite frames.\n"
    "Schema:\n"
    "- animation_hint: array (1..4) from [{anim_enum}]\n"
    "- description: one sentence\n"
    "- subject: short noun phrase\n"
    "- category: 'character'\n"
    "- style: 'pixel_art'\n"
    "- mood: []\n"
    "- palette: []\n"
    "- confidence: float 0..1\n"
)


def build_image_chat_messages(*, abs_path: Path, prompt: str) -> list[ChatMessage]:
    """이미지 1장 원본 바이트를 base64 인코딩해 ChatMessage 1개 반환.

    batch 경로 전용 — interactive 는 SpriteAnalyzer 가 리샘플 후 인코딩.
    """
    img_bytes = abs_path.read_bytes()
    img_b64 = base64.b64encode(img_bytes).decode("ascii")
    return [
        ChatMessage(role="user", content=prompt, images_b64=[img_b64]),
    ]


def build_audio_chat_messages(*, abs_path: Path, prompt: str) -> list[ChatMessage]:
    """오디오 파일 원본 바이트를 base64 인코딩해 ChatMessage 1개 반환.

    mime type 은 확장자 기반 — 알 수 없으면 application/octet-stream.
    batch 경로 전용 — interactive 는 SoundAnalyzer 가 librosa 리샘플 + 청크 분할.
    """
    audio_bytes = abs_path.read_bytes()
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    mime = _AUDIO_MIME_BY_SUFFIX.get(abs_path.suffix.lower(), "application/octet-stream")
    return [
        ChatMessage(role="user", content=prompt, audio_b64=[(audio_b64, mime)]),
    ]


def build_spritesheet_chat_messages(
    *,
    abs_path: Path,
    detection,
    prompt: str,
    anim_enum: str,
    max_long_edge: int = 768,
) -> list[ChatMessage]:
    """시트 자산을 batch 전송하기 위한 composite strip + 시트 전용 prompt.

    detect_sheet 결과의 frames 를 ``make_preview_composite`` 로 8칸 가로 strip
    으로 합성한 뒤 PNG base64 로 인코딩.  system 메시지에 schema (enum 동적
    주입) + user 메시지에 합성 이미지 1장.  sync SpritesheetAnalyzer 의
    ``_call_gemma`` 와 동일 schema.
    """
    import io

    from PIL import Image as _PILImage

    from ..sheet.preview import make_preview_composite

    with _PILImage.open(abs_path) as src:
        src.load()
        composite = make_preview_composite(
            src, list(detection.frames), max_size=max_long_edge,
        )
    buf = io.BytesIO()
    composite.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    system_content = prompt.format(anim_enum=anim_enum)
    return [
        ChatMessage(role="system", content=system_content),
        ChatMessage(
            role="user",
            content="Identify the animation in this strip.",
            images_b64=[img_b64],
        ),
    ]
