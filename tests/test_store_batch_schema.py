"""Phase 1 — batch_jobs table + assets.batch_job_id/batch_state 컬럼 마이그레이션."""

import sqlite3

import pytest

from assetcache.core.store import Store


@pytest.fixture
def fresh_store(tmp_path):
    db = tmp_path / "test.db"
    store = Store(str(db))
    store.initialize()
    return store


def test_batch_jobs_table_created(fresh_store):
    with sqlite3.connect(str(fresh_store.db_path)) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='batch_jobs'"
        ).fetchone()
        assert row is not None


def test_batch_jobs_columns(fresh_store):
    with sqlite3.connect(str(fresh_store.db_path)) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(batch_jobs)").fetchall()]
    expected = {
        "id", "backend", "modality", "backend_job_id", "asset_count",
        "submitted_at", "expires_at", "state", "completed_at",
        "success_count", "failure_count", "error", "display_name",
    }
    assert expected.issubset(set(cols))


def test_assets_batch_columns_added(fresh_store):
    with sqlite3.connect(str(fresh_store.db_path)) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(assets)").fetchall()}
    assert "batch_job_id" in cols
    assert "batch_state" in cols


def test_assets_batch_state_default_none(fresh_store):
    with sqlite3.connect(str(fresh_store.db_path)) as conn:
        conn.execute(
            "INSERT INTO packs (name, enabled, added_at) VALUES ('p', 1, 0)"
        )
        pack_id = conn.execute("SELECT id FROM packs").fetchone()[0]
        conn.execute(
            "INSERT INTO assets (pack_id, path, kind, file_hash, file_size, added_at, analysis_state) "
            "VALUES (?, 'a.png', 'sprite', 'h', 1, 0, 'pending')",
            (pack_id,),
        )
        row = conn.execute(
            "SELECT batch_state, batch_job_id FROM assets WHERE path='a.png'"
        ).fetchone()
        assert row == ("none", None)


def test_indexes_present(fresh_store):
    with sqlite3.connect(str(fresh_store.db_path)) as conn:
        idx = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()}
    assert "idx_batch_jobs_state" in idx
    assert "idx_assets_batch_state" in idx
    assert "idx_batch_jobs_backend_job_id" in idx


def test_initialize_idempotent(fresh_store):
    fresh_store.initialize()
    fresh_store.initialize()
    with sqlite3.connect(str(fresh_store.db_path)) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='batch_jobs'"
        ).fetchone()[0]
    assert count == 1


# ── Task 1.2: batch_jobs CRUD ──────────────────────────────────────────


def test_save_batch_job_returns_id(fresh_store):
    job_id = fresh_store.save_batch_job(
        backend="gemini",
        modality="chat_image",
        backend_job_id="batches/abc",
        asset_count=30,
        submitted_at=1000,
        expires_at=1000 + 172800,
        display_name="test-job",
    )
    assert isinstance(job_id, int) and job_id > 0


def test_get_batch_job_roundtrip(fresh_store):
    job_id = fresh_store.save_batch_job(
        backend="gemini", modality="chat_image",
        backend_job_id="batches/xyz", asset_count=10,
        submitted_at=2000, expires_at=2000 + 172800,
        display_name="d",
    )
    row = fresh_store.get_batch_job(job_id)
    assert row.backend == "gemini"
    assert row.modality == "chat_image"
    assert row.backend_job_id == "batches/xyz"
    assert row.state == "submitted"
    assert row.asset_count == 10
    assert row.success_count == 0
    assert row.failure_count == 0
    assert row.error is None
    assert row.completed_at is None


def test_update_batch_job_state(fresh_store):
    job_id = fresh_store.save_batch_job(
        backend="gemini", modality="chat_image",
        backend_job_id="batches/a", asset_count=5,
        submitted_at=0, expires_at=172800, display_name="d",
    )
    fresh_store.update_batch_job_state(
        job_id, state="succeeded", completed_at=100,
        success_count=4, failure_count=1,
    )
    row = fresh_store.get_batch_job(job_id)
    assert row.state == "succeeded"
    assert row.completed_at == 100
    assert row.success_count == 4
    assert row.failure_count == 1


def test_list_active_batch_jobs_filters_terminal(fresh_store):
    active_id = fresh_store.save_batch_job(
        backend="gemini", modality="chat_image",
        backend_job_id="batches/active", asset_count=1,
        submitted_at=0, expires_at=172800, display_name="d",
    )
    done_id = fresh_store.save_batch_job(
        backend="gemini", modality="chat_audio",
        backend_job_id="batches/done", asset_count=1,
        submitted_at=0, expires_at=172800, display_name="d",
    )
    fresh_store.update_batch_job_state(done_id, state="succeeded", completed_at=10)
    active = fresh_store.list_active_batch_jobs()
    ids = {r.id for r in active}
    assert active_id in ids
    assert done_id not in ids


def test_list_active_includes_running(fresh_store):
    job_id = fresh_store.save_batch_job(
        backend="gemini", modality="chat_image",
        backend_job_id="batches/r", asset_count=1,
        submitted_at=0, expires_at=172800, display_name="d",
    )
    fresh_store.update_batch_job_state(job_id, state="running")
    rows = fresh_store.list_active_batch_jobs()
    assert any(r.id == job_id for r in rows)


def test_get_batch_job_missing(fresh_store):
    assert fresh_store.get_batch_job(99999) is None


# ── Task 1.3: assets batch_state CRUD ────────────────────────────────


@pytest.fixture
def _seed_assets(fresh_store):
    """fresh_store 에 pack 1개 + N개 sprite asset 생성. return list[int]."""
    import sqlite3 as _s

    def make(count: int) -> list[int]:
        with _s.connect(fresh_store.db_path) as conn:
            conn.execute(
                "INSERT INTO packs (name, enabled, added_at) VALUES ('p', 1, 0)"
            )
            pack_id = conn.execute("SELECT id FROM packs ORDER BY id DESC LIMIT 1").fetchone()[0]
            ids = []
            for i in range(count):
                cur = conn.execute(
                    "INSERT INTO assets (pack_id, path, kind, file_hash, file_size, added_at, analysis_state) "
                    "VALUES (?, ?, 'sprite', ?, 1, 0, 'pending')",
                    (pack_id, f"a{i}.png", f"h{i}"),
                )
                ids.append(cur.lastrowid)
            return ids

    return make


def test_mark_assets_batch_queued(fresh_store, _seed_assets):
    asset_ids = _seed_assets(3)
    fresh_store.mark_assets_batch_queued(asset_ids)
    with sqlite3.connect(fresh_store.db_path) as conn:
        placeholders = ",".join("?" * len(asset_ids))
        rows = conn.execute(
            f"SELECT batch_state FROM assets WHERE id IN ({placeholders})", asset_ids
        ).fetchall()
    assert all(r[0] == "queued" for r in rows)


def test_mark_assets_batch_submitted(fresh_store, _seed_assets):
    asset_ids = _seed_assets(2)
    job_id = fresh_store.save_batch_job(
        backend="gemini", modality="chat_image",
        backend_job_id="batches/x", asset_count=2,
        submitted_at=0, expires_at=172800, display_name="d",
    )
    fresh_store.mark_assets_batch_submitted(asset_ids, job_id)
    with sqlite3.connect(fresh_store.db_path) as conn:
        placeholders = ",".join("?" * len(asset_ids))
        rows = conn.execute(
            f"SELECT batch_state, batch_job_id FROM assets WHERE id IN ({placeholders})",
            asset_ids,
        ).fetchall()
    assert all(r == ("submitted", job_id) for r in rows)


def test_mark_asset_batch_state_single(fresh_store, _seed_assets):
    asset_ids = _seed_assets(1)
    fresh_store.mark_asset_batch_state(asset_ids[0], "completed")
    with sqlite3.connect(fresh_store.db_path) as conn:
        s = conn.execute(
            "SELECT batch_state FROM assets WHERE id = ?", (asset_ids[0],)
        ).fetchone()[0]
    assert s == "completed"


def test_mark_assets_batch_queued_empty_list_noop(fresh_store):
    # 빈 리스트 → 에러 없이 통과
    fresh_store.mark_assets_batch_queued([])


def test_mark_assets_batch_queued_idempotent(fresh_store, _seed_assets):
    asset_ids = _seed_assets(2)
    fresh_store.mark_assets_batch_queued(asset_ids)  # 1st
    fresh_store.mark_assets_batch_queued(asset_ids)  # 2nd — re-queued, same state
    with sqlite3.connect(fresh_store.db_path) as conn:
        placeholders = ",".join("?" * len(asset_ids))
        rows = conn.execute(
            f"SELECT batch_state FROM assets WHERE id IN ({placeholders})", asset_ids
        ).fetchall()
    assert all(r[0] == "queued" for r in rows)


# ── Task 1.4: Store batch query ──────────────────────────────────────


def test_fetch_pending_by_modality_chat_image(fresh_store, _seed_assets):
    ids = _seed_assets(3)  # 3 sprite
    rows = fresh_store.fetch_pending_by_modality("chat_image", limit=10)
    assert len(rows) == 3
    assert all(r.kind == "sprite" for r in rows)


def test_fetch_pending_by_modality_includes_queued_default(fresh_store, _seed_assets):
    """M11.10 — default batch_state_in=('none','queued') — chat_image classify 후
    sheet promote 로 'queued' 마킹된 row 도 chat_spritesheet 가 fetch.
    """
    ids = _seed_assets(3)
    fresh_store.mark_assets_batch_queued(ids[:2])
    rows = fresh_store.fetch_pending_by_modality("chat_image", limit=10)
    # 'none' 1 + 'queued' 2 = 3
    assert len(rows) == 3
    assert {r.id for r in rows} == set(ids)


def test_fetch_pending_by_modality_explicit_none_only(fresh_store, _seed_assets):
    """명시적으로 batch_state_in=('none',) 전달 시 queued 제외."""
    ids = _seed_assets(3)
    fresh_store.mark_assets_batch_queued(ids[:2])
    rows = fresh_store.fetch_pending_by_modality(
        "chat_image", batch_state_in=("none",), limit=10,
    )
    assert len(rows) == 1
    assert rows[0].id == ids[2]


def test_fetch_pending_by_modality_chat_audio_filters(fresh_store, _seed_assets):
    _seed_assets(3)  # sprite 만
    rows = fresh_store.fetch_pending_by_modality("chat_audio", limit=10)
    assert len(rows) == 0


def test_fetch_pending_by_modality_limit(fresh_store, _seed_assets):
    _seed_assets(50)
    rows = fresh_store.fetch_pending_by_modality("chat_image", limit=30)
    assert len(rows) == 30


def test_list_assets_in_batch(fresh_store, _seed_assets):
    ids = _seed_assets(3)
    job_id = fresh_store.save_batch_job(
        backend="gemini", modality="chat_image",
        backend_job_id="batches/x", asset_count=3,
        submitted_at=0, expires_at=172800, display_name="d",
    )
    fresh_store.mark_assets_batch_submitted(ids, job_id)
    rows = fresh_store.list_assets_in_batch(job_id)
    assert {r.id for r in rows} == set(ids)


def test_list_recent_failures(fresh_store, _seed_assets):
    ids = _seed_assets(2)
    fresh_store.mark_asset_state(ids[0], "failed", error="non-json", analyzed_at=1000)
    fresh_store.mark_asset_state(ids[1], "failed", error="timeout", analyzed_at=2000)
    rows = fresh_store.list_recent_failures(limit=10)
    assert len(rows) == 2
    # 최신순 (analyzed_at DESC)
    assert rows[0].id == ids[1]
    assert rows[0].analysis_error == "timeout"


# ── Task 1.5: mark_asset_backends ───────────────────────────────────


def test_mark_asset_backends_image_only(fresh_store, _seed_assets):
    ids = _seed_assets(1)
    fresh_store.mark_asset_backends(ids[0], image="gemini")
    with sqlite3.connect(str(fresh_store.db_path)) as conn:
        row = conn.execute(
            "SELECT backend_image, backend_audio, backend_embed FROM assets WHERE id = ?",
            (ids[0],),
        ).fetchone()
    assert row == ("gemini", None, None)


def test_mark_asset_backends_all_three(fresh_store, _seed_assets):
    ids = _seed_assets(1)
    fresh_store.mark_asset_backends(ids[0], image="gemini", audio="ollama", embed="gemini")
    with sqlite3.connect(str(fresh_store.db_path)) as conn:
        row = conn.execute(
            "SELECT backend_image, backend_audio, backend_embed FROM assets WHERE id = ?",
            (ids[0],),
        ).fetchone()
    assert row == ("gemini", "ollama", "gemini")


def test_mark_asset_backends_none_args_preserve_existing(fresh_store, _seed_assets):
    ids = _seed_assets(1)
    fresh_store.mark_asset_backends(ids[0], image="ollama")
    fresh_store.mark_asset_backends(ids[0], audio="gemini")
    with sqlite3.connect(str(fresh_store.db_path)) as conn:
        row = conn.execute(
            "SELECT backend_image, backend_audio FROM assets WHERE id = ?",
            (ids[0],),
        ).fetchone()
    assert row == ("ollama", "gemini")


def test_mark_asset_backends_no_args_noop(fresh_store, _seed_assets):
    ids = _seed_assets(1)
    fresh_store.mark_asset_backends(ids[0])  # 모든 None — UPDATE 안 함
    # 예외 없이 통과


# ── Task 3.5: count_pending_by_modality ─────────────────────────────


def test_count_pending_by_modality_chat_image(fresh_store, _seed_assets):
    _seed_assets(3)  # 3 sprite
    assert fresh_store.count_pending_by_modality("chat_image") == 3


def test_count_pending_by_modality_chat_audio_zero(fresh_store, _seed_assets):
    _seed_assets(3)  # sprite only
    assert fresh_store.count_pending_by_modality("chat_audio") == 0


def test_count_pending_by_modality_excludes_queued(fresh_store, _seed_assets):
    ids = _seed_assets(5)
    fresh_store.mark_assets_batch_queued(ids[:2])
    assert fresh_store.count_pending_by_modality("chat_image") == 3
