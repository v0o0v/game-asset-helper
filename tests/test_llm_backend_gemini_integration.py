"""GeminiBackend integration — 실 API key 필요.

기본 `pytest -q` 에서는 `llm_integration` marker deselect 로 제외.
사용자 옵트인:

    $env:GEMINI_API_KEY = "AIza..."
    pytest -m llm_integration tests/test_llm_backend_gemini_integration.py
"""

from __future__ import annotations

import os

import pytest

from assetcache.core.llm.backends.gemini import GeminiBackend
from assetcache.core.llm.base import ChatMessage


pytestmark = pytest.mark.llm_integration


@pytest.fixture
def gemini():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY env not set")
    return GeminiBackend(
        api_key=api_key,
        model_image="gemini-2.5-flash",
        model_audio="gemini-2.5-flash",
        model_embed="gemini-embedding-001",
        timeout=60.0,
    )


def test_gemini_text_chat(gemini):
    out = gemini.chat(
        [ChatMessage("user", 'Reply with exact JSON: {"ok": true}')],
        force_json=True,
    )
    assert out.get("ok") is True


def test_gemini_test_connection(gemini):
    assert gemini.test_connection() is True


def test_gemini_embed_dim_768(gemini):
    vec = gemini.embed("hello world")
    assert isinstance(vec, list)
    assert len(vec) == 768
    assert all(isinstance(x, float) for x in vec)
