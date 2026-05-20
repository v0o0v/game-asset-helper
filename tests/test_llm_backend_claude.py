"""ClaudeBackend — anthropic SDK mock 기반.

Phase 2 Task 2.1 — image 전용 (audio/embed 미지원). audio_b64 입력은 무시,
embed() 호출은 hard BackendError 로 차단. chain 의 modality skip 으로
audio 모드에선 자동 제외 (chain.test 에서 별도 검증).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import anthropic
import pytest

from assetcache.core.llm.backends.claude import ClaudeBackend
from assetcache.core.llm.base import BackendError, ChatMessage


def test_claude_capabilities():
    """info: chat_image=True, chat_audio=False, text_embed=False."""
    cap = ClaudeBackend.info.capabilities
    assert cap.supports_chat_image is True
    assert cap.supports_chat_audio is False
    assert cap.supports_text_embed is False
    assert cap.embed_dim is None


def test_claude_init_empty_api_key_is_hard():
    with pytest.raises(BackendError) as exc:
        ClaudeBackend(api_key="", model_image="m", timeout=60.0)
    assert exc.value.transient is False
    assert exc.value.stage == "init"


def test_claude_chat_text_only(monkeypatch):
    """force_json=True + text response → dict 파싱."""
    fake_client = MagicMock()
    fake_response = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = '{"category": "ui"}'
    fake_response.content = [block]
    fake_client.messages.create.return_value = fake_response
    monkeypatch.setattr(
        "assetcache.core.llm.backends.claude.Anthropic",
        lambda **kw: fake_client,
    )
    b = ClaudeBackend(
        api_key="x", model_image="claude-haiku-4-5-20251001", timeout=60.0
    )
    out = b.chat([ChatMessage("user", "hi")])
    assert out == {"category": "ui"}
    # system prompt 가 JSON strict 모드로 전달됐는지
    call = fake_client.messages.create.call_args
    assert "json" in call.kwargs.get("system", "").lower()
    assert call.kwargs.get("model") == "claude-haiku-4-5-20251001"


def test_claude_chat_with_image(monkeypatch):
    """images_b64 가 source.type=base64 / media_type=image/png 으로 들어감."""
    fake_client = MagicMock()
    fake_response = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = '{"category": "icon"}'
    fake_response.content = [block]
    fake_client.messages.create.return_value = fake_response
    monkeypatch.setattr(
        "assetcache.core.llm.backends.claude.Anthropic",
        lambda **kw: fake_client,
    )

    b = ClaudeBackend(api_key="x", model_image="m", timeout=60.0)
    out = b.chat([ChatMessage("user", "describe", images_b64=["aW1n"])])
    assert out == {"category": "icon"}

    call = fake_client.messages.create.call_args
    msgs = call.kwargs.get("messages")
    assert msgs is not None
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    contents = msgs[0]["content"]
    # text + image part
    types = [c["type"] for c in contents]
    assert "text" in types
    assert "image" in types
    image_part = next(c for c in contents if c["type"] == "image")
    assert image_part["source"]["type"] == "base64"
    assert image_part["source"]["media_type"] == "image/png"
    assert image_part["source"]["data"] == "aW1n"


def test_claude_audio_b64_ignored_in_messages(monkeypatch):
    """capability 가 audio=False — audio_b64 입력은 _to_messages 에서 drop."""
    fake_client = MagicMock()
    fake_response = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = '{"ok": true}'
    fake_response.content = [block]
    fake_client.messages.create.return_value = fake_response
    monkeypatch.setattr(
        "assetcache.core.llm.backends.claude.Anthropic",
        lambda **kw: fake_client,
    )
    b = ClaudeBackend(api_key="x", model_image="m", timeout=60.0)
    b.chat([ChatMessage("user", "hi", audio_b64=[("aXNvbg==", "audio/wav")])])
    call = fake_client.messages.create.call_args
    msgs = call.kwargs.get("messages")
    contents = msgs[0]["content"]
    # audio block 없음 — text 만
    types = [c["type"] for c in contents]
    assert "audio" not in types
    assert "input_audio" not in types
    # image 도 없음 (audio_b64 만 전달했음)
    assert "image" not in types


def test_claude_embed_raises_hard():
    """embed() 호출 시 hard BackendError(stage=embed) — embedding 모델 없음."""
    b = ClaudeBackend.__new__(ClaudeBackend)
    with pytest.raises(BackendError) as exc:
        b.embed("text")
    assert exc.value.transient is False
    assert exc.value.stage == "embed"
    assert exc.value.backend == "claude"


def test_claude_chat_non_json_response_is_transient(monkeypatch):
    fake_client = MagicMock()
    fake_response = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = "not json at all"
    fake_response.content = [block]
    fake_client.messages.create.return_value = fake_response
    monkeypatch.setattr(
        "assetcache.core.llm.backends.claude.Anthropic",
        lambda **kw: fake_client,
    )
    b = ClaudeBackend(api_key="x", model_image="m", timeout=60.0)
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is True
    assert exc.value.stage == "chat"


def test_claude_auth_error_is_hard(monkeypatch):
    fake_client = MagicMock()
    fake_resp = MagicMock()  # httpx.Response stand-in
    fake_client.messages.create.side_effect = anthropic.AuthenticationError(
        message="invalid api key", response=fake_resp, body=None
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.claude.Anthropic",
        lambda **kw: fake_client,
    )
    b = ClaudeBackend(api_key="x", model_image="m", timeout=60.0)
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is False


def test_claude_bad_request_is_hard(monkeypatch):
    """모델명 잘못/입력 잘못 → BadRequestError → hard."""
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_client.messages.create.side_effect = anthropic.BadRequestError(
        message="invalid model", response=fake_resp, body=None
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.claude.Anthropic",
        lambda **kw: fake_client,
    )
    b = ClaudeBackend(api_key="x", model_image="m", timeout=60.0)
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is False


def test_claude_rate_limit_is_transient(monkeypatch):
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_client.messages.create.side_effect = anthropic.RateLimitError(
        message="429 too many", response=fake_resp, body=None
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.claude.Anthropic",
        lambda **kw: fake_client,
    )
    b = ClaudeBackend(api_key="x", model_image="m", timeout=60.0)
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is True


def test_claude_internal_error_is_transient(monkeypatch):
    """5xx Server error → transient → chain 다음 backend 시도 가능."""
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_client.messages.create.side_effect = anthropic.InternalServerError(
        message="500 server", response=fake_resp, body=None
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.claude.Anthropic",
        lambda **kw: fake_client,
    )
    b = ClaudeBackend(api_key="x", model_image="m", timeout=60.0)
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is True


def test_claude_test_connection_true(monkeypatch):
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.content = [MagicMock()]
    fake_client.messages.create.return_value = fake_response
    monkeypatch.setattr(
        "assetcache.core.llm.backends.claude.Anthropic",
        lambda **kw: fake_client,
    )
    b = ClaudeBackend(api_key="x", model_image="m", timeout=60.0)
    assert b.test_connection() is True


def test_claude_test_connection_false_on_error(monkeypatch):
    fake_client = MagicMock()
    fake_client.messages.create.side_effect = Exception("unreachable")
    monkeypatch.setattr(
        "assetcache.core.llm.backends.claude.Anthropic",
        lambda **kw: fake_client,
    )
    b = ClaudeBackend(api_key="x", model_image="m", timeout=60.0)
    assert b.test_connection() is False
