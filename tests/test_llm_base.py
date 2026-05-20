"""LLMBackend Protocol + 보조 타입 (BackendInfo/Capabilities/Error/ChatMessage)."""

from __future__ import annotations

import pytest

from assetcache.core.llm.base import (
    BackendCapabilities,
    BackendError,
    BackendInfo,
    ChatMessage,
    LLMBackend,
)


def test_backend_info_immutable():
    info = BackendInfo(
        name="x",
        display_name="X",
        homepage="https://example.com/",
        capabilities=BackendCapabilities(True, True, True, embed_dim=None),
    )
    with pytest.raises((AttributeError, Exception)):
        info.name = "y"  # type: ignore[misc]


def test_backend_capabilities_fields():
    cap = BackendCapabilities(
        supports_chat_image=True,
        supports_chat_audio=False,
        supports_text_embed=True,
        embed_dim=768,
    )
    assert cap.supports_chat_image is True
    assert cap.supports_chat_audio is False
    assert cap.supports_text_embed is True
    assert cap.embed_dim == 768


def test_backend_error_classification():
    e = BackendError(backend="x", stage="chat", transient=True)
    assert e.transient is True
    assert e.backend == "x"
    assert e.stage == "chat"
    assert e.cause is None

    e2 = BackendError(
        backend="y", stage="embed", transient=False,
        cause=RuntimeError("fail"),
    )
    assert e2.transient is False
    assert isinstance(e2.cause, RuntimeError)
    # RuntimeError 의 자손이어야 BackendChain 에서 try/except 가능
    assert isinstance(e2, RuntimeError)


def test_chat_message_dataclass_defaults():
    m = ChatMessage(role="user", content="hi")
    assert m.role == "user"
    assert m.content == "hi"
    assert m.images_b64 == []
    assert m.audio_b64 == []


def test_chat_message_dataclass_full():
    m = ChatMessage(
        role="user",
        content="describe",
        images_b64=["aW1n"],
        audio_b64=[("d", "audio/wav")],
    )
    assert m.images_b64 == ["aW1n"]
    assert m.audio_b64 == [("d", "audio/wav")]


def test_llm_backend_protocol_satisfied_by_stub():
    """runtime_checkable Protocol — duck-typed instance 가 isinstance() 통과."""

    class _Stub:
        info = BackendInfo(
            name="stub",
            display_name="Stub",
            homepage="",
            capabilities=BackendCapabilities(False, False, False, embed_dim=None),
        )

        def chat(self, messages, *, force_json=True, num_ctx=8000):
            return {}

        def embed(self, text, *, model=None):
            return [0.0]

        def test_connection(self):
            return True

    assert isinstance(_Stub(), LLMBackend)
