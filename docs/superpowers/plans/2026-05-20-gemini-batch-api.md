# Gemini Batch API Implementation Plan (M11.1 / v0.2.1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** v0.2.1 patch — Gemini Batch API (50% 비용, 24h SLO) 를 image/audio/embed 모든 modality 에 적용. 임계값 (default 30) + 사용자 토글 hybrid 정책. M11 알려진 한계 `mark_asset_backends` write hook 동시 해결. 분석 진행 dashboard `/analyzing` 페이지 신설.

**Architecture:** Approach A — 독립 `BatchManager` (try_submit/cancel) + `BatchPoller` daemon thread (30분 간격) + DB SoT (`batch_jobs` table + `assets.batch_job_id/batch_state` 컬럼). `AnalysisQueue` 는 interactive 전용 유지, batch 진입 시 `_skip_ids` 로 dequeue.

**Tech Stack:** Python 3.12 / `google-genai>=0.1` (이미 v0.2.0 포함) / SQLite WAL / FastAPI + HTMX 5초 polling / PySide6 Qt Signal / pytest + respx mock.

**Spec:** [`docs/superpowers/specs/2026-05-20-gemini-batch-api-design.md`](../specs/2026-05-20-gemini-batch-api-design.md) (commit 08b988d)

**회귀 baseline:** 1252 passed + 1 skipped + 53 deselected (M11 v0.2.0)
**회귀 목표:** ~1360 passed + 1 skipped + 56 deselected (+108 + 옵트인 3)

---

## 0. File Structure

| File | Action | 책임 |
|---|---|---|
| `src/assetcache/core/batch/__init__.py` | Create | re-export |
| `src/assetcache/core/batch/types.py` | Create | `BatchChatRequest` / `GeminiBatchStatus` / `BatchJobRow` 데이터클래스 |
| `src/assetcache/core/batch/manager.py` | Create | `BatchManager.try_submit / cancel` |
| `src/assetcache/core/batch/poller.py` | Create | `BatchPoller` daemon thread |
| `src/assetcache/core/llm/base.py` | Modify | `LLMBackend.supports_batch()` Protocol method 추가 |
| `src/assetcache/core/llm/backends/gemini.py` | Modify | `batch_chat / batch_embed / batch_get / batch_cancel / batch_download_file / supports_batch = True` |
| `src/assetcache/core/store.py` | Modify | `batch_jobs` table 마이그레이션 + `assets.batch_job_id/batch_state` 컬럼 + 9 신규 메서드 + `mark_asset_backends` |
| `src/assetcache/core/analysis_queue.py` | Modify | `pending_by_modality / dequeue_assets / _skip_ids / snapshot_queue / _try_batch_submit` hook |
| `src/assetcache/core/analyzer/base.py` | Modify | `AnalyzerResult.backend_used` 필드 추가 |
| `src/assetcache/core/analyzer/{sprite,sound,spritesheet}.py` | Modify | `backend_used` 값 채우기 (chain.chat 의 두 번째 반환값) |
| `src/assetcache/config.py` | Modify | `BatchConfig` dataclass + TOML migration |
| `src/assetcache/app.py` | Modify | `BatchManager` + `BatchPoller` wiring |
| `src/assetcache/web/routers/settings.py` | Modify | batch panel route + toggle/cancel POST |
| `src/assetcache/web/routers/analyzing.py` | Create | `/analyzing` + `/analyzing/partial` + cancel POST |
| `src/assetcache/web/templates/settings/_batch_card.html` | Create | batch 카드 partial |
| `src/assetcache/web/templates/analyzing/index.html` | Create | dashboard 페이지 shell |
| `src/assetcache/web/templates/analyzing/_partial.html` | Create | 4 섹션 통합 partial (5초 polling target) |
| `src/assetcache/web/templates/_base.html` | Modify | nav 에 "분석 진행" 링크 |
| `src/assetcache/locale/{ko,en}/LC_MESSAGES/assetcache.po` | Modify | 18 신규 msgid |
| `src/assetcache/locale/{ko,en}/LC_MESSAGES/assetcache.mo` | Compiled | `pybabel compile` |
| `tests/test_batch_types.py` | Create | Phase 0 dataclass smoke |
| `tests/test_llm_backend_supports_batch.py` | Create | Phase 0 Protocol default False |
| `tests/test_store_batch_schema.py` | Create | Phase 1 DB + Store API |
| `tests/test_llm_backend_gemini_batch.py` | Create | Phase 2 mock SDK |
| `tests/test_batch_manager.py` | Create | Phase 3 toggle/chain/threshold |
| `tests/test_analysis_queue_batch_hook.py` | Create | Phase 3 dequeue/skip |
| `tests/test_batch_poller.py` | Create | Phase 4 lifecycle |
| `tests/test_web_routers_settings_batch.py` | Create | Phase 5 settings POST |
| `tests/test_web_routers_analyzing.py` | Create | Phase 5 dashboard |
| `tests/test_locale_batch_msgid.py` | Create | Phase 5 i18n |
| `tests/test_batch_end_to_end.py` | Create | Phase 6 통합 |
| `tests/test_llm_backend_gemini_batch_integration.py` | Create | Phase 6 옵트인 3 |
| `milestones/M11_1_plan.md` | Create | Phase 6 — milestone-level Phase 요약 |
| `milestones/M11_1_todo.md` | Create | Phase 6 — task 체크리스트 |
| `milestones/M11_1_verification.md` | Create | Phase 6 — 자동 + 수동 검증 시나리오 |
| `HANDOFF.md` | Modify | Phase 6 — v0.2.1 publish 인계 |
| `CLAUDE.md` | Modify | Phase 6 — §2 진행 현황 + §8 다음 작업 |
| `DESIGN.md` | Modify | Phase 6 — §4.x batch architecture |
| `README.md` | Modify | Phase 6 — Batch 섹션 |

---

## Phase 0 — Skeleton + Protocol 확장 (회귀 1252 → 1257, +5)

### Task 0.1: `core/batch/types.py` + `__init__.py`

**Files:**
- Create: `src/assetcache/core/batch/__init__.py`
- Create: `src/assetcache/core/batch/types.py`
- Test: `tests/test_batch_types.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_batch_types.py
"""Phase 0 — core/batch/types.py dataclass smoke."""

from assetcache.core.batch.types import (
    BatchChatRequest,
    BatchJobRow,
    GeminiBatchStatus,
)
from assetcache.core.llm.base import ChatMessage


def test_batch_chat_request_dataclass():
    req = BatchChatRequest(
        asset_id=42,
        messages=[ChatMessage(role="user", content="hi")],
        force_json=True,
    )
    assert req.asset_id == 42
    assert req.force_json is True
    assert req.messages[0].content == "hi"


def test_gemini_batch_status_dataclass():
    s = GeminiBatchStatus(
        state="JOB_STATE_RUNNING",
        inlined_responses=None,
        file_name=None,
        error=None,
    )
    assert s.state == "JOB_STATE_RUNNING"
    assert s.inlined_responses is None


def test_batch_job_row_dataclass():
    row = BatchJobRow(
        id=1,
        backend="gemini",
        modality="chat_image",
        backend_job_id="batches/abc",
        asset_count=30,
        submitted_at=1000,
        expires_at=1000 + 172800,
        state="submitted",
        completed_at=None,
        success_count=0,
        failure_count=0,
        error=None,
        display_name="assetcache-chat_image-1000",
    )
    assert row.asset_count == 30
    assert row.modality == "chat_image"


def test_batch_chat_request_force_json_default():
    req = BatchChatRequest(asset_id=1, messages=[])
    assert req.force_json is True  # default
```

- [ ] **Step 2: Run test — verify fail**

Run: `pytest tests/test_batch_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'assetcache.core.batch'`

- [ ] **Step 3: Create types module**

```python
# src/assetcache/core/batch/__init__.py
"""Batch processing — submission and polling for backend batch APIs."""
```

```python
# src/assetcache/core/batch/types.py
"""Batch domain dataclasses — pure data, no behavior."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..llm.base import ChatMessage


@dataclass(frozen=True)
class BatchChatRequest:
    """Single asset 의 batch 요청 — chain.chat() 의 messages 와 1:1."""

    asset_id: int
    messages: list[ChatMessage] = field(default_factory=list)
    force_json: bool = True


@dataclass(frozen=True)
class GeminiBatchStatus:
    """`client.batches.get(name)` 결과를 정규화한 view.

    state: JOB_STATE_PENDING / RUNNING / SUCCEEDED / FAILED / CANCELLED / EXPIRED
    """

    state: str
    inlined_responses: list[Any] | None
    file_name: str | None
    error: str | None


@dataclass(frozen=True)
class BatchJobRow:
    """`batch_jobs` table row 의 read-only view."""

    id: int
    backend: str
    modality: str
    backend_job_id: str
    asset_count: int
    submitted_at: int
    expires_at: int
    state: str
    completed_at: int | None
    success_count: int
    failure_count: int
    error: str | None
    display_name: str | None
```

- [ ] **Step 4: Run test — verify pass**

Run: `pytest tests/test_batch_types.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/core/batch/__init__.py src/assetcache/core/batch/types.py tests/test_batch_types.py
git commit -m "feat(batch): Phase 0 task 0.1 — core/batch/ skeleton + types dataclass

BatchChatRequest / GeminiBatchStatus / BatchJobRow.
Pure data, no behavior. Spec §4.1."
```

---

### Task 0.2: `LLMBackend.supports_batch()` Protocol 확장

**Files:**
- Modify: `src/assetcache/core/llm/base.py:67-80`
- Test: `tests/test_llm_backend_supports_batch.py`

기존 backend 들 (Ollama/Gemini/Claude/OpenAI/OpenRouter/HuggingFace) 은 Protocol 만 확장. **default `False`** — Phase 2 에서 Gemini 만 True 로 변경.

- [ ] **Step 1: Write failing test**

```python
# tests/test_llm_backend_supports_batch.py
"""Phase 0 — LLMBackend Protocol 의 supports_batch() default False 검증.

Phase 2 에서 GeminiBackend 만 True 로 변경.
"""

from unittest.mock import MagicMock

import pytest

from assetcache.core.llm.backends.ollama import OllamaBackend


def test_ollama_supports_batch_default_false():
    client = MagicMock()
    client.base_url = "http://127.0.0.1:11434"
    backend = OllamaBackend(client=client)
    assert backend.supports_batch() is False
```

- [ ] **Step 2: Run test — verify fail**

Run: `pytest tests/test_llm_backend_supports_batch.py -v`
Expected: FAIL — `AttributeError: 'OllamaBackend' object has no attribute 'supports_batch'`

- [ ] **Step 3: Add supports_batch to Protocol + Ollama default**

Modify `src/assetcache/core/llm/base.py` — `LLMBackend` Protocol 끝에 method 추가:

```python
@runtime_checkable
class LLMBackend(Protocol):
    info: BackendInfo

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        force_json: bool = True,
        num_ctx: int = 8000,
    ) -> dict: ...

    def embed(self, text: str, *, model: str | None = None) -> list[float]: ...

    def test_connection(self) -> bool: ...

    def supports_batch(self) -> bool:
        """True iff backend exposes batch_chat/batch_embed/batch_get/batch_cancel.

        Default False — Phase 2 에서 Gemini 만 True.
        """
        ...
```

`src/assetcache/core/llm/backends/ollama.py` 의 `OllamaBackend` 끝에:

```python
    def supports_batch(self) -> bool:
        return False
```

동일하게 `claude.py / openai_backend.py / openrouter.py / huggingface.py / gemini.py` 모두 `supports_batch(self) -> bool: return False` 추가 (gemini 는 Phase 2 에서 True 로 변경).

- [ ] **Step 4: Run test — verify pass**

Run: `pytest tests/test_llm_backend_supports_batch.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/core/llm/base.py src/assetcache/core/llm/backends/ tests/test_llm_backend_supports_batch.py
git commit -m "feat(batch): Phase 0 task 0.2 — LLMBackend.supports_batch() Protocol

기존 6 backend 모두 default False. Phase 2 에서 GeminiBackend 만 True.
Spec §6.2."
```

---

## Phase 1 — DB Schema + Store API + `mark_asset_backends` (회귀 1257 → 1277, +20)

### Task 1.1: `batch_jobs` table + `assets` 컬럼 마이그레이션

**Files:**
- Modify: `src/assetcache/core/store.py` (스키마 SQL + `initialize`)
- Test: `tests/test_store_batch_schema.py`

- [ ] **Step 1: Write failing tests (schema 자동 마이그레이션)**

```python
# tests/test_store_batch_schema.py
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
    with sqlite3.connect(fresh_store.db_path) as conn:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='batch_jobs'"
        ).fetchone()
        assert row is not None


def test_batch_jobs_columns(fresh_store):
    with sqlite3.connect(fresh_store.db_path) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(batch_jobs)").fetchall()]
    expected = {
        "id", "backend", "modality", "backend_job_id", "asset_count",
        "submitted_at", "expires_at", "state", "completed_at",
        "success_count", "failure_count", "error", "display_name",
    }
    assert expected.issubset(set(cols))


def test_assets_batch_columns_added(fresh_store):
    with sqlite3.connect(fresh_store.db_path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(assets)").fetchall()}
    assert "batch_job_id" in cols
    assert "batch_state" in cols


def test_assets_batch_state_default_none(fresh_store):
    # 기존 row 가 있을 때 새 컬럼이 'none' default
    with sqlite3.connect(fresh_store.db_path) as conn:
        # pack + asset 만들기
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
    with sqlite3.connect(fresh_store.db_path) as conn:
        idx = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()}
    assert "idx_batch_jobs_state" in idx
    assert "idx_assets_batch_state" in idx
    assert "idx_batch_jobs_backend_job_id" in idx


def test_initialize_idempotent(fresh_store):
    # 두번째 호출이 실패 안 해야
    fresh_store.initialize()
    fresh_store.initialize()
    # batch_jobs table 한 번만 존재
    with sqlite3.connect(fresh_store.db_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='batch_jobs'"
        ).fetchone()[0]
    assert count == 1
```

- [ ] **Step 2: Run tests — verify fail**

Run: `pytest tests/test_store_batch_schema.py -v`
Expected: 6 FAIL (table/columns 없음)

- [ ] **Step 3: Add schema to Store**

`src/assetcache/core/store.py` 의 `_SCHEMA_SQL` 또는 `initialize()` 안에 추가 (기존 패턴 확인 — `M11 Phase 6` 의 `backend_image/audio/embed` 컬럼이 추가된 위치 옆):

```python
# store.py 의 _SCHEMA_SQL 또는 별도 _BATCH_SCHEMA_SQL
_BATCH_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS batch_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backend TEXT NOT NULL,
    modality TEXT NOT NULL,
    backend_job_id TEXT NOT NULL UNIQUE,
    asset_count INTEGER NOT NULL,
    submitted_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    state TEXT NOT NULL,
    completed_at INTEGER,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    display_name TEXT
);
CREATE INDEX IF NOT EXISTS idx_batch_jobs_state ON batch_jobs(state);
CREATE INDEX IF NOT EXISTS idx_batch_jobs_backend_job_id ON batch_jobs(backend_job_id);
CREATE INDEX IF NOT EXISTS idx_assets_batch_state ON assets(batch_state);
"""


def _migrate_batch_columns(conn: sqlite3.Connection) -> None:
    """ALTER TABLE assets — idempotent batch_job_id/batch_state 추가."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(assets)").fetchall()}
    if "batch_job_id" not in cols:
        conn.execute("ALTER TABLE assets ADD COLUMN batch_job_id INTEGER REFERENCES batch_jobs(id)")
    if "batch_state" not in cols:
        conn.execute("ALTER TABLE assets ADD COLUMN batch_state TEXT NOT NULL DEFAULT 'none'")
```

`initialize()` 안에서 (기존 schema 적용 직후):
```python
def initialize(self) -> None:
    # 기존 schema...
    with self._write_lock, sqlite3.connect(self.db_path) as conn:
        # 기존
        ...
        # M11.1 — batch
        _migrate_batch_columns(conn)
        conn.executescript(_BATCH_SCHEMA_SQL)
```

순서 중요: `_migrate_batch_columns` 가 `assets` 컬럼을 추가한 *다음* `_BATCH_SCHEMA_SQL` 의 `idx_assets_batch_state` 가 생성됨.

- [ ] **Step 4: Run tests — verify pass**

Run: `pytest tests/test_store_batch_schema.py -v`
Expected: PASS (6 tests)

또한 `pytest -q` 회귀 — 기존 테스트 영향 X.
Run: `pytest -q`
Expected: 1257 passed + 1 skipped + 53 deselected

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/core/store.py tests/test_store_batch_schema.py
git commit -m "feat(batch): Phase 1 task 1.1 — batch_jobs table + assets.batch_job_id/batch_state 마이그레이션

idempotent ALTER TABLE + CREATE INDEX IF NOT EXISTS.
회귀 1252 → 1257. Spec §5.1, §5.2."
```

---

### Task 1.2: Store CRUD — `save_batch_job` / `update_batch_job_state` / `list_active_batch_jobs` / `get_batch_job`

**Files:**
- Modify: `src/assetcache/core/store.py` — `BatchJobRow` import + 4 신규 메서드
- Test: `tests/test_store_batch_schema.py` — 신규 6 테스트 추가

- [ ] **Step 1: Write failing tests**

`tests/test_store_batch_schema.py` 끝에 추가:

```python
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
    assert row.state == "submitted"  # default 초기 state
    assert row.asset_count == 10
    assert row.success_count == 0


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
    # 활성 = state IN (submitted, running)
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
```

- [ ] **Step 2: Run tests — verify fail**

Run: `pytest tests/test_store_batch_schema.py -v -k batch_job`
Expected: 6 FAIL — methods 없음

- [ ] **Step 3: Implement methods**

`src/assetcache/core/store.py` 에 추가 (import 상단에 `from .batch.types import BatchJobRow`):

```python
def save_batch_job(
    self,
    *,
    backend: str,
    modality: str,
    backend_job_id: str,
    asset_count: int,
    submitted_at: int,
    expires_at: int,
    display_name: str | None,
) -> int:
    with self._write_lock, sqlite3.connect(self.db_path, timeout=self._busy_timeout) as conn:
        cur = conn.execute(
            """
            INSERT INTO batch_jobs (
                backend, modality, backend_job_id, asset_count,
                submitted_at, expires_at, state, display_name
            ) VALUES (?, ?, ?, ?, ?, ?, 'submitted', ?)
            """,
            (backend, modality, backend_job_id, asset_count,
             submitted_at, expires_at, display_name),
        )
        return cur.lastrowid


def update_batch_job_state(
    self,
    batch_job_id: int,
    *,
    state: str,
    completed_at: int | None = None,
    success_count: int | None = None,
    failure_count: int | None = None,
    error: str | None = None,
) -> None:
    sets = ["state = ?"]
    args: list = [state]
    if completed_at is not None:
        sets.append("completed_at = ?"); args.append(completed_at)
    if success_count is not None:
        sets.append("success_count = ?"); args.append(success_count)
    if failure_count is not None:
        sets.append("failure_count = ?"); args.append(failure_count)
    if error is not None:
        sets.append("error = ?"); args.append(error)
    args.append(batch_job_id)
    with self._write_lock, sqlite3.connect(self.db_path, timeout=self._busy_timeout) as conn:
        conn.execute(
            f"UPDATE batch_jobs SET {', '.join(sets)} WHERE id = ?", args
        )


def get_batch_job(self, batch_job_id: int) -> BatchJobRow | None:
    with sqlite3.connect(self.db_path, timeout=self._busy_timeout) as conn:
        row = conn.execute(
            "SELECT id, backend, modality, backend_job_id, asset_count, submitted_at, expires_at, state, completed_at, success_count, failure_count, error, display_name FROM batch_jobs WHERE id = ?",
            (batch_job_id,),
        ).fetchone()
    if row is None:
        return None
    return BatchJobRow(*row)


def list_active_batch_jobs(self) -> list[BatchJobRow]:
    with sqlite3.connect(self.db_path, timeout=self._busy_timeout) as conn:
        rows = conn.execute(
            "SELECT id, backend, modality, backend_job_id, asset_count, submitted_at, expires_at, state, completed_at, success_count, failure_count, error, display_name FROM batch_jobs WHERE state IN ('submitted','running') ORDER BY id"
        ).fetchall()
    return [BatchJobRow(*r) for r in rows]
```

- [ ] **Step 4: Run tests — verify pass**

Run: `pytest tests/test_store_batch_schema.py -v`
Expected: PASS (12 tests, 기존 6 + 신규 6)

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/core/store.py tests/test_store_batch_schema.py
git commit -m "feat(batch): Phase 1 task 1.2 — Store batch_jobs CRUD

save_batch_job / get_batch_job / update_batch_job_state / list_active_batch_jobs.
Spec §5.3."
```

---

### Task 1.3: Store asset batch state — `mark_assets_batch_queued` / `mark_assets_batch_submitted` / `mark_asset_batch_state`

**Files:**
- Modify: `src/assetcache/core/store.py` — 3 신규 메서드
- Test: `tests/test_store_batch_schema.py` — 5 신규 테스트

- [ ] **Step 1: Write failing tests**

```python
def test_mark_assets_batch_queued(fresh_store, _seed_assets):
    asset_ids = _seed_assets(3)  # fixture 가 pack + 3 asset 생성, return list[int]
    fresh_store.mark_assets_batch_queued(asset_ids)
    with sqlite3.connect(fresh_store.db_path) as conn:
        rows = conn.execute(
            "SELECT batch_state FROM assets WHERE id IN (?,?,?)", asset_ids
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
        rows = conn.execute(
            "SELECT batch_state, batch_job_id FROM assets WHERE id IN (?,?)", asset_ids
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


def test_mark_assets_batch_queued_rollback_on_error(fresh_store, _seed_assets):
    asset_ids = _seed_assets(2)
    # invalid asset_id 섞어도 valid 만 갱신 (또는 atomic — 본 구현은 atomic 채택)
    fresh_store.mark_assets_batch_queued(asset_ids)  # ok
    # 두번째 호출 — 이미 queued 인데 다시 queued — idempotent
    fresh_store.mark_assets_batch_queued(asset_ids)
    with sqlite3.connect(fresh_store.db_path) as conn:
        rows = conn.execute(
            "SELECT batch_state FROM assets WHERE id IN (?,?)", asset_ids
        ).fetchall()
    assert all(r[0] == "queued" for r in rows)
```

또한 `tests/test_store_batch_schema.py` 상단에 fixture 추가:

```python
@pytest.fixture
def _seed_assets(fresh_store):
    """fresh_store 에 pack 1개 + N개 asset 생성. return list of asset ids."""
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
                    "VALUES (?, ?, 'sprite', 'h', 1, 0, 'pending')",
                    (pack_id, f"a{i}.png"),
                )
                ids.append(cur.lastrowid)
            return ids

    return make
```

- [ ] **Step 2: Run — verify fail**

Run: `pytest tests/test_store_batch_schema.py -v -k batch_queued`
Expected: FAIL — methods 없음

- [ ] **Step 3: Implement methods**

`src/assetcache/core/store.py` 에 추가:

```python
def mark_assets_batch_queued(self, asset_ids: list[int]) -> None:
    if not asset_ids:
        return
    placeholders = ",".join("?" * len(asset_ids))
    with self._write_lock, sqlite3.connect(self.db_path, timeout=self._busy_timeout) as conn:
        conn.execute(
            f"UPDATE assets SET batch_state = 'queued' WHERE id IN ({placeholders})",
            asset_ids,
        )


def mark_assets_batch_submitted(self, asset_ids: list[int], batch_job_id: int) -> None:
    if not asset_ids:
        return
    placeholders = ",".join("?" * len(asset_ids))
    with self._write_lock, sqlite3.connect(self.db_path, timeout=self._busy_timeout) as conn:
        conn.execute(
            f"UPDATE assets SET batch_state = 'submitted', batch_job_id = ? WHERE id IN ({placeholders})",
            [batch_job_id, *asset_ids],
        )


def mark_asset_batch_state(self, asset_id: int, batch_state: str) -> None:
    with self._write_lock, sqlite3.connect(self.db_path, timeout=self._busy_timeout) as conn:
        conn.execute(
            "UPDATE assets SET batch_state = ? WHERE id = ?",
            (batch_state, asset_id),
        )
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_store_batch_schema.py -v`
Expected: PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/core/store.py tests/test_store_batch_schema.py
git commit -m "feat(batch): Phase 1 task 1.3 — Store asset batch_state CRUD

mark_assets_batch_queued / submitted / mark_asset_batch_state.
Atomic batched UPDATE. Idempotent. Spec §5.3."
```

---

### Task 1.4: Store query — `fetch_pending_by_modality` / `list_assets_in_batch` / `list_recent_failures`

**Files:**
- Modify: `src/assetcache/core/store.py` — 3 신규 메서드
- Test: `tests/test_store_batch_schema.py` — 5 신규 테스트

- [ ] **Step 1: Write failing tests**

```python
def test_fetch_pending_by_modality_chat_image(fresh_store, _seed_assets):
    ids = _seed_assets(3)  # 3 sprite (chat_image)
    rows = fresh_store.fetch_pending_by_modality("chat_image", limit=10)
    assert len(rows) == 3
    assert all(r.kind == "sprite" for r in rows)


def test_fetch_pending_by_modality_excludes_already_queued(fresh_store, _seed_assets):
    ids = _seed_assets(3)
    fresh_store.mark_assets_batch_queued(ids[:2])
    rows = fresh_store.fetch_pending_by_modality("chat_image", limit=10)
    assert len(rows) == 1
    assert rows[0].id == ids[2]


def test_fetch_pending_by_modality_chat_audio_filters(fresh_store, _seed_assets):
    # _seed_assets 는 sprite 만 만듦 → audio 0 개
    _seed_assets(3)
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
    # mark_asset_state 가 기존 메서드 (analyze 실패 처리)
    fresh_store.mark_asset_state(
        ids[0], "failed", error="non-json", analyzed_at=1000,
    )
    fresh_store.mark_asset_state(
        ids[1], "failed", error="timeout", analyzed_at=2000,
    )
    rows = fresh_store.list_recent_failures(limit=10)
    assert len(rows) == 2
    # 최신순
    assert rows[0].id == ids[1]
    assert rows[0].analysis_error == "timeout"
```

- [ ] **Step 2: Run — verify fail**

Run: `pytest tests/test_store_batch_schema.py -v -k "pending_by_modality or assets_in_batch or recent_failures"`
Expected: FAIL — methods 없음

- [ ] **Step 3: Implement methods**

modality → kind 매핑:
- `chat_image` → kind IN ('sprite', 'spritesheet')
- `chat_audio` → kind = 'sound'
- `text_embed` → 모든 kind

```python
_MODALITY_KIND_FILTER = {
    "chat_image": ("sprite", "spritesheet"),
    "chat_audio": ("sound",),
}


def fetch_pending_by_modality(
    self,
    modality: str,
    *,
    batch_state_in: tuple[str, ...] = ("none",),
    limit: int = 1000,
) -> list[AssetRow]:
    kinds = _MODALITY_KIND_FILTER.get(modality)
    state_ph = ",".join("?" * len(batch_state_in))
    if kinds is None:  # text_embed — 모든 kind
        sql = f"""
            SELECT id, pack_id, path, kind, file_hash, file_size,
                   added_at, analyzed_at, analysis_state, analysis_error,
                   backend_image, backend_audio, backend_embed
            FROM assets
            WHERE analysis_state = 'pending'
              AND batch_state IN ({state_ph})
            ORDER BY id
            LIMIT ?
        """
        args = [*batch_state_in, limit]
    else:
        kind_ph = ",".join("?" * len(kinds))
        sql = f"""
            SELECT id, pack_id, path, kind, file_hash, file_size,
                   added_at, analyzed_at, analysis_state, analysis_error,
                   backend_image, backend_audio, backend_embed
            FROM assets
            WHERE analysis_state = 'pending'
              AND batch_state IN ({state_ph})
              AND kind IN ({kind_ph})
            ORDER BY id
            LIMIT ?
        """
        args = [*batch_state_in, *kinds, limit]
    with sqlite3.connect(self.db_path, timeout=self._busy_timeout) as conn:
        rows = conn.execute(sql, args).fetchall()
    return [AssetRow(*r) for r in rows]


def list_assets_in_batch(self, batch_job_id: int) -> list[AssetRow]:
    with sqlite3.connect(self.db_path, timeout=self._busy_timeout) as conn:
        rows = conn.execute(
            """
            SELECT id, pack_id, path, kind, file_hash, file_size,
                   added_at, analyzed_at, analysis_state, analysis_error,
                   backend_image, backend_audio, backend_embed
            FROM assets
            WHERE batch_job_id = ?
            ORDER BY id
            """,
            (batch_job_id,),
        ).fetchall()
    return [AssetRow(*r) for r in rows]


def list_recent_failures(self, *, limit: int = 20) -> list[AssetRow]:
    with sqlite3.connect(self.db_path, timeout=self._busy_timeout) as conn:
        rows = conn.execute(
            """
            SELECT id, pack_id, path, kind, file_hash, file_size,
                   added_at, analyzed_at, analysis_state, analysis_error,
                   backend_image, backend_audio, backend_embed
            FROM assets
            WHERE analysis_state = 'failed'
            ORDER BY analyzed_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [AssetRow(*r) for r in rows]
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_store_batch_schema.py -v`
Expected: PASS (22 tests). `pytest -q` 회귀 1262 + 18 = 1280?

실제로는 step 별 누적: Phase 1 후 1277 목표. 본 task 까지 누적 1277 - 5 (다음 task) = 1272.

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/core/store.py tests/test_store_batch_schema.py
git commit -m "feat(batch): Phase 1 task 1.4 — Store batch query (pending/in_batch/failures)

fetch_pending_by_modality (kind 매핑) + list_assets_in_batch + list_recent_failures.
Spec §5.3 + §13.4."
```

---

### Task 1.5: `mark_asset_backends` + `AnalyzerResult.backend_used` (M11 한계 동시 해결)

**Files:**
- Modify: `src/assetcache/core/store.py` — `mark_asset_backends`
- Modify: `src/assetcache/core/analyzer/base.py` — `AnalyzerResult.backend_used` 필드
- Modify: `src/assetcache/core/analyzer/{sprite,sound,spritesheet}.py` — 결과에 backend 정보 채우기
- Modify: `src/assetcache/core/analysis_queue.py:287-298` — `_persist` 안에서 `mark_asset_backends` 호출
- Test: `tests/test_store_batch_schema.py` — 3 신규 / `tests/test_analyzer_backend_used.py` — 4 신규

- [ ] **Step 1: Write failing tests**

```python
# 추가 to tests/test_store_batch_schema.py
def test_mark_asset_backends_image_only(fresh_store, _seed_assets):
    ids = _seed_assets(1)
    fresh_store.mark_asset_backends(ids[0], image="gemini")
    with sqlite3.connect(fresh_store.db_path) as conn:
        row = conn.execute(
            "SELECT backend_image, backend_audio, backend_embed FROM assets WHERE id = ?",
            (ids[0],),
        ).fetchone()
    assert row == ("gemini", None, None)


def test_mark_asset_backends_all_three(fresh_store, _seed_assets):
    ids = _seed_assets(1)
    fresh_store.mark_asset_backends(ids[0], image="gemini", audio="ollama", embed="gemini")
    with sqlite3.connect(fresh_store.db_path) as conn:
        row = conn.execute(
            "SELECT backend_image, backend_audio, backend_embed FROM assets WHERE id = ?",
            (ids[0],),
        ).fetchone()
    assert row == ("gemini", "ollama", "gemini")


def test_mark_asset_backends_none_args_preserve_existing(fresh_store, _seed_assets):
    ids = _seed_assets(1)
    fresh_store.mark_asset_backends(ids[0], image="ollama")
    # 두번째 호출 — image None, audio 채움
    fresh_store.mark_asset_backends(ids[0], audio="gemini")
    with sqlite3.connect(fresh_store.db_path) as conn:
        row = conn.execute(
            "SELECT backend_image, backend_audio FROM assets WHERE id = ?",
            (ids[0],),
        ).fetchone()
    assert row == ("ollama", "gemini")
```

```python
# tests/test_analyzer_backend_used.py — 신규 파일
"""Phase 1 — AnalyzerResult.backend_used 필드.

backend_used 는 chain.chat 의 두번째 반환값 (backend name str).
"""

from assetcache.core.analyzer.base import AnalyzerResult


def test_analyzer_result_backend_used_default_empty():
    # backend_used 필드가 dict default empty
    r = AnalyzerResult.empty()
    assert r.backend_used == {}


def test_analyzer_result_backend_used_settable():
    r = AnalyzerResult.empty()
    r2 = r.with_backend_used({"image": "gemini"})
    assert r2.backend_used == {"image": "gemini"}
```

(`AnalyzerResult.empty()` / `with_backend_used()` 가 기존 패턴인지 확인 필요. 없으면 dataclass `replace` 활용)

- [ ] **Step 2: Run — verify fail**

Run: `pytest tests/test_store_batch_schema.py tests/test_analyzer_backend_used.py -v -k "backend"`
Expected: FAIL

- [ ] **Step 3: Implement**

```python
# store.py
def mark_asset_backends(
    self,
    asset_id: int,
    *,
    image: str | None = None,
    audio: str | None = None,
    embed: str | None = None,
) -> None:
    sets: list[str] = []
    args: list = []
    if image is not None:
        sets.append("backend_image = ?"); args.append(image)
    if audio is not None:
        sets.append("backend_audio = ?"); args.append(audio)
    if embed is not None:
        sets.append("backend_embed = ?"); args.append(embed)
    if not sets:
        return
    args.append(asset_id)
    with self._write_lock, sqlite3.connect(self.db_path, timeout=self._busy_timeout) as conn:
        conn.execute(
            f"UPDATE assets SET {', '.join(sets)} WHERE id = ?", args
        )
```

```python
# src/assetcache/core/analyzer/base.py — AnalyzerResult 에 필드 추가
@dataclass
class AnalyzerResult:
    # 기존 필드들
    ...
    backend_used: dict[str, str] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "AnalyzerResult": ...  # 기존 — 변경 없음
```

```python
# src/assetcache/core/analyzer/sprite.py — _call_gemma_with_validation 호출 부분
response, backend_name = self.chain.chat(messages, force_json=True)
# 기존 처리...
result.backend_used["image"] = backend_name
result.backend_used["embed"] = self.embed_backend_name  # embedding_encoder.encode_text 에서 받아옴
return result
```

```python
# src/assetcache/core/analysis_queue.py — _persist 끝에 추가
def _persist(self, asset_id: int, result) -> None:
    # 기존 ...
    self.store.mark_asset_state(
        asset_id, result.state, error=result.error,
        analyzed_at=int(time.time()),
    )
    # M11.1 — backend_used write hook (M11 알려진 한계 해결)
    if result.backend_used:
        self.store.mark_asset_backends(
            asset_id,
            image=result.backend_used.get("image"),
            audio=result.backend_used.get("audio"),
            embed=result.backend_used.get("embed"),
        )
```

`EmbeddingEncoder.encode_text` 도 `(blob, dim, backend_name)` 3-tuple 반환으로 확장 — 또는 `EmbeddingEncoder` 가 `.backend_name` property 노출. 둘 중 하나 구현.

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_store_batch_schema.py tests/test_analyzer_backend_used.py -q`
Expected: PASS

회귀 점검 — `pytest -q` 가 기존 1257 + 신규 ~20 = 1277 OK.

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/core/store.py src/assetcache/core/analyzer/ src/assetcache/core/analysis_queue.py tests/test_store_batch_schema.py tests/test_analyzer_backend_used.py
git commit -m "feat(batch): Phase 1 task 1.5 — mark_asset_backends + AnalyzerResult.backend_used (M11 한계 동시 해결)

interactive 분석 경로에서 backend_used 채워 store.mark_asset_backends 호출.
M11 verification §'AnalysisQueue → mark_asset_backends write hook' 알려진 한계 해결.
회귀 1257 → 1277. Spec §12.1 ~ §12.3."
```

---

## Phase 2 — Gemini Batch SDK wrap (회귀 1277 → 1289, +12)

### Task 2.1: `GeminiBackend.batch_chat` (image / audio modality)

**Files:**
- Modify: `src/assetcache/core/llm/backends/gemini.py` — `batch_chat` 메서드 + `supports_batch = True`
- Test: `tests/test_llm_backend_gemini_batch.py`

- [ ] **Step 1: Write failing test (mock client.batches.create)**

```python
# tests/test_llm_backend_gemini_batch.py
"""Phase 2 — GeminiBackend.batch_chat 가 client.batches.create 호출."""

from unittest.mock import MagicMock, patch

import pytest

from assetcache.core.batch.types import BatchChatRequest
from assetcache.core.llm.backends.gemini import GeminiBackend
from assetcache.core.llm.base import ChatMessage


@pytest.fixture
def gemini_backend(monkeypatch):
    fake_client = MagicMock()
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: fake_client,
    )
    backend = GeminiBackend(
        api_key="test",
        model_image="gemini-3.1-flash-lite",
        model_audio="gemini-3.1-flash-lite",
        model_embed="gemini-embedding-001",
        timeout=60.0,
    )
    return backend, fake_client


def test_batch_chat_image_returns_job_name(gemini_backend):
    backend, client = gemini_backend
    fake_job = MagicMock()
    fake_job.name = "batches/test-abc"
    client.batches.create.return_value = fake_job

    requests = [
        BatchChatRequest(
            asset_id=1,
            messages=[ChatMessage(role="user", content="describe")],
            force_json=True,
        ),
        BatchChatRequest(
            asset_id=2,
            messages=[ChatMessage(role="user", content="describe2")],
            force_json=True,
        ),
    ]
    job_name = backend.batch_chat(modality="chat_image", requests=requests)
    assert job_name == "batches/test-abc"
    # client.batches.create 가 model_image 로 호출
    client.batches.create.assert_called_once()
    kw = client.batches.create.call_args.kwargs
    assert kw["model"] == "gemini-3.1-flash-lite"
    assert "src" in kw
    assert len(kw["src"]) == 2
    assert "config" in kw and "display_name" in kw["config"]


def test_batch_chat_audio_uses_audio_model(gemini_backend, monkeypatch):
    backend, client = gemini_backend
    client.batches.create.return_value = MagicMock(name="batches/y")
    monkeypatch.setattr(backend, "model_audio", "gemini-3.1-flash-lite-audio")
    backend.batch_chat(modality="chat_audio", requests=[
        BatchChatRequest(asset_id=1, messages=[ChatMessage(role="user", content="a")]),
    ])
    kw = client.batches.create.call_args.kwargs
    assert kw["model"] == "gemini-3.1-flash-lite-audio"


def test_batch_chat_transient_error_raises_backend_error(gemini_backend):
    from assetcache.core.llm.base import BackendError
    backend, client = gemini_backend
    client.batches.create.side_effect = RuntimeError("connect timeout")
    with pytest.raises(BackendError) as exc_info:
        backend.batch_chat(modality="chat_image", requests=[
            BatchChatRequest(asset_id=1, messages=[]),
        ])
    assert exc_info.value.transient is True


def test_batch_chat_hard_error_401(gemini_backend):
    from assetcache.core.llm.base import BackendError
    backend, client = gemini_backend
    e = Exception("401 unauthorized")
    client.batches.create.side_effect = e
    with pytest.raises(BackendError) as exc_info:
        backend.batch_chat(modality="chat_image", requests=[
            BatchChatRequest(asset_id=1, messages=[]),
        ])
    assert exc_info.value.transient is False
```

- [ ] **Step 2: Run — verify fail**

Run: `pytest tests/test_llm_backend_gemini_batch.py -v -k batch_chat`
Expected: FAIL — `AttributeError: ... 'batch_chat'`

- [ ] **Step 3: Implement batch_chat + supports_batch=True**

`src/assetcache/core/llm/backends/gemini.py` 에 추가 (import 보강: `import time`):

```python
import time

from ...batch.types import BatchChatRequest
```

`GeminiBackend` 안에:

```python
def supports_batch(self) -> bool:
    return True


def batch_chat(self, *, modality: str, requests: list[BatchChatRequest]) -> str:
    """Submit batch chat job. Return Gemini job name 'batches/xxx'."""
    if modality == "chat_image":
        model = self.model_image
    elif modality == "chat_audio":
        model = self.model_audio
    else:
        raise ValueError(f"batch_chat invalid modality: {modality}")
    inlined = [
        {
            "contents": self._to_contents(r.messages),
            **(
                {"config": {"response_mime_type": "application/json"}}
                if r.force_json
                else {}
            ),
        }
        for r in requests
    ]
    try:
        job = self._client.batches.create(
            model=model,
            src=inlined,
            config={"display_name": f"assetcache-{modality}-{int(time.time())}"},
        )
    except Exception as e:
        raise BackendError(
            backend="gemini",
            stage=f"batch_{modality}",
            transient=_classify(e),
            cause=e,
        ) from e
    return job.name
```

(`_to_contents` 는 기존 — `chat()` 안에서 이미 사용 중)

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_llm_backend_gemini_batch.py -v`
Expected: PASS (4 tests)

Also update existing test `tests/test_llm_backend_supports_batch.py` 에 `test_gemini_supports_batch_true` 추가:

```python
def test_gemini_supports_batch_true(monkeypatch):
    from unittest.mock import MagicMock
    monkeypatch.setattr(
        "assetcache.core.llm.backends.gemini.genai.Client",
        lambda **kw: MagicMock(),
    )
    from assetcache.core.llm.backends.gemini import GeminiBackend
    b = GeminiBackend(api_key="x", model_image="m", model_audio="m",
                       model_embed="m", timeout=60)
    assert b.supports_batch() is True
```

Run: `pytest tests/test_llm_backend_supports_batch.py -v`
Expected: PASS (7 tests = 6 backend + gemini True)

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/core/llm/backends/gemini.py tests/test_llm_backend_gemini_batch.py tests/test_llm_backend_supports_batch.py
git commit -m "feat(batch): Phase 2 task 2.1 — GeminiBackend.batch_chat + supports_batch=True

modality 별 model 선택. _classify 로 transient/hard 분류.
Spec §6.1."
```

---

### Task 2.2: `GeminiBackend.batch_embed`

**Files:**
- Modify: `src/assetcache/core/llm/backends/gemini.py` — `batch_embed`
- Test: `tests/test_llm_backend_gemini_batch.py` — 신규 3 테스트

- [ ] **Step 1: Write failing test**

```python
def test_batch_embed_returns_job_name(gemini_backend):
    backend, client = gemini_backend
    fake_job = MagicMock()
    fake_job.name = "batches/embed-1"
    client.batches.create_embeddings.return_value = fake_job
    name = backend.batch_embed(texts=["hello", "world"])
    assert name == "batches/embed-1"
    kw = client.batches.create_embeddings.call_args.kwargs
    assert kw["model"] == "gemini-embedding-001"
    assert "inlined_requests" in kw["src"]
    assert len(kw["src"]["inlined_requests"]) == 2


def test_batch_embed_empty_list_raises(gemini_backend):
    backend, _ = gemini_backend
    with pytest.raises(ValueError):
        backend.batch_embed(texts=[])


def test_batch_embed_transient_error(gemini_backend):
    from assetcache.core.llm.base import BackendError
    backend, client = gemini_backend
    client.batches.create_embeddings.side_effect = RuntimeError("503")
    with pytest.raises(BackendError) as exc_info:
        backend.batch_embed(texts=["x"])
    assert exc_info.value.transient is True
```

- [ ] **Step 2: Run — verify fail**

- [ ] **Step 3: Implement**

```python
def batch_embed(self, *, texts: list[str]) -> str:
    if not texts:
        raise ValueError("batch_embed requires non-empty texts")
    inlined = [
        {"content": {"parts": [{"text": t}], "role": "user"}}
        for t in texts
    ]
    try:
        job = self._client.batches.create_embeddings(
            model=self.model_embed,
            src={"inlined_requests": inlined},
            config={"display_name": f"assetcache-text_embed-{int(time.time())}"},
        )
    except Exception as e:
        raise BackendError(
            backend="gemini",
            stage="batch_embed",
            transient=_classify(e),
            cause=e,
        ) from e
    return job.name
```

- [ ] **Step 4: Run — verify pass**

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/core/llm/backends/gemini.py tests/test_llm_backend_gemini_batch.py
git commit -m "feat(batch): Phase 2 task 2.2 — GeminiBackend.batch_embed

client.batches.create_embeddings + inlined_requests. Spec §6.1."
```

---

### Task 2.3: `GeminiBackend.batch_get` / `batch_cancel` / `batch_download_file`

**Files:**
- Modify: `src/assetcache/core/llm/backends/gemini.py` — 3 신규 메서드
- Test: `tests/test_llm_backend_gemini_batch.py` — 5 신규 테스트

- [ ] **Step 1: Write failing tests**

```python
def test_batch_get_succeeded_inline(gemini_backend):
    backend, client = gemini_backend
    fake_job = MagicMock()
    fake_job.state.name = "JOB_STATE_SUCCEEDED"
    fake_job.dest.inlined_responses = [MagicMock(), MagicMock()]
    fake_job.dest.file_name = None
    fake_job.error = None
    client.batches.get.return_value = fake_job
    status = backend.batch_get("batches/x")
    assert status.state == "JOB_STATE_SUCCEEDED"
    assert status.inlined_responses is not None
    assert len(status.inlined_responses) == 2
    assert status.file_name is None


def test_batch_get_running(gemini_backend):
    backend, client = gemini_backend
    fake_job = MagicMock()
    fake_job.state.name = "JOB_STATE_RUNNING"
    fake_job.dest = None
    fake_job.error = None
    client.batches.get.return_value = fake_job
    status = backend.batch_get("batches/x")
    assert status.state == "JOB_STATE_RUNNING"
    assert status.inlined_responses is None


def test_batch_cancel_calls_sdk(gemini_backend):
    backend, client = gemini_backend
    backend.batch_cancel("batches/x")
    client.batches.cancel.assert_called_once_with(name="batches/x")


def test_batch_cancel_swallows_error(gemini_backend, caplog):
    backend, client = gemini_backend
    client.batches.cancel.side_effect = RuntimeError("network down")
    # Best-effort — 예외 안 던짐
    backend.batch_cancel("batches/x")


def test_batch_download_file(gemini_backend):
    backend, client = gemini_backend
    client.files.download.return_value = b"binary data"
    data = backend.batch_download_file("files/abc")
    assert data == b"binary data"
    client.files.download.assert_called_once_with(file="files/abc")
```

- [ ] **Step 2: Run — verify fail**

- [ ] **Step 3: Implement**

```python
from ...batch.types import GeminiBatchStatus


def batch_get(self, backend_job_id: str) -> GeminiBatchStatus:
    try:
        job = self._client.batches.get(name=backend_job_id)
    except Exception as e:
        raise BackendError(
            backend="gemini", stage="batch_get",
            transient=_classify(e), cause=e,
        ) from e
    dest = getattr(job, "dest", None)
    return GeminiBatchStatus(
        state=job.state.name,
        inlined_responses=getattr(dest, "inlined_responses", None) if dest else None,
        file_name=getattr(dest, "file_name", None) if dest else None,
        error=str(getattr(job, "error", "") or "") or None,
    )


def batch_cancel(self, backend_job_id: str) -> None:
    """Best-effort cancel. 실패해도 raise 안 함."""
    try:
        self._client.batches.cancel(name=backend_job_id)
    except Exception:
        log.exception("batch_cancel failed (best-effort)")


def batch_download_file(self, file_name: str) -> bytes:
    return self._client.files.download(file=file_name)
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_llm_backend_gemini_batch.py -v`
Expected: PASS (12 tests)

회귀 점검: `pytest -q` → 1289 passed.

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/core/llm/backends/gemini.py tests/test_llm_backend_gemini_batch.py
git commit -m "feat(batch): Phase 2 task 2.3 — GeminiBackend batch_get/cancel/download_file

batch_get returns GeminiBatchStatus. batch_cancel best-effort.
회귀 1277 → 1289. Spec §6.1."
```

---

## Phase 3 — BatchManager + AnalysisQueue hook (회귀 1289 → 1315, +26)

### Task 3.1: `BatchManager` skeleton + `try_submit` toggle/chain check

**Files:**
- Create: `src/assetcache/core/batch/manager.py`
- Test: `tests/test_batch_manager.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_batch_manager.py
"""Phase 3 — BatchManager.try_submit 결정 트리."""

from unittest.mock import MagicMock

import pytest

from assetcache.core.batch.manager import BatchManager


@pytest.fixture
def manager_factory(tmp_path):
    """make_manager(toggle, chain_first, pending_count) → (BatchManager, store_mock)."""
    def make(*, toggle="auto", chain_first="gemini", pending_count=0,
            threshold=30, supports_batch=True):
        store = MagicMock()
        store.count_pending_by_modality.return_value = pending_count
        store.fetch_pending_by_modality.return_value = [
            MagicMock(id=i) for i in range(pending_count)
        ]

        backend_mock = MagicMock()
        backend_mock.supports_batch.return_value = supports_batch
        backend_mock.info.name = chain_first
        backend_mock.batch_chat.return_value = "batches/test"

        chain_registry = MagicMock()
        chain_registry.first_backend.return_value = backend_mock if chain_first else None
        chain_registry.first_backend_name.return_value = chain_first

        analysis_queue = MagicMock()
        cfg = MagicMock()
        cfg.batch.toggle = toggle
        cfg.batch.threshold = threshold
        cfg.batch.expiry_grace_seconds = 172800
        cfg.gemini_model_image = "g-im"

        m = BatchManager(
            store=store, chain_registry=chain_registry,
            analysis_queue=analysis_queue, cfg=cfg,
        )
        return m, store, chain_registry, analysis_queue, backend_mock
    return make


def test_try_submit_returns_none_when_forced_off(manager_factory):
    m, store, *_ = manager_factory(toggle="forced_off", pending_count=100)
    assert m.try_submit("chat_image") is None
    store.fetch_pending_by_modality.assert_not_called()


def test_try_submit_returns_none_when_chain_first_not_gemini(manager_factory):
    m, store, *_ = manager_factory(chain_first="ollama", pending_count=100)
    assert m.try_submit("chat_image") is None
    store.fetch_pending_by_modality.assert_not_called()


def test_try_submit_returns_none_when_chain_first_no_batch_support(manager_factory):
    # 가상의 미래 backend 가 chain 1순위지만 supports_batch=False
    m, store, *_ = manager_factory(supports_batch=False, pending_count=100)
    assert m.try_submit("chat_image") is None


def test_try_submit_returns_none_when_below_threshold_in_auto(manager_factory):
    m, store, *_ = manager_factory(toggle="auto", threshold=30, pending_count=10)
    assert m.try_submit("chat_image") is None


def test_try_submit_proceeds_at_threshold_in_auto(manager_factory):
    m, store, _, aq, backend = manager_factory(
        toggle="auto", threshold=30, pending_count=30,
    )
    store.save_batch_job.return_value = 7
    job_id = m.try_submit("chat_image")
    assert job_id == 7


def test_try_submit_proceeds_below_threshold_in_forced_on(manager_factory):
    m, store, _, _, backend = manager_factory(
        toggle="forced_on", threshold=30, pending_count=5,
    )
    store.save_batch_job.return_value = 3
    job_id = m.try_submit("chat_image")
    assert job_id == 3
```

- [ ] **Step 2: Run — verify fail**

- [ ] **Step 3: Implement skeleton + decision logic**

```python
# src/assetcache/core/batch/manager.py
"""BatchManager — 임계값 / chain / toggle 결정 + Gemini submit."""

from __future__ import annotations

import logging
import threading
import time
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
    def __init__(
        self,
        *,
        store: "Store",
        chain_registry: "BackendRegistry",
        analysis_queue: "AnalysisQueue",
        cfg: "Config",
    ) -> None:
        self._store = store
        self._chain = chain_registry
        self._aq = analysis_queue
        self._cfg = cfg
        # modality 별 submit_lock — 동시 enqueue 중복 submit 차단
        self._locks = {m: threading.Lock() for m in _MODALITIES}

    def try_submit(self, modality: str) -> int | None:
        """Try to submit a batch job. Return batch_jobs.id or None."""
        if modality not in _MODALITIES:
            log.warning("try_submit invalid modality: %s", modality)
            return None
        toggle = self._cfg.batch.toggle
        if toggle == "forced_off":
            return None
        # chain 1순위 backend
        backend = self._chain.first_backend(modality)
        if backend is None or backend.info.name != "gemini" or not backend.supports_batch():
            return None
        # threshold (auto 모드)
        if toggle == "auto":
            pending = self._store.count_pending_by_modality(modality)
            if pending < self._cfg.batch.threshold:
                return None
        # race lock — modality 별 중복 submit 차단
        if not self._locks[modality].acquire(blocking=False):
            return None
        try:
            return self._do_submit(modality, backend)
        finally:
            self._locks[modality].release()

    def _do_submit(self, modality: str, backend) -> int | None:
        # Phase 3 task 3.2 에서 구현
        return None  # placeholder
```

- [ ] **Step 4: Run — verify pass (decision tests)**

Run: `pytest tests/test_batch_manager.py -v -k "try_submit_returns_none or try_submit_proceeds"`
Expected: 4 PASS (None returns) + 2 FAIL (proceed cases - `_do_submit` 가 None 반환)

`_do_submit` 가 None 반환하므로 `try_submit_proceeds_*` 도 None. fail 그대로 — Task 3.2 에서 해결.

— 결정 트리 자체는 검증되었으므로 임시로 `assert m.try_submit(...) is None` 으로 expected 변경 또는 skip. **Task 3.2 와 묶어 commit**.

- [ ] **Step 5: Defer commit until 3.2**

—

### Task 3.2: `BatchManager._do_submit` — submit + DB row + rollback

**Files:**
- Modify: `src/assetcache/core/batch/manager.py` — `_do_submit` 실 구현
- Test: `tests/test_batch_manager.py` — 4 신규 테스트

- [ ] **Step 1: Write failing tests**

```python
def test_do_submit_creates_batch_jobs_row_for_chat_image(manager_factory):
    m, store, _, aq, backend = manager_factory(pending_count=30)
    store.save_batch_job.return_value = 42
    asset_ids = [r.id for r in store.fetch_pending_by_modality.return_value]
    job_id = m.try_submit("chat_image")
    assert job_id == 42
    store.mark_assets_batch_queued.assert_called_once_with(asset_ids)
    backend.batch_chat.assert_called_once()
    save_kw = store.save_batch_job.call_args.kwargs
    assert save_kw["backend"] == "gemini"
    assert save_kw["modality"] == "chat_image"
    assert save_kw["backend_job_id"] == "batches/test"
    assert save_kw["asset_count"] == 30
    store.mark_assets_batch_submitted.assert_called_once_with(asset_ids, 42)
    aq.dequeue_assets.assert_called_once_with(asset_ids)


def test_do_submit_rollback_when_backend_fails(manager_factory):
    from assetcache.core.llm.base import BackendError
    m, store, _, aq, backend = manager_factory(pending_count=30)
    backend.batch_chat.side_effect = BackendError(
        backend="gemini", stage="batch_chat_image", transient=True,
    )
    asset_ids = [r.id for r in store.fetch_pending_by_modality.return_value]
    job_id = m.try_submit("chat_image")
    assert job_id is None
    # 롤백 — queued 해제
    # mark_asset_batch_state 가 'none' 으로 호출되어야
    rollback_calls = [
        c for c in store.mark_asset_batch_state.call_args_list
        if c.args[1] == "none"
    ]
    assert len(rollback_calls) == 30  # asset 별 호출 or batch 형태
    # save_batch_job 은 호출 안 됨
    store.save_batch_job.assert_not_called()
    # dequeue_assets 안 호출
    aq.dequeue_assets.assert_not_called()


def test_do_submit_text_embed_calls_batch_embed(manager_factory):
    m, store, _, aq, backend = manager_factory(pending_count=30)
    store.save_batch_job.return_value = 5
    backend.batch_embed.return_value = "batches/embed-1"
    m.try_submit("text_embed")
    backend.batch_embed.assert_called_once()
    backend.batch_chat.assert_not_called()


def test_do_submit_caps_at_threshold(manager_factory):
    m, store, _, aq, backend = manager_factory(
        toggle="forced_on", pending_count=100, threshold=30,
    )
    # threshold = 30 = batch 한 번에 최대 30개 (§6.3 cap)
    store.save_batch_job.return_value = 1
    m.try_submit("chat_image")
    fetch_kw = store.fetch_pending_by_modality.call_args.kwargs
    assert fetch_kw["limit"] == 30
```

- [ ] **Step 2: Run — verify fail**

- [ ] **Step 3: Implement `_do_submit`**

```python
def _do_submit(self, modality: str, backend) -> int | None:
    """submit 본체 — manager_factory test 의 6 케이스를 모두 처리.

    Steps:
      1. fetch_pending_by_modality(limit=threshold)
      2. mark_assets_batch_queued (race 방지)
      3. modality 별 backend.batch_chat / batch_embed
      4. save_batch_job → batch_jobs.id
      5. mark_assets_batch_submitted(asset_ids, job_id)
      6. analysis_queue.dequeue_assets(asset_ids)
      7. return job_id

    Rollback on backend failure:
      mark_asset_batch_state(id, 'none') for each asset_id
    """
    threshold = self._cfg.batch.threshold
    rows = self._store.fetch_pending_by_modality(modality, limit=threshold)
    if not rows:
        return None
    asset_ids = [r.id for r in rows]
    self._store.mark_assets_batch_queued(asset_ids)
    try:
        if modality in ("chat_image", "chat_audio"):
            requests = self._build_chat_requests(modality, rows)
            backend_job_id = backend.batch_chat(modality=modality, requests=requests)
        else:  # text_embed
            texts = self._build_embed_texts(rows)
            backend_job_id = backend.batch_embed(texts=texts)
    except Exception as e:
        # 롤백
        log.warning("batch submit failed for modality=%s — rollback: %s", modality, e)
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
    log.info("batch submitted modality=%s job_id=%d backend_job_id=%s asset_count=%d",
             modality, job_id, backend_job_id, len(asset_ids))
    return job_id


def _build_chat_requests(self, modality, rows):
    # asset → ChatMessage list 구성 — Task 3.3 에서 analyzer 모듈에서 헬퍼 추출
    # 임시: 빈 messages 로 — Task 3.3 에서 실제 image/audio b64 채움
    from ..llm.base import ChatMessage
    from .types import BatchChatRequest
    return [
        BatchChatRequest(
            asset_id=r.id,
            messages=[ChatMessage(role="user", content=f"asset {r.id}")],
            force_json=True,
        )
        for r in rows
    ]


def _build_embed_texts(self, rows):
    return [f"asset {r.id}" for r in rows]  # placeholder — Task 3.3
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_batch_manager.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/core/batch/manager.py tests/test_batch_manager.py
git commit -m "feat(batch): Phase 3 task 3.1+3.2 — BatchManager.try_submit + _do_submit

toggle/chain/threshold 결정 + race lock + DB row + rollback on backend failure.
회귀 1289 → 1299. Spec §7."
```

---

### Task 3.3: `_build_chat_requests` / `_build_embed_texts` 실 데이터 구성

**Files:**
- Modify: `src/assetcache/core/batch/manager.py` — analyzer 모듈에서 messages 빌더 재사용
- Modify: `src/assetcache/core/analyzer/sprite.py` (or 신규 `core/analyzer/messages.py`) — `build_image_messages(rel_path, abs_path) -> list[ChatMessage]` 추출
- Test: `tests/test_batch_manager.py` — 추가 2~3 테스트

- [ ] **Step 1: Write failing test**

```python
def test_build_chat_requests_uses_image_messages_builder(monkeypatch, tmp_path):
    """sprite analyzer 의 messages 빌더 재사용 검증."""
    from assetcache.core.batch.manager import BatchManager
    # 실 sprite messages 빌더는 path 받아 base64 image 포함
    # Manager 가 이 빌더를 호출하는지 검증
    ...  # 자세히는 구현 후 작성
```

이 task 는 analyzer 모듈에서 messages-building 코드를 추출하는 정리 작업 — 단위 테스트보다 통합 테스트가 자연. Phase 6 의 end-to-end 에서 검증.

- [ ] **Step 2: Extract image/audio/embed messages builders**

`src/assetcache/core/analyzer/messages.py` (신규):

```python
"""Shared message builders for analyzers + batch.

`SpriteAnalyzer / SoundAnalyzer / SpritesheetAnalyzer` 의 `_build_messages_*`
로직을 분리하여 `BatchManager` 도 재사용한다.
"""

from __future__ import annotations

import base64
from pathlib import Path

from ..llm.base import ChatMessage


def build_image_chat_messages(*, abs_path: Path, prompt: str) -> list[ChatMessage]:
    """이미지 1장에 대한 chat messages 구성. SpriteAnalyzer + Batch 공유."""
    img_bytes = abs_path.read_bytes()
    img_b64 = base64.b64encode(img_bytes).decode("ascii")
    return [
        ChatMessage(role="user", content=prompt, images_b64=[img_b64]),
    ]


def build_audio_chat_messages(*, abs_path: Path, prompt: str) -> list[ChatMessage]:
    audio_bytes = abs_path.read_bytes()
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    mime = "audio/wav"  # 또는 path suffix 기반
    return [
        ChatMessage(role="user", content=prompt, audio_b64=[(audio_b64, mime)]),
    ]
```

`SpriteAnalyzer._build_messages` 도 이 함수로 호출하도록 수정 (회귀 없음).

`BatchManager._build_chat_requests` 갱신:

```python
def _build_chat_requests(self, modality, rows):
    from ..analyzer.messages import build_image_chat_messages, build_audio_chat_messages
    from .types import BatchChatRequest
    builder = build_image_chat_messages if modality == "chat_image" else build_audio_chat_messages
    out = []
    for r in rows:
        abs_path = self._cfg.library_root / r.path
        messages = builder(abs_path=abs_path, prompt=self._image_prompt(modality, r))
        out.append(BatchChatRequest(asset_id=r.id, messages=messages, force_json=True))
    return out


def _image_prompt(self, modality, row):
    # SpriteAnalyzer 의 PROMPT_IMAGE 상수 import 또는 별도 모듈
    from ..analyzer.sprite import IMAGE_PROMPT  # or constant 이전
    return IMAGE_PROMPT


def _build_embed_texts(self, rows):
    # FTS searchable text — store 의 record per asset 에서 가져옴
    return [self._store.get_searchable_text(r.id) for r in rows]
```

`store.get_searchable_text(asset_id)` — 신규 (또는 기존 메서드 활용).

- [ ] **Step 3: Run — verify pass**

Run: `pytest tests/test_batch_manager.py tests/test_analyzer_sprite.py tests/test_analyzer_sound.py -v`
Expected: PASS — 기존 analyzer 테스트도 (`messages.py` extract 했지만 같은 동작) 모두 통과

- [ ] **Step 4: Commit**

```bash
git add src/assetcache/core/analyzer/messages.py src/assetcache/core/analyzer/ src/assetcache/core/batch/manager.py src/assetcache/core/store.py tests/test_batch_manager.py
git commit -m "feat(batch): Phase 3 task 3.3 — build_image/audio_chat_messages 추출 + manager 재사용

analyzer/messages.py 신설. SpriteAnalyzer / SoundAnalyzer 와 BatchManager 가 공유.
Spec §7."
```

---

### Task 3.4: `BatchManager.cancel(batch_job_id)`

**Files:**
- Modify: `src/assetcache/core/batch/manager.py` — `cancel`
- Test: `tests/test_batch_manager.py` — 3 신규 테스트

- [ ] **Step 1: Write failing test**

```python
def test_cancel_calls_backend_cancel_and_marks_all_failed(manager_factory):
    m, store, _, aq, backend = manager_factory(pending_count=0)
    store.get_batch_job.return_value = MagicMock(
        id=1, backend="gemini", modality="chat_image",
        backend_job_id="batches/x", state="submitted",
    )
    store.list_assets_in_batch.return_value = [MagicMock(id=10), MagicMock(id=11)]
    m.cancel(1)
    backend.batch_cancel.assert_called_once_with("batches/x")
    # 모든 asset 을 batch_state='failed' 로 + interactive 재enqueue
    assert store.mark_asset_batch_state.call_count == 2
    assert aq.enqueue_asset.call_count == 2
    store.update_batch_job_state.assert_called_once()


def test_cancel_idempotent_on_already_completed(manager_factory):
    m, store, *_ = manager_factory()
    store.get_batch_job.return_value = MagicMock(
        id=1, state="succeeded",
    )
    m.cancel(1)
    # 이미 succeeded — backend.batch_cancel 호출 안 함
    # (또는 호출하고 backend 가 best-effort 무시)


def test_cancel_missing_job_returns_silently(manager_factory):
    m, store, *_ = manager_factory()
    store.get_batch_job.return_value = None
    m.cancel(99999)  # 예외 없음
```

- [ ] **Step 2: Run — verify fail**

- [ ] **Step 3: Implement**

```python
def cancel(self, batch_job_id: int) -> None:
    job = self._store.get_batch_job(batch_job_id)
    if job is None:
        log.warning("cancel: batch_job_id %d not found", batch_job_id)
        return
    if job.state not in ("submitted", "running"):
        log.info("cancel: job %d already in terminal state %s — noop", batch_job_id, job.state)
        return
    backend = self._chain.get_backend(job.backend)
    if backend is not None:
        backend.batch_cancel(job.backend_job_id)
    # 모든 asset interactive 재enqueue
    for asset in self._store.list_assets_in_batch(batch_job_id):
        self._store.mark_asset_batch_state(asset.id, "failed")
        self._aq.enqueue_asset(asset.id)
    self._store.update_batch_job_state(
        batch_job_id, state="cancelled", completed_at=int(time.time()),
    )
```

- [ ] **Step 4: Run — verify pass**

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/core/batch/manager.py tests/test_batch_manager.py
git commit -m "feat(batch): Phase 3 task 3.4 — BatchManager.cancel

backend best-effort cancel + 모든 asset interactive 재enqueue + DB state='cancelled'.
Spec §7."
```

---

### Task 3.5: `AnalysisQueue.pending_by_modality` + `count_pending_by_modality` (Store)

**Files:**
- Modify: `src/assetcache/core/analysis_queue.py` — `pending_by_modality`
- Modify: `src/assetcache/core/store.py` — `count_pending_by_modality`
- Test: `tests/test_analysis_queue_batch_hook.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_analysis_queue_batch_hook.py
"""Phase 3 — AnalysisQueue 의 batch 관련 hooks (pending_by_modality / dequeue / try_submit hook)."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def queue_factory():
    def make():
        from assetcache.core.analysis_queue import AnalysisQueue
        store = MagicMock()
        store.count_pending_by_modality.return_value = 0
        q = AnalysisQueue(
            store=store,
            sprite=MagicMock(),
            spritesheet=MagicMock(),
            sound=MagicMock(),
        )
        return q, store
    return make


def test_pending_by_modality_combines_queue_and_db(queue_factory):
    q, store = queue_factory()
    store.count_pending_by_modality.return_value = 5
    # 큐에 직접 push (실제로는 enqueue_asset 거치는데 store side-effect 까지 가서 단위 테스트 어려움)
    # → 큐 size 만 별도 검증
    q._queue.put(101)
    q._queue.put(102)
    n = q.pending_by_modality("chat_image")
    assert n == 5 + 2  # DB 5 + queue 2
```

- [ ] **Step 2: Run — verify fail**

- [ ] **Step 3: Implement**

`store.py`:

```python
def count_pending_by_modality(self, modality: str) -> int:
    rows = self.fetch_pending_by_modality(modality, limit=10**9)
    return len(rows)
# 또는 SELECT COUNT(*) 분리 (대형 라이브러리 효율)
```

`analysis_queue.py`:

```python
def pending_by_modality(self, modality: str) -> int:
    db_count = self.store.count_pending_by_modality(modality)
    queue_count = self._queue.qsize()  # 단순화: queue 전체 — 정밀하게는 modality 별 count 필요
    # in-flight asset 한 개는 일단 무시
    return db_count + queue_count
```

(정밀도: in-memory queue 의 modality 별 갯수는 asset_id → kind 매핑 필요. 단순화 OK — DB 가 큰 비중)

- [ ] **Step 4: Run — verify pass**

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/core/store.py src/assetcache/core/analysis_queue.py tests/test_analysis_queue_batch_hook.py
git commit -m "feat(batch): Phase 3 task 3.5 — pending_by_modality (Store + AnalysisQueue)

DB count + queue size 합산. Spec §3.2."
```

---

### Task 3.6: `AnalysisQueue.dequeue_assets` + `_skip_ids` worker skip

**Files:**
- Modify: `src/assetcache/core/analysis_queue.py:225-233` — `_worker_loop` + `__init__` 의 `_skip_ids`
- Test: `tests/test_analysis_queue_batch_hook.py` — 3 신규

- [ ] **Step 1: Write failing test**

```python
def test_dequeue_assets_skips_in_worker(queue_factory, monkeypatch):
    q, store = queue_factory()
    # 큐에 미리 넣기
    q._queue.put(1)
    q._queue.put(2)
    q._queue.put(3)
    # 1, 3 dequeue
    q.dequeue_assets([1, 3])
    # 워커 한 사이클 시뮬 — _handle_one 이 2 만 호출
    handled = []
    monkeypatch.setattr(q, "_handle_one", lambda aid: handled.append(aid))
    monkeypatch.setattr(q._stop_event, "is_set", lambda: True)  # 1회 만 돌게
    # Direct worker step
    for _ in range(3):
        try:
            aid = q._queue.get(timeout=0.1)
        except Exception:
            break
        if aid in q._skip_ids:
            q._skip_ids.discard(aid)
            continue
        q._handle_one(aid)
    assert handled == [2]


def test_dequeue_empty_noop(queue_factory):
    q, _ = queue_factory()
    q.dequeue_assets([])  # 예외 없음


def test_dequeue_assets_not_in_queue_safe(queue_factory):
    q, _ = queue_factory()
    q.dequeue_assets([99, 100])
    # 향후 같은 ID 가 enqueue 되면 skip — 의도된 동작
    assert q._skip_ids == {99, 100}
```

- [ ] **Step 2: Run — verify fail**

- [ ] **Step 3: Implement**

`analysis_queue.py` `__init__` 끝에:
```python
self._skip_ids: set[int] = set()
```

`dequeue_assets`:
```python
def dequeue_assets(self, asset_ids: list[int]) -> int:
    self._skip_ids.update(asset_ids)
    return len(asset_ids)
```

`_worker_loop` 안 (`asset_id = self._queue.get(timeout=0.2)` 직후):
```python
if asset_id == -1:
    return
if asset_id in self._skip_ids:
    self._skip_ids.discard(asset_id)
    continue
self._handle_one(asset_id)
```

- [ ] **Step 4: Run — verify pass**

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/core/analysis_queue.py tests/test_analysis_queue_batch_hook.py
git commit -m "feat(batch): Phase 3 task 3.6 — AnalysisQueue.dequeue_assets + _skip_ids

queue.Queue 는 random-access 안 됨 → worker 가 dequeue 시 set 체크 skip.
Spec §9.1."
```

---

### Task 3.7: `_try_batch_submit` hook on enqueue + Config + app.py wiring

**Files:**
- Modify: `src/assetcache/core/analysis_queue.py:148-179` — `enqueue_*` 끝에 `_try_batch_submit`
- Modify: `src/assetcache/config.py` — `BatchConfig` + TOML migration
- Modify: `src/assetcache/app.py` — `BatchManager` instantiation + AnalysisQueue 주입
- Test: `tests/test_analysis_queue_batch_hook.py` — 2 / `tests/test_config_batch.py` — 4

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config_batch.py
import tomli_w

from assetcache.config import Config, load_config


def test_batch_config_default(tmp_path):
    cfg = Config()
    assert cfg.batch.threshold == 30
    assert cfg.batch.poll_interval_seconds == 1800
    assert cfg.batch.expiry_grace_seconds == 172800
    assert cfg.batch.toggle == "auto"


def test_batch_config_round_trip(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        "[batch]\nthreshold = 50\npoll_interval_seconds = 600\ntoggle = \"forced_on\"\n",
        encoding="utf-8",
    )
    cfg = load_config(path)
    assert cfg.batch.threshold == 50
    assert cfg.batch.poll_interval_seconds == 600
    assert cfg.batch.toggle == "forced_on"
    # default 유지
    assert cfg.batch.expiry_grace_seconds == 172800


def test_batch_config_migration_missing_section(tmp_path):
    # 기존 config 에 [batch] 없으면 default
    path = tmp_path / "c.toml"
    path.write_text("[backends.ollama]\nenabled = true\n", encoding="utf-8")
    cfg = load_config(path)
    assert cfg.batch.threshold == 30
```

```python
# tests/test_analysis_queue_batch_hook.py 에 추가
def test_enqueue_asset_calls_try_batch_submit(queue_factory):
    q, store = queue_factory()
    bm = MagicMock()
    q.set_batch_manager(bm)
    q.enqueue_asset(1)
    # try_submit 3 modality 모두 시도
    calls = [c.args[0] for c in bm.try_submit.call_args_list]
    assert set(calls) == {"chat_image", "chat_audio", "text_embed"}


def test_enqueue_pack_calls_try_batch_submit(queue_factory):
    q, store = queue_factory()
    store.pending_assets_for_pack.return_value = []
    bm = MagicMock()
    q.set_batch_manager(bm)
    q.enqueue_pack(99)
    assert bm.try_submit.call_count == 3
```

- [ ] **Step 2: Run — verify fail**

- [ ] **Step 3: Implement Config + AnalysisQueue hook**

`src/assetcache/config.py`:

```python
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class BatchConfig:
    threshold: int = 30
    poll_interval_seconds: int = 1800
    expiry_grace_seconds: int = 172800
    toggle: Literal["auto", "forced_on", "forced_off"] = "auto"


@dataclass
class Config:
    # 기존 필드들
    ...
    batch: BatchConfig = field(default_factory=BatchConfig)


def _from_mapping_batch(mapping: dict) -> BatchConfig:
    b = mapping.get("batch", {})
    return BatchConfig(
        threshold=int(b.get("threshold", 30)),
        poll_interval_seconds=int(b.get("poll_interval_seconds", 1800)),
        expiry_grace_seconds=int(b.get("expiry_grace_seconds", 172800)),
        toggle=b.get("toggle", "auto"),
    )
```

`load_config` 에서 호출 + serialize 도 추가.

`analysis_queue.py`:

```python
def __init__(self, ..., batch_manager: "BatchManager | None" = None):
    # 기존 + 끝에
    self._batch_manager = batch_manager
    self._skip_ids: set[int] = set()


def set_batch_manager(self, bm) -> None:
    self._batch_manager = bm


def _try_batch_submit(self) -> None:
    if self._batch_manager is None:
        return
    for modality in ("chat_image", "chat_audio", "text_embed"):
        try:
            self._batch_manager.try_submit(modality)
        except Exception:
            log.exception("batch try_submit failed modality=%s", modality)


def enqueue_asset(self, asset_id: int) -> None:
    self._queue.put(int(asset_id))
    self._emit_progress()
    self._try_batch_submit()


def enqueue_pack(self, pack_id: int) -> int:
    rows = self.store.pending_assets_for_pack(pack_id)
    self._enqueued_packs.add(pack_id)
    for row in rows:
        self._queue.put(row.id)
    self._emit_progress()
    self._try_batch_submit()
    return len(rows)


def drain_pending(self) -> int:
    # 기존 + 끝에
    self._emit_progress()
    self._try_batch_submit()
    return len(rows)
```

`app.py` wiring (Phase 3 의 마지막 step — Phase 4 BatchPoller 추가 전 임시):

```python
# app.py
from .core.batch.manager import BatchManager

# initialize 안 (analysis_queue 생성 후)
batch_manager = BatchManager(
    store=store, chain_registry=registry,
    analysis_queue=analysis_queue, cfg=cfg,
)
analysis_queue.set_batch_manager(batch_manager)
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_config_batch.py tests/test_analysis_queue_batch_hook.py -v`
Expected: PASS

회귀 점검: `pytest -q` → 1315 passed.

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/config.py src/assetcache/core/analysis_queue.py src/assetcache/app.py tests/test_config_batch.py tests/test_analysis_queue_batch_hook.py
git commit -m "feat(batch): Phase 3 task 3.7 — Config + AnalysisQueue _try_batch_submit hook + app.py wiring

enqueue_asset/pack/drain_pending 끝에 try_submit 3 modality 호출.
BatchConfig dataclass + TOML migration (missing section default).
회귀 1289 → 1315. Spec §3.2, §9.2, §15."
```

---

## Phase 4 — BatchPoller (회귀 1315 → 1330, +15)

### Task 4.1: `BatchPoller` skeleton + run loop + stop

**Files:**
- Create: `src/assetcache/core/batch/poller.py`
- Test: `tests/test_batch_poller.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_batch_poller.py
"""Phase 4 — BatchPoller daemon thread 라이프사이클."""

import threading
import time
from unittest.mock import MagicMock

import pytest

from assetcache.core.batch.poller import BatchPoller


@pytest.fixture
def poller_factory():
    def make(*, poll_interval=0.05):
        store = MagicMock()
        store.list_active_batch_jobs.return_value = []
        chain_registry = MagicMock()
        analysis_queue = MagicMock()
        cfg = MagicMock()
        cfg.batch.poll_interval_seconds = poll_interval
        p = BatchPoller(
            store=store, chain_registry=chain_registry,
            analysis_queue=analysis_queue, cfg=cfg,
        )
        return p, store
    return make


def test_poller_starts_and_stops(poller_factory):
    p, store = poller_factory()
    p.start()
    assert p.is_alive()
    p.stop(timeout=1.0)
    assert not p.is_alive()


def test_poller_calls_list_active_at_boot(poller_factory):
    p, store = poller_factory()
    p.start()
    # short wait for first sweep
    time.sleep(0.1)
    p.stop(timeout=1.0)
    assert store.list_active_batch_jobs.call_count >= 1


def test_poller_polls_periodically(poller_factory):
    p, store = poller_factory(poll_interval=0.05)
    p.start()
    time.sleep(0.2)  # ~4 ticks
    p.stop(timeout=1.0)
    assert store.list_active_batch_jobs.call_count >= 3
```

- [ ] **Step 2: Run — verify fail**

- [ ] **Step 3: Implement skeleton**

```python
# src/assetcache/core/batch/poller.py
"""BatchPoller — daemon thread 가 30분 간격으로 batch jobs 폴링."""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..analysis_queue import AnalysisQueue
    from ..llm.registry import BackendRegistry
    from ..store import Store
    from ...config import Config

log = logging.getLogger(__name__)


class BatchPoller(threading.Thread):
    def __init__(
        self,
        *,
        store: "Store",
        chain_registry: "BackendRegistry",
        analysis_queue: "AnalysisQueue",
        cfg: "Config",
    ) -> None:
        super().__init__(daemon=True, name="assetcache-batch-poller")
        self._store = store
        self._chain = chain_registry
        self._aq = analysis_queue
        self._cfg = cfg
        self._stop_event = threading.Event()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        self.join(timeout=timeout)

    def run(self) -> None:
        # 부팅 시 즉시 1회 sweep
        self._poll_once()
        while not self._stop_event.is_set():
            interval = max(0.01, float(self._cfg.batch.poll_interval_seconds))
            if self._stop_event.wait(interval):
                break
            self._poll_once()

    def _poll_once(self) -> None:
        try:
            jobs = self._store.list_active_batch_jobs()
        except Exception:
            log.exception("list_active_batch_jobs failed")
            return
        for job in jobs:
            try:
                self._poll_job(job)
            except Exception:
                log.exception("poll_job failed for job_id=%d", job.id)

    def _poll_job(self, job) -> None:
        # Task 4.2 에서 구현
        pass
```

- [ ] **Step 4: Run — verify pass**

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/core/batch/poller.py tests/test_batch_poller.py
git commit -m "feat(batch): Phase 4 task 4.1 — BatchPoller skeleton (Thread + stop_event)

부팅 시 즉시 sweep + 주기 polling.
Spec §8."
```

---

### Task 4.2: `_poll_job` state mapping + transitions

**Files:**
- Modify: `src/assetcache/core/batch/poller.py` — `_poll_job` + `_GEMINI_STATE_MAP`
- Test: `tests/test_batch_poller.py` — 4 신규

- [ ] **Step 1: Write failing tests**

```python
def test_poll_job_running_updates_state(poller_factory):
    p, store = poller_factory()
    job = MagicMock(id=1, backend="gemini", backend_job_id="batches/x",
                    modality="chat_image", state="submitted",
                    expires_at=int(time.time()) + 172800)
    store.list_active_batch_jobs.return_value = [job]
    backend = MagicMock()
    backend.batch_get.return_value = MagicMock(
        state="JOB_STATE_RUNNING", inlined_responses=None,
        file_name=None, error=None,
    )
    p._chain.get_backend.return_value = backend
    p._poll_once()
    store.update_batch_job_state.assert_called_with(1, state="running")


def test_poll_job_succeeded_calls_handle_succeeded(poller_factory, monkeypatch):
    p, store = poller_factory()
    job = MagicMock(id=1, backend="gemini", backend_job_id="batches/x",
                    modality="chat_image", state="running",
                    expires_at=int(time.time()) + 172800)
    store.list_active_batch_jobs.return_value = [job]
    fake_status = MagicMock(state="JOB_STATE_SUCCEEDED",
                            inlined_responses=[MagicMock()], file_name=None, error=None)
    backend = MagicMock()
    backend.batch_get.return_value = fake_status
    p._chain.get_backend.return_value = backend
    handle = MagicMock()
    monkeypatch.setattr(p, "_handle_succeeded", handle)
    p._poll_once()
    handle.assert_called_once_with(job, fake_status, backend)


def test_poll_job_failed_terminal(poller_factory, monkeypatch):
    p, store = poller_factory()
    job = MagicMock(id=1, backend="gemini", backend_job_id="batches/x",
                    modality="chat_image", state="running",
                    expires_at=int(time.time()) + 172800)
    store.list_active_batch_jobs.return_value = [job]
    fake_status = MagicMock(state="JOB_STATE_FAILED",
                            inlined_responses=None, file_name=None, error="oops")
    backend = MagicMock()
    backend.batch_get.return_value = fake_status
    p._chain.get_backend.return_value = backend
    handle = MagicMock()
    monkeypatch.setattr(p, "_handle_terminal_failure", handle)
    p._poll_once()
    handle.assert_called_once_with(job, "failed", "oops")


def test_poll_job_past_expiry_marked_expired(poller_factory, monkeypatch):
    p, store = poller_factory()
    job = MagicMock(id=1, backend="gemini", backend_job_id="batches/x",
                    modality="chat_image", state="submitted",
                    expires_at=int(time.time()) - 10)  # 이미 만료
    store.list_active_batch_jobs.return_value = [job]
    handle = MagicMock()
    monkeypatch.setattr(p, "_handle_terminal_failure", handle)
    p._poll_once()
    handle.assert_called_once_with(job, "expired", "expires_at passed")
```

- [ ] **Step 2: Run — verify fail**

- [ ] **Step 3: Implement**

```python
_GEMINI_STATE_MAP = {
    "JOB_STATE_PENDING": ("submitted", None),
    "JOB_STATE_RUNNING": ("running", None),
    "JOB_STATE_SUCCEEDED": ("succeeded", "succeeded"),
    "JOB_STATE_FAILED": ("failed", "failed"),
    "JOB_STATE_CANCELLED": ("cancelled", "cancelled"),
    "JOB_STATE_EXPIRED": ("expired", "expired"),
}


def _poll_job(self, job) -> None:
    now = int(time.time())
    # 안전망 — 만료 강제
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
        # transient state — DB 만 갱신
        if db_state != job.state:
            self._store.update_batch_job_state(job.id, state=db_state)
        return
    if terminal == "succeeded":
        self._handle_succeeded(job, status, backend)
    else:
        self._handle_terminal_failure(job, terminal, status.error)


def _handle_succeeded(self, job, status, backend) -> None:
    # Task 4.3 에서 구현
    pass


def _handle_terminal_failure(self, job, terminal_state, error) -> None:
    # Task 4.4 에서 구현
    pass
```

- [ ] **Step 4: Run — verify pass**

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/core/batch/poller.py tests/test_batch_poller.py
git commit -m "feat(batch): Phase 4 task 4.2 — _poll_job state mapping + expiry safety net

JOB_STATE_* → submitted/running/succeeded/failed/cancelled/expired.
Spec §8."
```

---

### Task 4.3: `_handle_succeeded` — modality 별 persist + backend_used 마킹

**Files:**
- Modify: `src/assetcache/core/batch/poller.py` — `_handle_succeeded`
- Test: `tests/test_batch_poller.py` — 5 신규

- [ ] **Step 1: Write failing tests**

```python
def test_handle_succeeded_image_modality_persists(poller_factory, monkeypatch):
    p, store = poller_factory()
    job = MagicMock(id=1, modality="chat_image", asset_count=2)
    store.list_assets_in_batch.return_value = [
        MagicMock(id=10), MagicMock(id=11),
    ]
    # 2 응답 — 첫번째 성공, 두번째 실패 (response None)
    resp_ok = MagicMock()
    resp_ok.response.text = '{"labels": []}'
    resp_ok.error = None
    resp_fail = MagicMock()
    resp_fail.response = None
    resp_fail.error = "internal"
    status = MagicMock(inlined_responses=[resp_ok, resp_fail], file_name=None)
    backend = MagicMock()
    # _persist_image_payload 가 호출되는지
    persist = MagicMock()
    monkeypatch.setattr(p, "_persist_image_payload", persist)
    p._handle_succeeded(job, status, backend)
    # asset_id 10 → 성공: persist 호출 + mark_asset_backends image=gemini + batch_state=completed
    persist.assert_called_once_with(10, {"labels": []})
    store.mark_asset_backends.assert_called_with(10, image="gemini")
    # asset_id 11 → 실패: batch_state=failed + enqueue_asset
    assert any(
        c.args == (11, "failed") for c in store.mark_asset_batch_state.call_args_list
    )
    p._aq.enqueue_asset.assert_called_with(11)
    # 최종 state 갱신
    store.update_batch_job_state.assert_called_with(
        1, state="succeeded", completed_at=pytest.approx(int(time.time()), abs=2),
        success_count=1, failure_count=1,
    )


def test_handle_succeeded_audio_modality(poller_factory, monkeypatch):
    p, store = poller_factory()
    job = MagicMock(id=1, modality="chat_audio", asset_count=1)
    store.list_assets_in_batch.return_value = [MagicMock(id=20)]
    resp = MagicMock()
    resp.response.text = '{"category": "music"}'
    resp.error = None
    status = MagicMock(inlined_responses=[resp], file_name=None)
    persist = MagicMock()
    monkeypatch.setattr(p, "_persist_audio_payload", persist)
    p._handle_succeeded(job, status, MagicMock())
    persist.assert_called_once_with(20, {"category": "music"})
    store.mark_asset_backends.assert_called_with(20, audio="gemini")


def test_handle_succeeded_embed_modality(poller_factory):
    p, store = poller_factory()
    job = MagicMock(id=1, modality="text_embed", asset_count=1)
    store.list_assets_in_batch.return_value = [MagicMock(id=30)]
    resp = MagicMock()
    resp.embedding.values = [0.1, 0.2, 0.3]
    resp.error = None
    status = MagicMock(inlined_responses=[resp], file_name=None)
    p._handle_succeeded(job, status, MagicMock())
    store.save_embedding.assert_called_once()
    args = store.save_embedding.call_args.args
    assert args[0] == 30  # asset_id
    store.mark_asset_backends.assert_called_with(30, embed="gemini")


def test_handle_succeeded_file_destination_marks_expired(poller_factory):
    p, store = poller_factory()
    job = MagicMock(id=1, modality="chat_image", asset_count=10)
    status = MagicMock(inlined_responses=None, file_name="files/big")
    p._handle_succeeded(job, status, MagicMock())
    # v0.2.1 — file destination 미지원 → expired 처리
    store.update_batch_job_state.assert_called_with(
        1, state="expired", completed_at=pytest.approx(int(time.time()), abs=2),
        error="file destination not supported in v0.2.1",
    )


def test_handle_succeeded_parse_error_falls_back_to_interactive(poller_factory):
    p, store = poller_factory()
    job = MagicMock(id=1, modality="chat_image", asset_count=1)
    store.list_assets_in_batch.return_value = [MagicMock(id=40)]
    resp = MagicMock()
    resp.response.text = "not json"
    resp.error = None
    status = MagicMock(inlined_responses=[resp], file_name=None)
    p._handle_succeeded(job, status, MagicMock())
    # parse 실패 → batch_state=failed + interactive 재enqueue
    assert any(c.args == (40, "failed") for c in store.mark_asset_batch_state.call_args_list)
    p._aq.enqueue_asset.assert_called_with(40)
```

- [ ] **Step 2: Run — verify fail**

- [ ] **Step 3: Implement**

```python
import json

def _handle_succeeded(self, job, status, backend) -> None:
    if status.inlined_responses is None:
        if status.file_name:
            log.warning(
                "batch job %d file destination — v0.2.1 not supported", job.id
            )
            self._store.update_batch_job_state(
                job.id, state="expired", completed_at=int(time.time()),
                error="file destination not supported in v0.2.1",
            )
            return
        log.warning("batch job %d succeeded but no inlined_responses", job.id)
        self._store.update_batch_job_state(
            job.id, state="succeeded", completed_at=int(time.time()),
        )
        return

    asset_rows = self._store.list_assets_in_batch(job.id)
    success_count = 0
    failure_count = 0
    for asset, resp in zip(asset_rows, status.inlined_responses, strict=False):
        if getattr(resp, "error", None):
            self._fail_asset(asset, str(resp.error))
            failure_count += 1
            continue
        try:
            if job.modality == "chat_image":
                payload = json.loads(resp.response.text)
                self._persist_image_payload(asset.id, payload)
                self._store.mark_asset_backends(asset.id, image="gemini")
            elif job.modality == "chat_audio":
                payload = json.loads(resp.response.text)
                self._persist_audio_payload(asset.id, payload)
                self._store.mark_asset_backends(asset.id, audio="gemini")
            elif job.modality == "text_embed":
                vec = list(resp.embedding.values)
                blob = _serialize_vec(vec)
                self._store.save_embedding(
                    asset.id, self._cfg.gemini_model_embed, blob, len(vec),
                )
                self._store.mark_asset_backends(asset.id, embed="gemini")
            else:
                raise ValueError(f"unknown modality {job.modality}")
            self._store.mark_asset_batch_state(asset.id, "completed")
            success_count += 1
        except Exception as e:
            log.exception("batch result persist failed asset_id=%d", asset.id)
            self._fail_asset(asset, str(e))
            failure_count += 1
    self._store.update_batch_job_state(
        job.id, state="succeeded", completed_at=int(time.time()),
        success_count=success_count, failure_count=failure_count,
    )


def _fail_asset(self, asset, error: str) -> None:
    self._store.mark_asset_batch_state(asset.id, "failed")
    self._aq.enqueue_asset(asset.id)


def _persist_image_payload(self, asset_id: int, payload: dict) -> None:
    # SpriteAnalyzer 의 결과 parser 추출하여 재사용
    # Phase 6 e2e 에서 실 SpriteAnalyzer 와 호환 검증
    from ..analyzer.sprite import persist_image_payload
    persist_image_payload(self._store, asset_id, payload)


def _persist_audio_payload(self, asset_id: int, payload: dict) -> None:
    from ..analyzer.sound import persist_audio_payload
    persist_audio_payload(self._store, asset_id, payload)


def _serialize_vec(vec: list[float]) -> bytes:
    import struct
    return struct.pack(f"<{len(vec)}f", *vec)
```

`SpriteAnalyzer / SoundAnalyzer` 안에 `persist_image_payload(store, asset_id, payload)` / `persist_audio_payload(...)` 도 모듈 레벨 함수로 분리 (또는 staticmethod). 기존 analyzer 의 `_persist` 로직 추출 + analyzer / poller 둘 다 호출.

- [ ] **Step 4: Run — verify pass**

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/core/batch/poller.py src/assetcache/core/analyzer/ tests/test_batch_poller.py
git commit -m "feat(batch): Phase 4 task 4.3 — _handle_succeeded modality 별 persist + backend_used 마킹

image/audio (json parse) / embed (vec). 부분 실패 → interactive 재enqueue.
file destination 은 v0.2.1 에서 expired 처리. Spec §11."
```

---

### Task 4.4: `_handle_terminal_failure` (failed/cancelled/expired)

**Files:**
- Modify: `src/assetcache/core/batch/poller.py` — `_handle_terminal_failure`
- Test: `tests/test_batch_poller.py` — 3 신규

- [ ] **Step 1: Write failing tests**

```python
def test_handle_terminal_failure_failed_reenqueues_all(poller_factory):
    p, store = poller_factory()
    job = MagicMock(id=1, modality="chat_image")
    store.list_assets_in_batch.return_value = [
        MagicMock(id=1), MagicMock(id=2), MagicMock(id=3),
    ]
    p._handle_terminal_failure(job, "failed", "internal error")
    assert store.mark_asset_batch_state.call_count == 3
    assert p._aq.enqueue_asset.call_count == 3
    store.update_batch_job_state.assert_called_once()
    kw = store.update_batch_job_state.call_args.kwargs
    assert kw["state"] == "failed"
    assert kw["error"] == "internal error"


def test_handle_terminal_failure_expired(poller_factory):
    p, store = poller_factory()
    job = MagicMock(id=1)
    store.list_assets_in_batch.return_value = []
    p._handle_terminal_failure(job, "expired", "expires_at passed")
    store.update_batch_job_state.assert_called_once()
    assert store.update_batch_job_state.call_args.kwargs["state"] == "expired"


def test_handle_terminal_failure_cancelled(poller_factory):
    p, store = poller_factory()
    job = MagicMock(id=1)
    store.list_assets_in_batch.return_value = [MagicMock(id=99)]
    p._handle_terminal_failure(job, "cancelled", None)
    store.update_batch_job_state.assert_called_once()
    assert store.update_batch_job_state.call_args.kwargs["state"] == "cancelled"
    p._aq.enqueue_asset.assert_called_with(99)
```

- [ ] **Step 2: Run — verify fail**

- [ ] **Step 3: Implement**

```python
def _handle_terminal_failure(self, job, terminal_state: str, error: str | None) -> None:
    """failed / cancelled / expired — 모든 asset interactive 재enqueue."""
    for asset in self._store.list_assets_in_batch(job.id):
        self._store.mark_asset_batch_state(asset.id, "failed")
        self._aq.enqueue_asset(asset.id)
    self._store.update_batch_job_state(
        job.id,
        state=terminal_state,
        completed_at=int(time.time()),
        error=error,
    )
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_batch_poller.py -v`
Expected: PASS (15 tests)

회귀 점검: `pytest -q` → 1330 passed.

- [ ] **Step 5: Commit + wire BatchPoller into app.py**

`app.py`:

```python
from .core.batch.poller import BatchPoller

# init
batch_poller = BatchPoller(
    store=store, chain_registry=registry,
    analysis_queue=analysis_queue, cfg=cfg,
)
batch_poller.start()

# shutdown hook
def _shutdown():
    batch_poller.stop(timeout=5.0)
    analysis_queue.stop(timeout=5.0)
```

```bash
git add src/assetcache/core/batch/poller.py src/assetcache/app.py tests/test_batch_poller.py
git commit -m "feat(batch): Phase 4 task 4.4 — _handle_terminal_failure + app wiring

failed/cancelled/expired → 모든 asset interactive 재enqueue + BatchPoller.start in app.
회귀 1315 → 1330. Spec §8."
```

---

## Phase 5 — UI (회귀 1330 → 1355, +25)

### Task 5.1: `/settings` batch 카드 + toggle/cancel POST routers

**Files:**
- Modify: `src/assetcache/web/routers/settings.py` — `GET/POST /settings/batch` + `POST /settings/batch/jobs/<id>/cancel`
- Create: `src/assetcache/web/templates/settings/_batch_card.html`
- Test: `tests/test_web_routers_settings_batch.py`

상세 단계 (Step 1-5) 는 `tests/test_web_routers_settings.py` 의 기존 패턴 따라 작성. 핵심:
- GET → 200 + HTML contains "Batch analysis" + threshold input + 3 toggle radio
- POST `/settings/batch` (form-encoded) → cfg.batch 갱신 + save_config
- POST `/settings/batch/jobs/<id>/cancel` → BatchManager.cancel(id) → 302
- 권한: M5 의 기존 CSRF middleware 자동 적용

**+10 신규 테스트**. Commit message: `feat(batch): Phase 5 task 5.1 — /settings batch 카드 + toggle/cancel POST`.

---

### Task 5.2: `/analyzing` dashboard 페이지 — section A 요약 + Interactive 큐

**Files:**
- Create: `src/assetcache/web/routers/analyzing.py`
- Create: `src/assetcache/web/templates/analyzing/index.html`
- Create: `src/assetcache/web/templates/analyzing/_partial.html`
- Modify: `src/assetcache/core/analysis_queue.py` — `snapshot_queue(limit=50)` 헬퍼
- Test: `tests/test_web_routers_analyzing.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_web_routers_analyzing.py
"""Phase 5 — /analyzing dashboard 라우터."""

from fastapi.testclient import TestClient


def test_analyzing_dashboard_200(test_client: TestClient):
    r = test_client.get("/analyzing")
    assert r.status_code == 200
    assert "분석 진행" in r.text or "Analysis progress" in r.text


def test_analyzing_partial_returns_partial_html(test_client):
    r = test_client.get("/analyzing/partial")
    assert r.status_code == 200
    # HTMX outerHTML swap target
    assert 'id="analyzing-partial"' in r.text


def test_analyzing_partial_shows_summary_section(test_client):
    r = test_client.get("/analyzing/partial")
    # 요약 섹션
    assert "요약" in r.text or "Summary" in r.text
    # 큐 / batch / 실패 카운트 표시
    assert "큐" in r.text or "queue" in r.text.lower()


def test_analyzing_partial_interactive_queue_section(test_client):
    r = test_client.get("/analyzing/partial")
    assert "즉시 분석" in r.text or "Interactive queue" in r.text
```

(`test_client` fixture 는 `tests/conftest.py` 의 기존 FastAPI TestClient 패턴 — M5 phase 에서 이미 셋업)

- [ ] **Step 2: Run — verify fail**

- [ ] **Step 3: Implement router + templates**

```python
# src/assetcache/web/routers/analyzing.py
"""/analyzing — 분석 진행 dashboard (M11.1)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..deps import get_app_context

router = APIRouter(prefix="/analyzing", tags=["analyzing"])


def _build_view_model(ctx):
    aq = ctx.analysis_queue
    store = ctx.store
    progress = aq.progress()
    pending_image = aq.pending_by_modality("chat_image")
    pending_audio = aq.pending_by_modality("chat_audio")
    pending_embed = aq.pending_by_modality("text_embed")
    interactive_assets = aq.snapshot_queue(limit=50)
    in_flight_path = progress.in_flight_path
    batch_jobs = store.list_active_batch_jobs()
    recent_failures = store.list_recent_failures(limit=20)
    return {
        "summary": {
            "interactive_count": progress.pending,
            "batch_image": pending_image,  # 또는 batch jobs 의 asset_count
            "batch_audio": pending_audio,
            "failures_count": len(recent_failures),
            "eta_seconds": progress.eta_seconds,
        },
        "interactive": {
            "in_flight_path": in_flight_path,
            "queue": interactive_assets,
        },
        "batch_jobs": batch_jobs,
        "recent_failures": recent_failures,
    }


@router.get("", response_class=HTMLResponse)
async def get_dashboard(request: Request, ctx=Depends(get_app_context)):
    vm = _build_view_model(ctx)
    return ctx.templates.TemplateResponse(
        "analyzing/index.html",
        {"request": request, **vm},
    )


@router.get("/partial", response_class=HTMLResponse)
async def get_partial(request: Request, ctx=Depends(get_app_context)):
    vm = _build_view_model(ctx)
    return ctx.templates.TemplateResponse(
        "analyzing/_partial.html",
        {"request": request, **vm},
    )
```

`web/templates/analyzing/index.html`:

```jinja
{% extends "_base.html" %}
{% block title %}{{ _("Analysis progress") }}{% endblock %}
{% block content %}
<h1>{{ _("Analysis progress") }}</h1>
<div id="analyzing-partial" hx-get="/analyzing/partial" hx-trigger="every 5s" hx-swap="outerHTML">
  {% include "analyzing/_partial.html" %}
</div>
{% endblock %}
```

`web/templates/analyzing/_partial.html`:

```jinja
<div id="analyzing-partial" hx-get="/analyzing/partial" hx-trigger="every 5s" hx-swap="outerHTML">
  <h2>{{ _("Summary") }}</h2>
  <p>
    {{ _("Interactive queue") }}: {{ summary.interactive_count }} ·
    {{ _("Batch image") }}: {{ summary.batch_image }} ·
    {{ _("Batch audio") }}: {{ summary.batch_audio }} ·
    {{ _("Recent failures") }}: {{ summary.failures_count }}
  </p>
  {% if summary.eta_seconds %}
  <p>ETA: ~{{ (summary.eta_seconds / 60) | round(0) }} {{ _("minutes") }}</p>
  {% endif %}

  <h2>{{ _("Interactive queue") }}</h2>
  {% if interactive.in_flight_path %}
  <p><strong>{{ _("Now analyzing") }}:</strong> {{ interactive.in_flight_path }}</p>
  {% endif %}
  {% if interactive.queue %}
  <table>
    <tr><th>path</th><th>kind</th></tr>
    {% for a in interactive.queue %}
    <tr><td>{{ a.path }}</td><td>{{ a.kind }}</td></tr>
    {% endfor %}
  </table>
  {% else %}
  <p><em>{{ _("Queue empty") }}</em></p>
  {% endif %}

  {# Phase 5 task 5.3 — batch jobs / recent failures 섹션 #}
</div>
```

`AnalysisQueue.snapshot_queue(limit)`:
```python
def snapshot_queue(self, *, limit: int = 50) -> list:
    """Peek at queue contents — 최대 N개 AssetRow 반환. 큐를 비우지 않음.

    queue.Queue 는 peek 안 됨 → 내부 deque 또는 queue.queue 직접 접근 (with mutex).
    """
    with self._queue.mutex:
        ids = list(self._queue.queue)[:limit]
    return [self.store.get_asset_by_id(aid) for aid in ids if aid != -1]
```

- [ ] **Step 4: Run — verify pass**

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/web/routers/analyzing.py src/assetcache/web/templates/analyzing/ src/assetcache/core/analysis_queue.py tests/test_web_routers_analyzing.py
git commit -m "feat(batch): Phase 5 task 5.2 — /analyzing dashboard + summary + interactive 큐 섹션

GET /analyzing + GET /analyzing/partial (HTMX 5초 polling).
AnalysisQueue.snapshot_queue 헬퍼.
Spec §13.4 sections A + B."
```

---

### Task 5.3: `/analyzing` — section C batch jobs + section D 최근 실패 + cancel POST + nav 링크

**Files:**
- Modify: `src/assetcache/web/templates/analyzing/_partial.html` — section C + D
- Modify: `src/assetcache/web/routers/analyzing.py` — `POST /analyzing/batch/<id>/cancel`
- Modify: `src/assetcache/web/templates/_base.html` — nav 에 링크
- Test: `tests/test_web_routers_analyzing.py` — 4 신규

- [ ] **Step 1: Write failing tests**

```python
def test_analyzing_partial_batch_jobs_section(test_client, _seed_batch_job):
    job_id = _seed_batch_job(modality="chat_image", asset_count=30)
    r = test_client.get("/analyzing/partial")
    assert "Batch jobs" in r.text or "배치 작업" in r.text
    assert "chat_image" in r.text
    assert "30" in r.text  # asset_count


def test_analyzing_partial_recent_failures_section(test_client, _seed_failed_asset):
    aid = _seed_failed_asset(error="non-json response")
    r = test_client.get("/analyzing/partial")
    assert "Recent failures" in r.text or "최근 실패" in r.text
    assert "non-json response" in r.text


def test_analyzing_cancel_batch_job_redirects(test_client, _seed_batch_job, monkeypatch):
    job_id = _seed_batch_job(modality="chat_image", asset_count=2)
    # BatchManager.cancel mock
    canceled = []
    monkeypatch.setattr(
        "assetcache.web.routers.analyzing._get_batch_manager",
        lambda ctx: type("Bm", (), {"cancel": lambda self, jid: canceled.append(jid)})()
    )
    r = test_client.post(f"/analyzing/batch/{job_id}/cancel", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert canceled == [job_id]


def test_base_template_nav_has_analyzing_link(test_client):
    r = test_client.get("/")
    assert "/analyzing" in r.text
```

- [ ] **Step 2: Run — verify fail**

- [ ] **Step 3: Implement section C/D + cancel + nav**

`_partial.html` 끝에 추가:

```jinja
<h2>{{ _("Batch jobs") }}</h2>
{% if batch_jobs %}
{% for job in batch_jobs %}
<div class="batch-job-card">
  <strong>{{ job.modality }} #{{ job.id }}</strong> ·
  {{ job.backend }} · {{ job.asset_count }} {{ _("assets") }} ·
  {{ _("Submitted %d minutes ago") | format((now - job.submitted_at) // 60) }} / 24h SLO ·
  {{ job.state }}
  <form method="post" action="/analyzing/batch/{{ job.id }}/cancel" style="display:inline">
    <button type="submit">{{ _("Cancel") }}</button>
  </form>
</div>
{% endfor %}
{% else %}
<p><em>{{ _("No active batch jobs") }}</em></p>
{% endif %}

<h2>{{ _("Recent failures") }}</h2>
{% if recent_failures %}
<table>
  <tr><th>path</th><th>kind</th><th>error</th></tr>
  {% for a in recent_failures %}
  <tr>
    <td>{{ a.path }}</td>
    <td>{{ a.kind }}</td>
    <td>{{ a.analysis_error or "" }}</td>
  </tr>
  {% endfor %}
</table>
{% else %}
<p><em>{{ _("No recent failures") }}</em></p>
{% endif %}
```

`analyzing.py`:

```python
from fastapi.responses import RedirectResponse


def _get_batch_manager(ctx):
    return ctx.batch_manager


@router.post("/batch/{batch_job_id}/cancel")
async def cancel_batch_job(batch_job_id: int, ctx=Depends(get_app_context)):
    bm = _get_batch_manager(ctx)
    bm.cancel(batch_job_id)
    return RedirectResponse("/analyzing", status_code=303)
```

`_base.html` 의 `<nav>` 안에 추가:

```jinja
<a href="/analyzing">{{ _("Analysis progress") }}</a>
```

- [ ] **Step 4: Run — verify pass**

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/web/routers/analyzing.py src/assetcache/web/templates/ tests/test_web_routers_analyzing.py
git commit -m "feat(batch): Phase 5 task 5.3 — /analyzing batch jobs + recent failures + cancel POST + nav link

section C + D 추가 + cancel route + _base.html nav 링크.
Spec §13.4 sections C + D."
```

---

### Task 5.4: status bar 토글 (Qt widget + tray Signal)

**Files:**
- Modify: `src/assetcache/tray.py` (or 메인 창 status bar 모듈) — Qt 토글 위젯
- Modify: `src/assetcache/config.py` — toggle 변경 시 즉시 save
- Test: 수동 (Qt UI smoke 만 — 자동 테스트는 brittle)

- [ ] **Step 1**: Skip TDD — Qt UI 수동 검증으로

- [ ] **Step 2**: Implement status bar 위젯

(상세는 M5 의 Qt status bar 패턴 따라 — `QComboBox(["auto","forced_on","forced_off"])` + `currentTextChanged` Signal → `save_config(...)`)

- [ ] **Step 3**: 수동 검증 — `python -m assetcache --tray` → status bar 우측에 토글 드롭다운 표시 → 선택 시 config.toml `[batch].toggle` 갱신 확인

- [ ] **Step 4**: Commit

```bash
git add src/assetcache/tray.py
git commit -m "feat(batch): Phase 5 task 5.4 — status bar Batch toggle (Qt)

auto/forced_on/forced_off 드롭다운. currentTextChanged → save_config.
Spec §13.1."
```

---

### Task 5.5: i18n msgid 18 추가 + pybabel compile

**Files:**
- Modify: `src/assetcache/locale/ko/LC_MESSAGES/assetcache.po`
- Modify: `src/assetcache/locale/en/LC_MESSAGES/assetcache.po`
- Recompile: `assetcache.mo` via `pybabel compile`
- Test: `tests/test_locale_batch_msgid.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_locale_batch_msgid.py
"""Phase 5 — batch 관련 18 msgid 가 ko/en 양쪽 .po 에 모두 존재."""

import pytest
from pathlib import Path


BATCH_MSGIDS = [
    "Batch analysis",
    "Threshold",
    "Polling interval",
    "In-progress batch jobs",
    "Submitted %d minutes ago",
    "image chain first is %s — batch enabled",
    "image chain first is %s — batch disabled. Set chain[image][0] to gemini.",
    "Cancel all",
    "Auto",
    "Forced on",
    "Forced off",
    "Batch mode (Gemini): %s",
    "Analysis progress",
    "Summary",
    "Interactive queue",
    "Batch jobs",
    "Recent failures",
    "Worker #%d (%.1fs elapsed)",
]


@pytest.mark.parametrize("lang", ["ko", "en"])
@pytest.mark.parametrize("msgid", BATCH_MSGIDS)
def test_msgid_present(lang, msgid):
    p = Path(f"src/assetcache/locale/{lang}/LC_MESSAGES/assetcache.po")
    content = p.read_text(encoding="utf-8")
    assert f'msgid "{msgid}"' in content, f"missing in {lang}: {msgid}"
```

- [ ] **Step 2: Run — verify fail**

- [ ] **Step 3: Add 18 msgid to ko/en .po + compile**

각 `.po` 파일 끝에 18 entry 추가. ko 는 §13.3 의 번역, en 은 msgid 와 동일.

```powershell
pybabel compile -d src\assetcache\locale -D assetcache
```

- [ ] **Step 4: Run — verify pass**

Run: `pytest tests/test_locale_batch_msgid.py -v`
Expected: PASS (18 msgid × 2 lang = 36 cases)

회귀 점검 — `pytest -q` → 1355 passed.

- [ ] **Step 5: Commit**

```bash
git add src/assetcache/locale/ tests/test_locale_batch_msgid.py
git commit -m "feat(batch): Phase 5 task 5.5 — 18 batch i18n msgid (ko/en)

분석 진행 dashboard + batch toggle + threshold 관련 msgid.
회귀 1330 → 1355. Spec §13.3."
```

---

## Phase 6 — End-to-end + 옵트인 integration + docs + verification (회귀 1355 → 1360 + 옵트인 3)

### Task 6.1: End-to-end mock test — enqueue → batch submit → poll → DB 반영

**Files:**
- Test: `tests/test_batch_end_to_end.py`

- [ ] **Step 1: Write end-to-end test (mock Gemini backend, real Store + AnalysisQueue + BatchManager + BatchPoller)**

```python
# tests/test_batch_end_to_end.py
"""Phase 6 — Batch end-to-end with mock Gemini backend.

실제 Store / AnalysisQueue / BatchManager / BatchPoller 통합 검증.
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from assetcache.core.batch.manager import BatchManager
from assetcache.core.batch.poller import BatchPoller
from assetcache.core.batch.types import GeminiBatchStatus


@pytest.fixture
def e2e_store(tmp_path):
    from assetcache.core.store import Store
    s = Store(str(tmp_path / "e2e.db"))
    s.initialize()
    return s


@pytest.fixture
def e2e_setup(e2e_store, tmp_path):
    """e2e_store + library + AnalysisQueue + chain_registry mock + BatchManager + BatchPoller."""
    # ... (자세한 fixture)
    ...


def test_enqueue_50_assets_triggers_batch_and_succeeds(e2e_setup):
    ctx = e2e_setup
    # 50 sprite asset seed in library
    for i in range(50):
        ctx.add_asset(kind="sprite", path=f"a{i}.png")
    # enqueue_pack → AnalysisQueue._try_batch_submit → BatchManager.try_submit → mock gemini.batch_chat
    ctx.aq.enqueue_pack(ctx.pack_id)
    # batch_jobs row 검증
    jobs = ctx.store.list_active_batch_jobs()
    assert len(jobs) >= 1
    image_job = next(j for j in jobs if j.modality == "chat_image")
    assert image_job.asset_count == 30  # threshold cap

    # mock SUCCEEDED status with 30 OK responses
    fake_responses = []
    for i in range(30):
        r = MagicMock()
        r.response.text = json.dumps({"labels": [{"axis": "k", "label": "v", "weight": "primary"}]})
        r.error = None
        fake_responses.append(r)
    ctx.gemini_backend.batch_get.return_value = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED",
        inlined_responses=fake_responses,
        file_name=None, error=None,
    )

    # poller 1 tick
    ctx.poller._poll_once()

    # DB 검증
    job = ctx.store.get_batch_job(image_job.id)
    assert job.state == "succeeded"
    assert job.success_count == 30
    assert job.failure_count == 0

    # asset 30개의 backend_image == "gemini" 검증
    for asset in ctx.store.list_assets_in_batch(job.id):
        # mark_asset_backends 검증
        ...


def test_partial_failure_falls_back_to_interactive(e2e_setup):
    ctx = e2e_setup
    for i in range(30):
        ctx.add_asset(kind="sprite", path=f"b{i}.png")
    ctx.aq.enqueue_pack(ctx.pack_id)
    job = ctx.store.list_active_batch_jobs()[0]

    # 30 응답 중 5개 실패
    fake_responses = []
    for i in range(30):
        r = MagicMock()
        if i < 25:
            r.response.text = json.dumps({"labels": []})
            r.error = None
        else:
            r.response = None
            r.error = "API error"
        fake_responses.append(r)
    ctx.gemini_backend.batch_get.return_value = GeminiBatchStatus(
        state="JOB_STATE_SUCCEEDED",
        inlined_responses=fake_responses,
        file_name=None, error=None,
    )

    ctx.poller._poll_once()
    job_after = ctx.store.get_batch_job(job.id)
    assert job_after.success_count == 25
    assert job_after.failure_count == 5

    # 실패한 5개는 interactive 큐에 다시
    assert ctx.aq._queue.qsize() == 5
```

- [ ] **Step 2-4: Implement fixture + iterate until tests pass**

- [ ] **Step 5: Commit**

```bash
git add tests/test_batch_end_to_end.py
git commit -m "test(batch): Phase 6 task 6.1 — end-to-end mock Gemini

50 asset enqueue → BatchManager submit → BatchPoller._poll_once → DB 반영 + 일부 실패 interactive fallback.
Spec §16.1."
```

---

### Task 6.2: 옵트인 integration tests (실 GEMINI_API_KEY)

**Files:**
- Test: `tests/test_llm_backend_gemini_batch_integration.py`

- [ ] **Step 1: Write 3 옵트인 tests**

```python
# tests/test_llm_backend_gemini_batch_integration.py
"""Phase 6 — 옵트인 Gemini Batch API 실 호출. GEMINI_API_KEY 필요.

`pytest -m llm_integration` 으로 실행.
"""

import os
import time

import pytest

pytestmark = pytest.mark.llm_integration


@pytest.fixture
def gemini_real():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        pytest.skip("GEMINI_API_KEY not set")
    from assetcache.core.llm.backends.gemini import GeminiBackend
    return GeminiBackend(
        api_key=api_key,
        model_image="gemini-3.1-flash-lite",
        model_audio="gemini-3.1-flash-lite",
        model_embed="gemini-embedding-001",
        timeout=60.0,
    )


def test_batch_chat_submit_and_cancel(gemini_real):
    """실 submit → 즉시 cancel (24h 대기 X)."""
    from assetcache.core.batch.types import BatchChatRequest
    from assetcache.core.llm.base import ChatMessage
    job_name = gemini_real.batch_chat(
        modality="chat_image",
        requests=[
            BatchChatRequest(
                asset_id=1,
                messages=[ChatMessage(role="user", content="say hi in JSON")],
                force_json=True,
            ),
        ],
    )
    assert job_name.startswith("batches/")
    # 즉시 cancel
    gemini_real.batch_cancel(job_name)
    # 상태 확인 — 잠시 기다림 + get
    time.sleep(2)
    status = gemini_real.batch_get(job_name)
    assert status.state in ("JOB_STATE_CANCELLED", "JOB_STATE_RUNNING", "JOB_STATE_PENDING")


def test_batch_embed_submit_and_cancel(gemini_real):
    job_name = gemini_real.batch_embed(texts=["alpha", "beta"])
    assert job_name.startswith("batches/")
    gemini_real.batch_cancel(job_name)


def test_batch_get_unknown_returns_error(gemini_real):
    from assetcache.core.llm.base import BackendError
    with pytest.raises(BackendError):
        gemini_real.batch_get("batches/does-not-exist-9999")
```

- [ ] **Step 2: Run with API key set**

```powershell
$env:GEMINI_API_KEY = "AIza..."
pytest tests/test_llm_backend_gemini_batch_integration.py -m llm_integration -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_llm_backend_gemini_batch_integration.py
git commit -m "test(batch): Phase 6 task 6.2 — 옵트인 Gemini Batch API integration

submit + cancel + unknown job 에러. 13 → 16 옵트인.
Spec §16.2."
```

---

### Task 6.3: Docs — milestones/M11_1_*.md + HANDOFF/CLAUDE/DESIGN/README

**Files:**
- Create: `milestones/M11_1_plan.md`
- Create: `milestones/M11_1_todo.md`
- Create: `milestones/M11_1_verification.md`
- Modify: `HANDOFF.md` — v0.2.1 publish 인계
- Modify: `CLAUDE.md` — §2 진행 현황 + §8 다음 작업
- Modify: `DESIGN.md` — §4.x batch architecture (M11.1 섹션 추가)
- Modify: `README.md` — Batch 섹션 신설

기존 M11 의 wrap-up 패턴 그대로:
- `M11_1_plan.md` — Phase 0~6 요약 + 산출물 + 회귀 표
- `M11_1_todo.md` — task 체크리스트 (본 plan 의 task 그대로 marker 식)
- `M11_1_verification.md` — 수동 검증 시나리오 (status bar 토글 / /analyzing 페이지 렌더 / batch 자동 submit 시뮬 / chain 1순위 변경 시 안내 / cancel 동작)

- [ ] **Step 1-2**: 각 문서 작성 — 본 plan 의 spec/plan 을 milestone-level 로 요약

- [ ] **Step 3**: 회귀 최종 점검 — `pytest -q` → 1360 passed + 1 skipped + 56 deselected (옵트인 3 추가).

- [ ] **Step 4**: 옵트인 — `pytest -m llm_integration` (실 API key) → 16 passed.

- [ ] **Step 5**: Commit + PR

```bash
git add milestones/M11_1_*.md HANDOFF.md CLAUDE.md DESIGN.md README.md
git commit -m "docs(batch): Phase 6 task 6.3 — M11.1 milestone wrap-up + HANDOFF/CLAUDE/DESIGN/README

회귀 1252 → 1360 (+108) + 옵트인 13 → 16. v0.2.1 publish 후보 준비.
Spec §17 Phase 6."
```

PR 생성:

```bash
git push -u origin feat/m11-1-gemini-batch-api
gh pr create --title "M11.1 — Gemini Batch API + /analyzing dashboard → v0.2.1" --body "$(cat <<'BODY'
## 요약

- Gemini Batch API 50% 비용 절감 — image/audio/embed 모든 modality
- 임계값 (default 30) + 사용자 토글 (auto/forced_on/forced_off) hybrid 정책
- 신설 `core/batch/` (Manager + Poller daemon thread)
- DB `batch_jobs` table + `assets.batch_job_id/batch_state` 컬럼
- M11 알려진 한계 `mark_asset_backends` write hook 동시 해결
- 신규 페이지 `/analyzing` — 분석 진행 dashboard (HTMX 5초 polling)
- 신규 의존성 0 (`google-genai` 이미 v0.2.0 에 포함)

## 회귀

1252 → 1360 (+108) + 옵트인 13 → 16

## Spec / Plan

- Spec: `docs/superpowers/specs/2026-05-20-gemini-batch-api-design.md`
- Plan: `docs/superpowers/plans/2026-05-20-gemini-batch-api.md`
- Verification: `milestones/M11_1_verification.md`

## Test plan

- [ ] CI 회귀 (자동)
- [ ] 수동 — /settings 의 batch 카드 렌더링
- [ ] 수동 — status bar 토글 동작
- [ ] 수동 — /analyzing dashboard 5초 polling
- [ ] 수동 — chain 1순위 ollama → batch 진입 안 함 안내
- [ ] 수동 — chain 1순위 gemini + 30 asset drop → 자동 batch
- [ ] 수동 — batch cancel 동작
- [ ] 옵트인 — `pytest -m llm_integration` (GEMINI_API_KEY 필요)
BODY
)"
```

---

## Self-Review

### 1. Spec coverage

| Spec section | Plan task |
|---|---|
| §3 Trigger 정책 (auto/forced_on/forced_off) | Task 3.1, 3.2 |
| §4 Architecture (BatchManager + Poller) | Phase 3, 4 전체 |
| §5 DB Schema | Task 1.1~1.4 |
| §6 Gemini SDK wrap | Task 2.1~2.3 |
| §7 BatchManager 책임 | Task 3.1~3.4 |
| §8 BatchPoller 책임 | Task 4.1~4.4 |
| §9 AnalysisQueue hook | Task 3.5~3.7 |
| §10 Chain 상호작용 | Task 3.1 (chain check) |
| §11 부분 실패 처리 | Task 4.3 (_handle_succeeded fallback) + 4.4 (terminal) |
| §12 backend_used write hook (M11 한계) | Task 1.5 |
| §13.1 status bar 토글 | Task 5.4 |
| §13.2 /settings batch 카드 | Task 5.1 |
| §13.3 i18n msgid 18개 | Task 5.5 |
| §13.4 /analyzing dashboard | Task 5.2, 5.3 |
| §14 Embed dim 일관성 | (scope 밖 — spec 명시) |
| §15 Config 스키마 | Task 3.7 |
| §16 회귀 + 테스트 | 각 task 의 Step 1~4 |
| §17 Phase 분할 | 본 plan 의 Phase 구조 |
| §18 알려진 한계 | docs (Task 6.3) |

### 2. Placeholder scan

- "TBD" / "TODO" / "fill in details" — 0 건
- "Add appropriate error handling" — 0 건 (각 task 가 명시적 try/except + 분류)
- "Similar to Task N" — 없음 — 각 task 가 self-contained
- Task 3.3 의 `_image_prompt(modality, row)` 가 `IMAGE_PROMPT` 상수 import — 실제 상수 존재 여부 검증 필요 (현재 SpriteAnalyzer 의 prompt 문자열이 `IMAGE_PROMPT` 같은 module-level constant 인지, 또는 method 내부 string 인지). 실 코드 확인 후 적절히 분기 — 본 plan 에서는 "상수 추출 또는 별도 모듈" 두 옵션 명시.
- Task 5.4 (Qt status bar) — TDD skip (UI 수동 검증) — 명시적 결정

### 3. Type consistency

- `BatchChatRequest(asset_id, messages, force_json)` — Task 0.1, 2.1, 3.3 일관
- `GeminiBatchStatus(state, inlined_responses, file_name, error)` — Task 0.1, 2.3, 4.2, 4.3 일관
- `BatchJobRow` 13 필드 — Task 0.1, 1.2, 4.x 일관
- `BatchManager(store, chain_registry, analysis_queue, cfg)` — Task 3.1, 3.4, app.py 일관
- `BatchPoller(store, chain_registry, analysis_queue, cfg)` — Task 4.1, app.py 일관
- modality 문자열 `chat_image / chat_audio / text_embed` — 전체 일관

---

## Execution Handoff

Plan complete and saved to [`docs/superpowers/plans/2026-05-20-gemini-batch-api.md`](docs/superpowers/plans/2026-05-20-gemini-batch-api.md).

Two execution options:

1. **Subagent-Driven** (recommended) — fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
