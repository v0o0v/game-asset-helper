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
