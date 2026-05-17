"""Store write_lock + busy_timeout + new mark_asset_pending writer.

The single sqlite3 connection is shared across threads (``check_same_thread=False``),
so callers must serialise themselves.  After M2.1, ``Store.write_lock`` makes
this serialisation explicit and the writer methods all acquire it.
"""

from __future__ import annotations

import sqlite3
import threading

from gah.core.manifest import PackManifest
from gah.core.store import LabelScore, Store


def _seed_pack_and_assets(s: Store, n_assets: int = 50) -> list[int]:
    manifest = PackManifest(
        display_name="t", vendor=None, source_url=None,
        license=None, description=None,
    )
    pack_id = s.upsert_pack("pack_concurrency", manifest, scanned_at=1)
    ids: list[int] = []
    for i in range(n_assets):
        ids.append(
            s.upsert_asset(
                pack_id, f"pack_concurrency/file_{i}.png",
                "sprite", file_hash=f"h{i}", file_size=10, added_at=10 + i,
            )
        )
    return ids


def test_mark_asset_pending_updates_state(store) -> None:
    ids = _seed_pack_and_assets(store, n_assets=3)
    # 첫 자산을 일단 analyzing 으로 옮김
    store.mark_asset_analyzing(ids[0])
    row = store.get_asset_by_id(ids[0])
    assert row is not None and row.analysis_state == "analyzing"

    # 그 다음 mark_asset_pending 으로 되돌릴 수 있어야 한다 (drain_pending 의 자리)
    store.mark_asset_pending(ids[0])
    row = store.get_asset_by_id(ids[0])
    assert row is not None and row.analysis_state == "pending"


def test_busy_timeout_pragma_set(store) -> None:
    val = store.conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert val == 5000


def test_write_lock_prevents_database_is_locked(store) -> None:
    ids = _seed_pack_and_assets(store, n_assets=20)

    errors: list[BaseException] = []

    def worker_state(start: int, step: int) -> None:
        try:
            for offset in range(0, len(ids), 1):
                aid = ids[(start + offset) % len(ids)]
                state = "ok" if (offset % 2 == 0) else "partial"
                store.mark_asset_state(aid, state, analyzed_at=100 + offset)
        except sqlite3.Error as e:  # 모든 sqlite3 에러 — Operational/Interface/Programming 등
            errors.append(e)

    def worker_labels(start: int) -> None:
        try:
            for offset in range(0, len(ids), 1):
                aid = ids[(start + offset) % len(ids)]
                store.save_asset_labels(
                    aid,
                    [
                        LabelScore(
                            axis="category", label="icon",
                            score=0.5 + offset * 0.001,
                            source="gemma", weight="primary",
                        ),
                    ],
                )
        except sqlite3.Error as e:  # 모든 sqlite3 에러 — Operational/Interface/Programming 등
            errors.append(e)

    t1 = threading.Thread(target=worker_state, args=(0, 1))
    t2 = threading.Thread(target=worker_labels, args=(5,))
    t3 = threading.Thread(target=worker_state, args=(13, 2))
    threads = [t1, t2, t3]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15.0)

    assert errors == [], (
        f"write_lock should eliminate 'database is locked'; got {errors!r}"
    )

    # 그리고 최종 상태는 모두 일관된 값으로 마무리되어 있어야 한다 (열려 있는 트랜잭션이
    # 없어야만 read 가 즉시 답한다)
    rows = store.list_assets(limit=100)
    assert {r.id for r in rows} == set(ids)
