"""M11.10 — worker vs batch race 차단.

`enqueue_pack` 가 row 들을 큐에 넣은 직후 ``_try_batch_submit`` 호출하지만,
그 사이 worker thread 가 큐에서 pop 해 sync 분석 시작.  batch 의 fetch SQL 은
``analysis_state='pending'`` 인데 worker 가 이미 ``analyzing`` 으로 마킹한 row
는 batch 가 못 잡음 → worker sync 분석 진행 → 결과 batch 1 + sync 3.

해결: worker `_handle_one` 가 mark_asset_analyzing 전에 ``batch_state='none'``
인 경우에만 analyzing 으로 전환하는 atomic UPDATE 사용.  batch 가 먼저 잡으면
이 atomic UPDATE 가 0 row 변경 → worker skip.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from assetcache.core.manifest import PackManifest
from assetcache.core.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    s = Store(tmp_path / "test.db")
    s.initialize()
    yield s
    s.close()


def _add_pack_and_asset(store: Store) -> int:
    manifest = PackManifest(
        display_name="P1", vendor=None, source_url=None,
        license=None, description=None,
    )
    pack_id = store.upsert_pack(name="p1", manifest=manifest, scanned_at=1)
    aid = store.upsert_asset(
        pack_id=pack_id, rel_path="p1/sprite_0.png",
        kind="sprite", file_hash="h0", file_size=100, added_at=1,
    )
    return aid


def _make_batch_job(store: Store) -> int:
    return store.save_batch_job(
        backend="gemini", modality="chat_image",
        backend_job_id="batches/test", asset_count=1,
        submitted_at=1, expires_at=999999, display_name="test",
    )


def test_try_mark_analyzing_pending_default_succeeds(store):
    """batch_state='none' + analysis_state='pending' 일 때 True 반환 + 상태 변경."""
    aid = _add_pack_and_asset(store)
    # default: analysis_state='pending', batch_state='none'
    assert store.try_mark_asset_analyzing(aid) is True
    row = store.get_asset_by_id(aid)
    assert row is not None
    assert row.analysis_state == "analyzing"


def test_try_mark_analyzing_skipped_when_batch_submitted(store):
    """batch_state='submitted' 인 row 는 False 반환 + 상태 변경 없음."""
    aid = _add_pack_and_asset(store)
    job_id = _make_batch_job(store)
    store.mark_assets_batch_submitted([aid], batch_job_id=job_id)
    # 이제 batch 가 잡았으니 worker 는 skip 해야 함
    assert store.try_mark_asset_analyzing(aid) is False
    row = store.get_asset_by_id(aid)
    # 상태 그대로 'pending' (worker 가 'analyzing' 으로 안 바꿈)
    assert row.analysis_state == "pending"


def test_try_mark_analyzing_skipped_when_batch_queued(store):
    """batch_state='queued' 도 동일하게 worker skip."""
    aid = _add_pack_and_asset(store)
    store.mark_assets_batch_queued([aid])
    assert store.try_mark_asset_analyzing(aid) is False


def test_try_mark_analyzing_skipped_when_already_analyzing(store):
    """이미 다른 worker 가 analyzing 으로 바꾼 경우 — 중복 처리 차단."""
    aid = _add_pack_and_asset(store)
    store.mark_asset_analyzing(aid)
    # analysis_state='analyzing' → batch_state='none' 이지만 이미 처리 중
    assert store.try_mark_asset_analyzing(aid) is False


def test_handle_one_skips_when_batch_submitted(store, monkeypatch):
    """``_handle_one`` 가 batch_state='submitted' 인 row 를 발견하면 즉시 skip.

    AnalysisQueue 의 worker race window 차단.  analyzer 호출 0회 검증.
    """
    from unittest.mock import MagicMock
    aid = _add_pack_and_asset(store)
    job_id = _make_batch_job(store)
    store.mark_assets_batch_submitted([aid], batch_job_id=job_id)

    # AnalysisQueue 의 _handle_one 만 단독 호출 (worker thread 없이)
    from assetcache.core.analysis_queue import AnalysisQueue
    aq = AnalysisQueue.__new__(AnalysisQueue)
    aq.store = store
    aq.sprite = MagicMock()
    aq.spritesheet = MagicMock()
    aq.sound = MagicMock()
    aq.library_root = None
    aq._in_flight_path = None
    aq._touched_packs = set()
    aq._completed_in_session = 0
    aq._clock = lambda: 0.0
    aq._recent_durations = __import__("collections").deque(maxlen=10)
    aq._eta_window = 10

    # signal emit 우회
    aq._emit_progress = lambda: None
    aq._maybe_finalize_pack = lambda pid: None
    aq.analysisFinished = MagicMock()

    aq._handle_one(aid)

    # analyzer 들이 호출되지 않아야 — batch 가 가져갔으니
    aq.sprite.analyze.assert_not_called()
    aq.spritesheet.analyze.assert_not_called()
    aq.sound.analyze.assert_not_called()
