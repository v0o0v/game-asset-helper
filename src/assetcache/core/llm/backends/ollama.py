"""OllamaBackend — 기존 OllamaClient wrap.

행동 보존:
- chat/embed 시그니처 그대로.
- OllamaClient 내부의 cold-start retry + OpenAI↔native fallback 은 유지.
- 에러 분류만 BackendError 로 통일 — OllamaError 는 retry 가 소진된 후의 상태라
  transient=True 로 매핑 (chain 의 다음 backend 시도).
"""

from __future__ import annotations

import httpx

from ...ollama_client import OllamaClient, OllamaError
from ..base import (
    BackendCapabilities,
    BackendError,
    BackendInfo,
    ChatMessage,
    LLMBackend,
)


class OllamaBackend:
    info = BackendInfo(
        name="ollama",
        display_name="Ollama (local)",
        homepage="https://ollama.com/",
        capabilities=BackendCapabilities(
            supports_chat_image=True,
            supports_chat_audio=True,
            supports_text_embed=True,
            embed_dim=None,
        ),
        setup_url="https://ollama.com/download",
    )

    def __init__(self, *, client: OllamaClient) -> None:
        self._client = client

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        force_json: bool = True,
        num_ctx: int = 8000,
    ) -> dict:
        try:
            return self._client.chat(
                messages, force_json=force_json, num_ctx=num_ctx
            )
        except OllamaError as e:
            raise BackendError(
                backend="ollama", stage="chat", transient=True, cause=e
            ) from e

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        try:
            return self._client.embed(text, model=model)
        except OllamaError as e:
            raise BackendError(
                backend="ollama", stage="embed", transient=True, cause=e
            ) from e

    def test_connection(self) -> bool:
        try:
            r = httpx.get(f"{self._client.base_url}/api/tags", timeout=2.0)
            r.raise_for_status()
            return True
        except Exception:
            return False

    def supports_batch(self) -> bool:
        return False


_: LLMBackend = OllamaBackend.__new__(OllamaBackend)  # type: ignore[arg-type]
