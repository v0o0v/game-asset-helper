"""HuggingFaceBackend — huggingface_hub InferenceClient wrap (M11 Phase 4).

modality:
- chat_image: 모델별 — Qwen2.5-VL, Llama-3.2-Vision 등. messages content
  shape 은 OpenAI 호환 (text + image_url data URI)
- chat_audio: 모델별 (Qwen2-Audio 등) — input_audio 시도, 모델 미지원 시
  실패는 transient (chain fallback)
- text_embed: ``feature_extraction`` 호출. np.ndarray 반환 → list[float].
  embed_dim 은 모델별로 가변 — None.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np
from huggingface_hub import InferenceClient
from huggingface_hub import errors as hf_errors

from ..base import (
    BackendCapabilities,
    BackendError,
    BackendInfo,
    ChatMessage,
    LLMBackend,
)

log = logging.getLogger(__name__)


_HARD = (
    hf_errors.BadRequestError,
    hf_errors.HFValidationError,
    hf_errors.GatedRepoError,
    hf_errors.RepositoryNotFoundError,
)

_TRANSIENT = (
    hf_errors.OverloadedError,
    hf_errors.InferenceTimeoutError,
    hf_errors.InferenceEndpointTimeoutError,
)


def _classify(e: Exception) -> bool:
    """True → transient."""
    if isinstance(e, _HARD):
        return False
    if isinstance(e, _TRANSIENT):
        return True
    # HfHubHTTPError 의 status_code 검사 — 4xx 는 대부분 hard, 5xx/429 는 transient
    if isinstance(e, hf_errors.HfHubHTTPError):
        code = getattr(e.response, "status_code", None) if hasattr(e, "response") else None
        if isinstance(code, int):
            if code in (400, 401, 403, 404):
                return False
        return True
    return True  # 알 수 없는 예외 → transient


class HuggingFaceBackend:
    info = BackendInfo(
        name="huggingface",
        display_name="HuggingFace Inference",
        homepage="https://huggingface.co/docs/inference-providers/",
        capabilities=BackendCapabilities(
            supports_chat_image=True,
            supports_chat_audio=True,
            supports_text_embed=True,
            embed_dim=None,  # 모델별 가변
        ),
        setup_url="https://huggingface.co/settings/tokens",
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
                backend="huggingface",
                stage="init",
                transient=False,
                cause=ValueError("api_key empty"),
            )
        self._client = InferenceClient(token=api_key, timeout=timeout)
        self.model_image = model_image
        self.model_audio = model_audio
        self.model_embed = model_embed
        self.timeout = timeout

    def _select_model(self, messages: list[ChatMessage]) -> str:
        has_audio = any(m.audio_b64 for m in messages)
        return self.model_audio if has_audio else self.model_image

    def _to_messages(self, messages: list[ChatMessage]) -> list[dict[str, Any]]:
        """OpenAI 호환 content shape — HF chat_completion 이 동일 시그니처."""
        out: list[dict[str, Any]] = []
        for m in messages:
            content: list[dict[str, Any]] = []
            if m.content:
                content.append({"type": "text", "text": m.content})
            for b64 in m.images_b64:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
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
            "max_tokens": 2000,
        }
        if force_json:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            r = self._client.chat_completion(**kwargs)
        except Exception as e:
            transient = _classify(e)
            raise BackendError(
                backend="huggingface",
                stage="chat",
                transient=transient,
                cause=e,
            ) from e

        text = ""
        try:
            text = r.choices[0].message.content or ""
        except (AttributeError, IndexError) as e:
            raise BackendError(
                backend="huggingface",
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
                backend="huggingface",
                stage="chat",
                transient=True,
                cause=ValueError(f"non-json response: {text[:80]}"),
            ) from e

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        try:
            arr = self._client.feature_extraction(
                text, model=model or self.model_embed
            )
        except Exception as e:
            raise BackendError(
                backend="huggingface",
                stage="embed",
                transient=_classify(e),
                cause=e,
            ) from e

        # np.ndarray → list[float]. 2D (1, dim) 또는 (n_tokens, dim) shape 일 때
        # mean pooling 또는 첫 행 추출. 단순화: 1D 로 평탄화 또는 (1,dim) 첫 행
        if isinstance(arr, np.ndarray):
            if arr.ndim == 1:
                return arr.astype(float).tolist()
            if arr.ndim == 2:
                # (1, dim) → 첫 행, (n_tokens, dim) → mean pooling
                if arr.shape[0] == 1:
                    return arr[0].astype(float).tolist()
                return arr.mean(axis=0).astype(float).tolist()
            return arr.flatten().astype(float).tolist()
        # list[float] 직접 반환 가능성도 대비
        return [float(x) for x in arr]

    def test_connection(self) -> bool:
        try:
            self._client.chat_completion(
                model=self.model_image,
                messages=[{"role": "user", "content": "x"}],
                max_tokens=1,
            )
            return True
        except Exception:
            return False

    def supports_batch(self) -> bool:
        return False


_: LLMBackend = HuggingFaceBackend.__new__(HuggingFaceBackend)  # type: ignore[arg-type]
