"""M11.10 — text_embed modality batch 비활성 + stuck asset 복구.

LIVE 검증 중 발견 — text_embed async batch 가 sprite asset 17개 잡았는데,
응답에 inlined_responses 없어서 _handle_succeeded 가 빈 succeeded 마킹만
하고 종료.  asset 의 batch_state='submitted' 그대로 stuck.

해결:
1. ``BatchManager.try_submit('text_embed')`` 즉시 None — modality 비활성.
2. ``Store.recover_stuck_batch_assets()`` — boot-time 복원.
3. ``_handle_succeeded`` 의 빈 inlined_responses 케이스에서 asset 복원.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from assetcache.core.batch.manager import BatchManager
from assetcache.core.batch.poller import BatchPoller
from assetcache.core.batch.types import GeminiBatchStatus
from assetcache.core.manifest import PackManifest
from assetcache.core.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    s = Store(tmp_path / "test.db")
    s.initialize()
    yield s
    s.close()


def _add_pack_and_assets(store: Store, count: int) -> tuple[int, list[int]]:
    manifest = PackManifest(
        display_name="P1", vendor=None, source_url=None,
        license=None, description=None,
    )
    pack_id = store.upsert_pack(name="p1", manifest=manifest, scanned_at=1)
    ids: list[int] = []
    for i in range(count):
        aid = store.upsert_asset(
            pack_id=pack_id, rel_path=f"p1/sprite_{i}.png",
            kind="sprite", file_hash=f"h{i}", file_size=100, added_at=1,
        )
        ids.append(aid)
    return pack_id, ids


# ── 1. text_embed modality 비활성 ────────────────────────────────────


def test_try_submit_text_embed_returns_none(monkeypatch):
    """M11.10 — try_submit('text_embed') 는 즉시 None.  async embed batch 비활성."""
    store_mock = MagicMock()
    chain_registry = MagicMock()
    backend = MagicMock()
    backend.info.name = "gemini"
    backend.supports_batch.return_value = True
    chain_registry.first_backend.return_value = backend
    cfg = MagicMock()

    bm = BatchManager(
        store=store_mock, chain_registry=chain_registry,
        analysis_queue=MagicMock(), cfg=cfg,
    )
    assert bm.try_submit("text_embed") is None
    # fetch_pending 도 호출 안 됨 (modality 자체 reject)
    store_mock.fetch_pending_by_modality.assert_not_called()


def test_try_submit_chat_image_still_works(monkeypatch):
    """sanity — text_embed skip 후 chat_image 는 정상 동작."""
    store_mock = MagicMock()
    store_mock.fetch_pending_by_modality.return_value = []
    chain_registry = MagicMock()
    backend = MagicMock()
    backend.info.name = "gemini"
    backend.supports_batch.return_value = True
    chain_registry.first_backend.return_value = backend
    cfg = MagicMock()

    bm = BatchManager(
        store=store_mock, chain_registry=chain_registry,
        analysis_queue=MagicMock(), cfg=cfg,
    )
    bm.try_submit("chat_image")
    # fetch_pending 정상 호출 (pending=0 라 None 반환되지만 진입은 함)
    store_mock.fetch_pending_by_modality.assert_called()


# ── 2. Store.recover_stuck_batch_assets ──────────────────────────────


def _make_batch_job(store: Store, state: str = "submitted") -> int:
    job_id = store.save_batch_job(
        backend="gemini", modality="chat_image",
        backend_job_id="batches/test", asset_count=1,
        submitted_at=1, expires_at=999999, display_name="test",
    )
    if state != "submitted":
        store.update_batch_job_state(job_id, state=state)
    return job_id


def test_recover_restores_assets_with_succeeded_job(store):
    """batch_jobs.state='succeeded' 인데 asset.batch_state='submitted' stuck → 복원."""
    _, ids = _add_pack_and_assets(store, count=3)
    job_id = _make_batch_job(store, state="submitted")
    store.mark_assets_batch_submitted(ids, batch_job_id=job_id)
    # batch_jobs 가 이제 succeeded (응답 처리 실패로 asset 은 그대로 'submitted')
    store.update_batch_job_state(job_id, state="succeeded")

    recovered = store.recover_stuck_batch_assets()
    assert recovered == 3
    # 모든 asset 이 batch_state='none' 으로 복원
    for aid in ids:
        row = store.get_asset_by_id(aid)
        # AssetRow 에 batch_state 컬럼 없으니 raw SQL 확인
        result = store.conn.execute(
            "SELECT batch_state, batch_job_id FROM assets WHERE id = ?", (aid,)
        ).fetchone()
        assert result[0] == "none"
        assert result[1] is None


def test_recover_skips_assets_with_active_job(store):
    """batch_jobs.state='submitted' (active) 인 asset 은 복원 안 함."""
    _, ids = _add_pack_and_assets(store, count=2)
    job_id = _make_batch_job(store, state="submitted")
    store.mark_assets_batch_submitted(ids, batch_job_id=job_id)
    # batch_jobs 가 아직 active — asset 은 그대로 두어야

    recovered = store.recover_stuck_batch_assets()
    assert recovered == 0


def test_recover_restores_orphan_assets_with_null_job_id(store):
    """batch_job_id IS NULL 인데 batch_state='submitted' inconsistent 도 복원."""
    _, ids = _add_pack_and_assets(store, count=1)
    # 직접 inconsistent state 만들기
    store.conn.execute(
        "UPDATE assets SET batch_state = 'submitted' WHERE id = ?",
        (ids[0],),
    )

    recovered = store.recover_stuck_batch_assets()
    assert recovered == 1


# ── 3. _handle_succeeded 빈 inlined_responses 케이스 → asset 복원 ─────


def test_handle_succeeded_empty_inlined_responses_restores_assets(monkeypatch):
    """status.inlined_responses=None 일 때 asset 들 batch_state='none' 복원."""
    store_mock = MagicMock()
    asset_a = MagicMock(id=101)
    asset_b = MagicMock(id=102)
    store_mock.list_assets_in_batch.return_value = [asset_a, asset_b]

    cfg = MagicMock()
    cfg.batch.poll_interval_seconds = 5
    p = BatchPoller(
        store=store_mock, chain_registry=MagicMock(),
        analysis_queue=MagicMock(), cfg=cfg,
    )

    job = MagicMock(id=42)
    status = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED",
        inlined_responses=None,
        file_name=None,
        error=None,
    )
    p._handle_succeeded(job, status, backend=MagicMock())

    # 두 asset 모두 batch_state='none' 으로 복원
    calls = [c.args for c in store_mock.mark_asset_batch_state.call_args_list]
    assert (101, "none") in calls
    assert (102, "none") in calls


def test_handle_succeeded_file_destination_also_restores_assets(monkeypatch):
    """file destination 케이스도 expired 처리 + asset 복원."""
    store_mock = MagicMock()
    asset_a = MagicMock(id=201)
    store_mock.list_assets_in_batch.return_value = [asset_a]

    cfg = MagicMock()
    cfg.batch.poll_interval_seconds = 5
    p = BatchPoller(
        store=store_mock, chain_registry=MagicMock(),
        analysis_queue=MagicMock(), cfg=cfg,
    )

    job = MagicMock(id=43)
    status = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED",
        inlined_responses=None,
        file_name="files/abc",
        error=None,
    )
    p._handle_succeeded(job, status, backend=MagicMock())

    calls = [c.args for c in store_mock.mark_asset_batch_state.call_args_list]
    assert (201, "none") in calls
