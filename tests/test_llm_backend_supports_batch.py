"""Phase 0 — LLMBackend Protocol 의 supports_batch() default False 검증.

Phase 2 에서 GeminiBackend 만 True 로 변경.
"""

from unittest.mock import MagicMock

import pytest


def test_ollama_supports_batch_default_false():
    from assetcache.core.llm.backends.ollama import OllamaBackend

    client = MagicMock()
    client.base_url = "http://127.0.0.1:11434"
    backend = OllamaBackend(client=client)
    assert backend.supports_batch() is False


def test_openai_supports_batch_default_false(monkeypatch):
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: MagicMock(),
    )
    from assetcache.core.llm.backends.openai_backend import OpenAIBackend

    b = OpenAIBackend(
        api_key="x",
        model_image="m",
        model_audio="m",
        model_embed="m",
        timeout=60.0,
    )
    assert b.supports_batch() is False


def test_gemini_supports_batch_true(monkeypatch):
    """Phase 2 — GeminiBackend supports_batch True 로 변경."""
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: MagicMock(),
    )
    from assetcache.core.llm.backends.gemini import GeminiBackend

    b = GeminiBackend(
        api_key="x",
        model_image="m",
        model_audio="m",
        model_embed="m",
        timeout=60.0,
    )
    assert b.supports_batch() is True
