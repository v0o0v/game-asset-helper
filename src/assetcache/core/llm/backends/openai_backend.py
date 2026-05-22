"""OpenAIBackend — openai SDK wrap (M11 Phase 3).

3 modality 모두 지원 + ``base_url`` 인자 expose (M11.9 에서 OpenRouterBackend 제거됨,
``base_url`` 은 OpenAI-compatible endpoint 재사용 가능성을 위해 유지).

- chat_image: gpt-5.4-mini 등 vision — content type=image_url, data URI
- chat_audio: gpt-4o-audio-preview — content type=input_audio (base64 + format)
- text_embed: text-embedding-3-small — embeddings.create (1536 dim default)

모듈명이 `openai_backend.py` 인 이유는 SDK 패키지 `openai` 와의 import 충돌 회피.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import openai
from openai import OpenAI

from ..base import (
    BackendCapabilities,
    BackendError,
    BackendInfo,
    ChatMessage,
    LLMBackend,
)

log = logging.getLogger(__name__)


_HARD = (
    openai.AuthenticationError,
    openai.PermissionDeniedError,
    openai.BadRequestError,
    openai.NotFoundError,
)

_TRANSIENT = (
    openai.RateLimitError,
    openai.APIStatusError,
    openai.APIConnectionError,
    openai.APITimeoutError,
)


def _classify(e: Exception) -> bool:
    """True → transient."""
    if isinstance(e, _HARD):
        return False
    if isinstance(e, _TRANSIENT):
        return True
    return True  # 알 수 없는 예외 (네트워크 등) → transient


class OpenAIBackend:
    info = BackendInfo(
        name="openai",
        display_name="OpenAI",
        homepage="https://platform.openai.com/",
        capabilities=BackendCapabilities(
            supports_chat_image=True,
            supports_chat_audio=True,
            supports_text_embed=True,
            embed_dim=1536,
        ),
        setup_url="https://platform.openai.com/api-keys",
    )

    def __init__(
        self,
        *,
        api_key: str,
        model_image: str,
        model_audio: str,
        model_embed: str,
        timeout: float,
        base_url: str | None = None,
    ) -> None:
        if not api_key:
            raise BackendError(
                backend=self._backend_name(),
                stage="init",
                transient=False,
                cause=ValueError("api_key empty"),
            )
        self._client = OpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout
        )
        self.model_image = model_image
        self.model_audio = model_audio
        self.model_embed = model_embed
        self.timeout = timeout
        self.base_url = base_url

    def _backend_name(self) -> str:
        """subclass 가 self.info 를 override 하면 그쪽 name 반환."""
        return self.info.name

    def _select_model(self, messages: list[ChatMessage]) -> str:
        has_audio = any(m.audio_b64 for m in messages)
        return self.model_audio if has_audio else self.model_image

    def _to_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """ChatMessage 리스트 → openai chat completions content shape."""
        out: list[dict[str, Any]] = []
        for m in messages:
            content: list[dict[str, Any]] = []
            if m.content:
                content.append({"type": "text", "text": m.content})
            for b64 in m.images_b64:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{b64}",
                        },
                    }
                )
            for data, mime in m.audio_b64:
                fmt = mime.split("/")[-1] if "/" in mime else mime
                content.append(
                    {
                        "type": "input_audio",
                        "input_audio": {"data": data, "format": fmt},
                    }
                )
            out.append({"role": m.role, "content": content})
        return out

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        force_json: bool = True,
        num_ctx: int = 8000,
    ) -> dict:
        kwargs: dict[str, Any] = {
            "model": self._select_model(messages),
            "messages": self._to_messages(messages),
        }
        if force_json:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            r = self._client.chat.completions.create(**kwargs)
        except Exception as e:
            transient = _classify(e)
            raise BackendError(
                backend=self._backend_name(),
                stage="chat",
                transient=transient,
                cause=e,
            ) from e

        text = ""
        try:
            text = r.choices[0].message.content or ""
        except (AttributeError, IndexError) as e:
            raise BackendError(
                backend=self._backend_name(),
                stage="chat",
                transient=True,
                cause=ValueError(f"unexpected response shape: {e}"),
            ) from e

        if not force_json:
            return {"text": text}
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError) as e:
            raise BackendError(
                backend=self._backend_name(),
                stage="chat",
                transient=True,
                cause=ValueError(f"non-json response: {text[:80]}"),
            ) from e

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        try:
            r = self._client.embeddings.create(
                model=model or self.model_embed,
                input=text,
            )
        except Exception as e:
            raise BackendError(
                backend=self._backend_name(),
                stage="embed",
                transient=_classify(e),
                cause=e,
            ) from e
        return list(r.data[0].embedding)

    def test_connection(self) -> bool:
        try:
            list(self._client.models.list())
            return True
        except Exception:
            return False

    def supports_batch(self) -> bool:
        return False


_: LLMBackend = OpenAIBackend.__new__(OpenAIBackend)  # type: ignore[arg-type]
