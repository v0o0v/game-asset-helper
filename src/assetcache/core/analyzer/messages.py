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
# 범용 JSON metadata 요청. 분석 이후 BatchPoller 에서 enum 정규화 수행.
BATCH_IMAGE_PROMPT = (
    "You are a game asset metadata generator. "
    "Respond ONLY with valid JSON with fields: "
    "category (string), style (string), mood (array of strings), "
    "palette (array of strings), subject (short noun phrase), "
    "description (one sentence), confidence (float 0..1)."
)

BATCH_AUDIO_PROMPT = (
    "You are a game audio metadata generator. "
    "Respond ONLY with valid JSON with fields: "
    "category (string), mood (array of strings), instruments (array of strings), "
    "tempo (string or null), intensity (string), loopable (boolean), "
    "description (one sentence), confidence (float 0..1)."
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
