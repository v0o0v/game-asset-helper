"""ClaudeBackend — anthropic SDK wrap (M11 Phase 2).

**image 전용**:
- chat_image: ``claude-haiku-4-5-20251001`` 등 — text + image source(base64,
  image/png) 의 multipart content
- chat_audio: 미지원 — capabilities 가 False 라 ``BackendChain`` 이
  chat_audio 모드에서 자동 skip. ``audio_b64`` 입력이 들어와도
  ``_to_messages`` 가 무시
- text_embed: 미지원 — Anthropic 은 embedding 모델 없음. ``embed()``
  호출은 hard ``BackendError`` raise (chain.embed() 진입 자체가 막힘:
  ``BackendChain`` 의 ``_eligible`` 이 capability 체크)
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic
from anthropic import Anthropic

from ..base import (
    BackendCapabilities,
    BackendError,
    BackendInfo,
    ChatMessage,
    LLMBackend,
)

log = logging.getLogger(__name__)


_HARD = (
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
    anthropic.BadRequestError,
    anthropic.NotFoundError,
)

_TRANSIENT = (
    anthropic.RateLimitError,
    anthropic.APIStatusError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
)


class ClaudeBackend:
    info = BackendInfo(
        name="claude",
        display_name="Anthropic Claude",
        homepage="https://docs.claude.com/",
        capabilities=BackendCapabilities(
            supports_chat_image=True,
            supports_chat_audio=False,
            supports_text_embed=False,
            embed_dim=None,
        ),
        setup_url="https://console.anthropic.com/settings/keys",
    )

    def __init__(self, *, api_key: str, model_image: str, timeout: float) -> None:
        if not api_key:
            raise BackendError(
                backend="claude",
                stage="init",
                transient=False,
                cause=ValueError("api_key empty"),
            )
        self._client = Anthropic(api_key=api_key, timeout=timeout)
        self.model_image = model_image
        self.timeout = timeout

    def _to_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """ChatMessage 리스트 → anthropic messages 시그니처.

        audio_b64 는 capability 미지원이라 무시 (chain skip 으로 사전 차단되지만
        직접 호출 시 안전망).
        """
        out: list[dict[str, Any]] = []
        for m in messages:
            content: list[dict[str, Any]] = []
            if m.content:
                content.append({"type": "text", "text": m.content})
            for b64 in m.images_b64:
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": b64,
                        },
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
        system_prompt = (
            "Reply with strict JSON only — no prose, no markdown fences."
            if force_json
            else ""
        )
        try:
            r = self._client.messages.create(
                model=self.model_image,
                max_tokens=2000,
                system=system_prompt,
                messages=self._to_messages(messages),
            )
        except _HARD as e:
            raise BackendError(
                backend="claude", stage="chat", transient=False, cause=e
            ) from e
        except _TRANSIENT as e:
            raise BackendError(
                backend="claude", stage="chat", transient=True, cause=e
            ) from e
        except Exception as e:
            raise BackendError(
                backend="claude", stage="chat", transient=True, cause=e
            ) from e

        text = ""
        for block in r.content:
            if getattr(block, "type", None) == "text":
                text += getattr(block, "text", "") or ""

        if not force_json:
            return {"text": text}
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError) as e:
            raise BackendError(
                backend="claude",
                stage="chat",
                transient=True,
                cause=ValueError(f"non-json response: {text[:80]}"),
            ) from e

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        raise BackendError(
            backend="claude",
            stage="embed",
            transient=False,
            cause=NotImplementedError("Claude has no embedding model"),
        )

    def test_connection(self) -> bool:
        try:
            self._client.messages.create(
                model=self.model_image,
                max_tokens=1,
                messages=[{"role": "user", "content": "x"}],
            )
            return True
        except Exception:
            return False


_: LLMBackend = ClaudeBackend.__new__(ClaudeBackend)  # type: ignore[arg-type]
