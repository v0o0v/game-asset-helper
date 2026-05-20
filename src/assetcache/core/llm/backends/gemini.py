"""GeminiBackend — google-genai SDK wrap (M11 Phase 1).

modality:
- chat_image: gemini-2.5-flash 등 multimodal — text + inline_data(image/png)
- chat_audio: 동일 모델 — Part.from_bytes(audio, mime)
- text_embed: gemini-embedding-001 → embed_content (768 dim default)
"""

from __future__ import annotations

import base64
import json
import logging

from google import genai
from google.genai import types as genai_types

from ..base import (
    BackendCapabilities,
    BackendError,
    BackendInfo,
    ChatMessage,
    LLMBackend,
)

log = logging.getLogger(__name__)


_HARD_EXCEPTIONS: tuple[type[Exception], ...] = ()


def _classify(e: Exception) -> bool:
    """True → transient (chain 다음 backend 시도). False → hard (즉시 raise).

    분류 규칙:
    - `_HARD_EXCEPTIONS` 에 포함된 타입 → hard
    - `code` 속성이 4xx (400/401/403/404) 인 SDK 예외 → hard
    - 메시지에 401/403/permission/api key → hard
    - 그 외 모든 예외 (rate limit 429, 5xx, 네트워크 등) → transient
    """
    if isinstance(e, _HARD_EXCEPTIONS):
        return False
    code = getattr(e, "code", None)
    if isinstance(code, int):
        if code in (400, 401, 403, 404):
            return False
        return True
    msg = str(e).lower()
    if "401" in msg or "403" in msg or "permission" in msg or "api key" in msg:
        return False
    return True


class GeminiBackend:
    info = BackendInfo(
        name="gemini",
        display_name="Google Gemini",
        homepage="https://ai.google.dev/",
        capabilities=BackendCapabilities(
            supports_chat_image=True,
            supports_chat_audio=True,
            supports_text_embed=True,
            embed_dim=768,
        ),
        setup_url="https://aistudio.google.com/apikey",
    )

    def __init__(
        self,
        *,
        api_key: str,
        model_image: str,
        model_audio: str,
        model_embed: str,
        timeout: float,
    ) -> None:
        if not api_key:
            raise BackendError(
                backend="gemini",
                stage="init",
                transient=False,
                cause=ValueError("api_key empty"),
            )
        self._client = genai.Client(api_key=api_key)
        self.model_image = model_image
        self.model_audio = model_audio
        self.model_embed = model_embed
        self.timeout = timeout

    def _select_model(self, messages: list[ChatMessage]) -> str:
        has_audio = any(m.audio_b64 for m in messages)
        return self.model_audio if has_audio else self.model_image

    def _to_contents(self, messages: list[ChatMessage]) -> list:
        parts: list = []
        for m in messages:
            if m.content:
                parts.append(m.content)
            for b64 in m.images_b64:
                parts.append(
                    genai_types.Part.from_bytes(
                        data=base64.b64decode(b64),
                        mime_type="image/png",
                    )
                )
            for data, mime in m.audio_b64:
                parts.append(
                    genai_types.Part.from_bytes(
                        data=base64.b64decode(data),
                        mime_type=mime,
                    )
                )
        return parts

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        force_json: bool = True,
        num_ctx: int = 8000,
    ) -> dict:
        contents = self._to_contents(messages)
        cfg = genai_types.GenerateContentConfig(
            response_mime_type="application/json" if force_json else None,
        )
        try:
            r = self._client.models.generate_content(
                model=self._select_model(messages),
                contents=contents,
                config=cfg,
            )
        except Exception as e:
            transient = _classify(e)
            raise BackendError(
                backend="gemini", stage="chat", transient=transient, cause=e
            ) from e

        text = getattr(r, "text", "") or ""
        if not force_json:
            return {"text": text}
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError) as e:
            raise BackendError(
                backend="gemini",
                stage="chat",
                transient=True,
                cause=ValueError(f"non-json response: {text[:80]}"),
            ) from e

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        try:
            r = self._client.models.embed_content(
                model=model or self.model_embed,
                contents=text,
            )
        except Exception as e:
            raise BackendError(
                backend="gemini",
                stage="embed",
                transient=_classify(e),
                cause=e,
            ) from e
        return list(r.embeddings[0].values)

    def test_connection(self) -> bool:
        try:
            list(self._client.models.list())
            return True
        except Exception:
            return False


_: LLMBackend = GeminiBackend.__new__(GeminiBackend)  # type: ignore[arg-type]
