"""M11 후속 — BackendInfo.setup_url 필드 + 3 backend (ollama/gemini/openai) 별 정확한 URL.

M11.9: claude/openrouter/huggingface 백엔드 제거 후 setup_url 검증은
잔존 3 backend (+ field 존재) 만 cover.
"""

from __future__ import annotations

from assetcache.core.llm.backends.gemini import GeminiBackend
from assetcache.core.llm.backends.ollama import OllamaBackend
from assetcache.core.llm.backends.openai_backend import OpenAIBackend


def test_backend_info_has_setup_url_field():
    """BackendInfo dataclass 에 setup_url 필드 존재."""
    info = OllamaBackend.info
    assert hasattr(info, "setup_url")


def test_ollama_setup_url():
    assert OllamaBackend.info.setup_url == "https://ollama.com/download"


def test_gemini_setup_url():
    assert GeminiBackend.info.setup_url == "https://aistudio.google.com/apikey"


def test_openai_setup_url():
    assert OpenAIBackend.info.setup_url == "https://platform.openai.com/api-keys"
