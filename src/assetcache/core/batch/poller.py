"""BatchPoller — daemon thread 가 active batch jobs 를 주기 polling.

Phase 4 task 4.1: skeleton + run loop + stop.
Phase 4 task 4.2: _poll_job state mapping + expiry safety.
Phase 4 task 4.3: _handle_succeeded (modality 별 persist + backend_used).
Phase 4 task 4.4: _handle_terminal_failure (failed/cancelled/expired → interactive 재enqueue).
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..analysis_queue import AnalysisQueue
    from ..llm.registry import BackendRegistry
    from ..store import Store
    from ...config import Config

log = logging.getLogger(__name__)


class BatchPoller(threading.Thread):
    """daemon thread — `cfg.batch.poll_interval_seconds` 마다 active job 폴링.

    부팅 시 즉시 1회 sweep + 이후 주기 wake.
    단일 job 실패가 다른 job polling 차단 X (try/except 내부).
    """

    def __init__(
        self,
        *,
        store: "Store",
        chain_registry: "BackendRegistry",
        analysis_queue: "AnalysisQueue",
        cfg: "Config",
    ) -> None:
        super().__init__(daemon=True, name="assetcache-batch-poller")
        self._store = store
        self._chain = chain_registry
        self._aq = analysis_queue
        self._cfg = cfg
        self._stop_event = threading.Event()

    def stop(self, timeout: float = 5.0) -> None:
        """Signal stop + join. idempotent (stop() 두 번 호출 안전)."""
        self._stop_event.set()
        # 만약 thread 가 아직 시작 안 됐으면 join() 이 즉시 return
        if self.is_alive():
            self.join(timeout=timeout)

    def run(self) -> None:
        # 부팅 시 즉시 1회 sweep (재개 보장)
        self._poll_once()
        while not self._stop_event.is_set():
            interval = max(0.01, float(self._cfg.batch.poll_interval_seconds))
            if self._stop_event.wait(interval):
                break
            self._poll_once()

    def _poll_once(self) -> None:
        try:
            jobs = self._store.list_active_batch_jobs()
        except Exception:
            log.exception("list_active_batch_jobs failed — skipping sweep")
            return
        for job in jobs:
            try:
                self._poll_job(job)
            except Exception:
                log.exception("poll_job failed for job_id=%s", getattr(job, "id", "?"))

    def _poll_job(self, job) -> None:
        """Task 4.2 에서 실 구현 — state mapping + 만료 safety + 결과 처리 dispatch."""
        pass

    def _handle_succeeded(self, job, status, backend) -> None:
        """Task 4.3 에서 실 구현."""
        pass

    def _handle_terminal_failure(self, job, terminal_state, error) -> None:
        """Task 4.4 에서 실 구현."""
        pass
