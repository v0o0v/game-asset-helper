"""Phase 4 — BatchPoller daemon thread lifecycle."""

import time
from unittest.mock import MagicMock

import pytest

from assetcache.core.batch.poller import BatchPoller


@pytest.fixture
def poller_factory():
    def make(*, poll_interval=0.05):
        store = MagicMock()
        store.list_active_batch_jobs.return_value = []
        chain_registry = MagicMock()
        analysis_queue = MagicMock()
        cfg = MagicMock()
        cfg.batch.poll_interval_seconds = poll_interval
        p = BatchPoller(
            store=store, chain_registry=chain_registry,
            analysis_queue=analysis_queue, cfg=cfg,
        )
        return p, store
    return make


def test_poller_starts_and_stops(poller_factory):
    p, store = poller_factory()
    p.start()
    assert p.is_alive()
    p.stop(timeout=1.0)
    assert not p.is_alive()


def test_poller_calls_list_active_at_boot(poller_factory):
    p, store = poller_factory()
    p.start()
    time.sleep(0.1)  # 부팅 sweep 가 동작할 시간
    p.stop(timeout=1.0)
    assert store.list_active_batch_jobs.call_count >= 1


def test_poller_polls_periodically(poller_factory):
    p, store = poller_factory(poll_interval=0.05)
    p.start()
    time.sleep(0.25)  # ~5 ticks
    p.stop(timeout=1.0)
    # boot + ~4 periodic = 5+
    assert store.list_active_batch_jobs.call_count >= 3


def test_poll_once_swallows_single_job_failure(poller_factory):
    p, store = poller_factory()
    job_a = MagicMock(id=1)
    job_b = MagicMock(id=2)
    store.list_active_batch_jobs.return_value = [job_a, job_b]
    poll_call_count = [0]
    def faulty_poll_job(job):
        poll_call_count[0] += 1
        if job.id == 1:
            raise RuntimeError("network error")
    p._poll_job = faulty_poll_job
    p._poll_once()
    # 둘 다 시도되어야
    assert poll_call_count[0] == 2


def test_is_daemon(poller_factory):
    p, _ = poller_factory()
    assert p.daemon is True


def test_poll_job_running_updates_state(poller_factory):
    import time
    from assetcache.core.batch.types import GeminiBatchStatus
    p, store = poller_factory()
    job = MagicMock(id=1, backend="gemini", backend_job_id="batches/x",
                    modality="chat_image", state="submitted",
                    expires_at=int(time.time()) + 172800)
    store.list_active_batch_jobs.return_value = [job]
    backend = MagicMock()
    backend.batch_get.return_value = GeminiBatchStatus(
        state="JOB_STATE_RUNNING", inlined_responses=None,
        file_name=None, error=None,
    )
    p._chain.get_backend.return_value = backend
    p._poll_once()
    store.update_batch_job_state.assert_called_with(1, state="running")


def test_poll_job_succeeded_calls_handle_succeeded(poller_factory, monkeypatch):
    import time
    from assetcache.core.batch.types import GeminiBatchStatus
    p, store = poller_factory()
    job = MagicMock(id=1, backend="gemini", backend_job_id="batches/x",
                    modality="chat_image", state="running",
                    expires_at=int(time.time()) + 172800)
    store.list_active_batch_jobs.return_value = [job]
    status = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED", inlined_responses=[MagicMock()],
        file_name=None, error=None,
    )
    backend = MagicMock()
    backend.batch_get.return_value = status
    p._chain.get_backend.return_value = backend
    handle = MagicMock()
    monkeypatch.setattr(p, "_handle_succeeded", handle)
    p._poll_once()
    handle.assert_called_once_with(job, status, backend)


def test_poll_job_failed_terminal(poller_factory, monkeypatch):
    import time
    from assetcache.core.batch.types import GeminiBatchStatus
    p, store = poller_factory()
    job = MagicMock(id=1, backend="gemini", backend_job_id="batches/x",
                    modality="chat_image", state="running",
                    expires_at=int(time.time()) + 172800)
    store.list_active_batch_jobs.return_value = [job]
    status = GeminiBatchStatus(
        state="JOB_STATE_FAILED", inlined_responses=None,
        file_name=None, error="oops",
    )
    backend = MagicMock()
    backend.batch_get.return_value = status
    p._chain.get_backend.return_value = backend
    handle = MagicMock()
    monkeypatch.setattr(p, "_handle_terminal_failure", handle)
    p._poll_once()
    handle.assert_called_once_with(job, "failed", "oops")


def test_poll_job_past_expiry_marked_expired(poller_factory, monkeypatch):
    import time
    p, store = poller_factory()
    job = MagicMock(id=1, backend="gemini", backend_job_id="batches/x",
                    modality="chat_image", state="submitted",
                    expires_at=int(time.time()) - 10)  # 이미 만료
    store.list_active_batch_jobs.return_value = [job]
    handle = MagicMock()
    monkeypatch.setattr(p, "_handle_terminal_failure", handle)
    backend = MagicMock()
    p._chain.get_backend.return_value = backend
    p._poll_once()
    # safety net — backend.batch_get 호출 안 됨, 바로 terminal_failure('expired')
    backend.batch_get.assert_not_called()
    handle.assert_called_once()
    args = handle.call_args.args
    assert args[0] is job
    assert args[1] == "expired"


def test_poll_job_no_state_change_no_update(poller_factory):
    import time
    from assetcache.core.batch.types import GeminiBatchStatus
    p, store = poller_factory()
    # 이미 'running' 상태인데 다시 RUNNING — update 안 함
    job = MagicMock(id=1, backend="gemini", backend_job_id="batches/x",
                    modality="chat_image", state="running",
                    expires_at=int(time.time()) + 172800)
    store.list_active_batch_jobs.return_value = [job]
    backend = MagicMock()
    backend.batch_get.return_value = GeminiBatchStatus(
        state="JOB_STATE_RUNNING", inlined_responses=None,
        file_name=None, error=None,
    )
    p._chain.get_backend.return_value = backend
    p._poll_once()
    store.update_batch_job_state.assert_not_called()


def test_handle_succeeded_image_modality_persists(poller_factory):
    from assetcache.core.batch.types import GeminiBatchStatus
    p, store = poller_factory()
    job = MagicMock(id=1, modality="chat_image", asset_count=2)
    store.list_assets_in_batch.return_value = [
        MagicMock(id=10), MagicMock(id=11),
    ]
    # 첫번째 응답 성공 / 두번째 실패
    resp_ok = MagicMock()
    resp_ok.response.text = '{"labels": []}'
    resp_ok.error = None
    resp_fail = MagicMock()
    resp_fail.response = None
    resp_fail.error = "internal"
    status = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED",
        inlined_responses=[resp_ok, resp_fail],
        file_name=None, error=None,
    )
    backend = MagicMock()
    p._handle_succeeded(job, status, backend)
    # 성공: asset 10 → mark_asset_backends(image='gemini') + batch_state='completed'
    store.mark_asset_backends.assert_any_call(10, image="gemini")
    completed_calls = [
        c for c in store.mark_asset_batch_state.call_args_list
        if c.args[1] == "completed"
    ]
    assert (10, "completed") in [tuple(c.args) for c in completed_calls]
    # 실패: asset 11 → batch_state='failed' + enqueue
    failed_calls = [
        tuple(c.args) for c in store.mark_asset_batch_state.call_args_list
        if c.args[1] == "failed"
    ]
    assert (11, "failed") in failed_calls
    p._aq.enqueue_asset.assert_called_with(11)
    # 최종 job state 'succeeded' + success_count=1, failure_count=1
    store.update_batch_job_state.assert_called_once()
    kw = store.update_batch_job_state.call_args.kwargs
    assert kw["state"] == "succeeded"
    assert kw["success_count"] == 1
    assert kw["failure_count"] == 1


def test_handle_succeeded_audio_modality(poller_factory):
    from assetcache.core.batch.types import GeminiBatchStatus
    p, store = poller_factory()
    job = MagicMock(id=1, modality="chat_audio", asset_count=1)
    store.list_assets_in_batch.return_value = [MagicMock(id=20)]
    resp = MagicMock()
    resp.response.text = '{"category": "music"}'
    resp.error = None
    status = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED", inlined_responses=[resp],
        file_name=None, error=None,
    )
    p._handle_succeeded(job, status, MagicMock())
    store.mark_asset_backends.assert_called_with(20, audio="gemini")


def test_handle_succeeded_embed_modality(poller_factory):
    from assetcache.core.batch.types import GeminiBatchStatus
    p, store = poller_factory()
    job = MagicMock(id=1, modality="text_embed", asset_count=1)
    store.list_assets_in_batch.return_value = [MagicMock(id=30)]
    resp = MagicMock()
    resp.embedding.values = [0.1, 0.2, 0.3]
    resp.error = None
    status = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED", inlined_responses=[resp],
        file_name=None, error=None,
    )
    p._cfg.backends.gemini.model_embed = "gemini-embedding-001"
    p._handle_succeeded(job, status, MagicMock())
    store.save_embedding.assert_called_once()
    args = store.save_embedding.call_args.args
    assert args[0] == 30  # asset_id
    # backend_used embed='gemini'
    store.mark_asset_backends.assert_called_with(30, embed="gemini")


def test_handle_succeeded_file_destination_marks_expired(poller_factory):
    from assetcache.core.batch.types import GeminiBatchStatus
    p, store = poller_factory()
    job = MagicMock(id=1, modality="chat_image", asset_count=10)
    status = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED", inlined_responses=None,
        file_name="files/big", error=None,
    )
    p._handle_succeeded(job, status, MagicMock())
    # v0.2.1 — file destination 미지원 → state='expired'
    store.update_batch_job_state.assert_called_once()
    kw = store.update_batch_job_state.call_args.kwargs
    assert kw["state"] == "expired"


def test_handle_succeeded_parse_error_falls_back_to_interactive(poller_factory):
    from assetcache.core.batch.types import GeminiBatchStatus
    p, store = poller_factory()
    job = MagicMock(id=1, modality="chat_image", asset_count=1)
    store.list_assets_in_batch.return_value = [MagicMock(id=40)]
    resp = MagicMock()
    resp.response.text = "not valid json"
    resp.error = None
    status = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED", inlined_responses=[resp],
        file_name=None, error=None,
    )
    p._handle_succeeded(job, status, MagicMock())
    # parse 실패 → batch_state='failed' + interactive 재enqueue
    failed_calls = [
        tuple(c.args) for c in store.mark_asset_batch_state.call_args_list
        if c.args[1] == "failed"
    ]
    assert (40, "failed") in failed_calls
    p._aq.enqueue_asset.assert_called_with(40)


def test_handle_terminal_failure_failed_reenqueues_all(poller_factory):
    p, store = poller_factory()
    job = MagicMock(id=1, modality="chat_image")
    store.list_assets_in_batch.return_value = [
        MagicMock(id=1), MagicMock(id=2), MagicMock(id=3),
    ]
    p._handle_terminal_failure(job, "failed", "internal error")
    # 모든 3 asset 'failed' + interactive 재enqueue
    failed_calls = [
        c for c in store.mark_asset_batch_state.call_args_list
        if c.args[1] == "failed"
    ]
    assert len(failed_calls) == 3
    assert p._aq.enqueue_asset.call_count == 3
    # job state 갱신
    store.update_batch_job_state.assert_called_once()
    kw = store.update_batch_job_state.call_args.kwargs
    assert kw["state"] == "failed"
    assert kw["error"] == "internal error"


def test_handle_terminal_failure_expired(poller_factory):
    p, store = poller_factory()
    job = MagicMock(id=1, modality="chat_image")
    store.list_assets_in_batch.return_value = []
    p._handle_terminal_failure(job, "expired", "expires_at passed")
    store.update_batch_job_state.assert_called_once()
    kw = store.update_batch_job_state.call_args.kwargs
    assert kw["state"] == "expired"
    assert kw["error"] == "expires_at passed"


def test_handle_terminal_failure_cancelled(poller_factory):
    p, store = poller_factory()
    job = MagicMock(id=1, modality="chat_image")
    store.list_assets_in_batch.return_value = [MagicMock(id=99)]
    p._handle_terminal_failure(job, "cancelled", None)
    store.update_batch_job_state.assert_called_once()
    kw = store.update_batch_job_state.call_args.kwargs
    assert kw["state"] == "cancelled"
    p._aq.enqueue_asset.assert_called_with(99)
