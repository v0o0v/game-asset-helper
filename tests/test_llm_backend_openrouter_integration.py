"""OpenRouterBackend integration — 실 OpenRouter API key 필요.

기본 `pytest -q` 에서는 `llm_integration` marker deselect.
사용자 옵트인:

    $env:OPENROUTER_API_KEY = "sk-or-..."
    pytest -m llm_integration tests/test_llm_backend_openrouter_integration.py
"""

from __future__ import annotations

import os

import pytest

from assetcache.core.llm.backends.openrouter import OpenRouterBackend
from assetcache.core.llm.base import BackendError, ChatMessage


pytestmark = pytest.mark.llm_integration


@pytest.fixture
def openrouter_b():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        pytest.skip("OPENROUTER_API_KEY env not set")
    return OpenRouterBackend(
        api_key=api_key,
        model_image="google/gemma-3-27b-it:free",
        timeout=60.0,
    )


def test_openrouter_text_chat(openrouter_b):
    out = openrouter_b.chat(
        [ChatMessage("user", 'Reply with exact JSON: {"ok": true}')],
        force_json=True,
    )
    assert out.get("ok") is True


def test_openrouter_embed_raises_even_with_real_key(openrouter_b):
    """실 API key 있어도 embed 는 항상 hard (capability 미지원)."""
    with pytest.raises(BackendError) as exc:
        openrouter_b.embed("hello")
    assert exc.value.transient is False
    assert exc.value.stage == "embed"
