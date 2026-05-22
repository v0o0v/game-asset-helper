"""BatchManager — modality 별 batch 진입 결정 + Gemini submit + rollback.

Phase 3 task 3.1+3.2 — toggle/chain/threshold 결정 트리 + race lock.
Phase 3 task 3.3 — _build_chat_requests / _build_embed_texts 를
  analyzer/messages.py 공유 빌더 + store.get_searchable_text 로 교체.
"""

from __future__ import annotations

import collections
import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from .types import BatchChatRequest

if TYPE_CHECKING:
    from ..analysis_queue import AnalysisQueue
    from ..labels import LabelRegistry
    from ..llm.registry import BackendRegistry
    from ..sheet.detect import SheetDetection
    from ..store import Store
    from ...config import Config

log = logging.getLogger(__name__)

_MODALITIES = ("chat_image", "chat_spritesheet", "chat_audio", "text_embed")

# M11.3 — sweep memory cache 최대 entries.  일반 라이브러리는 ≤ 1000장 시트.
_DETECTION_CACHE_MAX_SIZE = 1024

# M11.10 — batch chunk size.  Gemini Batch API inline payload 안전 한도 100.
# threshold 사용자 설정 제거 (batch-only 정책) — chunk 단위 hardcoded.
_BATCH_CHUNK_SIZE = 100


class _BoundedLRUCache(collections.OrderedDict):
    """OrderedDict 변형 — max_size 초과 시 가장 오래된 entry 부터 evict.

    ``classify_image_assets`` 가 ``cache[row.id] = detection`` 식으로 직접
    작성하기 때문에 ``__setitem__`` 에서 eviction 처리.  re-assignment 시에는
    가장 최근 사용으로 이동 (`move_to_end`).
    """

    def __init__(self, max_size: int = _DETECTION_CACHE_MAX_SIZE) -> None:
        super().__init__()
        self._max_size = max_size

    def __setitem__(self, key, value) -> None:
        if key in self:
            self.move_to_end(key)
        super().__setitem__(key, value)
        while len(self) > self._max_size:
            self.popitem(last=False)


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
        registry: "LabelRegistry | None" = None,
    ) -> None:
        self._store = store
        self._chain = chain_registry
        self._aq = analysis_queue
        self._cfg = cfg
        self._library_dir = library_dir
        self._registry = registry
        self._locks = {m: threading.Lock() for m in _MODALITIES}
        # M11.3 옵션 C — sweep 메모리 캐시.  chat_image classify 가 채운
        # detection 을 chat_spritesheet classify 가 재사용.  instance lifetime.
        self._detection_cache: "_BoundedLRUCache[int, SheetDetection | None]" = (
            _BoundedLRUCache()
        )

    def try_submit(self, modality: str) -> int | None:
        """Try to submit a batch job for `modality`. Return batch_jobs.id or None.

        M11.10 — batch-only 정책: ``cfg.batch.toggle`` / ``cfg.batch.threshold`` 무시.
        gemini backend + supports_batch() 만족하면 무조건 batch 시도.  fetch_pending
        이 0 row 반환하면 자연스럽게 None (no work to do).
        """
        if modality not in _MODALITIES:
            log.warning("try_submit invalid modality: %s", modality)
            return None
        backend = self._chain.first_backend(modality)
        if backend is None:
            return None
        if backend.info.name != "gemini" or not backend.supports_batch():
            return None
        if not self._locks[modality].acquire(blocking=False):
            return None
        try:
            return self._do_submit(modality, backend)
        finally:
            self._locks[modality].release()

    def _do_submit(self, modality: str, backend) -> int | None:
        # M11.10 — batch chunk size 는 hardcoded 100 (Gemini Batch API inline payload
        # 안전 한도).  사용자 설정 불가.  pending > 100 이면 다음 try_submit 가 자연
        # 처리 (race lock + 다시 호출).
        rows = self._store.fetch_pending_by_modality(modality, limit=_BATCH_CHUNK_SIZE)
        if not rows:
            return None

        sheet_results: list = []  # [(AssetRow, SheetDetection), ...] — chat_spritesheet 전용
        if modality == "chat_image":
            # M11.2 — fetch 후 시트 식별 + kind promote.  시트 rows 는 batch 에 안 보내고
            # 다음 sweep 의 chat_spritesheet 가 픽업.  sprite rows 만 chat_image batch.
            # M11.3 — sweep cache 전달 + sprite_meta 자동 enrich+save (옵션 B+C).
            from .sheet_classifier import classify_image_assets
            _sheets, rows = classify_image_assets(
                rows, library_dir=self._library_dir, store=self._store,
                cache=self._detection_cache,
                alpha_color_weight=self._cfg.grid_detect_alpha_color_weight,
            )
            if not rows:
                # 전부 시트 — promote 만 수행, batch submit 0.
                return None
        elif modality == "chat_spritesheet":
            # spritesheet kind 는 이미 promote 된 상태.  builder 에 detection 을 전달하기
            # 위해 detect_sheet 다시 호출.  detect miss 면 skip.
            # M11.3 — 같은 sweep cache 재사용 → chat_image 가 이미 채운 결과 hit.
            from .sheet_classifier import classify_image_assets
            sheet_results, _ = classify_image_assets(
                rows, library_dir=self._library_dir, store=self._store,
                cache=self._detection_cache,
                alpha_color_weight=self._cfg.grid_detect_alpha_color_weight,
            )
            if not sheet_results:
                log.warning(
                    "chat_spritesheet submit: 0 detect_sheet hits in %d rows",
                    len(rows),
                )
                return None
            rows = [row for row, _ in sheet_results]

        asset_ids = [r.id for r in rows]
        self._store.mark_assets_batch_queued(asset_ids)
        try:
            if modality in ("chat_image", "chat_audio"):
                requests = self._build_chat_requests(modality, rows)
            elif modality == "chat_spritesheet":
                requests = self._build_spritesheet_requests(sheet_results)
            else:  # text_embed
                texts = self._build_embed_texts(rows)

            if modality in ("chat_image", "chat_audio", "chat_spritesheet"):
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

    def _build_spritesheet_requests(self, sheet_results):
        """시트 + detection 튜플 list 를 composite strip + 시트 전용 prompt 로 변환.

        sheet_results: ``[(AssetRow, SheetDetection), ...]`` from classify_image_assets.
        registry 가 있으면 ``list_labels('animation')`` 으로 enum 동적 주입.
        없으면 빈 enum 으로 fallback (sync SpritesheetAnalyzer 와 동일 동작).
        """
        from ..analyzer.messages import (
            BATCH_SPRITESHEET_PROMPT,
            build_spritesheet_chat_messages,
        )

        anim_enum = ""
        if self._registry is not None:
            try:
                anim_enum = ", ".join(self._registry.list_labels("animation"))
            except Exception:  # noqa: BLE001 — registry 오류 silent fallback
                anim_enum = ""

        out: list[BatchChatRequest] = []
        for row, detection in sheet_results:
            if self._library_dir is not None:
                abs_path = (self._library_dir / row.path).resolve()
            else:
                abs_path = Path(row.path)
            try:
                messages = build_spritesheet_chat_messages(
                    abs_path=abs_path,
                    detection=detection,
                    prompt=BATCH_SPRITESHEET_PROMPT,
                    anim_enum=anim_enum,
                )
            except (OSError, ValueError) as e:
                log.warning(
                    "batch spritesheet: cannot build composite asset_id=%d (%s): %s",
                    row.id, abs_path, e,
                )
                continue
            out.append(BatchChatRequest(
                asset_id=row.id,
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
