"""HuggingFaceBackend integration — 실 HF token 필요.

기본 `pytest -q` 에서는 `llm_integration` marker deselect.
사용자 옵트인:

    $env:HF_TOKEN = "hf_..."
    pytest -m llm_integration tests/test_llm_backend_huggingface_integration.py

(HF 의 free tier 는 월 quota 작음 — 1~2 호출이면 충분히 검증 가능.)
"""

from __future__ import annotations

import os

import pytest

from assetcache.core.llm.backends.huggingface import HuggingFaceBackend
from assetcache.core.llm.base import ChatMessage


pytestmark = pytest.mark.llm_integration


@pytest.fixture
def hf_b():
    api_key = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_API_KEY")
    if not api_key:
        pytest.skip("HF_TOKEN / HUGGINGFACE_API_KEY env not set")
    return HuggingFaceBackend(
        api_key=api_key,
        model_image="meta-llama/Llama-3.2-3B-Instruct",
        model_audio="",
        model_embed="sentence-transformers/all-MiniLM-L6-v2",
        timeout=120.0,  # HF cold-start 가 느릴 수 있음
    )


def test_huggingface_text_chat(hf_b):
    out = hf_b.chat(
        [ChatMessage("user", 'Reply with exact JSON: {"ok": true}')],
        force_json=True,
    )
    assert out.get("ok") is True


def test_huggingface_embed_returns_floats(hf_b):
    vec = hf_b.embed("hello world")
    assert isinstance(vec, list)
    assert len(vec) > 0
    assert all(isinstance(x, float) for x in vec)
