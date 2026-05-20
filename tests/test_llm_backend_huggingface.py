"""HuggingFaceBackend — InferenceClient mock 기반.

Phase 4 Task 4.2 — HuggingFace Inference Providers (`InferenceClient`)
통합. chat_completion + feature_extraction. embed_dim 은 모델별로 가변
이라 None.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest
from huggingface_hub import errors as hf_errors

from assetcache.core.llm.backends.huggingface import HuggingFaceBackend
from assetcache.core.llm.base import BackendError, ChatMessage


def _make_chat_response(text: str) -> MagicMock:
    r = MagicMock()
    choice = MagicMock()
    choice.message.content = text
    r.choices = [choice]
    return r


def test_huggingface_capabilities():
    cap = HuggingFaceBackend.info.capabilities
    assert cap.supports_chat_image is True
    assert cap.supports_chat_audio is True
    assert cap.supports_text_embed is True
    assert cap.embed_dim is None  # 모델별 가변


def test_huggingface_init_empty_api_key_is_hard():
    with pytest.raises(BackendError) as exc:
        HuggingFaceBackend(
            api_key="",
            model_image="m-i",
            model_audio="m-a",
            model_embed="m-e",
            timeout=60.0,
        )
    assert exc.value.transient is False
    assert exc.value.stage == "init"


def test_huggingface_init_passes_token(monkeypatch):
    captured = {}

    def fake_client(**kw):
        captured.update(kw)
        return MagicMock()

    monkeypatch.setattr(
        "assetcache.core.llm.backends.huggingface.InferenceClient", fake_client
    )
    HuggingFaceBackend(
        api_key="hf_token_test",
        model_image="Qwen/Qwen2.5-VL-72B-Instruct",
        model_audio="",
        model_embed="",
        timeout=60.0,
    )
    assert captured.get("token") == "hf_token_test"
    assert captured.get("timeout") == 60.0


def test_huggingface_chat_text_only(monkeypatch):
    fake_client = MagicMock()
    fake_client.chat_completion.return_value = _make_chat_response(
        '{"category": "tile"}'
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.huggingface.InferenceClient",
        lambda **kw: fake_client,
    )
    b = HuggingFaceBackend(
        api_key="hf_x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    out = b.chat([ChatMessage("user", "hi")])
    assert out == {"category": "tile"}
    call = fake_client.chat_completion.call_args
    assert call.kwargs.get("model") == "m-i"


def test_huggingface_chat_with_image(monkeypatch):
    """images_b64 → OpenAI 호환 content type=image_url (HF chat_completion 도 동일 shape)."""
    fake_client = MagicMock()
    fake_client.chat_completion.return_value = _make_chat_response(
        '{"category": "icon"}'
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.huggingface.InferenceClient",
        lambda **kw: fake_client,
    )
    b = HuggingFaceBackend(
        api_key="hf_x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    out = b.chat([ChatMessage("user", "describe", images_b64=["aW1n"])])
    assert out == {"category": "icon"}

    call = fake_client.chat_completion.call_args
    msgs = call.kwargs.get("messages")
    contents = msgs[0]["content"]
    types = [c["type"] for c in contents]
    assert "text" in types
    assert "image_url" in types
    image_part = next(c for c in contents if c["type"] == "image_url")
    assert image_part["image_url"]["url"].startswith("data:image/png;base64,")


def test_huggingface_chat_with_audio_selects_audio_model(monkeypatch):
    fake_client = MagicMock()
    fake_client.chat_completion.return_value = _make_chat_response('{"k": "sfx"}')
    monkeypatch.setattr(
        "assetcache.core.llm.backends.huggingface.InferenceClient",
        lambda **kw: fake_client,
    )
    b = HuggingFaceBackend(
        api_key="hf_x",
        model_image="m-i",
        model_audio="audio-model",
        model_embed="m-e",
        timeout=60.0,
    )
    out = b.chat([ChatMessage("user", "x", audio_b64=[("YQ==", "audio/wav")])])
    assert out == {"k": "sfx"}
    call = fake_client.chat_completion.call_args
    assert call.kwargs.get("model") == "audio-model"


def test_huggingface_chat_non_json_response_is_transient(monkeypatch):
    fake_client = MagicMock()
    fake_client.chat_completion.return_value = _make_chat_response("free prose")
    monkeypatch.setattr(
        "assetcache.core.llm.backends.huggingface.InferenceClient",
        lambda **kw: fake_client,
    )
    b = HuggingFaceBackend(
        api_key="hf_x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is True
    assert exc.value.stage == "chat"


def test_huggingface_bad_request_is_hard(monkeypatch):
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_client.chat_completion.side_effect = hf_errors.BadRequestError(
        "invalid model", response=fake_resp
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.huggingface.InferenceClient",
        lambda **kw: fake_client,
    )
    b = HuggingFaceBackend(
        api_key="hf_x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is False


def test_huggingface_gated_repo_is_hard(monkeypatch):
    """GatedRepoError → hard (사용자 라이선스 동의 필요)."""
    fake_client = MagicMock()
    fake_resp = MagicMock()
    fake_client.chat_completion.side_effect = hf_errors.GatedRepoError(
        "gated repo, please accept license", response=fake_resp
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.huggingface.InferenceClient",
        lambda **kw: fake_client,
    )
    b = HuggingFaceBackend(
        api_key="hf_x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is False


def test_huggingface_overloaded_is_transient(monkeypatch):
    fake_client = MagicMock()
    fake_client.chat_completion.side_effect = hf_errors.OverloadedError(
        "model overloaded"
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.huggingface.InferenceClient",
        lambda **kw: fake_client,
    )
    b = HuggingFaceBackend(
        api_key="hf_x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is True


def test_huggingface_embed_returns_list_of_floats(monkeypatch):
    fake_client = MagicMock()
    fake_client.feature_extraction.return_value = np.array([0.1, 0.2, 0.3])
    monkeypatch.setattr(
        "assetcache.core.llm.backends.huggingface.InferenceClient",
        lambda **kw: fake_client,
    )
    b = HuggingFaceBackend(
        api_key="hf_x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="embed-model",
        timeout=60.0,
    )
    vec = b.embed("hello")
    assert vec == [pytest.approx(0.1), pytest.approx(0.2), pytest.approx(0.3)]
    call = fake_client.feature_extraction.call_args
    assert call.kwargs.get("model") == "embed-model"


def test_huggingface_embed_2d_array_flattened(monkeypatch):
    """일부 embed 모델은 (1, dim) 또는 (n_tokens, dim) 반환 → 평균 풀링 또는 1D 변환."""
    fake_client = MagicMock()
    # (1, 3) shape — 일부 모델
    fake_client.feature_extraction.return_value = np.array([[0.4, 0.5, 0.6]])
    monkeypatch.setattr(
        "assetcache.core.llm.backends.huggingface.InferenceClient",
        lambda **kw: fake_client,
    )
    b = HuggingFaceBackend(
        api_key="hf_x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    vec = b.embed("hello")
    assert isinstance(vec, list)
    assert len(vec) == 3


def test_huggingface_embed_error_classified(monkeypatch):
    fake_client = MagicMock()
    fake_client.feature_extraction.side_effect = hf_errors.OverloadedError("overload")
    monkeypatch.setattr(
        "assetcache.core.llm.backends.huggingface.InferenceClient",
        lambda **kw: fake_client,
    )
    b = HuggingFaceBackend(
        api_key="hf_x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    with pytest.raises(BackendError) as exc:
        b.embed("hello")
    assert exc.value.stage == "embed"
    assert exc.value.transient is True


def test_huggingface_test_connection_true(monkeypatch):
    """test_connection: 가벼운 chat_completion call (max_tokens=1) 성공 시 True."""
    fake_client = MagicMock()
    fake_client.chat_completion.return_value = MagicMock()
    monkeypatch.setattr(
        "assetcache.core.llm.backends.huggingface.InferenceClient",
        lambda **kw: fake_client,
    )
    b = HuggingFaceBackend(
        api_key="hf_x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    assert b.test_connection() is True


def test_huggingface_test_connection_false_on_error(monkeypatch):
    fake_client = MagicMock()
    fake_client.chat_completion.side_effect = Exception("unreachable")
    monkeypatch.setattr(
        "assetcache.core.llm.backends.huggingface.InferenceClient",
        lambda **kw: fake_client,
    )
    b = HuggingFaceBackend(
        api_key="hf_x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    assert b.test_connection() is False
