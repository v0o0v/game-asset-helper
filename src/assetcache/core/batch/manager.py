"""BatchManager — modality 별 batch 진입 결정 + Gemini submit + rollback.

Phase 3 task 3.1+3.2 — toggle/chain/threshold 결정 트리 + race lock.
Phase 3 task 3.3 에서 _build_chat_requests / _build_embed_texts 가 분석 이미지/오디오
실 바이트 로딩으로 교체됨 (현재는 placeholder).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from .types import BatchChatRequest

if TYPE_CHECKING:
    from ..analysis_queue import AnalysisQueue
    from ..llm.registry import BackendRegistry
    from ..store import Store
    from ...config import Config

log = logging.getLogger(__name__)

_MODALITIES = ("chat_image", "chat_audio", "text_embed")


class BatchManager:
    """Gemini Batch API 진입 결정 + submission + rollback.

    `AnalysisQueue.enqueue_*` 가 매번 호출 — toggle/chain/threshold 검사 후
    조건 충족 시 batch 제출. modality 별 race lock 으로 중복 submit 방지.
    """

    def __init__(
        self,
        *,
        store: "Store",
        chain_registry: "BackendRegistry",
        analysis_queue: "AnalysisQueue",
        cfg: "Config",
    ) -> None:
        self._store = store
        self._chain = chain_registry
        self._aq = analysis_queue
        self._cfg = cfg
        self._locks = {m: threading.Lock() for m in _MODALITIES}

    def try_submit(self, modality: str) -> int | None:
        """Try to submit a batch job for `modality`. Return batch_jobs.id or None.

        Decision flow:
        1. modality 유효성 check
        2. cfg.batch.toggle == 'forced_off' → None
        3. chain[modality][0] not gemini / no batch support → None
        4. auto 모드 + pending < threshold → None
        5. race lock acquire (non-blocking) → _do_submit
        """
        if modality not in _MODALITIES:
            log.warning("try_submit invalid modality: %s", modality)
            return None
        toggle = self._cfg.batch.toggle
        if toggle == "forced_off":
            return None
        backend = self._chain.first_backend(modality)
        if backend is None:
            return None
        if backend.info.name != "gemini" or not backend.supports_batch():
            return None
        if toggle == "auto":
            pending = self._store.count_pending_by_modality(modality)
            if pending < self._cfg.batch.threshold:
                return None
        if not self._locks[modality].acquire(blocking=False):
            return None
        try:
            return self._do_submit(modality, backend)
        finally:
            self._locks[modality].release()

    def _do_submit(self, modality: str, backend) -> int | None:
        threshold = self._cfg.batch.threshold
        rows = self._store.fetch_pending_by_modality(modality, limit=threshold)
        if not rows:
            return None
        asset_ids = [r.id for r in rows]
        self._store.mark_assets_batch_queued(asset_ids)
        try:
            if modality in ("chat_image", "chat_audio"):
                requests = self._build_chat_requests(modality, rows)
                backend_job_id = backend.batch_chat(
                    modality=modality, requests=requests,
                )
            else:  # text_embed
                texts = self._build_embed_texts(rows)
                backend_job_id = backend.batch_embed(texts=texts)
        except Exception as e:
            log.warning(
                "batch submit failed modality=%s — rollback: %s", modality, e,
            )
            for aid in asset_ids:
                self._store.mark_asset_batch_state(aid, "none")
            return None
        now = int(time.time())
        job_id = self._store.save_batch_job(
            backend="gemini",
            modality=modality,
            backend_job_id=backend_job_id,
            asset_count=len(asset_ids),
            submitted_at=now,
            expires_at=now + self._cfg.batch.expiry_grace_seconds,
            display_name=f"assetcache-{modality}-{now}",
        )
        self._store.mark_assets_batch_submitted(asset_ids, job_id)
        self._aq.dequeue_assets(asset_ids)
        log.info(
            "batch submitted modality=%s job_id=%d backend_job_id=%s count=%d",
            modality, job_id, backend_job_id, len(asset_ids),
        )
        return job_id

    def _build_chat_requests(self, modality, rows):
        """Phase 3 task 3.1+3.2: placeholder — Task 3.3 에서 실 이미지/오디오 base64 로 교체."""
        from ..llm.base import ChatMessage
        return [
            BatchChatRequest(
                asset_id=r.id,
                messages=[
                    ChatMessage(role="user", content=f"placeholder asset {r.id}"),
                ],
                force_json=True,
            )
            for r in rows
        ]

    def _build_embed_texts(self, rows):
        """Phase 3 task 3.1+3.2: placeholder — Task 3.3 에서 store.get_searchable_text 로 교체."""
        return [f"placeholder asset {r.id}" for r in rows]
