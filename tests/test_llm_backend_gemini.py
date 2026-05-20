"""GeminiBackend — google-genai SDK mock 기반.

Phase 1 Task 1.1 — chat (text/image/audio) + embed + 에러 분류.
실 API 호출 통합 테스트는 `test_llm_backend_gemini_integration.py` 에서
(`@pytest.mark.llm_integration` 옵트인).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from assetcache.core.llm.backends.gemini import GeminiBackend
from assetcache.core.llm.base import BackendError, ChatMessage


def test_gemini_capabilities():
    """info 가 chat_image + chat_audio + text_embed 모두 True 로 선언."""
    cap = GeminiBackend.info.capabilities
    assert cap.supports_chat_image
    assert cap.supports_chat_audio
    assert cap.supports_text_embed
    assert cap.embed_dim == 768


def test_gemini_init_empty_api_key_is_hard():
    """빈 api_key → BackendError(transient=False)."""
    with pytest.raises(BackendError) as exc:
        GeminiBackend(
            api_key="",
            model_image="m-i",
            model_audio="m-a",
            model_embed="m-e",
            timeout=60.0,
        )
    assert exc.value.transient is False
    assert exc.value.stage == "init"


def test_gemini_chat_text_only(monkeypatch):
    """force_json=True + text-only 응답 → dict 파싱."""
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.text = '{"category": "sprite"}'
    fake_client.models.generate_content.return_value = fake_response

    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: fake_client,
    )
    b = GeminiBackend(
        api_key="x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    out = b.chat([ChatMessage("user", "hi")])
    assert out == {"category": "sprite"}
    # text-only → model_image 선택 (audio 없음)
    call = fake_client.models.generate_content.call_args
    assert call.kwargs.get("model") == "m-i"


def test_gemini_chat_with_image(monkeypatch):
    """images_b64 가 inline_data Part 로 contents 에 들어가는지."""
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.text = '{"category": "icon"}'
    fake_client.models.generate_content.return_value = fake_response
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: fake_client,
    )

    b = GeminiBackend(
        api_key="x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    # "aW1n" = base64("img")
    out = b.chat([ChatMessage("user", "describe", images_b64=["aW1n"])])
    assert out == {"category": "icon"}

    call = fake_client.models.generate_content.call_args
    contents = call.kwargs.get("contents")
    assert contents is not None, "contents kwarg should be passed"
    # 최소 2 개 — text + 1 image Part
    assert len(contents) >= 2
    # text part 가 포함
    assert any(isinstance(p, str) and "describe" in p for p in contents)
    # image part 가 inline_data.mime_type=image/png 으로 들어감
    from google.genai import types as genai_types
    image_parts = [p for p in contents if isinstance(p, genai_types.Part)]
    assert len(image_parts) == 1
    assert image_parts[0].inline_data.mime_type == "image/png"


def test_gemini_chat_with_audio_selects_audio_model(monkeypatch):
    """audio_b64 가 있으면 model_audio 선택."""
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.text = '{"kind": "music"}'
    fake_client.models.generate_content.return_value = fake_response
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: fake_client,
    )

    b = GeminiBackend(
        api_key="x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    out = b.chat([ChatMessage("user", "describe", audio_b64=[("aXNvbg==", "audio/wav")])])
    assert out == {"kind": "music"}

    call = fake_client.models.generate_content.call_args
    assert call.kwargs.get("model") == "m-a"


def test_gemini_chat_non_json_response_is_transient(monkeypatch):
    """force_json=True 인데 응답이 JSON 이 아니면 transient BackendError."""
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.text = "not json at all"
    fake_client.models.generate_content.return_value = fake_response
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: fake_client,
    )
    b = GeminiBackend(
        api_key="x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is True
    assert exc.value.stage == "chat"


def test_gemini_auth_error_is_hard(monkeypatch):
    """SDK 의 ClientError(401) 또는 'permission' 메시지 → hard."""
    fake_client = MagicMock()

    class _PermDenied(Exception):
        pass

    fake_client.models.generate_content.side_effect = _PermDenied("403 permission denied")
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: fake_client,
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini._HARD_EXCEPTIONS",
        (_PermDenied,),
    )
    b = GeminiBackend(
        api_key="x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is False
    assert exc.value.stage == "chat"


def test_gemini_rate_limit_is_transient(monkeypatch):
    """generic Exception('429') → transient."""
    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = Exception(
        "429 Too Many Requests"
    )
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: fake_client,
    )
    b = GeminiBackend(
        api_key="x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    with pytest.raises(BackendError) as exc:
        b.chat([ChatMessage("user", "hi")])
    assert exc.value.transient is True


def test_gemini_embed_returns_list_of_floats(monkeypatch):
    """embed → SDK 응답에서 embeddings[0].values 추출 list[float] 반환."""
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_embedding = MagicMock()
    fake_embedding.values = [0.1, 0.2, 0.3]
    fake_response.embeddings = [fake_embedding]
    fake_client.models.embed_content.return_value = fake_response
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: fake_client,
    )

    b = GeminiBackend(
        api_key="x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    vec = b.embed("hello world")
    assert vec == [0.1, 0.2, 0.3]
    call = fake_client.models.embed_content.call_args
    assert call.kwargs.get("model") == "m-e"


def test_gemini_embed_error_classified(monkeypatch):
    """embed 호출 실패도 transient/hard 로 분류돼 BackendError."""
    fake_client = MagicMock()
    fake_client.models.embed_content.side_effect = Exception("500 server error")
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: fake_client,
    )
    b = GeminiBackend(
        api_key="x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    with pytest.raises(BackendError) as exc:
        b.embed("hello")
    assert exc.value.stage == "embed"
    assert exc.value.transient is True


def test_gemini_test_connection_true(monkeypatch):
    """test_connection: models.list() 가 성공하면 True."""
    fake_client = MagicMock()
    fake_client.models.list.return_value = iter([MagicMock()])
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: fake_client,
    )
    b = GeminiBackend(
        api_key="x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    assert b.test_connection() is True


def test_gemini_test_connection_false_on_error(monkeypatch):
    """test_connection: 예외가 나면 False (raise 안 함)."""
    fake_client = MagicMock()
    fake_client.models.list.side_effect = Exception("unreachable")
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: fake_client,
    )
    b = GeminiBackend(
        api_key="x",
        model_image="m-i",
        model_audio="m-a",
        model_embed="m-e",
        timeout=60.0,
    )
    assert b.test_connection() is False
