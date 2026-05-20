"""BatchPoller — daemon thread 가 active batch jobs 를 주기 polling.

Phase 4 task 4.1: skeleton + run loop + stop.
Phase 4 task 4.2: _poll_job state mapping + expiry safety.
Phase 4 task 4.3: _handle_succeeded (modality 별 persist + backend_used).
Phase 4 task 4.4: _handle_terminal_failure (failed/cancelled/expired → interactive 재enqueue).
"""

from __future__ import annotations

import json
import logging
import struct
import threading
import time
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from ..analysis_queue import AnalysisQueue
    from ..llm.registry import BackendRegistry
    from ..store import Store
    from ...config import Config

log = logging.getLogger(__name__)


def _serialize_vec(vec: list[float]) -> bytes:
    """EmbeddingEncoder.encode_text 와 동일한 float32 little-endian blob 반환.

    ``np.asarray(vec, dtype=np.float32).tobytes()`` 와 identical.
    decode_vector(blob, dim) 으로 round-trip 가능.
    """
    arr = np.asarray(vec, dtype=np.float32)
    return arr.tobytes()


# Gemini Job state → (DB state, terminal_flag | None)
# terminal_flag None  = transient (PENDING / RUNNING)
# terminal_flag str   = terminal state name
_GEMINI_STATE_MAP: dict[str, tuple[str, str | None]] = {
    "JOB_STATE_PENDING": ("submitted", None),
    "JOB_STATE_RUNNING": ("running", None),
    "JOB_STATE_SUCCEEDED": ("succeeded", "succeeded"),
    "JOB_STATE_FAILED": ("failed", "failed"),
    "JOB_STATE_CANCELLED": ("cancelled", "cancelled"),
    "JOB_STATE_EXPIRED": ("expired", "expired"),
}


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
        """Poll one job — state mapping + expiry safety net + result dispatch."""
        now = int(time.time())
        # 안전망: 만료 → terminal failure 강제 (backend.batch_get 안 호출)
        if now > job.expires_at and job.state in ("submitted", "running"):
            self._handle_terminal_failure(job, "expired", "expires_at passed")
            return
        backend = self._chain.get_backend(job.backend)
        if backend is None:
            log.warning("backend %s not registered for job %d", job.backend, job.id)
            return
        status = backend.batch_get(job.backend_job_id)
        db_state, terminal = _GEMINI_STATE_MAP.get(status.state, ("running", None))
        if terminal is None:
            # transient — DB 만 갱신 (state 변경 시)
            if db_state != job.state:
                self._store.update_batch_job_state(job.id, state=db_state)
            return
        if terminal == "succeeded":
            self._handle_succeeded(job, status, backend)
        else:
            self._handle_terminal_failure(job, terminal, status.error)

    def _handle_succeeded(self, job, status, backend) -> None:
        """JOB_STATE_SUCCEEDED — modality 별 persist + 부분 실패 fallback.

        v0.2.1: inline destination 만 지원. file destination 은 expired 처리.
        """
        if status.inlined_responses is None:
            if status.file_name:
                log.warning(
                    "batch job %d file destination (%s) — v0.2.1 미지원, expired 처리",
                    job.id, status.file_name,
                )
                self._store.update_batch_job_state(
                    job.id,
                    state="expired",
                    completed_at=int(time.time()),
                    error="file destination not supported in v0.2.1",
                )
                return
            # 응답 없음 — 빈 succeeded 마킹
            self._store.update_batch_job_state(
                job.id,
                state="succeeded",
                completed_at=int(time.time()),
            )
            return

        asset_rows = self._store.list_assets_in_batch(job.id)
        success_count = 0
        failure_count = 0

        for asset, resp in zip(asset_rows, status.inlined_responses, strict=False):
            # 개별 응답 오류 처리
            if getattr(resp, "error", None) is not None or getattr(resp, "response", None) is None:
                self._fail_asset(asset)
                failure_count += 1
                continue

            try:
                if job.modality == "chat_image":
                    payload = json.loads(resp.response.text)
                    self._persist_image_payload(asset.id, payload)
                    self._store.mark_asset_backends(asset.id, image="gemini")
                elif job.modality == "chat_audio":
                    payload = json.loads(resp.response.text)
                    self._persist_audio_payload(asset.id, payload)
                    self._store.mark_asset_backends(asset.id, audio="gemini")
                elif job.modality == "text_embed":
                    vec = list(resp.embedding.values)
                    blob = _serialize_vec(vec)
                    model = self._cfg.backends.gemini.model_embed
                    self._store.save_embedding(asset.id, model, blob, len(vec))
                    self._store.mark_asset_backends(asset.id, embed="gemini")
                else:
                    raise ValueError(f"unknown modality {job.modality!r}")

                self._store.mark_asset_batch_state(asset.id, "completed")
                success_count += 1
            except Exception:
                log.exception(
                    "batch result persist 실패 — asset_id=%d job_id=%d",
                    asset.id, job.id,
                )
                self._fail_asset(asset)
                failure_count += 1

        self._store.update_batch_job_state(
            job.id,
            state="succeeded",
            completed_at=int(time.time()),
            success_count=success_count,
            failure_count=failure_count,
        )

    def _fail_asset(self, asset) -> None:
        """단일 asset 실패 — batch_state='failed' + interactive 재시도 enqueue."""
        self._store.mark_asset_batch_state(asset.id, "failed")
        self._aq.enqueue_asset(asset.id)

    def _persist_image_payload(self, asset_id: int, payload: dict) -> None:
        """이미지 결과 최소 persist — 빈 라벨 + analyzed_at 마킹.

        TODO M12: SpriteAnalyzer payload 파서 통합으로 실제 라벨 추출.
        현재 v0.2.1: 완료 표시만 하고 라벨은 비워둔다.
        """
        self._store.save_asset_labels(asset_id, [])
        self._store.mark_asset_state(
            asset_id, "ok", error=None, analyzed_at=int(time.time()),
        )

    def _persist_audio_payload(self, asset_id: int, payload: dict) -> None:
        """오디오 결과 최소 persist — 빈 라벨 + analyzed_at 마킹.

        TODO M12: SoundAnalyzer payload 파서 통합으로 실제 라벨 추출.
        현재 v0.2.1: 완료 표시만 하고 라벨은 비워둔다.
        """
        self._store.save_asset_labels(asset_id, [])
        self._store.mark_asset_state(
            asset_id, "ok", error=None, analyzed_at=int(time.time()),
        )

    def _handle_terminal_failure(self, job, terminal_state, error) -> None:
        """Task 4.4 에서 실 구현."""
        pass
