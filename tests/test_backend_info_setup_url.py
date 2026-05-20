"""M11 후속 — BackendInfo.setup_url 필드 + 6 backend 별 정확한 URL."""

from __future__ import annotations

from assetcache.core.llm.backends.claude import ClaudeBackend
from assetcache.core.llm.backends.gemini import GeminiBackend
from assetcache.core.llm.backends.huggingface import HuggingFaceBackend
from assetcache.core.llm.backends.ollama import OllamaBackend
from assetcache.core.llm.backends.openai_backend import OpenAIBackend
from assetcache.core.llm.backends.openrouter import OpenRouterBackend


def test_backend_info_has_setup_url_field():
    """BackendInfo dataclass 에 setup_url 필드 존재."""
    info = OllamaBackend.info
    assert hasattr(info, "setup_url")


def test_ollama_setup_url():
    assert OllamaBackend.info.setup_url == "https://ollama.com/download"


def test_gemini_setup_url():
    assert GeminiBackend.info.setup_url == "https://aistudio.google.com/apikey"


def test_claude_setup_url():
    assert (
        ClaudeBackend.info.setup_url
        == "https://console.anthropic.com/settings/keys"
    )


def test_openai_setup_url():
    assert OpenAIBackend.info.setup_url == "https://platform.openai.com/api-keys"


def test_openrouter_setup_url():
    assert OpenRouterBackend.info.setup_url == "https://openrouter.ai/settings/keys"


def test_huggingface_setup_url():
    assert (
        HuggingFaceBackend.info.setup_url
        == "https://huggingface.co/settings/tokens"
    )
