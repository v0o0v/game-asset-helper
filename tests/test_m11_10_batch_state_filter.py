"""M11.10 — boot-time race fix: batch_state='submitted' asset 은 worker 큐에 안 들어감.

LIVE 검증 중 발견 — 트레이 재부팅 시 BatchPoller 가 batch_get 응답 가져오기
전에 worker 가 batch_state='submitted' 인 23개 sprite 들을 sync 분석으로 처리.
결과 53 sync calls.  ``store.next_pending_asset`` / ``pending_assets_for_pack``
의 SQL 에 ``batch_state='none'`` 필터 추가해 race 차단.
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


def _make_batch_job(store: Store) -> int:
    """FK constraint 통과용 dummy batch_jobs row."""
    return store.save_batch_job(
        backend="gemini", modality="chat_image",
        backend_job_id="batches/test", asset_count=1,
        submitted_at=1, expires_at=999999, display_name="test",
    )


def test_next_pending_asset_skips_batch_submitted_state(store):
    """batch_state IN ('submitted', 'queued', 'completed') 인 asset 은
    next_pending_asset 가 안 반환한다.  worker 가 batch path 중인 asset 을
    중복 sync 처리하는 race 방지.
    """
    _, ids = _add_pack_and_assets(store, count=3)
    job_id = _make_batch_job(store)
    store.mark_assets_batch_submitted([ids[0]], batch_job_id=job_id)
    store.mark_assets_batch_queued([ids[1]])

    row = store.next_pending_asset()
    assert row is not None
    assert row.id == ids[2], (
        f"batch_state='none' 인 asset 만 반환해야 함, got {row.id} (expected {ids[2]})"
    )

    store.mark_asset_analyzing(ids[2])
    assert store.next_pending_asset() is None


def test_pending_assets_for_pack_skips_batch_submitted_state(store):
    """pending_assets_for_pack 도 batch_state='none' 만 반환.

    drain_pending / enqueue_pack 시 batch 처리 중인 asset 을 큐에 다시 안 넣음.
    """
    pack_id, ids = _add_pack_and_assets(store, count=4)
    job_id = _make_batch_job(store)
    store.mark_assets_batch_submitted([ids[0], ids[1]], batch_job_id=job_id)
    store.mark_asset_batch_state(ids[2], "completed")

    rows = store.pending_assets_for_pack(pack_id=pack_id)
    returned_ids = {r.id for r in rows}
    assert returned_ids == {ids[3]}, (
        f"batch_state='none' 인 asset 만 반환해야 함, got {returned_ids}"
    )


def test_count_pending_assets_unchanged_for_dashboard(store):
    """count_pending_assets 는 변경 X — 대시보드 표시는 batch 처리 중도 포함.

    사용자 입장에서 'pending' 상태로 보이는 게 직관적 (batch 응답 대기 중도
    분석 끝나지 않음).  worker enqueue 만 batch_state 필터.
    """
    _, ids = _add_pack_and_assets(store, count=3)
    job_id = _make_batch_job(store)
    store.mark_assets_batch_submitted([ids[0]], batch_job_id=job_id)
    assert store.count_pending_assets() == 3
