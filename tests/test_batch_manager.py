"""Phase 3 task 3.1+3.2 — BatchManager.try_submit + _do_submit."""

from unittest.mock import MagicMock, patch

import pytest

from assetcache.core.batch.manager import BatchManager
from assetcache.core.batch.types import BatchChatRequest
from assetcache.core.llm.base import ChatMessage


def _make_fake_requests(rows):
    """테스트용 가짜 BatchChatRequest 목록 (파일 I/O 없이)."""
    return [
        BatchChatRequest(
            asset_id=r.id,
            messages=[ChatMessage(role="user", content=f"test{r.id}")],
            force_json=True,
        )
        for r in rows
    ]


@pytest.fixture
def manager_factory():
    """Factory — produce (manager, store, chain_registry, analysis_queue, backend_mock).

    _build_chat_requests 는 파일 I/O 를 수행하므로 기본적으로 fake 구현으로 patch.
    특정 테스트에서 monkeypatch 로 override 가능.
    """
    def make(*, toggle="auto", chain_first="gemini", pending_count=0,
            threshold=30, supports_batch=True):
        store = MagicMock()
        store.count_pending_by_modality.return_value = pending_count
        store.fetch_pending_by_modality.return_value = [
            MagicMock(id=i) for i in range(pending_count)
        ]
        store.save_batch_job.return_value = 0  # default unless overridden

        backend_mock = MagicMock()
        backend_mock.supports_batch.return_value = supports_batch
        backend_mock.info.name = chain_first if chain_first else "none"
        backend_mock.batch_chat.return_value = "batches/test"
        backend_mock.batch_embed.return_value = "batches/test"

        chain_registry = MagicMock()
        chain_registry.first_backend.return_value = backend_mock if chain_first else None

        analysis_queue = MagicMock()
        cfg = MagicMock()
        cfg.batch.toggle = toggle
        cfg.batch.threshold = threshold
        cfg.batch.expiry_grace_seconds = 172800

        m = BatchManager(
            store=store, chain_registry=chain_registry,
            analysis_queue=analysis_queue, cfg=cfg,
        )
        # 파일 I/O 없이 동작하도록 _build_chat_requests 기본 patch
        m._build_chat_requests = lambda modality, rows: _make_fake_requests(rows)
        return m, store, chain_registry, analysis_queue, backend_mock
    return make


def test_try_submit_returns_none_when_forced_off(manager_factory):
    m, store, *_ = manager_factory(toggle="forced_off", pending_count=100)
    assert m.try_submit("chat_image") is None
    store.fetch_pending_by_modality.assert_not_called()


def test_try_submit_returns_none_when_chain_first_not_gemini(manager_factory):
    m, store, *_ = manager_factory(chain_first="ollama", pending_count=100)
    assert m.try_submit("chat_image") is None
    store.fetch_pending_by_modality.assert_not_called()


def test_try_submit_returns_none_when_chain_first_no_batch_support(manager_factory):
    m, store, *_ = manager_factory(supports_batch=False, pending_count=100)
    assert m.try_submit("chat_image") is None


def test_try_submit_returns_none_when_below_threshold_in_auto(manager_factory):
    m, store, *_ = manager_factory(toggle="auto", threshold=30, pending_count=10)
    assert m.try_submit("chat_image") is None
    store.fetch_pending_by_modality.assert_not_called()


def test_try_submit_proceeds_at_threshold_in_auto(manager_factory):
    m, store, _, aq, backend = manager_factory(toggle="auto", threshold=30, pending_count=30)
    store.save_batch_job.return_value = 7
    job_id = m.try_submit("chat_image")
    assert job_id == 7


def test_try_submit_proceeds_below_threshold_in_forced_on(manager_factory):
    m, store, _, aq, backend = manager_factory(toggle="forced_on", threshold=30, pending_count=5)
    store.save_batch_job.return_value = 3
    job_id = m.try_submit("chat_image")
    assert job_id == 3


def test_do_submit_creates_batch_jobs_row_for_chat_image(manager_factory):
    m, store, _, aq, backend = manager_factory(pending_count=30)
    store.save_batch_job.return_value = 42
    asset_ids = [r.id for r in store.fetch_pending_by_modality.return_value]
    job_id = m.try_submit("chat_image")
    assert job_id == 42
    store.mark_assets_batch_queued.assert_called_once_with(asset_ids)
    backend.batch_chat.assert_called_once()
    save_kw = store.save_batch_job.call_args.kwargs
    assert save_kw["backend"] == "gemini"
    assert save_kw["modality"] == "chat_image"
    assert save_kw["backend_job_id"] == "batches/test"
    assert save_kw["asset_count"] == 30
    store.mark_assets_batch_submitted.assert_called_once_with(asset_ids, 42)
    aq.dequeue_assets.assert_called_once_with(asset_ids)


def test_do_submit_rollback_when_backend_fails(manager_factory):
    from assetcache.core.llm.base import BackendError
    m, store, _, aq, backend = manager_factory(pending_count=30)
    backend.batch_chat.side_effect = BackendError(
        backend="gemini", stage="batch_chat_image", transient=True,
    )
    asset_ids = [r.id for r in store.fetch_pending_by_modality.return_value]
    job_id = m.try_submit("chat_image")
    assert job_id is None
    # Rollback: 각 asset_id 마다 mark_asset_batch_state('none')
    rollback_calls = [
        c for c in store.mark_asset_batch_state.call_args_list
        if c.args[1] == "none"
    ]
    assert len(rollback_calls) == 30
    store.save_batch_job.assert_not_called()
    aq.dequeue_assets.assert_not_called()


def test_do_submit_text_embed_calls_batch_embed(manager_factory):
    m, store, _, aq, backend = manager_factory(pending_count=30)
    store.save_batch_job.return_value = 5
    backend.batch_embed.return_value = "batches/embed-1"
    m.try_submit("text_embed")
    backend.batch_embed.assert_called_once()
    backend.batch_chat.assert_not_called()


def test_do_submit_caps_at_threshold(manager_factory):
    m, store, _, aq, backend = manager_factory(
        toggle="forced_on", pending_count=100, threshold=30,
    )
    store.save_batch_job.return_value = 1
    m.try_submit("chat_image")
    fetch_kw = store.fetch_pending_by_modality.call_args.kwargs
    assert fetch_kw["limit"] == 30


def test_do_submit_filters_out_oserror_skipped_assets(manager_factory, monkeypatch):
    """OSError 로 일부 asset 빌드 실패 시 — 실패 항목은 batch_state='none' 으로 복구 + asset_count 는 filtered."""
    m, store, _, aq, backend = manager_factory(toggle="forced_on", pending_count=5)
    store.save_batch_job.return_value = 100
    # _build_chat_requests 가 5개 중 2개 skip 하도록 patch
    from assetcache.core.batch.types import BatchChatRequest
    from assetcache.core.llm.base import ChatMessage
    def build_partial(modality, rows):
        # 첫 3개만 build, 나머지 2 (id 3, 4) 는 OSError 처럼 skip
        return [
            BatchChatRequest(
                asset_id=r.id,
                messages=[ChatMessage(role="user", content=f"x{r.id}")],
                force_json=True,
            )
            for r in rows[:3]
        ]
    monkeypatch.setattr(m, "_build_chat_requests", build_partial)
    job_id = m.try_submit("chat_image")
    assert job_id == 100
    # asset_count = 3 (filtered), not 5
    save_kw = store.save_batch_job.call_args.kwargs
    assert save_kw["asset_count"] == 3
    # mark_assets_batch_submitted 가 3개 만 받음
    submitted_call = store.mark_assets_batch_submitted.call_args
    assert len(submitted_call.args[0]) == 3
    assert submitted_call.args[0] == [0, 1, 2]
    # skipped (id 3, 4) 가 'none' 으로 복구
    skipped_calls = [
        c for c in store.mark_asset_batch_state.call_args_list
        if c.args[1] == "none"
    ]
    assert len(skipped_calls) == 2
    skipped_ids = {c.args[0] for c in skipped_calls}
    assert skipped_ids == {3, 4}


def test_do_submit_aborts_when_all_assets_fail_to_build(manager_factory, monkeypatch):
    """모든 asset OSError → empty requests → submit 호출 안 됨, 모두 'none' rollback."""
    m, store, _, aq, backend = manager_factory(toggle="forced_on", pending_count=3)
    monkeypatch.setattr(m, "_build_chat_requests", lambda mod, rows: [])
    job_id = m.try_submit("chat_image")
    assert job_id is None
    backend.batch_chat.assert_not_called()
    store.save_batch_job.assert_not_called()
    # 모든 3 asset → 'none'
    rollback_calls = [
        c for c in store.mark_asset_batch_state.call_args_list
        if c.args[1] == "none"
    ]
    assert len(rollback_calls) == 3


def test_cancel_calls_backend_cancel_and_marks_all_failed(manager_factory):
    m, store, _, aq, backend = manager_factory(pending_count=0)
    store.get_batch_job.return_value = MagicMock(
        id=1, backend="gemini", modality="chat_image",
        backend_job_id="batches/x", state="submitted",
    )
    store.list_assets_in_batch.return_value = [MagicMock(id=10), MagicMock(id=11)]
    # chain_registry.get_backend mock 보강 — manager_factory 가 first_backend 만 가짐
    m._chain.get_backend.return_value = backend
    m.cancel(1)
    backend.batch_cancel.assert_called_once_with("batches/x")
    # 모든 asset 'failed' + interactive 재enqueue
    failed_calls = [
        c for c in store.mark_asset_batch_state.call_args_list
        if c.args[1] == "failed"
    ]
    assert len(failed_calls) == 2
    assert aq.enqueue_asset.call_count == 2
    # batch_job state = cancelled
    store.update_batch_job_state.assert_called_once()
    kw = store.update_batch_job_state.call_args.kwargs
    assert kw["state"] == "cancelled"


def test_cancel_idempotent_on_already_terminal(manager_factory):
    m, store, *_ = manager_factory()
    store.get_batch_job.return_value = MagicMock(
        id=1, state="succeeded",
    )
    m.cancel(1)
    # 이미 succeeded — backend.batch_cancel 호출 안 함
    # store.update_batch_job_state 호출 안 함
    store.update_batch_job_state.assert_not_called()
    m._chain.get_backend.assert_not_called()


def test_cancel_missing_job_returns_silently(manager_factory):
    m, store, *_ = manager_factory()
    store.get_batch_job.return_value = None
    m.cancel(99999)  # 예외 없음
    store.list_assets_in_batch.assert_not_called()
