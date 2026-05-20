"""OpenRouterBackend — OpenAIBackend specialization (image only).

Phase 4 Task 4.1 — OpenRouter API 는 OpenAI 호환 endpoint
(`https://openrouter.ai/api/v1`) — `OpenAIBackend` 의 base_url
specialization 으로 구현. info 만 image-only 로 override + embed 안전망.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import openai
import pytest

from assetcache.core.llm.backends.openrouter import OpenRouterBackend
from assetcache.core.llm.backends.openai_backend import OpenAIBackend
from assetcache.core.llm.base import BackendError, ChatMessage


def _make_chat_response(text: str) -> MagicMock:
    r = MagicMock()
    choice = MagicMock()
    choice.message.content = text
    r.choices = [choice]
    return r


def test_openrouter_capabilities():
    """image only — audio/embed=False, embed_dim=None."""
    cap = OpenRouterBackend.info.capabilities
    assert cap.supports_chat_image is True
    assert cap.supports_chat_audio is False
    assert cap.supports_text_embed is False
    assert cap.embed_dim is None


def test_openrouter_info_name():
    """name='openrouter' — subclass info override 확인."""
    assert OpenRouterBackend.info.name == "openrouter"


def test_openrouter_is_subclass_of_openai_backend():
    """OpenAIBackend 의 chat/embed 메서드 상속 — Phase 3 코드 재사용."""
    assert issubclass(OpenRouterBackend, OpenAIBackend)


def test_openrouter_init_uses_openrouter_base_url(monkeypatch):
    """OpenAI 클라이언트 init 에 base_url='https://openrouter.ai/api/v1' 전달."""
    captured = {}

    def fake_openai(**kw):
        captured.update(kw)
        return MagicMock()

    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI", fake_openai
    )
    OpenRouterBackend(
        api_key="sk-or-test",
        model_image="google/gemma-4-27b-it:free",
        timeout=60.0,
    )
    assert captured["api_key"] == "sk-or-test"
    assert captured["base_url"] == "https://openrouter.ai/api/v1"


def test_openrouter_init_empty_api_key_is_hard():
    with pytest.raises(BackendError) as exc:
        OpenRouterBackend(api_key="", model_image="m", timeout=60.0)
    assert exc.value.transient is False
    assert exc.value.stage == "init"


def test_openrouter_chat_text_only(monkeypatch):
    """OpenAIBackend.chat 을 상속 — text 응답 dict 파싱."""
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _make_chat_response(
        '{"category": "icon"}'
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: fake_client,
    )
    b = OpenRouterBackend(
        api_key="sk-or-x",
        model_image="google/gemma-4-27b-it:free",
        timeout=60.0,
    )
    out = b.chat([ChatMessage("user", "describe")])
    assert out == {"category": "icon"}


def test_openrouter_embed_raises_hard():
    """capability=False 안전망 — embed 직접 호출 시 hard BackendError."""
    b = OpenRouterBackend.__new__(OpenRouterBackend)
    with pytest.raises(BackendError) as exc:
        b.embed("text")
    assert exc.value.transient is False
    assert exc.value.stage == "embed"
    assert exc.value.backend == "openrouter"


def test_openrouter_rate_limit_is_transient(monkeypatch):
    """429 → transient — chain 이 다음 backend 로 fallback 가능."""
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_client.chat.completions.create.side_effect = openai.RateLimitError(
        message="429", response=fake_resp, body=None
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: fake_client,
    )
    b = OpenRouterBackend(api_key="sk-or-x", model_image="m", timeout=60.0)
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is True
    assert exc.value.backend == "openrouter"  # subclass name


def test_openrouter_auth_error_is_hard(monkeypatch):
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_client.chat.completions.create.side_effect = openai.AuthenticationError(
        message="invalid", response=fake_resp, body=None
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: fake_client,
    )
    b = OpenRouterBackend(api_key="sk-or-x", model_image="m", timeout=60.0)
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is False
    assert exc.value.backend == "openrouter"
