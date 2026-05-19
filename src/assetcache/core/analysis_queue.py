"""Analysis queue worker + ETA / progress tracker.

Single-consumer queue (``concurrency=1`` by default) that runs the
sprite / sound analyzers off the GUI thread and emits Qt signals so
the main window can render progress without polling.

``AnalysisProgress`` snapshots are pure data — both the test suite
and the status bar widget consume them through the same dataclass.
The ETA window keeps the last *N* observed analysis durations and
averages them; this is intentionally simple because mixed-kind
queues have ±50% noise anyway (see plan §6).
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import QObject, Signal

from .analyzer.base import AnalyzerInput
from .pack_aggregate import write_aggregate

if TYPE_CHECKING:
    from .analyzer.sound import SoundAnalyzer
    from .analyzer.sprite import SpriteAnalyzer
    from .analyzer.spritesheet import SpritesheetAnalyzer
    from .store import Store

log = logging.getLogger(__name__)


# ── public dataclass ────────────────────────────────────────────────


@dataclass(frozen=True)
class AnalysisProgress:
    completed_in_session: int   # 이번 부팅 후 완료한 분석 (성공·실패 포함)
    pending: int                # 큐 + in-flight + DB pending 합
    in_flight_path: str | None  # 현재 분석 중인 에셋 상대 경로
    eta_seconds: float | None   # 표본 < 3개면 None
    avg_duration_seconds: float | None


# ── ko duration formatter ───────────────────────────────────────────


def _format_duration_kor(seconds: float | None) -> str:
    if seconds is None:
        return "계산 중…"
    seconds = round(float(seconds))
    if seconds < 60:
        return f"{seconds}초"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes}분"
    hours = minutes // 60
    remainder = minutes - hours * 60
    return f"{hours}시간 {remainder}분"


# ── the queue ───────────────────────────────────────────────────────


class AnalysisQueue(QObject):
    analysisFinished = Signal(int)
    progressChanged = Signal(object)

    def __init__(
        self,
        store: "Store",
        *,
        sprite: "SpriteAnalyzer",
        spritesheet: "SpritesheetAnalyzer",  # M6 신규
        sound: "SoundAnalyzer",
        concurrency: int = 1,
        eta_window: int = 10,
        clock: Callable[[], float] = time.monotonic,
        library_root: Path | None = None,
    ) -> None:
        super().__init__()
        self.store = store
        self.sprite = sprite
        self.spritesheet = spritesheet  # M6
        self.sound = sound
        self.concurrency = max(1, int(concurrency))
        self.library_root = library_root
        self._clock = clock

        self._queue: "queue.Queue[int]" = queue.Queue()
        self._init_progress_tracker(window=eta_window)
        self._in_flight_path: str | None = None
        self._completed_in_session = 0
        self._enqueued_packs: set[int] = set()
        self._touched_packs: set[int] = set()
        self._stop_event = threading.Event()
        self._executor: ThreadPoolExecutor | None = None
        self._futures: list = []

    # -- progress tracker (also used by tests via __new__) -----------

    def _init_progress_tracker(self, *, window: int) -> None:
        self._eta_window = max(1, int(window))
        self._recent_durations: deque[float] = deque(maxlen=self._eta_window)

    def _record_duration(self, duration: float, *, success: bool = True) -> None:
        # 메모리 결정: 실패도 시간 표본에 포함 (ETA 정확도)
        self._recent_durations.append(float(duration))

    # -- lifecycle ----------------------------------------------------

    def start(self) -> None:
        if self._executor is not None:
            return
        self._stop_event.clear()
        self._executor = ThreadPoolExecutor(
            max_workers=self.concurrency, thread_name_prefix="assetcache-analyze"
        )
        for _ in range(self.concurrency):
            fut = self._executor.submit(self._worker_loop)
            self._futures.append(fut)

    def stop(self, timeout: float = 5.0) -> None:
        if self._executor is None:
            return
        self._stop_event.set()
        # 워커가 큐.get() 에 묶여 있을 수 있어 sentinel 을 채워 깨운다
        for _ in range(self.concurrency):
            self._queue.put(-1)
        for fut in self._futures:
            try:
                fut.result(timeout=timeout)
            except Exception:  # pragma: no cover - 안전망
                pass
        self._executor.shutdown(wait=True)
        self._executor = None
        self._futures.clear()

    # -- enqueue ------------------------------------------------------

    def enqueue_asset(self, asset_id: int) -> None:
        self._queue.put(int(asset_id))
        self._emit_progress()

    def enqueue_pack(self, pack_id: int) -> int:
        rows = self.store.pending_assets_for_pack(pack_id)
        self._enqueued_packs.add(pack_id)
        for row in rows:
            self._queue.put(row.id)
        self._emit_progress()
        return len(rows)

    def drain_pending(self) -> int:
        """Boot-time helper: enqueue everything currently marked pending."""
        # 한 번에 sweep
        rows = []
        while True:
            row = self.store.next_pending_asset()
            if row is None:
                break
            rows.append(row)
            # 다음 next_pending_asset 가 같은 행을 다시 반환하지 않게 표시
            self.store.mark_asset_analyzing(row.id)
        # 표시는 했지만 실제 분석은 워커에 위임 — 큐에 다시 넣는다
        for row in rows:
            # pending 으로 되돌려서 워커가 정상 처리하게.
            # M2.1: raw conn.execute 가 아니라 Store 메서드를 거쳐 write_lock 안에서.
            self.store.mark_asset_pending(row.id)
            self._queue.put(row.id)
            self._enqueued_packs.add(row.pack_id)
        self._emit_progress()
        return len(rows)

    # -- progress snapshot -------------------------------------------

    @staticmethod
    def _build_progress(
        *,
        recent_durations,
        completed: int,
        pending: int,
        in_flight: str | None,
    ) -> AnalysisProgress:
        samples = list(recent_durations)
        avg: float | None = None
        if len(samples) >= 3:
            avg = sum(samples) / len(samples)
        eta = avg * pending if avg is not None else None
        return AnalysisProgress(
            completed_in_session=completed,
            pending=pending,
            in_flight_path=in_flight,
            eta_seconds=eta,
            avg_duration_seconds=avg,
        )

    def progress(self) -> AnalysisProgress:
        pending = (
            self._queue.qsize()
            + (1 if self._in_flight_path else 0)
            + self.store.count_pending_assets()
        )
        return self._build_progress(
            recent_durations=self._recent_durations,
            completed=self._completed_in_session,
            pending=pending,
            in_flight=self._in_flight_path,
        )

    def _emit_progress(self) -> None:
        try:
            self.progressChanged.emit(self.progress())
        except Exception:  # pragma: no cover - 시그널은 부작용 없게
            log.exception("progressChanged emit failed")

    # -- worker -------------------------------------------------------

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                asset_id = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if asset_id == -1:  # sentinel
                return
            self._handle_one(asset_id)

    def _handle_one(self, asset_id: int) -> None:
        row = self.store.get_asset_by_id(asset_id)
        if row is None:
            return
        self._in_flight_path = row.path
        self._touched_packs.add(row.pack_id)
        self._emit_progress()
        t0 = self._clock()
        success = True
        try:
            self.store.mark_asset_analyzing(asset_id)
            inp = self._build_input(row)
            # M6: 이미지 kind (sprite/spritesheet) 는 SpritesheetAnalyzer 로 라우팅.
            # 한 번 promote 된 spritesheet 도 재분석 시 같은 analyzer 가 받아야 함
            # — 안 그러면 SoundAnalyzer 가 PNG 를 받아 fail.
            analyzer = (
                self.spritesheet if row.kind in ("sprite", "spritesheet")
                else self.sound
            )
            result = analyzer.analyze(inp)
            self._persist(asset_id, result)
        except Exception as e:  # noqa: BLE001 — 워커가 죽으면 안 됨
            success = False
            log.exception("analysis failed for asset_id=%d", asset_id)
            self.store.mark_asset_state(
                asset_id, "failed", error=repr(e),
                analyzed_at=int(time.time()),
            )
        finally:
            duration = self._clock() - t0
            self._record_duration(duration, success=success)
            self._completed_in_session += 1
            self._in_flight_path = None
            self._maybe_finalize_pack(row.pack_id)
            self._emit_progress()
            try:
                self.analysisFinished.emit(asset_id)
            except Exception:  # pragma: no cover
                log.exception("analysisFinished emit failed")

    def _build_input(self, row) -> AnalyzerInput:
        if self.library_root is not None:
            abs_path = (self.library_root / row.path).resolve()
        else:
            abs_path = Path(row.path)
        return AnalyzerInput(
            asset_id=row.id,
            pack_id=row.pack_id,
            abs_path=abs_path,
            rel_path=row.path,
        )

    def _persist(self, asset_id: int, result) -> None:
        if result.sprite_meta is not None:
            self.store.save_sprite_meta(asset_id, result.sprite_meta)
        if result.sound_meta is not None:
            self.store.save_sound_meta(asset_id, result.sound_meta)
        self.store.save_asset_labels(asset_id, result.labels)
        if result.embedding_dim > 0:
            self.store.save_embedding(
                asset_id, result.embedding_model,
                result.embedding_vector, result.embedding_dim,
            )
        self.store.update_fts(asset_id, result.searchable.for_fts)
        # M6 — SpritesheetAnalyzer 만 sprite → spritesheet promote (다른 analyzer 는 영향 X)
        if result.kind == "spritesheet":
            self.store.update_asset_kind(asset_id, "spritesheet")
        self.store.mark_asset_state(
            asset_id, result.state, error=result.error,
            analyzed_at=int(time.time()),
        )

    def _maybe_finalize_pack(self, pack_id: int) -> None:
        # 팩에 pending 이 0 개면 aggregate_meta 한 번 새로 씀
        if not self.store.pending_assets_for_pack(pack_id):
            try:
                write_aggregate(self.store, pack_id)
            except Exception:  # pragma: no cover
                log.exception("aggregate update failed for pack_id=%d",
                              pack_id)
