"""EmbeddingEncoder tests using a fake OllamaClient."""

from __future__ import annotations

import numpy as np
import pytest

from gah.core.embedding import EmbeddingEncoder, decode_vector
from gah.core.ollama_client import OllamaError


class _FakeOllama:
    """Minimal stand-in for OllamaClient.embed."""

    def __init__(self, vector: list[float]) -> None:
        self.vector = vector
        self.calls: list[dict] = []

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        self.calls.append({"text": text, "model": model})
        return list(self.vector)


def test_encode_text_returns_bytes_and_dim() -> None:
    fake = _FakeOllama([0.1, 0.2, 0.3, 0.4])
    enc = EmbeddingEncoder(fake)  # type: ignore[arg-type]
    blob, dim = enc.encode_text("hello")
    assert dim == 4
    assert len(blob) == 4 * 4  # 4 floats × 4 bytes


def test_encode_text_uses_configured_model_name() -> None:
    fake = _FakeOllama([0.1])
    enc = EmbeddingEncoder(fake, model="my-embed-model")  # type: ignore[arg-type]
    enc.encode_text("hi")
    assert fake.calls[0]["model"] == "my-embed-model"


def test_decode_vector_roundtrips_through_blob() -> None:
    original = np.array([0.5, -0.25, 1.0, -1.0], dtype=np.float32)
    restored = decode_vector(original.tobytes(), dim=4)
    assert np.allclose(restored, original)


def test_first_call_determines_dim() -> None:
    """Once the encoder has seen one response, the dim is locked to that length."""
    fake = _FakeOllama([0.0] * 768)
    enc = EmbeddingEncoder(fake)  # type: ignore[arg-type]
    _, dim1 = enc.encode_text("first")
    _, dim2 = enc.encode_text("second")
    assert dim1 == dim2 == 768


def test_encode_text_propagates_ollama_error() -> None:
    class _ErrOllama:
        def embed(self, text, *, model=None):  # noqa: ANN001
            raise OllamaError(stage="embed", path="openai", cause=None)

    enc = EmbeddingEncoder(_ErrOllama())  # type: ignore[arg-type]
    with pytest.raises(OllamaError):
        enc.encode_text("oops")


def test_decode_vector_is_callable_as_instance_method() -> None:
    """M3 회귀 가드 — HybridSearcher 가 ``self.embedder.decode_vector`` 를
    인스턴스 메서드로 호출한다. fake 픽스처와 실 EmbeddingEncoder 의
    인터페이스가 일치해야 silent fail 이 안 난다.
    """
    fake = _FakeOllama([0.1, 0.2, 0.3, 0.4])
    enc = EmbeddingEncoder(fake)  # type: ignore[arg-type]
    blob, dim = enc.encode_text("hello")
    arr = enc.decode_vector(blob, dim)
    assert arr.tolist() == pytest.approx([0.1, 0.2, 0.3, 0.4])
