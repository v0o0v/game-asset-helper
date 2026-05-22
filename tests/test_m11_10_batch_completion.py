"""M11.10 — text_embed multi-input batch + chat 결과 embedding 채움.

Spec: docs/superpowers/specs/2026-05-22-m11-10-batch-completion.md
Plan: milestones/M11_10_plan.md

Phase 1: BackendChain.batch_embed + GeminiBackend.embed_multi 신설.
Phase 2: BatchPoller._handle_succeeded 가 chat_* 결과 persist 후 1회 multi-input embed 로 모든 asset embedding 채움.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from assetcache.core.batch.poller import BatchPoller
from assetcache.core.batch.types import GeminiBatchStatus
from assetcache.core.llm.base import (
    BackendCapabilities,
    BackendError,
    BackendInfo,
    ChatMessage,
)
from assetcache.core.llm.chain import BackendChain


# ── Phase 1: BackendChain.batch_embed ───────────────────────────────


@dataclass
class _FakeBackend:
    name: str = "fake"
    supports_image: bool = False
    supports_audio: bool = False
    supports_embed: bool = True
    embed_dim: int | None = 8
    embed_multi_impl = None  # optional callable
    embed_impl = None  # fallback single

    def __post_init__(self) -> None:
        self.embed_calls: list[str] = []
        self.embed_multi_calls: list[list[str]] = []
        self.info = BackendInfo(
            name=self.name,
            display_name=self.name,
            homepage="https://example/",
            capabilities=BackendCapabilities(
                supports_chat_image=self.supports_image,
                supports_chat_audio=self.supports_audio,
                supports_text_embed=self.supports_embed,
                embed_dim=self.embed_dim,
            ),
        )

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        self.embed_calls.append(text)
        if self.embed_impl is not None:
            return self.embed_impl(text)
        return [float(len(text))] * 4

    def embed_multi(self, texts: list[str]) -> list[list[float]]:
        self.embed_multi_calls.append(list(texts))
        if self.embed_multi_impl is not None:
            return self.embed_multi_impl(texts)
        return [[float(len(t))] * 4 for t in texts]


@dataclass
class _FakeBackendNoMulti:
    """embed_multi 없는 백엔드 — fallback path 검증용."""

    name: str = "fake-no-multi"

    def __post_init__(self) -> None:
        self.embed_calls: list[str] = []
        self.info = BackendInfo(
            name=self.name,
            display_name=self.name,
            homepage="https://example/",
            capabilities=BackendCapabilities(
                supports_chat_image=False,
                supports_chat_audio=False,
                supports_text_embed=True,
                embed_dim=8,
            ),
        )

    def embed(self, text: str, *, model: str | None = None) -> list[float]:
        self.embed_calls.append(text)
        return [1.0, 2.0, 3.0, 4.0]


def test_backend_chain_batch_embed_uses_primary_embed_multi():
    """chain.batch_embed → primary.embed_multi 1회 + 개별 embed 0회."""
    primary = _FakeBackend(name="gemini")
    chain = BackendChain([primary], modality="text_embed")

    vectors, name = chain.batch_embed(["alpha", "bravo", "charlie"])

    assert name == "gemini"
    assert len(vectors) == 3
    assert len(primary.embed_multi_calls) == 1
    assert primary.embed_multi_calls[0] == ["alpha", "bravo", "charlie"]
    assert primary.embed_calls == []  # 단일 embed 호출 0


def test_backend_chain_batch_embed_fallback_to_loop_when_no_embed_multi():
    """embed_multi 미지원 backend → 개별 embed N회 fallback."""
    primary = _FakeBackendNoMulti()
    chain = BackendChain([primary], modality="text_embed")

    vectors, name = chain.batch_embed(["x", "y", "z"])

    assert name == "fake-no-multi"
    assert len(vectors) == 3
    assert primary.embed_calls == ["x", "y", "z"]


def test_backend_chain_batch_embed_only_text_embed_modality():
    """chat_image chain 에서 batch_embed 호출 시 BackendError."""
    primary = _FakeBackend(name="gemini", supports_image=True, supports_embed=False)
    chain = BackendChain([primary], modality="chat_image")

    with pytest.raises(BackendError):
        chain.batch_embed(["x"])


def test_backend_chain_batch_embed_empty_returns_empty():
    """빈 input → 빈 output, primary 호출 안 함."""
    primary = _FakeBackend(name="gemini")
    chain = BackendChain([primary], modality="text_embed")

    vectors, name = chain.batch_embed([])

    assert vectors == []
    assert name == "gemini"
    assert primary.embed_multi_calls == []
    assert primary.embed_calls == []


def test_backend_chain_batch_embed_empty_chain_raises():
    """eligible backend 0 → BackendError."""
    chain = BackendChain([], modality="text_embed")
    with pytest.raises(BackendError):
        chain.batch_embed(["x"])


# ── Phase 1: GeminiBackend.embed_multi ──────────────────────────────


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


def test_gemini_embed_multi_single_http_call(gemini_backend):
    """embed_multi(['a','b','c']) → embed_content 1회 호출 + contents=['a','b','c']."""
    backend, client = gemini_backend
    resp = MagicMock()
    resp.embeddings = [
        MagicMock(values=[0.1, 0.2, 0.3, 0.4]),
        MagicMock(values=[0.5, 0.6, 0.7, 0.8]),
        MagicMock(values=[0.9, 1.0, 1.1, 1.2]),
    ]
    client.models.embed_content.return_value = resp

    vectors = backend.embed_multi(["a", "b", "c"])

    assert len(vectors) == 3
    assert vectors[0] == [0.1, 0.2, 0.3, 0.4]
    assert vectors[2] == [0.9, 1.0, 1.1, 1.2]
    # 1 HTTP call (N texts)
    client.models.embed_content.assert_called_once()
    kw = client.models.embed_content.call_args.kwargs
    assert kw["model"] == "gemini-embedding-001"
    assert kw["contents"] == ["a", "b", "c"]


def test_gemini_embed_multi_empty_returns_empty(gemini_backend):
    """빈 input → 빈 output, embed_content 미호출."""
    backend, client = gemini_backend
    vectors = backend.embed_multi([])
    assert vectors == []
    client.models.embed_content.assert_not_called()


def test_gemini_embed_multi_transient_error_raises_backend_error(gemini_backend):
    """transient 에러 (503 등) → BackendError(transient=True)."""
    backend, client = gemini_backend
    client.models.embed_content.side_effect = RuntimeError("503 unavailable")
    with pytest.raises(BackendError) as exc_info:
        backend.embed_multi(["x"])
    assert exc_info.value.transient is True
    assert exc_info.value.stage == "embed"


def test_gemini_embed_multi_hard_error_401(gemini_backend):
    """401 → BackendError(transient=False)."""
    backend, client = gemini_backend
    client.models.embed_content.side_effect = Exception("401 unauthorized")
    with pytest.raises(BackendError) as exc_info:
        backend.embed_multi(["x"])
    assert exc_info.value.transient is False


# ── Phase 2: BatchPoller — chat 결과 후 multi-input embed batch ────


@pytest.fixture
def poller_with_embed_chain(monkeypatch):
    """BatchPoller + chain_registry.get_chain('text_embed') stub.

    chat_image batch 성공 시 BatchPoller 가 chain.batch_embed 를 1회 호출하는지 검증.
    """
    store = MagicMock()
    chain_registry = MagicMock()
    analysis_queue = MagicMock()
    cfg = MagicMock()
    cfg.batch.poll_interval_seconds = 0.05
    cfg.grid_detect_alpha_color_weight = 0.5
    # backends.gemini.model_embed (dict access path)
    cfg.backends = {"gemini": {"model_embed": "gemini-embedding-001"}}

    # text_embed chain — batch_embed 가 vectors 반환
    embed_chain = MagicMock()
    embed_chain.batch_embed = MagicMock(
        return_value=([[0.1] * 8, [0.2] * 8, [0.3] * 8], "gemini"),
    )
    chain_registry.get_chain = MagicMock(return_value=embed_chain)

    registry = MagicMock()
    registry.list_labels = MagicMock(return_value=[])

    p = BatchPoller(
        store=store, chain_registry=chain_registry,
        analysis_queue=analysis_queue, cfg=cfg,
        registry=registry, library_dir=None,
    )
    return p, store, chain_registry, embed_chain


def _make_chat_image_job(modality: str = "chat_image"):
    import time
    return MagicMock(
        id=1, backend="gemini", backend_job_id="batches/x",
        modality=modality, state="running",
        expires_at=int(time.time()) + 172800,
    )


def _make_chat_image_response(text: str):
    """inlined_responses 의 1개 항목 — chat 결과."""
    item = MagicMock()
    item.error = None
    item.response = MagicMock()
    item.response.text = (
        '{"category":"other","style":"other","mood":[],"palette":[],'
        '"animation_hint":[],"subject":"s","description":"' + text + '","confidence":0.5}'
    )
    return item


def test_batch_poller_chat_image_persists_embeddings_via_batch_embed(
    poller_with_embed_chain,
):
    """chat_image batch 성공 → 모든 description 모아 batch_embed 1회 호출 + save_embedding N회."""
    p, store, chain_registry, embed_chain = poller_with_embed_chain
    job = _make_chat_image_job("chat_image")
    asset_rows = [
        MagicMock(id=101, path="a.png"),
        MagicMock(id=102, path="b.png"),
        MagicMock(id=103, path="c.png"),
    ]
    store.list_assets_in_batch.return_value = asset_rows

    # 응답 3개
    status = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED",
        inlined_responses=[
            _make_chat_image_response("desc-a"),
            _make_chat_image_response("desc-b"),
            _make_chat_image_response("desc-c"),
        ],
        file_name=None, error=None,
    )
    backend = MagicMock()
    backend.batch_get.return_value = status
    chain_registry.get_backend.return_value = backend
    store.list_active_batch_jobs.return_value = [job]

    p._poll_once()

    # 1) chain_registry.get_chain('text_embed') 호출됨
    chain_registry.get_chain.assert_any_call("text_embed")
    # 2) embed_chain.batch_embed 정확히 1회 호출 (모든 description 모아서)
    assert embed_chain.batch_embed.call_count == 1
    # 3) save_embedding 이 asset id 별로 호출됨
    embedding_save_ids = {
        c.args[0] for c in store.save_embedding.call_args_list
    }
    assert embedding_save_ids == {101, 102, 103}


def test_batch_poller_chat_spritesheet_persists_embeddings_via_batch_embed(
    poller_with_embed_chain,
):
    """chat_spritesheet batch 성공 → batch_embed 1회 + save_embedding N회."""
    p, store, chain_registry, embed_chain = poller_with_embed_chain
    job = _make_chat_image_job("chat_spritesheet")
    asset_rows = [
        MagicMock(id=201, path="sheet1.png"),
        MagicMock(id=202, path="sheet2.png"),
    ]
    store.list_assets_in_batch.return_value = asset_rows

    # embed_chain 의 반환 vectors 길이를 2 로 매칭
    embed_chain.batch_embed.return_value = ([[0.1] * 8, [0.2] * 8], "gemini")

    status = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED",
        inlined_responses=[
            _make_chat_image_response("sheet-a"),
            _make_chat_image_response("sheet-b"),
        ],
        file_name=None, error=None,
    )
    backend = MagicMock()
    backend.batch_get.return_value = status
    chain_registry.get_backend.return_value = backend
    store.list_active_batch_jobs.return_value = [job]

    p._poll_once()

    assert embed_chain.batch_embed.call_count == 1
    save_ids = {c.args[0] for c in store.save_embedding.call_args_list}
    assert save_ids == {201, 202}


def test_batch_poller_chat_audio_persists_embeddings_via_batch_embed(
    poller_with_embed_chain,
):
    """chat_audio batch 성공 → batch_embed 1회 + save_embedding N회."""
    p, store, chain_registry, embed_chain = poller_with_embed_chain
    job = _make_chat_image_job("chat_audio")
    asset_rows = [
        MagicMock(id=301, path="s1.wav"),
        MagicMock(id=302, path="s2.wav"),
    ]
    store.list_assets_in_batch.return_value = asset_rows

    embed_chain.batch_embed.return_value = ([[0.1] * 8, [0.2] * 8], "gemini")

    # chat_audio payload — audio validator schema 와 호환
    def _audio_resp(desc: str):
        item = MagicMock()
        item.error = None
        item.response = MagicMock()
        item.response.text = (
            '{"sound_category":"sfx","sound_mood":[],"sound_timbre":[],'
            '"sound_environment":[],"sound_instrument":[],'
            '"sound_use":[],"sound_tempo":"medium","sound_intensity":"low",'
            '"sound_genre":"other","sound_voice_type":"none",'
            '"description":"' + desc + '","confidence":0.5}'
        )
        return item

    status = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED",
        inlined_responses=[_audio_resp("a"), _audio_resp("b")],
        file_name=None, error=None,
    )
    backend = MagicMock()
    backend.batch_get.return_value = status
    chain_registry.get_backend.return_value = backend
    store.list_active_batch_jobs.return_value = [job]

    p._poll_once()

    assert embed_chain.batch_embed.call_count == 1
    save_ids = {c.args[0] for c in store.save_embedding.call_args_list}
    assert save_ids == {301, 302}


def test_batch_poller_embed_failure_does_not_fail_chat_persist(
    poller_with_embed_chain, caplog,
):
    """batch_embed 가 예외를 던져도 chat asset 들은 ok 상태로 persist 됨."""
    p, store, chain_registry, embed_chain = poller_with_embed_chain
    embed_chain.batch_embed.side_effect = BackendError(
        backend="gemini", stage="embed_multi", transient=True,
    )
    job = _make_chat_image_job("chat_image")
    asset_rows = [MagicMock(id=401, path="x.png")]
    store.list_assets_in_batch.return_value = asset_rows
    status = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED",
        inlined_responses=[_make_chat_image_response("d")],
        file_name=None, error=None,
    )
    backend = MagicMock()
    backend.batch_get.return_value = status
    chain_registry.get_backend.return_value = backend
    store.list_active_batch_jobs.return_value = [job]

    p._poll_once()

    # chat asset 은 'ok' 로 mark
    state_calls = [
        c for c in store.mark_asset_state.call_args_list
        if c.args[0] == 401
    ]
    assert state_calls, "asset should be marked 'ok' even if embed fails"
    # embedding 은 저장 안 됨 (또는 0 dim)
    save_embedding_calls = [
        c for c in store.save_embedding.call_args_list
        if c.args[0] == 401
    ]
    assert save_embedding_calls == []


def test_batch_poller_text_embed_modality_unchanged_path(
    poller_with_embed_chain,
):
    """기존 text_embed (Gemini Batch API) modality 경로는 변경 없음 — save_embedding 직접 호출."""
    p, store, chain_registry, embed_chain = poller_with_embed_chain
    job = _make_chat_image_job("text_embed")
    asset_rows = [MagicMock(id=501, path="x.png")]
    store.list_assets_in_batch.return_value = asset_rows

    embed_resp = MagicMock()
    embed_resp.error = None
    embed_resp.embedding = MagicMock(values=[0.5] * 8)
    embed_resp.response = MagicMock()  # response 가 None 이면 skip 됨
    status = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED",
        inlined_responses=[embed_resp],
        file_name=None, error=None,
    )
    backend = MagicMock()
    backend.batch_get.return_value = status
    chain_registry.get_backend.return_value = backend
    store.list_active_batch_jobs.return_value = [job]

    p._poll_once()

    # text_embed 자체 경로 — save_embedding 1회 (501)
    assert store.save_embedding.call_args_list, "text_embed modality must save embedding"
    save_ids = {c.args[0] for c in store.save_embedding.call_args_list}
    assert 501 in save_ids
    # chat_* 경로의 batch_embed 는 호출 안 됨 (text_embed modality 자체)
    assert embed_chain.batch_embed.call_count == 0
