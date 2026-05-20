"""Phase 3 task 3.1+3.2 — BatchManager.try_submit + _do_submit."""

from unittest.mock import MagicMock

import pytest

from assetcache.core.batch.manager import BatchManager


@pytest.fixture
def manager_factory():
    """Factory — produce (manager, store, chain_registry, analysis_queue, backend_mock)."""
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
