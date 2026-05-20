"""OpenAIBackend — openai SDK mock 기반.

Phase 3 Task 3.1 — image/audio/embed 3 modality + base_url expose (Phase 4
OpenRouter specialization 용).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import openai
import pytest

from assetcache.core.llm.backends.openai_backend import OpenAIBackend
from assetcache.core.llm.base import BackendError, ChatMessage


def _make_chat_response(text: str) -> MagicMock:
    r = MagicMock()
    choice = MagicMock()
    choice.message.content = text
    r.choices = [choice]
    return r


def test_openai_capabilities():
    cap = OpenAIBackend.info.capabilities
    assert cap.supports_chat_image is True
    assert cap.supports_chat_audio is True
    assert cap.supports_text_embed is True
    assert cap.embed_dim == 1536


def test_openai_init_empty_api_key_is_hard():
    with pytest.raises(BackendError) as exc:
        OpenAIBackend(
            api_key="",
            model_image="m-i",
            model_audio="m-a",
            model_embed="m-e",
            timeout=60.0,
        )
    assert exc.value.transient is False
    assert exc.value.stage == "init"


def test_openai_init_passes_base_url(monkeypatch):
    """base_url 인자가 openai.OpenAI 에 그대로 전달 — Phase 4 OpenRouter 용."""
    captured = {}

    def fake_openai(**kw):
        captured.update(kw)
        return MagicMock()

    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI", fake_openai
    )
    OpenAIBackend(
        api_key="sk-test",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
        base_url="https://openrouter.ai/api/v1",
    )
    assert captured["api_key"] == "sk-test"
    assert captured["base_url"] == "https://openrouter.ai/api/v1"


def test_openai_chat_text_only(monkeypatch):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _make_chat_response(
        '{"category": "sprite"}'
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: fake_client,
    )
    b = OpenAIBackend(
        api_key="sk-x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    out = b.chat([ChatMessage("user", "hi")])
    assert out == {"category": "sprite"}

    call = fake_client.chat.completions.create.call_args
    assert call.kwargs.get("model") == "m-i"  # audio 없음 → image model
    assert call.kwargs.get("response_format") == {"type": "json_object"}


def test_openai_chat_with_image(monkeypatch):
    """images_b64 → content type=image_url, url=data:image/png;base64,…"""
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _make_chat_response(
        '{"category": "icon"}'
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: fake_client,
    )
    b = OpenAIBackend(
        api_key="sk-x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    out = b.chat([ChatMessage("user", "describe", images_b64=["aW1n"])])
    assert out == {"category": "icon"}

    call = fake_client.chat.completions.create.call_args
    msgs = call.kwargs.get("messages")
    contents = msgs[0]["content"]
    types = [c["type"] for c in contents]
    assert "text" in types
    assert "image_url" in types
    image_part = next(c for c in contents if c["type"] == "image_url")
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")
    assert image_part["image_url"]["url"].endswith("aW1n")


def test_openai_chat_with_audio_selects_audio_model(monkeypatch):
    """audio_b64 → content type=input_audio + model=model_audio."""
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _make_chat_response(
        '{"kind": "sfx"}'
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: fake_client,
    )
    b = OpenAIBackend(
        api_key="sk-x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    out = b.chat([ChatMessage("user", "describe", audio_b64=[("aXNvbg==", "audio/wav")])])
    assert out == {"kind": "sfx"}

    call = fake_client.chat.completions.create.call_args
    assert call.kwargs.get("model") == "m-a"
    msgs = call.kwargs.get("messages")
    contents = msgs[0]["content"]
    types = [c["type"] for c in contents]
    assert "input_audio" in types
    audio_part = next(c for c in contents if c["type"] == "input_audio")
    assert audio_part["input_audio"]["data"] == "aXNvbg=="
    assert audio_part["input_audio"]["format"] == "wav"


def test_openai_chat_force_json_false_omits_response_format(monkeypatch):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _make_chat_response(
        "free-form prose"
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: fake_client,
    )
    b = OpenAIBackend(
        api_key="sk-x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    out = b.chat([ChatMessage("user", "hi")], force_json=False)
    assert out == {"text": "free-form prose"}
    call = fake_client.chat.completions.create.call_args
    assert "response_format" not in call.kwargs or call.kwargs.get("response_format") is None


def test_openai_chat_non_json_response_is_transient(monkeypatch):
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _make_chat_response(
        "not json at all"
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: fake_client,
    )
    b = OpenAIBackend(
        api_key="sk-x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is True
    assert exc.value.stage == "chat"


def test_openai_auth_error_is_hard(monkeypatch):
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_client.chat.completions.create.side_effect = openai.AuthenticationError(
        message="invalid api key", response=fake_resp, body=None
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: fake_client,
    )
    b = OpenAIBackend(
        api_key="sk-x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is False


def test_openai_bad_request_is_hard(monkeypatch):
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_client.chat.completions.create.side_effect = openai.BadRequestError(
        message="invalid model", response=fake_resp, body=None
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: fake_client,
    )
    b = OpenAIBackend(
        api_key="sk-x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is False


def test_openai_rate_limit_is_transient(monkeypatch):
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_client.chat.completions.create.side_effect = openai.RateLimitError(
        message="429", response=fake_resp, body=None
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: fake_client,
    )
    b = OpenAIBackend(
        api_key="sk-x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is True


def test_openai_internal_error_is_transient(monkeypatch):
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_client.chat.completions.create.side_effect = openai.InternalServerError(
        message="500", response=fake_resp, body=None
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: fake_client,
    )
    b = OpenAIBackend(
        api_key="sk-x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is True


def test_openai_embed_returns_list_of_floats(monkeypatch):
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_data = MagicMock()
    fake_data.embedding = [0.1, 0.2, 0.3]
    fake_resp.data = [fake_data]
    fake_client.embeddings.create.return_value = fake_resp
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: fake_client,
    )
    b = OpenAIBackend(
        api_key="sk-x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    vec = b.embed("hello world")
    assert vec == [0.1, 0.2, 0.3]
    call = fake_client.embeddings.create.call_args
    assert call.kwargs.get("model") == "m-e"


def test_openai_embed_error_classified(monkeypatch):
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_client.embeddings.create.side_effect = openai.RateLimitError(
        message="429", response=fake_resp, body=None
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: fake_client,
    )
    b = OpenAIBackend(
        api_key="sk-x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    with pytest.raises(BackendError) as exc:
        b.embed("hello")
    assert exc.value.stage == "embed"
    assert exc.value.transient is True


def test_openai_test_connection_true(monkeypatch):
    fake_client = MagicMock()
    fake_client.models.list.return_value = iter([MagicMock()])
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: fake_client,
    )
    b = OpenAIBackend(
        api_key="sk-x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    assert b.test_connection() is True


def test_openai_test_connection_false_on_error(monkeypatch):
    fake_client = MagicMock()
    fake_client.models.list.side_effect = Exception("unreachable")
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: fake_client,
    )
    b = OpenAIBackend(
        api_key="sk-x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    assert b.test_connection() is False
