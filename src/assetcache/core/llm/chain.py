"""BackendChain — modality 별 fallback 로직.

semantics (spec §4):
- 1순위 success → 1순위 반환 + name.
- 1순위 transient 에러 → 다음 backend.
- 1순위 hard 에러 → 즉시 raise (다음 backend 시도 안 함).
- modality 비대응 backend (Claude on audio) → 자동 skip.
- text_embed modality 는 fallback 안 함 — 1순위만 사용 (dim 일관성).
- 모두 실패 / 빈 chain / 모두 ineligible → BackendError(backend="<chain>").
"""

from __future__ import annotations

import logging
from typing import Literal

from .base import BackendError, ChatMessage, LLMBackend

log = logging.getLogger(__name__)

Modality = Literal["chat_image", "chat_audio", "text_embed"]


class BackendChain:
    def __init__(self, backends: list[LLMBackend], *, modality: Modality) -> None:
        self.backends = list(backends)
        self.modality = modality

    def _eligible(self) -> list[LLMBackend]:
        """capabilities 가 modality 를 지원하는 backend 만."""
        result: list[LLMBackend] = []
        for b in self.backends:
            cap = b.info.capabilities
            if self.modality == "chat_image" and cap.supports_chat_image:
                result.append(b)
            elif self.modality == "chat_audio" and cap.supports_chat_audio:
                result.append(b)
            elif self.modality == "text_embed" and cap.supports_text_embed:
                result.append(b)
        return result

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        force_json: bool = True,
        num_ctx: int = 8000,
    ) -> tuple[dict, str]:
        """Return ``(response_dict, backend_name_used)``."""
        eligible = self._eligible()
        if not eligible:
            raise BackendError(
                backend="<chain>", stage=self.modality, transient=False
            )
        last_transient: BackendError | None = None
        for backend in eligible:
            try:
                response = backend.chat(
                    messages, force_json=force_json, num_ctx=num_ctx
                )
                return response, backend.info.name
            except BackendError as e:
                if not e.transient:
                    raise
                log.info(
                    "backend %s transient fail (%s); trying next",
                    backend.info.name, e.stage,
                )
                last_transient = e
                continue
        raise BackendError(
            backend="<chain>",
            stage=self.modality,
            transient=False,
            cause=last_transient,
        )

    def embed(
        self, text: str, *, model: str | None = None
    ) -> tuple[list[float], str]:
        """text_embed chain — fallback 안 함, 1순위만 사용."""
        if self.modality != "text_embed":
            raise BackendError(
                backend="<chain>",
                stage="embed",
                transient=False,
                cause=ValueError(
                    f"embed() called on {self.modality} chain"
                ),
            )
        eligible = self._eligible()
        if not eligible:
            raise BackendError(
                backend="<chain>", stage="embed", transient=False
            )
        primary = eligible[0]
        return primary.embed(text, model=model), primary.info.name
