"""OllamaBackend — 기존 OllamaClient wrap. 호출 위임 + 에러 변환 검증."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from assetcache.core.llm.backends.ollama import OllamaBackend
from assetcache.core.llm.base import BackendError, ChatMessage, LLMBackend
from assetcache.core.ollama_client import OllamaError


def _client():
    c = MagicMock()
    c.base_url = "http://127.0.0.1:11434"
    return c


def test_ollama_backend_is_protocol():
    b = OllamaBackend(client=_client())
    assert isinstance(b, LLMBackend)


def test_ollama_backend_info_capabilities():
    b = OllamaBackend(client=_client())
    assert b.info.name == "ollama"
    assert b.info.display_name == "Ollama (local)"
    cap = b.info.capabilities
    assert cap.supports_chat_image
    assert cap.supports_chat_audio
    assert cap.supports_text_embed


def test_ollama_backend_chat_delegates():
    c = _client()
    c.chat.return_value = {"ok": True}
    b = OllamaBackend(client=c)
    out = b.chat([ChatMessage("user", "hi")], force_json=True, num_ctx=8000)
    assert out == {"ok": True}
    c.chat.assert_called_once()


def test_ollama_backend_chat_wraps_ollama_error_as_transient():
    c = _client()
    c.chat.side_effect = OllamaError(stage="chat", path="native")
    b = OllamaBackend(client=c)
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.backend == "ollama"
    assert exc.value.transient is True
    assert isinstance(exc.value.cause, OllamaError)


def test_ollama_backend_embed_delegates():
    c = _client()
    c.embed.return_value = [0.1, 0.2]
    b = OllamaBackend(client=c)
    assert b.embed("text") == [0.1, 0.2]


def test_ollama_backend_embed_wraps_ollama_error_as_transient():
    c = _client()
    c.embed.side_effect = OllamaError(stage="embed", path="native")
    b = OllamaBackend(client=c)
    with pytest.raises(BackendError) as exc:
        b.embed("text")
    assert exc.value.backend == "ollama"
    assert exc.value.stage == "embed"
    assert exc.value.transient is True


def test_ollama_backend_test_connection_success():
    c = _client()
    b = OllamaBackend(client=c)
    fake_response = MagicMock()
    fake_response.raise_for_status = MagicMock(return_value=None)
    with patch(
        "assetcache.core.llm.backends.ollama.httpx.get",
        return_value=fake_response,
    ) as mock_get:
        assert b.test_connection() is True
        mock_get.assert_called_once_with(
            "http://127.0.0.1:11434/api/tags", timeout=2.0
        )


def test_ollama_backend_test_connection_failure():
    c = _client()
    b = OllamaBackend(client=c)
    with patch(
        "assetcache.core.llm.backends.ollama.httpx.get",
        side_effect=OSError("connect refused"),
    ):
        assert b.test_connection() is False


def test_ollama_backend_supports_chatmessage_from_llm_base():
    """LLMBackend.chat 의 messages 인자는 llm.base.ChatMessage (반드시)."""
    from assetcache.core.llm.base import ChatMessage as BaseChatMessage

    c = _client()
    c.chat.return_value = {"ok": True}
    b = OllamaBackend(client=c)
    # base.ChatMessage 인스턴스가 전달돼야 (필드 호환 — duck-typed)
    b.chat([BaseChatMessage("user", "hi")])
    c.chat.assert_called_once()
