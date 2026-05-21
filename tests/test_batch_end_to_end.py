"""Phase 6 task 6.1 — end-to-end mock test.

실 Store + AnalysisQueue + BatchManager + BatchPoller 사용.
Gemini backend 만 MagicMock 으로 대체 — 파일 I/O 없이 전체 흐름 검증.

시나리오:
  1. 30 sprite enqueue → batch submit → mock SUCCEEDED 30 → DB success_count=30
  2. 30 enqueue → 25 OK + 5 error → DB success_count=25 + failure_count=5
     + 실패한 5개 interactive 재enqueue
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import pytest

from assetcache.core.batch.manager import BatchManager
from assetcache.core.batch.poller import BatchPoller
from assetcache.core.batch.types import BatchChatRequest, GeminiBatchStatus
from assetcache.core.llm.base import ChatMessage


# ── helpers ─────────────────────────────────────────────────────────────────


def _fake_chat_requests(rows):
    """파일 I/O 없이 BatchChatRequest 목록 생성 (_build_chat_requests stub)."""
    return [
        BatchChatRequest(
            asset_id=r.id,
            messages=[ChatMessage(role="user", content=f"analyze {r.id}")],
            force_json=True,
        )
        for r in rows
    ]


def _ok_response(text: str = json.dumps({"labels": []})):
    """batch_get 응답 중 성공한 개별 응답 stub."""
    r = MagicMock()
    r.response.text = text
    r.error = None
    return r


def _err_response(msg: str = "API error"):
    """batch_get 응답 중 실패한 개별 응답 stub."""
    r = MagicMock()
    r.response = None
    r.error = msg
    return r


# ── fixture ──────────────────────────────────────────────────────────────────


class _E2ECtx:
    """e2e_setup fixture 의 context 객체.

    store, aq, bm, poller, gemini_backend, pack_id, add_asset 를 담는다.
    """
    store: "object"
    aq: "object"
    bm: BatchManager
    poller: BatchPoller
    gemini_backend: MagicMock
    pack_id: int

    def add_asset(self, kind: str, path: str) -> int:
        ...


@pytest.fixture
def e2e_setup(tmp_path):
    """실 Store + AnalysisQueue + BatchManager + BatchPoller.  Gemini backend 만 mock.

    - AnalysisQueue.start() 를 호출하지 않아 worker thread 없이 동작.
    - enqueue_pack → _try_batch_submit → BatchManager.try_submit 이 동기 호출됨.
    - _build_chat_requests 는 파일 I/O 를 stub 으로 대체.
    - BatchPoller.start() 를 호출하지 않아 _poll_once() 만 직접 호출.
    """
    from assetcache.config import BatchConfig, Config
    from assetcache.core.analysis_queue import AnalysisQueue
    from assetcache.core.manifest import PackManifest
    from assetcache.core.store import Store

    # ── DB 초기화 ──────────────────────────────────────────────────────────
    db_path = tmp_path / "e2e.db"
    store = Store(str(db_path))
    store.initialize()

    # pack 생성
    manifest = PackManifest(
        display_name="e2e-pack",
        vendor=None,
        source_url=None,
        license=None,
        description=None,
    )
    pack_id = store.upsert_pack("e2e-pack", manifest, scanned_at=int(time.time()))

    # ── config (threshold=30 auto) ─────────────────────────────────────────
    cfg = Config()
    cfg.batch = BatchConfig(threshold=30, poll_interval_seconds=3600, toggle="auto")

    # ── mock gemini backend ────────────────────────────────────────────────
    gemini_backend = MagicMock()
    gemini_backend.info.name = "gemini"
    gemini_backend.supports_batch.return_value = True
    gemini_backend.batch_chat.return_value = "batches/e2e-test-job"

    chain_registry = MagicMock()
    chain_registry.first_backend.return_value = gemini_backend
    chain_registry.get_backend.return_value = gemini_backend

    # ── AnalysisQueue (실, worker 없음) ────────────────────────────────────
    aq = AnalysisQueue(
        store=store,
        sprite=MagicMock(),
        spritesheet=MagicMock(),
        sound=MagicMock(),
    )

    # ── BatchManager ───────────────────────────────────────────────────────
    bm = BatchManager(
        store=store,
        chain_registry=chain_registry,
        analysis_queue=aq,
        cfg=cfg,
        library_dir=tmp_path,
    )
    # 파일 I/O 없이 동작하도록 _build_chat_requests stub
    bm._build_chat_requests = lambda modality, rows: _fake_chat_requests(rows)
    aq.set_batch_manager(bm)

    # ── BatchPoller (실, thread 없음) ──────────────────────────────────────
    poller = BatchPoller(
        store=store,
        chain_registry=chain_registry,
        analysis_queue=aq,
        cfg=cfg,
    )

    # ── context 조립 ───────────────────────────────────────────────────────
    ctx = _E2ECtx()
    ctx.store = store
    ctx.aq = aq
    ctx.bm = bm
    ctx.poller = poller
    ctx.gemini_backend = gemini_backend
    ctx.pack_id = pack_id

    def add_asset(kind: str, path: str) -> int:
        return store.upsert_asset(
            pack_id,
            path,
            kind,
            file_hash=f"hash:{path}",
            file_size=1,
            added_at=int(time.time()),
        )

    ctx.add_asset = add_asset

    yield ctx

    store.close()


# ── 시나리오 1: 30 sprite → batch submit → SUCCEEDED 30 ──────────────────────


def test_enqueue_30_assets_triggers_batch_and_succeeds(e2e_setup):
    """30 sprite enqueue → BatchManager.try_submit → mock SUCCEEDED → success_count=30."""
    ctx = e2e_setup

    # 30 sprite asset 삽입
    for i in range(30):
        ctx.add_asset("sprite", f"a{i:02d}.png")

    # enqueue_pack → _try_batch_submit → BatchManager.try_submit
    enqueued = ctx.aq.enqueue_pack(ctx.pack_id)
    assert enqueued == 30

    # batch_jobs row 생성 확인
    jobs = ctx.store.list_active_batch_jobs()
    assert len(jobs) >= 1
    image_job = next(j for j in jobs if j.modality == "chat_image")
    assert image_job.asset_count == 30
    assert image_job.state in ("submitted", "running")

    # mock: SUCCEEDED + 30 OK 응답
    fake_responses = [_ok_response() for _ in range(30)]
    ctx.gemini_backend.batch_get.return_value = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED",
        inlined_responses=fake_responses,
        file_name=None,
        error=None,
    )

    # poller 1 tick (thread 없이 직접 호출)
    ctx.poller._poll_once()

    # DB 검증 — batch_job 완료 확인
    job_after = ctx.store.get_batch_job(image_job.id)
    assert job_after.state == "succeeded"
    assert job_after.success_count == 30
    assert job_after.failure_count == 0


def test_batch_job_created_with_correct_backend_and_modality(e2e_setup):
    """batch_jobs 행의 backend='gemini', modality='chat_image' 검증."""
    ctx = e2e_setup
    for i in range(30):
        ctx.add_asset("sprite", f"c{i:02d}.png")
    ctx.aq.enqueue_pack(ctx.pack_id)

    jobs = ctx.store.list_active_batch_jobs()
    assert len(jobs) >= 1
    job = jobs[0]
    assert job.backend == "gemini"
    assert job.modality == "chat_image"
    assert job.backend_job_id == "batches/e2e-test-job"


# ── 시나리오 2: 30 enqueue → 25 OK + 5 error → fallback ─────────────────────


def test_partial_failure_falls_back_to_interactive(e2e_setup):
    """30 enqueue → SUCCEEDED 25 OK / 5 error → success=25, failure=5 + 5개 재enqueue."""
    ctx = e2e_setup

    for i in range(30):
        ctx.add_asset("sprite", f"b{i:02d}.png")
    ctx.aq.enqueue_pack(ctx.pack_id)

    jobs = ctx.store.list_active_batch_jobs()
    assert jobs, "batch_jobs 행이 없음 — try_submit 미실행"
    job = jobs[0]

    # 25 OK / 5 error
    fake_responses = [
        _ok_response() if i < 25 else _err_response()
        for i in range(30)
    ]
    ctx.gemini_backend.batch_get.return_value = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED",
        inlined_responses=fake_responses,
        file_name=None,
        error=None,
    )

    ctx.poller._poll_once()

    job_after = ctx.store.get_batch_job(job.id)
    assert job_after.state == "succeeded"
    assert job_after.success_count == 25
    assert job_after.failure_count == 5


def test_failed_assets_re_enqueued_to_interactive_queue(e2e_setup, monkeypatch):
    """부분 실패 시 실패한 asset 이 aq.enqueue_asset() 으로 재삽입됨.

    enqueue_asset 호출 횟수로 검증 (queue 내부 구조에 의존하지 않음).
    """
    ctx = e2e_setup

    for i in range(30):
        ctx.add_asset("sprite", f"d{i:02d}.png")
    ctx.aq.enqueue_pack(ctx.pack_id)

    jobs = ctx.store.list_active_batch_jobs()
    assert jobs
    job = jobs[0]

    n_fail = 7
    fake_responses = [
        _ok_response() if i < (30 - n_fail) else _err_response()
        for i in range(30)
    ]
    ctx.gemini_backend.batch_get.return_value = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED",
        inlined_responses=fake_responses,
        file_name=None,
        error=None,
    )

    # enqueue_asset 호출 감시
    enqueue_calls: list[int] = []
    original_enqueue = ctx.aq.enqueue_asset
    def spy_enqueue(asset_id: int) -> None:
        enqueue_calls.append(asset_id)
        original_enqueue(asset_id)
    monkeypatch.setattr(ctx.aq, "enqueue_asset", spy_enqueue)

    ctx.poller._poll_once()

    # _fail_asset → enqueue_asset 가 n_fail 번 호출되어야 함
    assert len(enqueue_calls) == n_fail, (
        f"enqueue_asset 호출 {n_fail}회 예상, 실제={len(enqueue_calls)}"
    )


# ── 시나리오 3: threshold 미달 시 batch submit 안 함 ─────────────────────────


def test_below_threshold_no_batch_submit(e2e_setup):
    """pending < threshold (30) 일 때 batch_jobs 생성 안 함."""
    ctx = e2e_setup

    for i in range(10):
        ctx.add_asset("sprite", f"e{i:02d}.png")
    ctx.aq.enqueue_pack(ctx.pack_id)

    jobs = ctx.store.list_active_batch_jobs()
    # pending=10 < threshold=30 → batch submit 없어야 함
    assert len(jobs) == 0


# ── 시나리오 4: terminal failure → 전체 asset interactive 재enqueue ───────────


def test_job_state_failed_re_enqueues_all(e2e_setup, monkeypatch):
    """JOB_STATE_FAILED → _handle_terminal_failure → 30개 전부 enqueue_asset 호출."""
    ctx = e2e_setup

    for i in range(30):
        ctx.add_asset("sprite", f"f{i:02d}.png")
    ctx.aq.enqueue_pack(ctx.pack_id)

    jobs = ctx.store.list_active_batch_jobs()
    assert jobs
    job = jobs[0]

    ctx.gemini_backend.batch_get.return_value = GeminiBatchStatus(
        state="JOB_STATE_FAILED",
        inlined_responses=None,
        file_name=None,
        error="Backend error",
    )

    # enqueue_asset 호출 감시
    enqueue_calls: list[int] = []
    original_enqueue = ctx.aq.enqueue_asset
    def spy_enqueue(asset_id: int) -> None:
        enqueue_calls.append(asset_id)
        original_enqueue(asset_id)
    monkeypatch.setattr(ctx.aq, "enqueue_asset", spy_enqueue)

    ctx.poller._poll_once()

    job_after = ctx.store.get_batch_job(job.id)
    assert job_after.state == "failed"

    # _handle_terminal_failure → 30개 전부 enqueue_asset 호출
    assert len(enqueue_calls) == 30, (
        f"terminal failure 후 30회 enqueue_asset 예상, 실제={len(enqueue_calls)}"
    )
