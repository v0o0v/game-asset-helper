"""BatchManager — modality 별 batch 진입 결정 + Gemini submit + rollback.

Phase 3 task 3.1+3.2 — toggle/chain/threshold 결정 트리 + race lock.
Phase 3 task 3.3 — _build_chat_requests / _build_embed_texts 를
  analyzer/messages.py 공유 빌더 + store.get_searchable_text 로 교체.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
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
        library_dir: Path | None = None,
    ) -> None:
        self._store = store
        self._chain = chain_registry
        self._aq = analysis_queue
        self._cfg = cfg
        self._library_dir = library_dir
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
                asset_ids_built = [req.asset_id for req in requests]
                # OSError 로 skip 된 asset 은 즉시 'none' 으로 복구 (interactive fallback)
                skipped = set(asset_ids) - set(asset_ids_built)
                for aid in skipped:
                    self._store.mark_asset_batch_state(aid, "none")
                if not requests:
                    log.warning(
                        "batch submit modality=%s: all assets failed to build, abort",
                        modality,
                    )
                    return None
                backend_job_id = backend.batch_chat(
                    modality=modality, requests=requests,
                )
                # use filtered list for count / mark / dequeue
                asset_ids = asset_ids_built
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
        """실 이미지/오디오 바이트를 base64 인코딩해 BatchChatRequest 목록 반환.

        library_dir 가 없으면 row.path 를 절대 경로로 사용(테스트/fallback).
        """
        from ..analyzer.messages import (
            BATCH_AUDIO_PROMPT,
            BATCH_IMAGE_PROMPT,
            build_audio_chat_messages,
            build_image_chat_messages,
        )

        if modality == "chat_image":
            builder = build_image_chat_messages
            prompt = BATCH_IMAGE_PROMPT
        else:
            builder = build_audio_chat_messages
            prompt = BATCH_AUDIO_PROMPT

        out = []
        for r in rows:
            if self._library_dir is not None:
                abs_path = (self._library_dir / r.path).resolve()
            else:
                abs_path = Path(r.path)
            try:
                messages = builder(abs_path=abs_path, prompt=prompt)
            except OSError as e:
                log.warning("batch: cannot read asset %d (%s): %s", r.id, abs_path, e)
                continue
            out.append(BatchChatRequest(
                asset_id=r.id,
                messages=messages,
                force_json=True,
            ))
        return out

    def _build_embed_texts(self, rows):
        """assets_fts 의 searchable_text 를 사용. 미등록이면 path + kind 폴백."""
        out = []
        for r in rows:
            text = self._store.get_searchable_text(r.id)
            if text is None:
                text = f"{r.path} {r.kind}"
            out.append(text)
        return out

    def cancel(self, batch_job_id: int) -> None:
        """User-initiated cancel — backend best-effort + 모든 asset interactive 재enqueue.

        이미 terminal 상태인 job 은 noop.
        Missing job (못 찾으면) silent return.
        """
        job = self._store.get_batch_job(batch_job_id)
        if job is None:
            log.warning("cancel: batch_job_id %d not found", batch_job_id)
            return
        if job.state in ("succeeded", "failed", "cancelled", "expired"):
            log.info(
                "cancel: job %d already terminal (%s) — noop",
                batch_job_id, job.state,
            )
            return
        backend = self._chain.get_backend(job.backend)
        if backend is not None and hasattr(backend, "batch_cancel"):
            backend.batch_cancel(job.backend_job_id)
        # 모든 asset interactive 재enqueue
        for asset in self._store.list_assets_in_batch(batch_job_id):
            self._store.mark_asset_batch_state(asset.id, "failed")
            self._aq.enqueue_asset(asset.id)
        self._store.update_batch_job_state(
            batch_job_id, state="cancelled", completed_at=int(time.time()),
        )
