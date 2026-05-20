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
import time

from google import genai
from google.genai import types as genai_types

from ..base import (
    BackendCapabilities,
    BackendError,
    BackendInfo,
    ChatMessage,
    LLMBackend,
)
from ...batch.types import BatchChatRequest, GeminiBatchStatus

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

    def supports_batch(self) -> bool:
        return True  # M11.1 Phase 2 — Gemini Batch API 지원

    def batch_chat(
        self,
        *,
        modality: str,
        requests: list[BatchChatRequest],
    ) -> str:
        """배치 chat 작업 제출. Gemini job name 'batches/xxx' 반환.

        modality: 'chat_image' (model_image 사용) 또는 'chat_audio' (model_audio 사용).
        text_embed 는 batch_embed() 사용.
        """
        if modality == "chat_image":
            model = self.model_image
        elif modality == "chat_audio":
            model = self.model_audio
        else:
            raise ValueError(f"batch_chat invalid modality: {modality!r}")

        inlined = []
        for r in requests:
            item: dict = {"contents": self._to_contents(r.messages)}
            if r.force_json:
                item["config"] = {"response_mime_type": "application/json"}
            inlined.append(item)

        try:
            job = self._client.batches.create(
                model=model,
                src=inlined,
                config={"display_name": f"assetcache-{modality}-{int(time.time())}"},
            )
        except Exception as e:
            raise BackendError(
                backend="gemini",
                stage=f"batch_{modality}",
                transient=_classify(e),
                cause=e,
            ) from e
        return job.name

    def batch_embed(self, *, texts: list[str]) -> str:
        """배치 임베딩 작업 제출. Gemini job name 'batches/xxx' 반환.

        `client.batches.create_embeddings` 사용 — `chat` batch 와 다른 SDK 엔드포인트.
        각 text → `inlined_requests` 의 한 항목 ({"content": {"parts": [{"text": t}], "role": "user"}}).
        """
        if not texts:
            raise ValueError("batch_embed requires non-empty texts")
        inlined = [
            {"content": {"parts": [{"text": t}], "role": "user"}}
            for t in texts
        ]
        try:
            job = self._client.batches.create_embeddings(
                model=self.model_embed,
                src={"inlined_requests": inlined},
                config={"display_name": f"assetcache-text_embed-{int(time.time())}"},
            )
        except Exception as e:
            raise BackendError(
                backend="gemini",
                stage="batch_embed",
                transient=_classify(e),
                cause=e,
            ) from e
        return job.name

    def batch_get(self, backend_job_id: str) -> GeminiBatchStatus:
        """배치 작업 상태 폴링. 정규화된 GeminiBatchStatus 반환.

        SDK 의 job.state 는 JOB_STATE_PENDING / RUNNING / SUCCEEDED / FAILED / CANCELLED / EXPIRED.
        job.dest 는 SUCCEEDED 일 때만 의미 — inlined_responses 또는 file_name.
        """
        try:
            job = self._client.batches.get(name=backend_job_id)
        except Exception as e:
            raise BackendError(
                backend="gemini",
                stage="batch_get",
                transient=_classify(e),
                cause=e,
            ) from e
        dest = getattr(job, "dest", None)
        inlined = getattr(dest, "inlined_responses", None) if dest is not None else None
        file_name = getattr(dest, "file_name", None) if dest is not None else None
        error_val = getattr(job, "error", None)
        error_str = str(error_val) if error_val else None
        return GeminiBatchStatus(
            state=job.state.name,
            inlined_responses=inlined,
            file_name=file_name,
            error=error_str,
        )

    def batch_cancel(self, backend_job_id: str) -> None:
        """Best-effort cancel — 실패해도 raise 안 함 (idempotent semantics).

        BatchManager.cancel 가 호출 — 만료 / 이미 완료 / 네트워크 오류 등 모두 무시.
        """
        try:
            self._client.batches.cancel(name=backend_job_id)
        except Exception:
            log.exception("batch_cancel failed (best-effort, swallowed)")

    def batch_download_file(self, file_name: str) -> bytes:
        """File destination 의 결과 다운로드 (v0.2.1 에서는 미사용, v0.2.x 후속)."""
        return self._client.files.download(file=file_name)


_: LLMBackend = GeminiBackend.__new__(GeminiBackend)  # type: ignore[arg-type]
