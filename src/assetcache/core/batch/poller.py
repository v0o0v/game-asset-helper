"""BatchPoller — daemon thread 가 active batch jobs 를 주기 polling.

Phase 4 task 4.1: skeleton + run loop + stop.
Phase 4 task 4.2: _poll_job state mapping + expiry safety.
Phase 4 task 4.3: _handle_succeeded (modality 별 persist + backend_used).
Phase 4 task 4.4: _handle_terminal_failure (failed/cancelled/expired → interactive 재enqueue).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from ..analyzer.payload_parser import (
    audio_payload_to_labels,
    collect_label_descriptions,
    image_payload_to_labels,
    validate_audio_payload,
    validate_image_payload,
)
from ..analyzer.spritesheet_meta import (
    detection_to_animation_labels,
    enrich_sprite_meta_with_sheet,
)
from ..analyzer.tech_meta import compute_sound_meta, compute_sprite_meta
from ..searchable import build_searchable
from ..sheet.detect import detect_sheet

if TYPE_CHECKING:
    from ..analysis_queue import AnalysisQueue
    from ..labels import LabelRegistry
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
        registry: "LabelRegistry | None" = None,
        library_dir: Path | None = None,
    ) -> None:
        super().__init__(daemon=True, name="assetcache-batch-poller")
        self._store = store
        self._chain = chain_registry
        self._aq = analysis_queue
        self._cfg = cfg
        # M11.1 patch — LabelRegistry 가 있을 때만 batch 결과 → label 변환을 수행.
        # None 이면 (이전 동작) labels 빈 채로 mark ok — 기존 옵트인 테스트 호환.
        self._registry = registry
        # v0.2.x patch — library_dir 가 있으면 batch 경로도 sprite_meta /
        # sound_meta 를 sync 와 동등하게 채움.  None 이면 meta 충전 skip.
        self._library_dir = library_dir
        self._stop_event = threading.Event()

    def stop(self, timeout: float = 5.0) -> None:
        """Signal stop + join. idempotent (stop() 두 번 호출 안전)."""
        self._stop_event.set()
        # 만약 thread 가 아직 시작 안 됐으면 join() 이 즉시 return
        if self.is_alive():
            self.join(timeout=timeout)

    def run(self) -> None:
        interval = max(0.01, float(self._cfg.batch.poll_interval_seconds))
        log.info("BatchPoller daemon started (poll_interval=%.1fs)", interval)
        # 부팅 시 즉시 1회 sweep (재개 보장)
        self._poll_once()
        while not self._stop_event.is_set():
            interval = max(0.01, float(self._cfg.batch.poll_interval_seconds))
            if self._stop_event.wait(interval):
                break
            self._poll_once()
        log.info("BatchPoller daemon stopped")

    def _poll_once(self) -> None:
        try:
            jobs = self._store.list_active_batch_jobs()
        except Exception:
            log.exception("list_active_batch_jobs failed — skipping sweep")
            return
        if jobs:
            log.info("BatchPoller tick: %d active job(s)", len(jobs))
        else:
            log.debug("BatchPoller tick: 0 active jobs")
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
                    self._persist_image_payload(asset, payload)
                    self._store.mark_asset_backends(asset.id, image="gemini")
                elif job.modality == "chat_spritesheet":
                    payload = json.loads(resp.response.text)
                    self._persist_spritesheet_payload(asset, payload)
                    self._store.mark_asset_backends(asset.id, image="gemini")
                elif job.modality == "chat_audio":
                    payload = json.loads(resp.response.text)
                    self._persist_audio_payload(asset, payload)
                    self._store.mark_asset_backends(asset.id, audio="gemini")
                elif job.modality == "text_embed":
                    vec = list(resp.embedding.values)
                    blob = _serialize_vec(vec)
                    model = self._get_gemini_embed_model()
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

    def _persist_image_payload(self, asset, payload: dict) -> None:
        """이미지 batch 결과를 실 labels + sprite_meta + searchable text 로 persist.

        sync SpriteAnalyzer 와 동일한 ``validate_image_payload`` →
        ``image_payload_to_labels`` 경로를 사용한다.  enum whitelist
        위반은 ``other`` 로 demote 되며, 모두 demote 됐어도 ``state='ok'``
        (partial 라벨이라도 검색은 가능).

        ``self._library_dir`` 가 있으면:
          * ``compute_sprite_meta`` 로 tech 메타 (width/height/alpha/
            pixel_art/dominant_colors) 채움.
          * ``detect_sheet`` 로 spritesheet 검출 → 시트면 frame_w/h/count
            + animations_json (Aseprite frameTags) 채움 + frameTags 기반
            animation 라벨 추가 + kind='spritesheet' promote.

        ``self._registry`` 가 None 이면 (테스트 fallback) 이전 동작 —
        labels 빈 채로 mark ok.

        한계: batch prompt 는 시트를 의식하지 않으므로 sync 와 달리 Gemma
        의 ``animation_hint`` 추측 라벨은 없음.  Aseprite frameTags 가
        없는 grid-only 시트는 animation 라벨이 비어 있음.
        """
        analyzed_at = int(time.time())
        if self._registry is None:
            self._store.save_asset_labels(asset.id, [])
            self._store.mark_asset_state(
                asset.id, "ok", error=None, analyzed_at=analyzed_at,
            )
            return

        ok, err, fixed = validate_image_payload(payload, self._registry)
        if not ok:
            log.info(
                "batch image payload validation: asset_id=%d %s",
                asset.id, err,
            )
        labels = image_payload_to_labels(fixed)

        sprite_meta = self._try_compute_sprite_meta(asset)
        if sprite_meta is not None:
            sheet_result = self._try_enrich_with_sheet(asset, sprite_meta)
            if sheet_result is not None:
                sprite_meta, anim_labels = sheet_result
                labels.extend(anim_labels)
                self._store.update_asset_kind(asset.id, "spritesheet")
            self._store.save_sprite_meta(asset.id, sprite_meta)

        descs = collect_label_descriptions(labels, self._registry)
        searchable = build_searchable(
            meta=sprite_meta,
            labels=labels,
            label_descriptions=descs,
            description=fixed.get("description") or "",
            rel_path=asset.path,
        )
        self._store.save_asset_labels(asset.id, labels)
        self._store.update_fts(asset.id, searchable.for_fts)
        self._store.mark_asset_state(
            asset.id, "ok", error=None, analyzed_at=analyzed_at,
        )

    def _persist_spritesheet_payload(self, asset, payload: dict) -> None:
        """시트 batch 결과를 sync SpritesheetAnalyzer 와 동등하게 persist.

        sync 와 차이:
        * sync 는 ``_call_gemma`` 가 동기로 호출 — 여기는 batch 응답을 받았을 뿐
          schema 동일.
        * 동일 ``validate_image_payload`` + ``image_payload_to_labels`` 사용 →
          animation_hint 가 enum 안에 있으면 그대로 라벨화.
        * ``_try_enrich_with_sheet`` 로 frame 박스 + frameTags 추가 라벨 (중복
          제거됨).  grid-only 시트도 Gemma animation_hint 가 살아남아 PR #18
          한계 해소.

        kind 는 이미 ``classify_image_assets`` 단계에서 ``spritesheet`` 로
        promote 된 상태.  ``_try_enrich_with_sheet`` 가 다시 호출돼도 idempotent.
        """
        analyzed_at = int(time.time())
        if self._registry is None:
            self._store.save_asset_labels(asset.id, [])
            self._store.mark_asset_state(
                asset.id, "ok", error=None, analyzed_at=analyzed_at,
            )
            return

        ok, err, fixed = validate_image_payload(payload, self._registry)
        if not ok:
            log.info(
                "batch spritesheet payload validation: asset_id=%d %s",
                asset.id, err,
            )
        labels = image_payload_to_labels(fixed)

        sprite_meta = self._try_compute_sprite_meta(asset)
        if sprite_meta is not None:
            sheet_result = self._try_enrich_with_sheet(asset, sprite_meta)
            if sheet_result is not None:
                sprite_meta, anim_labels = sheet_result
                # frameTags 추가 — 중복 (animation_hint 의 walk + frameTag 의 walk) 은
                # label key 기반으로 dedupe
                seen = {(l.axis, l.label) for l in labels}
                for new in anim_labels:
                    if (new.axis, new.label) not in seen:
                        labels.append(new)
                        seen.add((new.axis, new.label))
                # kind promote — chat_spritesheet 경로에서는 이미 promoted 지만
                # 누락된 케이스 (BatchManager 가 라이브러리 변경된 후 poll) 안전망
                self._store.update_asset_kind(asset.id, "spritesheet")
            self._store.save_sprite_meta(asset.id, sprite_meta)

        descs = collect_label_descriptions(labels, self._registry)
        searchable = build_searchable(
            meta=sprite_meta,
            labels=labels,
            label_descriptions=descs,
            description=fixed.get("description") or "",
            rel_path=asset.path,
        )
        self._store.save_asset_labels(asset.id, labels)
        self._store.update_fts(asset.id, searchable.for_fts)
        self._store.mark_asset_state(
            asset.id, "ok", error=None, analyzed_at=analyzed_at,
        )

    def _try_compute_sprite_meta(self, asset):
        """library_dir 가 있으면 파일에서 SpriteMeta 계산, 실패 시 None."""
        if self._library_dir is None:
            return None
        try:
            abs_path = (self._library_dir / asset.path).resolve()
            return compute_sprite_meta(abs_path)
        except Exception as e:  # noqa: BLE001 — file I/O 오류 robust skip
            log.warning(
                "batch: sprite_meta 계산 실패 — asset_id=%d path=%s: %s",
                asset.id, asset.path, e,
            )
            return None

    def _try_enrich_with_sheet(self, asset, base_meta):
        """detect_sheet 가 hit 하면 (enriched_meta, animation_labels) 튜플 반환.

        시트가 아니거나 검출 실패 시 None — 일반 sprite 로 진행한다.
        library_dir 가 없거나 검출에서 예외가 나면 silently skip.
        """
        if self._library_dir is None:
            return None
        try:
            abs_path = (self._library_dir / asset.path).resolve()
            detection = detect_sheet(abs_path)
        except Exception as e:  # noqa: BLE001 — sheet 검출 자체가 실패해도 sprite 진행
            log.warning(
                "batch: spritesheet 검출 실패 — asset_id=%d path=%s: %s",
                asset.id, asset.path, e,
            )
            return None
        if detection is None:
            return None
        enriched = enrich_sprite_meta_with_sheet(base_meta, detection)
        anim_labels = detection_to_animation_labels(detection)
        return enriched, anim_labels

    def _persist_audio_payload(self, asset, payload: dict) -> None:
        """오디오 batch 결과를 실 labels + sound_meta + searchable text 로 persist.

        sync SoundAnalyzer 와 동일한 ``validate_audio_payload`` →
        ``audio_payload_to_labels`` 경로.  ``self._library_dir`` 가 있으면
        ``compute_sound_meta`` 로 tech (duration/sr/channels/loudness/bpm)
        + payload (category/loopable/tempo 등) 를 합쳐서 SoundMeta 채움.
        ``audio_path_used`` 는 ``'batch'`` 로 표시.
        """
        analyzed_at = int(time.time())
        if self._registry is None:
            self._store.save_asset_labels(asset.id, [])
            self._store.mark_asset_state(
                asset.id, "ok", error=None, analyzed_at=analyzed_at,
            )
            return

        ok, fixed, err = validate_audio_payload(payload, self._registry)
        if not ok:
            log.info(
                "batch audio payload validation: asset_id=%d %s",
                asset.id, err,
            )
        labels = audio_payload_to_labels(fixed)
        descs = collect_label_descriptions(labels, self._registry)

        sound_meta = self._try_compute_sound_meta(asset, fixed)
        if sound_meta is not None:
            self._store.save_sound_meta(asset.id, sound_meta)

        searchable = build_searchable(
            meta=sound_meta,
            labels=labels,
            label_descriptions=descs,
            description=fixed.get("description") or "",
            rel_path=asset.path,
        )
        self._store.save_asset_labels(asset.id, labels)
        self._store.update_fts(asset.id, searchable.for_fts)
        self._store.mark_asset_state(
            asset.id, "ok", error=None, analyzed_at=analyzed_at,
        )

    def _try_compute_sound_meta(self, asset, payload: dict):
        """library_dir 가 있으면 파일에서 SoundMeta 계산, 실패 시 None."""
        if self._library_dir is None:
            return None
        try:
            abs_path = (self._library_dir / asset.path).resolve()
            return compute_sound_meta(
                abs_path, payload=payload, audio_path_used="batch",
            )
        except Exception as e:  # noqa: BLE001 — 파일 I/O 오류 robust skip
            log.warning(
                "batch: sound_meta 계산 실패 — asset_id=%d path=%s: %s",
                asset.id, asset.path, e,
            )
            return None

    def _get_gemini_embed_model(self) -> str:
        """Phase 4.4 fix — cfg.backends.gemini.model_embed 의 안전한 access path.

        실 Config 에서 backends 는 dict[str, dict[str, Any]].
        테스트 MagicMock 에서는 attribute 체인으로 접근하므로 두 경로 모두 지원.
        """
        backends = getattr(self._cfg, "backends", None)
        if backends is None:
            return "gemini-embedding-001"
        # 실 Config: dict 형태 (hasattr "gemini" == False 이므로 __getitem__ 경로)
        if hasattr(backends, "__getitem__") and not hasattr(backends, "gemini"):
            try:
                return backends["gemini"]["model_embed"]
            except (KeyError, TypeError):
                return "gemini-embedding-001"
        # MagicMock / attribute 형태 fallback
        gemini = getattr(backends, "gemini", None)
        if gemini is None:
            return "gemini-embedding-001"
        return getattr(gemini, "model_embed", "gemini-embedding-001")

    def _handle_terminal_failure(self, job, terminal_state: str, error: str | None) -> None:
        """failed / cancelled / expired — 모든 asset interactive 재enqueue + job 갱신."""
        for asset in self._store.list_assets_in_batch(job.id):
            self._store.mark_asset_batch_state(asset.id, "failed")
            self._aq.enqueue_asset(asset.id)
        self._store.update_batch_job_state(
            job.id,
            state=terminal_state,
            completed_at=int(time.time()),
            error=error,
        )
