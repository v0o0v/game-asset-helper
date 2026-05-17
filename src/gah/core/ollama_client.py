"""Thin HTTP wrapper around an Ollama-compatible backend.

Per memory ``project_m2_analysis_backend.md``:

* First tries the OpenAI-compatible ``POST /v1/chat/completions``
  endpoint (works for LM Studio / llama-server / Ollama ≥0.10).
* Falls back to Ollama's native ``POST /api/chat`` on 4xx/5xx /
  connect errors.  The native path packs both images **and** audio
  into a single ``images: [base64, ...]`` array — verified
  empirically against ``gemma4:e4b`` (memory
  ``project_ollama_multimodal_api_shape.md``).

``base_url`` is the only knob a user needs to flip when swapping
backends — everything else (model name, timeout, retries) flows in
from :class:`gah.config.Config`.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

log = logging.getLogger(__name__)


# ── public types ────────────────────────────────────────────────────


@dataclass
class ChatMessage:
    role: str                                   # 'system' | 'user'
    content: str
    images_b64: list[str] = field(default_factory=list)
    # (data, mime) — e.g. ("base64...", "audio/wav")
    audio_b64: list[tuple[str, str]] = field(default_factory=list)


class OllamaError(RuntimeError):
    """Raised when both transports fail or all retries are exhausted."""

    def __init__(self, *, stage: str, path: str | None,
                 cause: Exception | None = None) -> None:
        super().__init__(f"OllamaError(stage={stage}, path={path})")
        self.stage = stage
        self.path = path
        self.cause = cause


# ── client ──────────────────────────────────────────────────────────


class OllamaClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_retries: int = 3,
        parallel: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        # 동시 호출 cap — 같은 모델 슬롯을 N 개가 두드리지 못하게.
        # chat()/embed() 가 같은 세마포어를 공유한다(둘 다 같은 Ollama 프로세스 자원).
        self.parallel = max(1, int(parallel))
        self._sem = threading.Semaphore(self.parallel)

    # -- chat ---------------------------------------------------------

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        force_json: bool = True,
        num_ctx: int = 8000,
    ) -> dict:
        """Run a chat completion; return the parsed JSON content dict.

        Two failure modes have very different costs and so are handled
        differently:

        * **Transport error / non-2xx**: try OpenAI-compatible first;
          if it dies, fall back to native within the *same* attempt.
          If both transports refuse the request we raise immediately
          — repeated calls won't help, and our callers (the analyzers)
          have their own fallback paths (e.g. spectrogram).  ``max_retries``
          does *not* apply here.
        * **200 with non-JSON content**: the backend is responsive but
          confused.  Retry up to ``max_retries`` times on the same
          endpoint, with exponential backoff.

        모든 백엔드 호출은 ``self._sem`` 안에서 일어난다 — retry 의 sleep 도
        세마포어 슬롯을 점유한 채로 — 다른 워커가 같은 모델에 동시에 cold-
        start 를 걸지 않게.
        """
        with self._sem:
            # ── 1. Transport: 한 번만 시도. OpenAI → native 폴백. ──────
            last_path: str | None = None
            try:
                raw = self._call_openai(messages, num_ctx=num_ctx,
                                        force_json=force_json)
                last_path = "openai"
            except httpx.HTTPError as e:
                log.debug("OpenAI path failed (%s); trying native", e)
                try:
                    raw = self._call_native(messages, num_ctx=num_ctx,
                                            force_json=force_json)
                    last_path = "native"
                except httpx.HTTPError as e2:
                    raise OllamaError(
                        stage="chat", path="native", cause=e2,
                    ) from e2

            # ── 2. Parse: force_json invalid 면 같은 backend 에서 retry. ─
            last_exc: Exception | None = None
            for attempt in range(self.max_retries + 1):
                parsed = self._parse_content(raw, source=last_path or "openai")
                if not force_json or parsed is not None:
                    return parsed if parsed is not None else raw
                last_exc = ValueError(
                    f"{last_path} response was not valid JSON"
                )
                if attempt >= self.max_retries:
                    break
                time.sleep(min(2 ** attempt * 0.1, 2.0))
                caller = (self._call_openai if last_path == "openai"
                           else self._call_native)
                try:
                    raw = caller(messages, num_ctx=num_ctx,
                                  force_json=force_json)
                except httpx.HTTPError as e:
                    raise OllamaError(
                        stage="chat", path=last_path, cause=e,
                    ) from e

            raise OllamaError(stage="chat", path=last_path, cause=last_exc)

    # -- embed --------------------------------------------------------

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        model_name = model or "nomic-embed-text"
        # chat 과 같은 세마포어를 공유 — 같은 백엔드 자원 점유.
        with self._sem:
            # OpenAI-compatible first
            try:
                r = httpx.post(
                    f"{self.base_url}/v1/embeddings",
                    json={"model": model_name, "input": text},
                    timeout=self.timeout_seconds,
                )
                if r.status_code == 200:
                    body = r.json()
                    # OpenAI shape: {"data": [{"embedding": [...]}]}
                    if "data" in body:
                        return list(body["data"][0]["embedding"])
                    # Some backends use top-level "embedding"
                    if "embedding" in body:
                        return list(body["embedding"])
            except httpx.HTTPError as e:
                log.debug("OpenAI embed path failed (%s); trying native", e)

            # Native fallback
            try:
                r = httpx.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": model_name, "prompt": text},
                    timeout=self.timeout_seconds,
                )
                r.raise_for_status()
                body = r.json()
                return list(body["embedding"])
            except httpx.HTTPError as e:
                raise OllamaError(stage="embed", path="native", cause=e) from e

    # -- internals ----------------------------------------------------

    def _call_openai(
        self, messages: list[ChatMessage], *, num_ctx: int, force_json: bool
    ) -> dict:
        payload_messages = [self._to_openai_message(m) for m in messages]
        body: dict[str, Any] = {
            "model": self.model,
            "messages": payload_messages,
            "stream": False,
        }
        if force_json:
            body["response_format"] = {"type": "json_object"}
        r = httpx.post(
            f"{self.base_url}/v1/chat/completions",
            json=body,
            timeout=self.timeout_seconds,
        )
        r.raise_for_status()
        return r.json()

    def _call_native(
        self, messages: list[ChatMessage], *, num_ctx: int, force_json: bool
    ) -> dict:
        payload_messages = [self._to_native_message(m) for m in messages]
        body: dict[str, Any] = {
            "model": self.model,
            "messages": payload_messages,
            "stream": False,
            "options": {"num_ctx": num_ctx},
        }
        if force_json:
            body["format"] = "json"
        r = httpx.post(
            f"{self.base_url}/api/chat",
            json=body,
            timeout=self.timeout_seconds,
        )
        r.raise_for_status()
        return r.json()

    @staticmethod
    def _to_openai_message(m: ChatMessage) -> dict:
        # 텍스트 + 이미지/오디오 멀티파트 콘텐츠
        if not m.images_b64 and not m.audio_b64:
            return {"role": m.role, "content": m.content}
        parts: list[dict] = [{"type": "text", "text": m.content}]
        for b64 in m.images_b64:
            parts.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        for data, mime in m.audio_b64:
            fmt = mime.split("/", 1)[-1] if "/" in mime else mime
            parts.append({
                "type": "input_audio",
                "input_audio": {"data": data, "format": fmt},
            })
        return {"role": m.role, "content": parts}

    @staticmethod
    def _to_native_message(m: ChatMessage) -> dict:
        # 메모리 실측: 이미지·오디오 모두 단일 images 배열
        combined: list[str] = []
        combined.extend(m.images_b64)
        combined.extend(data for data, _mime in m.audio_b64)
        msg: dict[str, Any] = {"role": m.role, "content": m.content}
        if combined:
            msg["images"] = combined
        return msg

    @staticmethod
    def _parse_content(raw: dict, *, source: str) -> dict | None:
        """Extract assistant content and parse JSON.  Return None on failure."""
        try:
            if source == "openai":
                content = raw["choices"][0]["message"]["content"]
            else:  # native
                content = raw["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None
        if isinstance(content, list):
            # OpenAI multipart — only consider text parts
            text_parts = [
                c.get("text", "") for c in content if c.get("type") == "text"
            ]
            content = " ".join(text_parts).strip()
        if not isinstance(content, str):
            return None
        try:
            return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return None


# ── base64 helpers ──────────────────────────────────────────────────


def encode_image(path: Path) -> str:
    """Read ``path`` and return its base64-encoded bytes (no data: prefix)."""
    raw = Path(path).read_bytes()
    return base64.b64encode(raw).decode("ascii")


def encode_audio_clip(samples, sample_rate: int) -> str:
    """Encode a 1-D float32 sample buffer as WAV and return base64.

    ``samples`` may be any object that ``numpy.asarray`` accepts.
    """
    import numpy as np
    import soundfile as sf

    arr = np.asarray(samples, dtype=np.float32)
    buf = io.BytesIO()
    sf.write(buf, arr, sample_rate, subtype="PCM_16", format="WAV")
    return base64.b64encode(buf.getvalue()).decode("ascii")
