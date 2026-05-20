"""OpenRouterBackend — ``OpenAIBackend`` specialization (M11 Phase 4).

OpenRouter API 는 OpenAI 호환 endpoint (``https://openrouter.ai/api/v1``).
``OpenAIBackend`` 의 ``base_url`` 인자를 그대로 활용 — 코드 재사용, info 만
image-only 로 override.

modality:
- chat_image: OpenRouter routing 통해 다양한 모델 (gemma, llama, qwen 등)
- chat_audio: 미지원 — capability=False
- text_embed: 미지원 — capability=False (OpenRouter 는 embedding endpoint
  제공 안 함; 일부 모델별로 다르나 통일성 위해 미지원으로 분류)
"""

from __future__ import annotations

from ..base import (
    BackendCapabilities,
    BackendError,
    BackendInfo,
    LLMBackend,
)
from .openai_backend import OpenAIBackend


_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterBackend(OpenAIBackend):
    info = BackendInfo(
        name="openrouter",
        display_name="OpenRouter (free routing)",
        homepage="https://openrouter.ai/",
        capabilities=BackendCapabilities(
            supports_chat_image=True,
            supports_chat_audio=False,
            supports_text_embed=False,
            embed_dim=None,
        ),
        setup_url="https://openrouter.ai/settings/keys",
    )

    def __init__(self, *, api_key: str, model_image: str, timeout: float) -> None:
        super().__init__(
            api_key=api_key,
            model_image=model_image,
            model_audio="",
            model_embed="",
            timeout=timeout,
            base_url=_OPENROUTER_BASE_URL,
        )

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        """capability=False 안전망 — 직접 호출 시 hard BackendError.

        chain.embed 진입은 ``_eligible`` 의 capability 체크로 이미 막혀 있어
        실제로 도달하지 않지만, 직접 호출 시나 contract 위반 보호.
        """
        raise BackendError(
            backend="openrouter",
            stage="embed",
            transient=False,
            cause=NotImplementedError(
                "OpenRouter has no unified embedding endpoint"
            ),
        )


_: LLMBackend = OpenRouterBackend.__new__(OpenRouterBackend)  # type: ignore[arg-type]
