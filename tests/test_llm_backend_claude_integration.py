"""ClaudeBackend integration — 실 Anthropic API key 필요.

기본 `pytest -q` 에서는 `llm_integration` marker deselect 로 제외.
사용자 옵트인:

    $env:ANTHROPIC_API_KEY = "sk-ant-..."
    pytest -m llm_integration tests/test_llm_backend_claude_integration.py
"""

from __future__ import annotations

import os

import pytest

from assetcache.core.llm.backends.claude import ClaudeBackend
from assetcache.core.llm.base import BackendError, ChatMessage


pytestmark = pytest.mark.llm_integration


@pytest.fixture
def claude():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY env not set")
    return ClaudeBackend(
        api_key=api_key,
        model_image="claude-haiku-4-5-20251001",
        timeout=60.0,
    )


def test_claude_text_chat(claude):
    out = claude.chat(
        [ChatMessage("user", 'Reply with exact JSON: {"ok": true}')],
        force_json=True,
    )
    assert out.get("ok") is True


def test_claude_test_connection(claude):
    assert claude.test_connection() is True


def test_claude_embed_raises_even_with_real_key(claude):
    """실 API key 가 있어도 embed 는 항상 hard BackendError (지원 안 함)."""
    with pytest.raises(BackendError) as exc:
        claude.embed("hello")
    assert exc.value.transient is False
    assert exc.value.stage == "embed"
