"""OpenAIBackend integration — 실 OpenAI API key 필요.

기본 `pytest -q` 에서는 `llm_integration` marker deselect 로 제외.
사용자 옵트인:

    $env:OPENAI_API_KEY = "sk-..."
    pytest -m llm_integration tests/test_llm_backend_openai_integration.py
"""

from __future__ import annotations

import os

import pytest

from assetcache.core.llm.backends.openai_backend import OpenAIBackend
from assetcache.core.llm.base import ChatMessage


pytestmark = pytest.mark.llm_integration


@pytest.fixture
def openai_b():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY env not set")
    return OpenAIBackend(
        api_key=api_key,
        model_image="gpt-4o-mini",
        model_audio="gpt-4o-audio-preview",
        model_embed="text-embedding-3-small",
        timeout=60.0,
    )


def test_openai_text_chat(openai_b):
    out = openai_b.chat(
        [ChatMessage("user", 'Reply with exact JSON: {"ok": true}')],
        force_json=True,
    )
    assert out.get("ok") is True


def test_openai_test_connection(openai_b):
    assert openai_b.test_connection() is True


def test_openai_embed_dim_1536(openai_b):
    vec = openai_b.embed("hello world")
    assert isinstance(vec, list)
    assert len(vec) == 1536
    assert all(isinstance(x, float) for x in vec)
