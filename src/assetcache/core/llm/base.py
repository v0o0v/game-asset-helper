"""LLMBackend Protocol + 보조 타입 (M11 §3).

ChatMessage 는 기존 ollama_client.ChatMessage 와 동일 구조 — Phase 0 에서
이쪽으로 canonical 이전. 두 모듈 모두 같은 dataclass 를 노출하지만,
새 코드는 이 모듈에서 import 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class ChatMessage:
    role: str
    content: str
    images_b64: list[str] = field(default_factory=list)
    audio_b64: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class BackendCapabilities:
    supports_chat_image: bool
    supports_chat_audio: bool
    supports_text_embed: bool
    embed_dim: int | None


@dataclass(frozen=True)
class BackendInfo:
    name: str
    display_name: str
    homepage: str
    capabilities: BackendCapabilities
    # M11 후속 — API key 발급 (또는 ollama 의 경우 설치) direct link.
    # /settings 페이지의 backend 카드 안의 "Get key →" 한 줄 link 와
    # `<details>` block 본문에서 활용.
    setup_url: str | None = None


class BackendError(RuntimeError):
    """모든 backend wrapper 가 던지는 통일 에러.

    transient=True → BackendChain 이 다음 backend 로 fallback.
    transient=False → chain 즉시 raise + UI 배너 (auth / quota / 모델 X).
    """

    def __init__(
        self,
        *,
        backend: str,
        stage: str,
        transient: bool,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            f"BackendError(backend={backend}, stage={stage}, transient={transient})"
        )
        self.backend = backend
        self.stage = stage
        self.transient = transient
        self.cause = cause


@runtime_checkable
class LLMBackend(Protocol):
    info: BackendInfo

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        force_json: bool = True,
        num_ctx: int = 8000,
    ) -> dict: ...

    def embed(self, text: str, *, model: str | None = None) -> list[float]: ...

    def test_connection(self) -> bool: ...
