"""Embedding encoder backed by :class:`BackendChain` (M11) or duck-typed embed source.

M11 migration: 기존 `_EmbedCapable` Protocol (단순 `.embed(text)` 인스턴스) 와
새 `BackendChain[modality=text_embed]` 둘 다 받는다.

- BackendChain 은 `embed()` 가 `(vec, backend_name)` 튜플 반환 → 풀어서 vec 만 사용.
- duck-typed (구 `OllamaClient` / 테스트 fake) 는 `embed()` 가 `list[float]` 반환 → 그대로.

encode_text 의 외부 동작은 동일 — `(blob, dim)` 튜플 반환 + first-use dim lock.

다음 마일스톤에서 BackendChain 채택을 강제하고 duck-typed path 제거 예정.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import numpy as np

log = logging.getLogger(__name__)


class _EmbedCapable(Protocol):
    """legacy — 단순 `.embed(text, *, model)` 호출 가능한 객체."""

    def embed(self, text: str, *, model: str | None = None) -> list[float]: ...


def _unwrap_embed_result(result: Any) -> list[float]:
    """BackendChain.embed → (vec, name) / legacy → list[float] 양쪽 흡수."""
    if isinstance(result, tuple) and len(result) == 2:
        vec, _name = result
        return list(vec)
    return list(result)


class EmbeddingEncoder:
    def __init__(
        self,
        client: Any,  # BackendChain | _EmbedCapable
        *,
        model: str = "nomic-embed-text",
    ) -> None:
        self.client = client
        self.model = model
        self._dim: int | None = None

    def encode_text(self, text: str) -> tuple[bytes, int]:
        """Return ``(blob, dim)`` for ``text``.

        first-use dim lock — 후속 호출이 다른 dim 반환 시 warn (검색은 cosine 이라
        균일 dim 필수, 다른 backend 로 교체 시 재인덱싱 권유).
        """
        result = self.client.embed(text, model=self.model)
        vec = _unwrap_embed_result(result)
        arr = np.asarray(vec, dtype=np.float32)
        if self._dim is None:
            self._dim = int(arr.size)
        elif arr.size != self._dim:
            log.warning(
                "embedding dim changed: %d → %d (model %r)",
                self._dim, arr.size, self.model,
            )
        return arr.tobytes(), int(arr.size)

    def decode_vector(self, blob: bytes, dim: int) -> np.ndarray:
        """Round-trip ``encode_text`` 의 blob 을 numpy 로 풀기.

        M3 HybridSearcher 가 검색 쿼리 임베딩을 ``self.embedder.decode_vector``
        로 호출한다 — fake/real 인터페이스 갭을 막기 위해 같은 시그니처를
        클래스 메서드로 노출. 모듈 함수 ``decode_vector`` 와 동일 동작.
        """
        return decode_vector(blob, dim)


def decode_vector(blob: bytes, dim: int) -> np.ndarray:
    arr = np.frombuffer(blob, dtype=np.float32)
    if arr.size != dim:
        raise ValueError(
            f"blob size {arr.size} does not match expected dim {dim}"
        )
    return arr
