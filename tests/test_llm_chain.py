"""BackendChain — modality skip + transient fallback + hard raise."""

from __future__ import annotations

import pytest

from assetcache.core.llm.base import (
    BackendCapabilities,
    BackendError,
    BackendInfo,
    ChatMessage,
)
from assetcache.core.llm.chain import BackendChain


def _backend(
    name,
    *,
    img=True,
    aud=True,
    emb=True,
    chat_result=None,
    chat_error=None,
    embed_result=None,
    embed_error=None,
):
    class _Stub:
        info = BackendInfo(
            name=name,
            display_name=name,
            homepage="",
            capabilities=BackendCapabilities(img, aud, emb, embed_dim=None),
        )

        def chat(self, messages, **kw):
            if chat_error is not None:
                raise chat_error
            return chat_result if chat_result is not None else {"backend": name}

        def embed(self, text, *, model=None):
            if embed_error is not None:
                raise embed_error
            return embed_result if embed_result is not None else [1.0, 2.0]

        def test_connection(self):
            return True

    return _Stub()


def test_chain_chat_first_success():
    chain = BackendChain([_backend("a"), _backend("b")], modality="chat_image")
    result, used = chain.chat([ChatMessage("user", "hi")])
    assert used == "a"
    assert result == {"backend": "a"}


def test_chain_chat_transient_fallback():
    a_fail = _backend(
        "a", chat_error=BackendError(backend="a", stage="chat", transient=True)
    )
    b_ok = _backend("b")
    chain = BackendChain([a_fail, b_ok], modality="chat_image")
    result, used = chain.chat([ChatMessage("user", "hi")])
    assert used == "b"
    assert result == {"backend": "b"}


def test_chain_chat_hard_raises_immediately():
    a_hard = _backend(
        "a", chat_error=BackendError(backend="a", stage="chat", transient=False)
    )
    b_ok = _backend("b")
    chain = BackendChain([a_hard, b_ok], modality="chat_image")
    with pytest.raises(BackendError) as exc:
        chain.chat([ChatMessage("user", "hi")])
    assert exc.value.backend == "a"
    assert exc.value.transient is False


def test_chain_modality_skip_audio_unsupported():
    a_no_audio = _backend("a", aud=False)
    b_ok = _backend("b")
    chain = BackendChain([a_no_audio, b_ok], modality="chat_audio")
    result, used = chain.chat([ChatMessage("user", "hi")])
    assert used == "b"


def test_chain_modality_skip_image_unsupported():
    a_no_image = _backend("a", img=False)
    b_ok = _backend("b")
    chain = BackendChain([a_no_image, b_ok], modality="chat_image")
    result, used = chain.chat([ChatMessage("user", "hi")])
    assert used == "b"


def test_chain_all_transient_fail_raises_chain_error():
    a = _backend(
        "a", chat_error=BackendError(backend="a", stage="chat", transient=True)
    )
    b = _backend(
        "b", chat_error=BackendError(backend="b", stage="chat", transient=True)
    )
    chain = BackendChain([a, b], modality="chat_image")
    with pytest.raises(BackendError) as exc:
        chain.chat([ChatMessage("user", "hi")])
    assert exc.value.backend == "<chain>"


def test_chain_embed_no_fallback():
    """embedding chain 은 1순위만 사용 — dim 일관성 보장."""
    a_fail = _backend(
        "a", emb=True, embed_error=BackendError(backend="a", stage="embed", transient=True)
    )
    b_ok = _backend("b", embed_result=[3.0])
    chain = BackendChain([a_fail, b_ok], modality="text_embed")
    with pytest.raises(BackendError):
        chain.embed("x")


def test_chain_embed_primary_success():
    a_ok = _backend("a", embed_result=[1.5, 2.5])
    b_ok = _backend("b", embed_result=[9.9])
    chain = BackendChain([a_ok, b_ok], modality="text_embed")
    vec, used = chain.embed("x")
    assert vec == [1.5, 2.5]
    assert used == "a"


def test_chain_empty_raises():
    chain = BackendChain([], modality="chat_image")
    with pytest.raises(BackendError):
        chain.chat([ChatMessage("user", "hi")])


def test_chain_no_eligible_backend_raises():
    """모두 capability 미지원 → eligible 0 → BackendError."""
    a_none = _backend("a", img=False, aud=False, emb=False)
    chain = BackendChain([a_none], modality="chat_image")
    with pytest.raises(BackendError):
        chain.chat([ChatMessage("user", "hi")])


def test_chain_embed_on_wrong_modality_raises():
    """text_embed 가 아닌 chain 에서 embed() 호출 → 명확한 에러."""
    a_ok = _backend("a")
    chain = BackendChain([a_ok], modality="chat_image")
    with pytest.raises(BackendError):
        chain.embed("x")


