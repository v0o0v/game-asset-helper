"""Phase 2 — GeminiBackend.batch_chat mock tests."""

from unittest.mock import MagicMock

import pytest

from assetcache.core.batch.types import BatchChatRequest
from assetcache.core.llm.base import ChatMessage


@pytest.fixture
def gemini_backend(monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: fake_client,
    )
    from assetcache.core.llm.backends.gemini import GeminiBackend
    backend = GeminiBackend(
        api_key="test",
        model_image="gemini-3.1-flash-lite",
        model_audio="gemini-3.1-flash-lite",
        model_embed="gemini-embedding-001",
        timeout=60.0,
    )
    return backend, fake_client


def test_batch_chat_image_returns_job_name(gemini_backend):
    backend, client = gemini_backend
    fake_job = MagicMock()
    fake_job.name = "batches/test-abc"
    client.batches.create.return_value = fake_job

    requests = [
        BatchChatRequest(
            asset_id=1,
            messages=[ChatMessage(role="user", content="describe")],
            force_json=True,
        ),
        BatchChatRequest(
            asset_id=2,
            messages=[ChatMessage(role="user", content="describe2")],
            force_json=True,
        ),
    ]
    job_name = backend.batch_chat(modality="chat_image", requests=requests)
    assert job_name == "batches/test-abc"
    client.batches.create.assert_called_once()
    kw = client.batches.create.call_args.kwargs
    assert kw["model"] == "gemini-3.1-flash-lite"
    assert "src" in kw
    assert len(kw["src"]) == 2
    assert "config" in kw and "display_name" in kw["config"]


def test_batch_chat_audio_uses_audio_model(gemini_backend, monkeypatch):
    backend, client = gemini_backend
    fake_job = MagicMock()
    fake_job.name = "batches/y"
    client.batches.create.return_value = fake_job
    monkeypatch.setattr(backend, "model_audio", "gemini-3.1-flash-lite-audio")
    backend.batch_chat(modality="chat_audio", requests=[
        BatchChatRequest(asset_id=1, messages=[ChatMessage(role="user", content="a")]),
    ])
    kw = client.batches.create.call_args.kwargs
    assert kw["model"] == "gemini-3.1-flash-lite-audio"


def test_batch_chat_invalid_modality_raises(gemini_backend):
    backend, _ = gemini_backend
    with pytest.raises(ValueError, match="modality"):
        backend.batch_chat(modality="text_embed", requests=[])


def test_batch_chat_transient_error_raises_backend_error(gemini_backend):
    from assetcache.core.llm.base import BackendError
    backend, client = gemini_backend
    client.batches.create.side_effect = RuntimeError("connect timeout")
    with pytest.raises(BackendError) as exc_info:
        backend.batch_chat(modality="chat_image", requests=[
            BatchChatRequest(asset_id=1, messages=[ChatMessage(role="user", content="x")]),
        ])
    assert exc_info.value.transient is True


def test_batch_chat_hard_error_401(gemini_backend):
    from assetcache.core.llm.base import BackendError
    backend, client = gemini_backend
    client.batches.create.side_effect = Exception("401 unauthorized")
    with pytest.raises(BackendError) as exc_info:
        backend.batch_chat(modality="chat_image", requests=[
            BatchChatRequest(asset_id=1, messages=[ChatMessage(role="user", content="x")]),
        ])
    assert exc_info.value.transient is False


def test_batch_embed_returns_job_name(gemini_backend):
    backend, client = gemini_backend
    fake_job = MagicMock()
    fake_job.name = "batches/embed-1"
    client.batches.create_embeddings.return_value = fake_job
    name = backend.batch_embed(texts=["hello", "world"])
    assert name == "batches/embed-1"
    kw = client.batches.create_embeddings.call_args.kwargs
    assert kw["model"] == "gemini-embedding-001"
    assert "inlined_requests" in kw["src"]
    assert len(kw["src"]["inlined_requests"]) == 2


def test_batch_embed_empty_list_raises(gemini_backend):
    backend, _ = gemini_backend
    with pytest.raises(ValueError):
        backend.batch_embed(texts=[])


def test_batch_embed_transient_error(gemini_backend):
    from assetcache.core.llm.base import BackendError
    backend, client = gemini_backend
    client.batches.create_embeddings.side_effect = RuntimeError("503 unavailable")
    with pytest.raises(BackendError) as exc_info:
        backend.batch_embed(texts=["x"])
    assert exc_info.value.transient is True
