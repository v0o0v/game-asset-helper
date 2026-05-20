"""M11 Phase 7 Task 7.1 — cross-backend integration.

실 SDK 호출 없이 (mock 으로) 6 backend 가 BackendChain 안에서 함께 동작
하는 시나리오 검증. 회귀 보호용.

Phase 0~6 의 단위 테스트는 backend 별로 검증했지만, 본 모듈은 chain 의
fallback semantics 가 실 backend 인스턴스 (mock 응답 + capability flag)
와 결합됐을 때 회귀가 없는지 통합적으로 검증.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from assetcache.core.llm.base import BackendError, ChatMessage
from assetcache.core.llm.chain import BackendChain


def _setup_gemini_mock(monkeypatch):
    """GeminiBackend 가 instantiate 가능하도록 genai.Client monkeypatch."""
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: MagicMock(),
    )


def _setup_claude_mock(monkeypatch):
    monkeypatch.setattr(
        "assetcache.core.llm.backends.claude.Anthropic",
        lambda **kw: MagicMock(),
    )


def _setup_openai_mock(monkeypatch):
    monkeypatch.setattr(
        "assetcache.core.llm.backends.openai_backend.OpenAI",
        lambda **kw: MagicMock(),
    )


def test_chain_three_backends_first_transient_falls_back(monkeypatch):
    """3 backend chain — 1순위 transient → 2순위 success."""
    from assetcache.core.llm.backends.gemini import GeminiBackend
    from assetcache.core.llm.backends.claude import ClaudeBackend
    from assetcache.core.llm.backends.openai_backend import OpenAIBackend

    _setup_gemini_mock(monkeypatch)
    _setup_claude_mock(monkeypatch)
    _setup_openai_mock(monkeypatch)

    gemini = GeminiBackend(
        api_key="x", model_image="m", model_audio="m", model_embed="m", timeout=60.0
    )
    claude = ClaudeBackend(api_key="x", model_image="m", timeout=60.0)
    openai_b = OpenAIBackend(
        api_key="x", model_image="m", model_audio="m", model_embed="m", timeout=60.0
    )

    # gemini transient fail, claude success
    gemini.chat = MagicMock(
        side_effect=BackendError(
            backend="gemini", stage="chat", transient=True
        )
    )
    claude.chat = MagicMock(return_value={"category": "icon"})
    openai_b.chat = MagicMock(return_value={"should_not_reach": True})

    chain = BackendChain(
        [gemini, claude, openai_b], modality="chat_image"
    )
    result, used = chain.chat([ChatMessage("user", "describe")])
    assert result == {"category": "icon"}
    assert used == "claude"
    # gemini 가 시도되고 claude 에서 성공 — openai 는 호출 안 됨
    gemini.chat.assert_called_once()
    claude.chat.assert_called_once()
    openai_b.chat.assert_not_called()


def test_chain_three_backends_first_hard_raises_immediately(monkeypatch):
    """1순위 hard error → 즉시 raise, 다음 backend 시도 안 함."""
    from assetcache.core.llm.backends.gemini import GeminiBackend
    from assetcache.core.llm.backends.claude import ClaudeBackend

    _setup_gemini_mock(monkeypatch)
    _setup_claude_mock(monkeypatch)

    gemini = GeminiBackend(
        api_key="x", model_image="m", model_audio="m", model_embed="m", timeout=60.0
    )
    claude = ClaudeBackend(api_key="x", model_image="m", timeout=60.0)

    gemini.chat = MagicMock(
        side_effect=BackendError(
            backend="gemini", stage="chat", transient=False  # hard
        )
    )
    claude.chat = MagicMock(return_value={"never": True})

    chain = BackendChain([gemini, claude], modality="chat_image")
    with pytest.raises(BackendError) as exc:
        chain.chat([ChatMessage("user", "hi")])
    assert exc.value.backend == "gemini"
    assert exc.value.transient is False
    claude.chat.assert_not_called()


def test_chain_audio_modality_skips_claude_and_openrouter(monkeypatch):
    """chat_audio chain — capability audio=False 인 claude/openrouter 자동 skip."""
    from assetcache.core.llm.backends.claude import ClaudeBackend
    from assetcache.core.llm.backends.openrouter import OpenRouterBackend
    from assetcache.core.llm.backends.gemini import GeminiBackend

    _setup_claude_mock(monkeypatch)
    _setup_openai_mock(monkeypatch)  # openrouter uses openai_backend.OpenAI
    _setup_gemini_mock(monkeypatch)

    claude = ClaudeBackend(api_key="x", model_image="m", timeout=60.0)
    openrouter = OpenRouterBackend(
        api_key="x", model_image="m", timeout=60.0
    )
    gemini = GeminiBackend(
        api_key="x", model_image="m", model_audio="m", model_embed="m", timeout=60.0
    )

    claude.chat = MagicMock(return_value={"never": True})
    openrouter.chat = MagicMock(return_value={"never": True})
    gemini.chat = MagicMock(return_value={"kind": "sfx"})

    chain = BackendChain(
        [claude, openrouter, gemini], modality="chat_audio"
    )
    result, used = chain.chat([ChatMessage("user", "audio")])
    # claude (audio=False) + openrouter (audio=False) 둘 다 skip
    assert used == "gemini"
    assert result == {"kind": "sfx"}
    claude.chat.assert_not_called()
    openrouter.chat.assert_not_called()
    gemini.chat.assert_called_once()


def test_chain_embed_no_fallback_with_real_backends(monkeypatch):
    """text_embed chain 은 1순위만 — Gemini transient fail 도 fallback 안 함."""
    from assetcache.core.llm.backends.gemini import GeminiBackend
    from assetcache.core.llm.backends.openai_backend import OpenAIBackend

    _setup_gemini_mock(monkeypatch)
    _setup_openai_mock(monkeypatch)

    gemini = GeminiBackend(
        api_key="x", model_image="m", model_audio="m", model_embed="m", timeout=60.0
    )
    openai_b = OpenAIBackend(
        api_key="x", model_image="m", model_audio="m", model_embed="m", timeout=60.0
    )
    gemini.embed = MagicMock(
        side_effect=BackendError(
            backend="gemini", stage="embed", transient=True
        )
    )
    openai_b.embed = MagicMock(return_value=[0.1] * 1536)

    chain = BackendChain([gemini, openai_b], modality="text_embed")
    with pytest.raises(BackendError):
        chain.embed("hello")
    # openai 는 호출 안 됨 — embed 는 fallback 안 함 (dim 일관성)
    openai_b.embed.assert_not_called()


def test_chain_all_six_backends_eligible_in_image_chain(monkeypatch):
    """6 backend 모두 image=True 라 chat_image chain 에 다 들어갈 수 있음."""
    from assetcache.core.llm.backends.gemini import GeminiBackend
    from assetcache.core.llm.backends.claude import ClaudeBackend
    from assetcache.core.llm.backends.openai_backend import OpenAIBackend
    from assetcache.core.llm.backends.openrouter import OpenRouterBackend
    from assetcache.core.llm.backends.huggingface import HuggingFaceBackend

    _setup_gemini_mock(monkeypatch)
    _setup_claude_mock(monkeypatch)
    _setup_openai_mock(monkeypatch)
    monkeypatch.setattr(
        "assetcache.core.llm.backends.huggingface.InferenceClient",
        lambda **kw: MagicMock(),
    )

    gemini = GeminiBackend(
        api_key="x", model_image="m", model_audio="m", model_embed="m", timeout=60.0
    )
    claude = ClaudeBackend(api_key="x", model_image="m", timeout=60.0)
    openai_b = OpenAIBackend(
        api_key="x", model_image="m", model_audio="m", model_embed="m", timeout=60.0
    )
    openrouter = OpenRouterBackend(
        api_key="x", model_image="m", timeout=60.0
    )
    hf = HuggingFaceBackend(
        api_key="x", model_image="m", model_audio="m", model_embed="m", timeout=60.0
    )

    chain = BackendChain(
        [gemini, claude, openai_b, openrouter, hf], modality="chat_image"
    )
    eligible = chain._eligible()
    assert len(eligible) == 5
    assert [b.info.name for b in eligible] == [
        "gemini", "claude", "openai", "openrouter", "huggingface"
    ]
