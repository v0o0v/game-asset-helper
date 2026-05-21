# 2026-05-20 — Gemini Batch API Design Spec (M11.1 / v0.2.1)

## 0. 본 spec 의 위치

- 상위 roadmap: [`2026-05-20-roadmap-design.md`](./2026-05-20-roadmap-design.md) §4 M11~M18.
- 전제: [`2026-05-20-m11-multi-backend-llm-design.md`](./2026-05-20-m11-multi-backend-llm-design.md) — M11 의 LLMBackend Protocol / BackendChain / 6 backend / `gemini-3.1-flash-lite` default / `assets.backend_image/audio/embed` 컬럼.
- 본 spec 은 M11 알려진 한계 "Gemini Batch API 활용 (50% 비용, 24h SLO)" + "AnalysisQueue → mark_asset_backends write hook" 둘을 동시 해결.
- 본 spec 다음: `milestones/M11_1_plan.md` 또는 `milestones/M12_plan.md` → todo → TDD cycle.
- Version 후보: **v0.2.1 patch** (옵트인 기능, 기존 동작 변경 0). M11 → M11.1 자연 연속.

## 1. 한 줄 요약

Gemini Batch API (50% 비용 절감, 24h target / 48h hard expire, multimodal + embedding) 를 `image / audio / embed` 모든 modality 에 적용. `AnalysisQueue` pending 이 임계값 (default 30) 을 넘고 해당 modality chain 1순위가 Gemini 면 자동 batch. 사용자가 status bar 토글로 `auto / forced_on / forced_off` 강제 가능. drop 1장은 임계값 미만 → interactive 그대로. 신설 `core/batch/` (Manager + Poller daemon) + DB `batch_jobs` table + `assets.batch_job_id/batch_state` 컬럼 + 신규 페이지 `/analyzing` (interactive 큐 + batch jobs + 최근 실패 통합 dashboard, HTMX 5초 polling). 신규 의존성 0 (`google-genai` 이미 v0.2.0 에 포함).

## 2. Context — 현재 코드 표면 (M11 v0.2.0 baseline)

### 2.1 핵심 모듈

`src/assetcache/core/analysis_queue.py`:
- `class AnalysisQueue(QObject)` — `ThreadPoolExecutor` 단일 워커 (`concurrency=1` default), `enqueue_asset / enqueue_pack / drain_pending`.
- `_handle_one(asset_id)` → `analyzer.analyze(inp)` 동기 호출 → `store.save_*` + `mark_asset_state`. **단일 워커가 24h batch job 에 blocking 되면 interactive 가 멈춤** → 본 spec 은 batch 를 별도 thread 로 분리해야 함의 근거.
- Qt Signal `progressChanged(AnalysisProgress)` — UI 가 polling 없이 수신.

`src/assetcache/core/llm/backends/gemini.py`:
- `class GeminiBackend` — sync `chat(messages)` / `embed(text)` / `test_connection()`.
- `self._client = genai.Client(api_key=...)` — Batch API 도 같은 client 인스턴스에서 `client.batches.*`.

`src/assetcache/core/llm/chain.py`:
- `class BackendChain(modality: Literal["chat_image","chat_audio","text_embed"])` — `chat(messages) -> (dict, str)` (response + backend_name).
- 본 spec 의 batch 도 chain 1순위 확인용으로 `BackendChain.first_backend_name` 같은 helper 추가.

`src/assetcache/core/store.py`:
- `assets.backend_image / backend_audio / backend_embed` 컬럼 이미 존재 (M11 Phase 6 schema). **단 write path 미구현** — 본 spec Phase 1 에서 `mark_asset_backends()` 추가하여 동시 해결.

### 2.2 회귀 baseline

`pytest -q` → **1252 passed + 1 skipped + 53 deselected** (2026-05-20, M11 v0.2.0 publish 후 main).

### 2.3 Config 키 (현재)

```toml
[backends.gemini]
enabled = true
api_key = "AIza..."
model_image = "gemini-3.1-flash-lite"
model_audio = "gemini-3.1-flash-lite"
model_embed = "gemini-embedding-001"

[chains]
chat_image = ["gemini", "ollama"]
chat_audio = ["gemini", "ollama"]
text_embed = ["gemini", "ollama"]
```

본 spec 신규 추가 (§15 참조):

```toml
[batch]
threshold = 30                       # modality 별 pending >= threshold AND chain[modality][0] == "gemini" → 자동 batch
poll_interval_seconds = 1800         # 30분
expiry_grace_seconds = 172800        # 48h (Gemini hard expire)
toggle = "auto"                      # auto / forced_on / forced_off
```

## 3. 결정 매트릭스 — Trigger 정책

### 3.1 Trigger 결정 (사용자 답변 2026-05-20)

| 옵션 | 채택 |
|---|---|
| 자동 임계값 + 사용자 override toggle | ✅ |
| 자동 임계값만 | ❌ |
| 사용자 명시 toggle 만 | ❌ |
| Pack-import 시점 모달 | ❌ |

### 3.2 임계값 의미

- modality 별 독립 카운트: `AnalysisQueue.progress_by_modality("chat_image")` 가 `>= batch.threshold` 일 때 image 만 batch
- 카운트 정의: 큐 size + DB `state='pending'` 이면서 `batch_state IN ('none','queued')` 인 row 수 (이미 batch 진행 중인 건 제외)
- AnalysisQueue 에 `pending_by_modality()` helper 추가 — modality 는 `asset.kind` 로 매핑:
  - `sprite / spritesheet` → `chat_image`
  - `sound` → `chat_audio`
  - 모든 asset → `text_embed` (embed 는 항상 양쪽)

### 3.3 Toggle 3-state

| 값 | 동작 |
|---|---|
| `auto` (default) | 임계값 + chain[modality][0] == "gemini" 모두 충족 → batch / 아니면 interactive |
| `forced_on` | chain[modality][0] == "gemini" 일 때 모든 신규 → batch (임계값 무시). chain 1순위 != gemini 면 UI 안내 + interactive 동작 (silent fallback) |
| `forced_off` | 항상 interactive (임계값/chain 무관) |

### 3.4 Modality 결정 (사용자 답변)

**image + audio + embed 모두 batch 대상** — 모든 modality 의 chain 1순위가 gemini 일 때 각각 독립 batch job. 사용자가 결정.

근거: Gemini Batch API 는 multimodal + embedding 모두 지원. embed 의 cost 는 작지만 정책 일관성 + chain 변경 시 자동 적용.

## 4. 결정 매트릭스 — Architecture (Approach A)

사용자 답변 2026-05-20: **A. 독립 BatchManager + 전용 polling thread** 채택. B/C 비교 표 §4.3.

### 4.1 모듈 구조

```
src/assetcache/core/batch/
├── __init__.py
├── manager.py           # BatchManager — 임계값/chain check + submit 결정
├── poller.py            # BatchPoller — daemon thread + 30분 polling + 부팅 복구
├── jsonl.py             # request 직렬화 + result parsing helper
└── types.py             # BatchJob / BatchRequest / BatchResult dataclass
```

### 4.2 데이터 흐름

```
[drop N files]
        │
AnalysisQueue.enqueue_pack()
        │
        ├─ BatchManager.try_submit(modality) 호출
        │        │
        │        ├─ toggle == forced_off → skip
        │        ├─ chain[modality][0] != "gemini" → skip (forced_on 이면 UI 안내)
        │        ├─ pending_by_modality(modality) < threshold AND toggle == auto → skip
        │        └─ 모두 충족 → submit:
        │             1. asset_ids ← store.fetch_pending_by_modality(modality, batch_state='none')
        │             2. store.mark_assets_batch_queued(asset_ids)
        │             3. gemini.batch_chat / batch_embed → backend_job_id
        │             4. store.save_batch_job(backend_job_id, modality, asset_ids, submitted_at)
        │             5. store.mark_assets_batch_submitted(asset_ids, batch_job_id)
        │             6. AnalysisQueue 내부 큐에서 해당 asset_id 들 dequeue
        │
        └─ batch submit 실패 시 → 기존 interactive 경로 그대로 (큐 잔존)

[BatchPoller daemon thread, 30분 간격]
        │
        ├─ store.list_active_batch_jobs() → state IN (submitted, running)
        ├─ for each job:
        │        ├─ gemini.batch_get(backend_job_id) → state 갱신
        │        ├─ JOB_STATE_SUCCEEDED → download results:
        │        │     1. results = gemini.batch_results(backend_job_id)
        │        │     2. for each (asset_id, result):
        │        │          - 성공: store.save_asset_analysis(..., backend_X='gemini') + mark_asset_backends + batch_state='completed'
        │        │          - 실패: batch_state='failed' + AnalysisQueue.enqueue_asset(asset_id) → chain 다음 backend interactive 재시도
        │        ├─ JOB_STATE_FAILED → 전체 실패 + assets 전부 interactive 재시도
        │        ├─ JOB_STATE_CANCELLED → 사용자 cancel — interactive 재enqueue
        │        ├─ JOB_STATE_EXPIRED → state='expired' + interactive 재enqueue
        │        └─ now > expires_at AND state in (submitted, running) → 안전망: state='expired' 강제
```

### 4.3 Approach 비교 (decision 근거)

| 항목 | A: 독립 BatchManager | B: AnalysisQueue 확장 | C: FastAPI background task |
|---|---|---|---|
| 단일 worker blocking 위험 | ❌ 없음 | ⚠️ batch worker thread 추가 필요 → 사실상 분리 | ❌ asyncio loop 별도 |
| 부팅 복구 | ✅ DB SoT 자연 | ⚠️ AnalysisQueue 안에 복구 로직 비대 | ⚠️ FastAPI lifespan 의존 |
| 테스트 격리 | ✅ 단위 mock 쉬움 | ⚠️ AnalysisQueue mock 복잡도 ↑ | ⚠️ asyncio fixture 추가 |
| AnalysisQueue 회귀 영향 | 최소 (hook 1개) | 큼 | 보통 |
| 신설 코드 | ~600~800줄 | ~300줄 | ~500줄 |
| 트레이 단독 사용 (서버 없이) | ✅ | ✅ | ❌ FastAPI 필수 |

**A 선택 근거**: blocking 위험 회피 + DB SoT 부팅 복구 자연 + AnalysisQueue 회귀 회피 + 테스트 격리.

## 5. DB Schema

### 5.1 `assets` 컬럼 추가

```sql
ALTER TABLE assets ADD COLUMN batch_job_id INTEGER REFERENCES batch_jobs(id);
ALTER TABLE assets ADD COLUMN batch_state TEXT NOT NULL DEFAULT 'none';
CREATE INDEX idx_assets_batch_state ON assets(batch_state);
```

`batch_state` 값:
- `none` — batch 와 무관 (default, interactive 만)
- `queued` — BatchManager 가 submit 진입 직전 마킹 (race condition 방지)
- `submitted` — Gemini 에 제출 완료, polling 대기
- `completed` — batch 결과 DB 반영 완료
- `failed` — batch 에서 실패 → interactive 재시도 큐로 보냄 (해당 asset 의 `state` 는 `analyzing` 으로 갱신됨)
- `expired` — 48h 지나도 미완료, interactive 재시도

### 5.2 `batch_jobs` table 신설

```sql
CREATE TABLE batch_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backend TEXT NOT NULL,              -- "gemini" (v0.2.x 에서 유일)
    modality TEXT NOT NULL,             -- chat_image / chat_audio / text_embed
    backend_job_id TEXT NOT NULL UNIQUE,-- Gemini "batches/abc123"
    asset_count INTEGER NOT NULL,
    submitted_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,        -- submitted_at + batch.expiry_grace_seconds
    state TEXT NOT NULL,                -- submitted/running/succeeded/failed/cancelled/expired
    completed_at INTEGER,
    success_count INTEGER NOT NULL DEFAULT 0,
    failure_count INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    display_name TEXT                   -- Gemini config['display_name'] (디버깅 용)
);
CREATE INDEX idx_batch_jobs_state ON batch_jobs(state);
CREATE INDEX idx_batch_jobs_backend_job_id ON batch_jobs(backend_job_id);
```

### 5.3 Store API 확장

`src/assetcache/core/store.py` 신규 메서드:

```python
def save_batch_job(self, *, backend, modality, backend_job_id, asset_count,
                   submitted_at, expires_at, display_name) -> int: ...   # returns batch_jobs.id
def update_batch_job_state(self, batch_job_id, *, state, completed_at=None,
                            success_count=None, failure_count=None, error=None) -> None: ...
def list_active_batch_jobs(self) -> list[BatchJobRow]: ...
def get_batch_job(self, batch_job_id) -> BatchJobRow | None: ...
def mark_assets_batch_queued(self, asset_ids: list[int]) -> None: ...
def mark_assets_batch_submitted(self, asset_ids: list[int], batch_job_id: int) -> None: ...
def mark_asset_batch_state(self, asset_id: int, batch_state: str) -> None: ...
def fetch_pending_by_modality(self, modality: str, *,
                              batch_state_in: tuple[str,...] = ("none",),
                              limit: int = 1000) -> list[AssetRow]: ...

# M11 알려진 한계 동시 해결
def mark_asset_backends(self, asset_id: int, *,
                        image: str | None = None,
                        audio: str | None = None,
                        embed: str | None = None) -> None:
    """assets.backend_image / backend_audio / backend_embed 갱신. None 이면 해당 컬럼 무변경."""
```

write 는 모두 `self._write_lock` 안에서 (M2.1 패턴 유지).

### 5.4 마이그레이션 (boot)

`Store._migrate()` 의 schema_version 1 증가:
- `PRAGMA user_version` 으로 추적
- 기존 DB 부팅 시 새 컬럼/테이블 `IF NOT EXISTS` 로 추가 (idempotent)

회귀 baseline DB (M11) 와 호환 — 새 컬럼은 default 값으로 채워짐 (`batch_state='none'`).

## 6. Gemini Batch API SDK wrap

### 6.1 GeminiBackend 확장

`src/assetcache/core/llm/backends/gemini.py` 에 신규 메서드:

```python
from google.genai import types as genai_types

class GeminiBackend:
    # ... 기존 (chat / embed / test_connection)

    def supports_batch(self) -> bool:
        return True

    def batch_chat(self, *, modality: str,
                   requests: list[BatchChatRequest]) -> str:
        """Submit batch chat job. Return backend_job_id (Gemini 'batches/xxx' name).

        modality: "chat_image" or "chat_audio" → self.model_image or self.model_audio
        """
        model = self.model_image if modality == "chat_image" else self.model_audio
        inlined = [
            {
                "contents": self._to_contents(r.messages),
                "config": {"response_mime_type": "application/json"} if r.force_json else {},
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
            raise BackendError(backend="gemini", stage=f"batch_{modality}",
                               transient=_classify(e), cause=e) from e
        return job.name  # "batches/abc123"

    def batch_embed(self, *, texts: list[str]) -> str:
        """Submit batch embedding job. Return backend_job_id."""
        inlined = [{"content": {"parts": [{"text": t}], "role": "user"}} for t in texts]
        try:
            job = self._client.batches.create_embeddings(
                model=self.model_embed,
                src={"inlined_requests": inlined},
                config={"display_name": f"assetcache-text_embed-{int(time.time())}"},
            )
        except Exception as e:
            raise BackendError(backend="gemini", stage="batch_embed",
                               transient=_classify(e), cause=e) from e
        return job.name

    def batch_get(self, backend_job_id: str) -> "GeminiBatchStatus":
        """Poll job. Return state + optional inline results."""
        try:
            job = self._client.batches.get(name=backend_job_id)
        except Exception as e:
            raise BackendError(backend="gemini", stage="batch_get",
                               transient=_classify(e), cause=e) from e
        return GeminiBatchStatus(
            state=job.state.name,                          # JOB_STATE_*
            inlined_responses=getattr(job.dest, "inlined_responses", None),
            file_name=getattr(job.dest, "file_name", None) if job.dest else None,
            error=getattr(job, "error", None),
        )

    def batch_download_file(self, file_name: str) -> bytes:
        return self._client.files.download(file=file_name)

    def batch_cancel(self, backend_job_id: str) -> None:
        try:
            self._client.batches.cancel(name=backend_job_id)
        except Exception:
            log.exception("batch_cancel failed (best-effort)")
```

`BatchChatRequest` / `GeminiBatchStatus` dataclass 는 `core/batch/types.py` 정의 (§4.1 모듈 구조).

### 6.2 다른 backend 의 batch_chat 미지원

M11 의 6 backend 중 본 spec 에서는 **Gemini 만** batch 도입. 다른 backend (Claude / OpenAI / OpenRouter / HF) 는 `supports_batch() → False` default.

`LLMBackend` Protocol 에 `supports_batch() -> bool` 추가 (default 구현은 base.py 에서 False — 모든 기존 backend 영향 0).

OpenAI Batch API 도 존재하지만 본 spec scope 밖 (§18 후속).

### 6.3 inline vs file destination 결정

Gemini Batch API 한계:
- inline: 총 request payload 20MB 이하
- file: 최대 2GB

본 프로젝트 한 image asset 의 base64 payload ~50KB~500KB (PNG 512x512). audio 는 base64 mel-spectrogram PNG ~30KB.
- 50 image @ 500KB = 25MB → file destination 필요할 수도
- 안전 정책: **submit 시 payload size 계산 → 18MB 초과면 file destination**. v0.2.1 에서는 단순화: **inline 만 사용 + 임계값 batch 자동 분할** (한 batch job 당 최대 30 asset 으로 cap, threshold default = 30 과 일치).
- 30+ asset 의 추가 분량은 다음 polling tick 에서 또 submit (다음 chunk).

## 7. BatchManager 책임

`src/assetcache/core/batch/manager.py`:

```python
class BatchManager:
    def __init__(self, *, store: Store, chain_registry: "BackendRegistry",
                 analysis_queue: "AnalysisQueue", cfg: "Config") -> None: ...

    def try_submit(self, modality: str) -> int | None:
        """Try to submit a batch job for the given modality. Return batch_jobs.id or None.

        Decision flow:
        1. cfg.batch.toggle == "forced_off" → None
        2. chain[modality][0].name != "gemini" → None (forced_on 이면 emit UI 안내)
        3. pending = store.count_pending_by_modality(modality)
        4. cfg.batch.toggle == "auto" AND pending < cfg.batch.threshold → None
        5. asset_ids = store.fetch_pending_by_modality(modality, limit=cfg.batch.threshold)
        6. store.mark_assets_batch_queued(asset_ids)  ← race condition 방지
        7. backend = chain[modality][0]
        8. backend_job_id = backend.batch_chat(...) or batch_embed(...)
        9. row_id = store.save_batch_job(...)
        10. store.mark_assets_batch_submitted(asset_ids, row_id)
        11. analysis_queue.dequeue_assets(asset_ids)  ← interactive 큐에서 제거
        12. emit signal "batch_submitted" → UI 갱신
        """
```

- `try_submit` 는 `AnalysisQueue.enqueue_*` 호출 직후, `_emit_progress` 안에서 호출. modality 3개 각각 시도.
- thread safety: `_submit_lock` 으로 modality 별 중복 submit 차단 (동시 enqueue 다발 발생 시).
- 실패 시 (e.g. `BackendError`): `mark_assets_batch_queued` 롤백 → `batch_state='none'` 복귀 + 사용자 알림 + interactive 자동 fallback.

## 8. BatchPoller 책임

`src/assetcache/core/batch/poller.py`:

```python
class BatchPoller(threading.Thread):
    def __init__(self, *, store, chain_registry, analysis_queue, cfg, clock=time.monotonic):
        super().__init__(daemon=True, name="assetcache-batch-poller")
        self._stop_event = threading.Event()
        # ...

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        self.join(timeout=timeout)

    def run(self) -> None:
        # 부팅 시 즉시 1회 sweep (재개)
        self._poll_once()
        while not self._stop_event.is_set():
            self._stop_event.wait(self._cfg.batch.poll_interval_seconds)
            if self._stop_event.is_set():
                break
            self._poll_once()

    def _poll_once(self) -> None:
        jobs = self._store.list_active_batch_jobs()
        for job_row in jobs:
            try:
                self._poll_job(job_row)
            except Exception:
                log.exception("batch poll failed for job_id=%d", job_row.id)
                # 단일 job 실패가 다른 job polling 막지 않게

    def _poll_job(self, job_row) -> None:
        backend = self._chain_registry.get_backend("gemini")
        now = int(time.time())
        if now > job_row.expires_at and job_row.state in ("submitted", "running"):
            self._handle_expired(job_row)
            return
        status = backend.batch_get(job_row.backend_job_id)
        # state mapping: JOB_STATE_PENDING → submitted, JOB_STATE_RUNNING → running, etc.
        ...
        if status.state == "JOB_STATE_SUCCEEDED":
            self._handle_succeeded(job_row, status, backend)
        elif status.state in ("JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"):
            self._handle_terminal_failure(job_row, status)
```

- daemon thread → 트레이 종료 시 자동 정리
- 부팅 시 즉시 1회 sweep 으로 재개 보장
- 단일 job polling 실패가 다른 job 차단 안 함
- 만료 처리: 48h 지나도 미완료 → state='expired' + 모든 asset interactive 재enqueue (안전망)

## 9. AnalysisQueue 통합 hook

### 9.1 신규 메서드

`AnalysisQueue` 에 추가:

```python
def pending_by_modality(self, modality: str) -> int:
    """Count of assets pending for this modality (queue + DB)."""
    ...

def dequeue_assets(self, asset_ids: list[int]) -> int:
    """Remove asset_ids from internal queue (BatchManager 가 submit 후 호출)."""
    # queue.Queue 는 random-access 안 됨 → 내부 set + worker 가 dequeue 시 set 체크하여 skip
    self._skip_ids.update(asset_ids)
    return len(asset_ids)

def _worker_loop(self) -> None:
    # 기존 + skip 체크
    while not self._stop_event.is_set():
        asset_id = self._queue.get(timeout=0.2)
        if asset_id == -1: return
        if asset_id in self._skip_ids:
            self._skip_ids.discard(asset_id)
            continue
        self._handle_one(asset_id)
```

### 9.2 enqueue 후 batch try_submit hook

`enqueue_asset / enqueue_pack / drain_pending` 끝에:

```python
def _try_batch_submit(self) -> None:
    if self._batch_manager is None: return
    for modality in ("chat_image", "chat_audio", "text_embed"):
        try:
            self._batch_manager.try_submit(modality)
        except Exception:
            log.exception("batch try_submit failed for modality=%s", modality)
```

batch_manager 가 None 이면 (config disabled 또는 inject 안됨) noop — 회귀 1252 baseline 영향 0.

## 10. Chain 상호작용 + chain rebuild

- BatchManager 가 chain[modality][0] 을 매 submit 시점에 동적 조회 (`chain_registry.first_backend_name(modality)`) — 사용자가 chain 변경 후 트레이 재시작 없이 다음 batch 부터 반영
- chain 1순위가 `gemini` 가 아니면 batch 진입 자체 안 함
- forced_on 인데 chain 1순위 != gemini → UI 안내 signal emit ("이미지 체인 1순위를 Gemini 로 설정하세요. 현재 batch 토글 ON 이지만 interactive 로 동작합니다.")

## 11. 부분 실패 처리

`BatchPoller._handle_succeeded` 로직:

```python
def _handle_succeeded(self, job_row, status, backend) -> None:
    # 1. 결과 download (inline 만 사용 — §6.3 정책)
    results = status.inlined_responses or []
    if not results and status.file_name:
        # file destination — v0.2.x 후속 (v0.2.1 inline 만)
        log.warning("batch result file destination — v0.2.1 not supported, marking expired")
        self._handle_expired(job_row); return

    # 2. asset_ids 순서 = submit 시 순서 (Gemini 가 같은 순서 보장)
    asset_ids = self._store.list_assets_in_batch(job_row.id)
    success_count = 0
    failure_count = 0

    for asset_id, inline_resp in zip(asset_ids, results, strict=False):
        if inline_resp.response is None or getattr(inline_resp, "error", None):
            # 개별 실패 → interactive 재시도
            self._store.mark_asset_batch_state(asset_id, "failed")
            self._analysis_queue.enqueue_asset(asset_id)  # chain 다음 backend (e.g. ollama) 시도
            failure_count += 1
            continue
        # 성공 — modality 별 persist 분기 (analyzer 의 parser 재사용):
        try:
            if job_row.modality == "chat_image":
                payload = json.loads(inline_resp.response.text)
                # SpriteAnalyzer / SpritesheetAnalyzer 의 _parse_chat_payload 함수 추출하여 재사용
                self._persist_image_payload(asset_id, payload)
                self._store.mark_asset_backends(asset_id, image="gemini")
            elif job_row.modality == "chat_audio":
                payload = json.loads(inline_resp.response.text)
                self._persist_audio_payload(asset_id, payload)
                self._store.mark_asset_backends(asset_id, audio="gemini")
            elif job_row.modality == "text_embed":
                # embed batch 는 response.text 가 아니라 inline_resp.embedding.values
                vec = list(inline_resp.embedding.values)
                self._store.save_embedding(asset_id, self._cfg.gemini_model_embed,
                                            self._serialize_vec(vec), len(vec))
                self._store.mark_asset_backends(asset_id, embed="gemini")
            self._store.mark_asset_batch_state(asset_id, "completed")
            success_count += 1
        except Exception:
            log.exception("batch result parse failed asset_id=%d", asset_id)
            self._store.mark_asset_batch_state(asset_id, "failed")
            self._analysis_queue.enqueue_asset(asset_id)
            failure_count += 1

    self._store.update_batch_job_state(job_row.id,
        state="succeeded", completed_at=int(time.time()),
        success_count=success_count, failure_count=failure_count)
```

핵심: 실패 항목만 interactive 재enqueue → chain 의 다음 backend (보통 ollama) 가 interactive 처리. chain semantic 유지.

## 12. Per-asset backend_used write hook (M11 알려진 한계 동시 해결)

### 12.1 문제

M11 verification §"AnalysisQueue → mark_asset_backends write hook" 알려진 한계: `assets.backend_image/audio/embed` 컬럼 schema 만 준비, write path 미구현.

### 12.2 본 spec 해결

`store.mark_asset_backends()` 추가 (§5.3) + 두 경로에서 호출:

1. **AnalysisQueue interactive 경로** — `_persist(asset_id, result)` 안에서 `mark_asset_backends(asset_id, image=result.backend_used_image, ...)`. `AnalyzerResult` 에 `backend_used: dict[str, str | None]` 필드 추가 (`{"image": "ollama", "embed": "ollama"}`).
2. **BatchPoller 경로** — `_handle_succeeded` 안에서 (§11).

`Analyzer.analyze()` 의 `chain.chat()` 반환 `(response, backend_name)` 의 두 번째 요소를 result 에 담아 store 에 전달.

### 12.3 시그니처 변경 영향

- `core/analyzer/sprite.py / sound.py / spritesheet.py` 의 `AnalyzerResult` 에 `backend_used: dict` 필드 추가 → 기존 테스트 fixture 다수 영향 (dataclass 필드 default `{}` 로 회귀 0 유지)
- `core/store.py` 의 `save_asset_analysis` 와 별도 호출 (`mark_asset_backends` 는 단독) — 회귀 0

## 13. UI 통합

### 13.1 status bar 토글

메인 창 status bar 우측에 추가:

```
[분석 진행: 12/80 (ETA 2분)]   [🚀 Batch: auto ▼]   [⚙️]
```

드롭다운 옵션: `auto / 강제 ON / 강제 OFF`. 선택 즉시 `config.toml [batch].toggle` 저장 + tray Signal `batchToggleChanged` emit.

### 13.2 /settings 의 Batch 카드

`/settings` 페이지 하단에 신규 섹션:

```
─ Batch 분석 ─────────────────────────
Gemini Batch API (50% 비용 절감, 최대 24시간)

상태: image_chain 1순위가 Gemini 입니다 ✅
      audio_chain 1순위가 Ollama 입니다 ⚠️ (batch 미사용)

토글: ○ auto  ● 강제 ON  ○ 강제 OFF
임계값: [30] 장 (auto 모드에서 자동 batch 진입)
폴링 주기: [30] 분

[진행 중 batch job]
- image · 80 장 · 제출 후 2시간 12분 / 24시간 SLO · 진행 중
- text_embed · 80 장 · 제출 후 2시간 12분 / 24시간 SLO · 진행 중

[테스트 batch submit (1 장)]   [모두 cancel]
```

- HTMX `hx-post /settings/batch` 로 부분 저장
- 진행 중 batch job 카드: `hx-get /settings/batch/jobs` 폴링 (10초)
- cancel 버튼: `hx-post /settings/batch/jobs/<id>/cancel` → BatchManager.cancel → Gemini cancel + 모든 asset interactive 재enqueue

### 13.3 i18n msgid 추가 (총 18개)

ko/en `.po` 신규:

1. `"Batch analysis"` / `"배치 분석"`
2. `"Threshold"` / `"임계값"`
3. `"Polling interval"` / `"폴링 주기"`
4. `"In-progress batch jobs"` / `"진행 중 배치 작업"`
5. `"Submitted %d minutes ago"` / `"%d분 전 제출"`
6. `"image chain first is %s — batch enabled"` / `"이미지 체인 1순위가 %s 입니다 — batch 활성"`
7. `"image chain first is %s — batch disabled. Set chain[image][0] to gemini."` / `"이미지 체인 1순위가 %s 입니다 — batch 비활성. 이미지 체인 1순위를 gemini 로 설정하세요."`
8. `"Cancel all"` / `"모두 취소"`
9. `"Auto"` / `"자동"` (toggle 옵션)
10. `"Forced on"` / `"강제 ON"`
11. `"Forced off"` / `"강제 OFF"`
12. `"Batch mode (Gemini): %s"` / `"배치 모드 (Gemini): %s"` (status bar)
13. `"Analysis progress"` / `"분석 진행"` (§13.4 페이지 nav 링크 + 페이지 제목)
14. `"Summary"` / `"요약"`
15. `"Interactive queue"` / `"즉시 분석 큐"`
16. `"Batch jobs"` / `"배치 작업"`
17. `"Recent failures"` / `"최근 실패"`
18. `"Worker #%d (%.1fs elapsed)"` / `"워커 #%d (%.1f초 경과)"`

### 13.4 분석 진행 페이지 `/analyzing` (사용자 요청 2026-05-20)

분석 중인 asset 의 현재 상태를 한 화면에서 볼 수 있는 dashboard. 메인 창 상단 nav 에 "분석 진행" 링크 추가.

#### URL 구조

| Method · URL | 용도 |
|---|---|
| `GET /analyzing` | 전체 dashboard HTML (초기 렌더) |
| `GET /analyzing/partial` | HTMX 갱신용 부분 HTML (5초 polling) |
| `POST /analyzing/batch/<batch_job_id>/cancel` | 진행 중 batch job cancel — `/settings/batch/jobs/<id>/cancel` 의 alias (편의용) |

#### 페이지 섹션

**섹션 A: 요약 (상단)**
```
요약: 즉시 분석 큐 12 · 배치 image 80 · 배치 audio 3 · 실패 2
ETA: 약 2시간 14분 (auto 추정 — interactive 평균 × 12 + batch 24h SLO max)
```

**섹션 B: Interactive queue**
| path | kind | state | 처리 |
|---|---|---|---|
| `pack/foo/bar.png` | sprite | analyzing | 워커 #1 (3.2초 경과) |
| `pack/foo/baz.png` | sprite | pending | 큐 #1 |
| `pack/foo/qux.wav` | sound | pending | 큐 #2 |

— 최대 50 행. 그 이상은 `+N more` summary.

**섹션 C: Batch jobs**
```
[image · job #1] gemini · 80 장 · 제출 2시간 12분 전 / 24시간 SLO        [cancel]
  ├ pack/foo/file_001.png · queued
  ├ pack/foo/file_002.png · queued
  └ +78 more

[text_embed · job #2] gemini · 80 장 · 제출 2시간 12분 전 / 24시간 SLO   [cancel]
  └ +80 more
```

각 batch job 카드는 expand/collapse (HTMX `hx-target` swap). 기본은 collapsed (상위 정보만).

**섹션 D: 최근 실패 (interactive 재시도 후에도 실패)**
| path | kind | error | 시간 |
|---|---|---|---|
| `pack/x/bad.png` | sprite | non-json response | 5분 전 |
| `pack/y/zip.wav` | sound | timeout after 60s | 12분 전 |

— `assets.state='failed' AND batch_state IN ('failed','none')` 의 최근 20개. `error` 컬럼 표시.

#### 새로고침

- HTMX `hx-get="/analyzing/partial" hx-trigger="every 5s" hx-swap="outerHTML"` polling
- SSE 는 v0.2.x 후속 — polling 단순화 우선
- AnalysisProgress Signal 변경 시 즉시 갱신은 Qt 트레이 전용 — 웹 페이지는 polling

#### 신규 router

`web/routers/analyzing.py`:
- `get_dashboard()` → `templates/analyzing/index.html`
- `get_partial()` → `templates/analyzing/_partial.html` (섹션 A~D 통합)
- `cancel_batch_job(batch_job_id)` → BatchManager.cancel(batch_job_id) → 302 redirect

#### 데이터 소스

- 큐 상태: `AnalysisQueue.progress()` + `AnalysisQueue.snapshot_queue()` (신규 helper, 큐 내부 최대 50개 path 노출)
- in-flight: `AnalysisQueue._in_flight_path` (이미 있음)
- batch job: `store.list_active_batch_jobs()` + `store.list_assets_in_batch(job_id, limit=2)`
- 최근 실패: `store.list_recent_failures(limit=20)` (신규)

#### 신규 의존성 / 회귀 영향

- 신규 의존성 0 (HTMX 이미 M5 에서 사용)
- 신규 테스트 +10:
  - `tests/test_web_routers_analyzing.py` — `GET /analyzing` 200 / `GET /analyzing/partial` 부분 HTML / 4 섹션 렌더 / batch cancel POST / 최근 실패 표시 / 빈 큐 상태 정상 렌더

## 14. Embed dim 일관성

- Gemini `gemini-embedding-001` default 768 dim ≈ Ollama `nomic-embed-text` 768 — 사용자가 chain 변경해도 dim 동일 → cosine 유효
- 사용자가 dim 다른 모델 (e.g. `gemini-embedding-001` 의 3072 옵션) 선택 시 → 기존 cosine search 무효 → /settings 에 "재분석 권유" 안내 (M11 §10.1 와 동일 정책 — M11.1 scope 밖, M12 candidate)

## 15. Config 스키마 확장

`config.py::Config` dataclass 확장:

```python
@dataclass
class BatchConfig:
    threshold: int = 30
    poll_interval_seconds: int = 1800       # 30분
    expiry_grace_seconds: int = 172800      # 48h
    toggle: Literal["auto", "forced_on", "forced_off"] = "auto"

@dataclass
class Config:
    # ... 기존
    batch: BatchConfig = field(default_factory=BatchConfig)
```

TOML:
```toml
[batch]
threshold = 30
poll_interval_seconds = 1800
expiry_grace_seconds = 172800
toggle = "auto"
```

마이그레이션: 기존 config.toml 에 `[batch]` 섹션 없으면 default 적용 (silent migration).

## 16. 회귀 + 테스트 전략

### 16.1 신규 unit 테스트

| 영역 | 파일 | 테스트 | 회귀 Δ |
|---|---|---|---:|
| Phase 0 skeleton | `tests/test_batch_types.py` + `tests/test_llm_backend_supports_batch.py` | dataclass smoke / `LLMBackend.supports_batch()` Protocol default False | +5 |
| Schema migration + Store API | `tests/test_store_batch_schema.py` | column add idempotency / batch_jobs CRUD / fetch_pending_by_modality / mark_assets_batch_* / `mark_asset_backends` (M11 한계 동시) | +20 |
| BatchManager | `tests/test_batch_manager.py` | toggle 3-state / chain check / threshold / submit success / submit failure rollback / race condition lock | +18 |
| BatchPoller | `tests/test_batch_poller.py` | poll_once with mock backend / succeeded path / failed path / cancelled / expired / 부팅 재개 / 단일 job 실패가 다른 job 영향 X | +15 |
| Gemini batch SDK wrap | `tests/test_llm_backend_gemini_batch.py` | mock `client.batches.create / get / cancel` + result parsing | +12 |
| AnalysisQueue hook | `tests/test_analysis_queue_batch_hook.py` | dequeue_assets / skip_ids worker behavior / try_submit hook on enqueue | +8 |
| UI router (settings) | `tests/test_web_routers_settings_batch.py` | GET batch panel / POST toggle / POST cancel / GET active jobs | +10 |
| UI router (analyzing) | `tests/test_web_routers_analyzing.py` | GET dashboard / GET partial / 4 섹션 렌더 / batch cancel POST / 최근 실패 표시 / 빈 큐 상태 | +10 |
| i18n msgid | `tests/test_locale_batch_msgid.py` | ko/en 둘 다 18 신규 msgid 존재 (§13.3 목록) | +5 |
| End-to-end (mock backend) | `tests/test_batch_end_to_end.py` | enqueue 50 → batch submit → mock poll → succeeded → DB 반영 / 일부 실패 → interactive 재enqueue | +5 |

**합계 신규 ~108 tests** → 1252 + 108 = **~1360** (옵트인 제외, 옵트인 +3 별도).

### 16.2 옵트인 integration 테스트

`@pytest.mark.llm_integration` (기존 마커 재사용):

```python
@pytest.mark.llm_integration
def test_gemini_batch_real_submit_and_poll():
    """실 GEMINI_API_KEY 로 batch submit + 즉시 cancel (실 24h 대기 없음).
    부팅 복구도 같이 검증."""
```

신규 옵트인 ~3 케이스 → 13 + 3 = 16 옵트인.

### 16.3 회귀 baseline 유지

Phase 0 (skeleton + Protocol 확장만) → 회귀 1252 그대로. 이후 Phase 각 산출물마다 신규 테스트.

## 17. Phase 분할

| Phase | 산출물 | 신규 테스트 | 누적 |
|---|---|---:|---:|
| 0 | `core/batch/__init__.py` + `types.py` + `LLMBackend.supports_batch()` Protocol 확장 (default False) | +5 | 1257 |
| 1 | DB schema (`batch_jobs` table + `assets.batch_job_id/batch_state` 컬럼) + Store API + `mark_asset_backends` (M11 한계 동시) | +20 | 1277 |
| 2 | `GeminiBackend.batch_chat / batch_embed / batch_get / batch_cancel / batch_download_file` + `BatchChatRequest / GeminiBatchStatus` dataclass | +12 | 1289 |
| 3 | `BatchManager.try_submit` + chain check + race lock + AnalysisQueue hook (`pending_by_modality` / `dequeue_assets` / `_skip_ids`) | +18 + 8 | 1315 |
| 4 | `BatchPoller` daemon + 부팅 복구 + 만료 처리 + 부분 실패 → interactive 재enqueue | +15 | 1330 |
| 5 | UI — status bar 토글 + `/settings` batch 카드 + `/analyzing` dashboard + AnalysisQueue.snapshot_queue + store.list_recent_failures + i18n 18 msgid | +10 + 10 + 5 | 1355 |
| 6 | end-to-end + 옵트인 integration + docs (HANDOFF / CLAUDE / DESIGN §4.x / README batch 섹션) + verification | +5 + 3 옵트인 | **1360 + 3 옵트인** |

**목표**: ~1360 회귀 + 16 옵트인 (기존 13 + 신규 3).

## 18. 알려진 한계 + 후속 마일스톤 의존

### 18.1 본 spec scope 밖

| 항목 | 결정 | 후속 |
|---|---|---|
| OpenAI Batch API (50% 할인) | 미구현 | v0.2.x 또는 v0.3.0 |
| Anthropic Batch API | 미구현 | v0.2.x 또는 v0.3.0 |
| 비용 가시화 (실제 절감 추적) | 미구현 | M12 (벤치마크) 와 자연 결합 |
| Embed dim 변경 시 자동 re-embed | M11 §10.1 와 동일 — 수동 cleanup | M12 candidate |
| File destination (inline 20MB 초과 batch) | inline + 30개 cap 으로 회피 | v0.2.x |
| 사용자가 진행 중 batch job 부분 cancel (asset 단위) | 미구현 (job 전체만 cancel) | v0.2.x |
| 임계값을 modality 별 다르게 (image=30 / audio=10) | global threshold 하나 | reactive |

### 18.2 후속 의존

- **M12 (측정/벤치마크)**: batch 의 50% 비용 실측. batch_jobs 테이블의 success_count/failure_count + Gemini API quota 통계 결합.
- **M14 (MCP 원격)**: batch job 진행 상태를 원격 MCP client 가 polling 가능. `find_asset` 응답에 batch_state 추가 candidate.
- **M16 (유사 검색)**: embed batch 가 대량 backfill 의 핵심 — 본 spec 의 batch_embed 가 M16 의 자연 도구.

## 19. 출처

### 본 spec 의 web research (2026-05-20)

- [Gemini Batch API docs (Python SDK)](https://ai.google.dev/gemini-api/docs/batch-api) — `client.batches.create / get / list / cancel / delete`, `create_embeddings`, JOB_STATE_*, 24h target / 48h hard expire, inline 20MB / file 2GB
- [google-genai GitHub README](https://github.com/googleapis/python-genai) — `InlinedRequest` / `BatchJobSource` data structures
- (M11 spec 참조 — Gemini SDK 일반 사용은 그쪽에 명시)

### 본 프로젝트 historical fact

- `src/assetcache/core/analysis_queue.py` (single-worker ThreadPoolExecutor, Qt Signal pattern) — 본 spec batch hook 위치 결정 근거
- `src/assetcache/core/llm/backends/gemini.py` (sync chat/embed pattern) — batch_* 메서드 위치
- `src/assetcache/core/store.py` (write_lock pattern, schema_version 추적) — DB 확장 위치
- M11 spec [`2026-05-20-m11-multi-backend-llm-design.md`](./2026-05-20-m11-multi-backend-llm-design.md) §10.1 (알려진 한계: backend_used write hook + Gemini Batch API) — 본 spec 의 동시 해결 대상

### 향후 참고 (M12+ 의존)

- [OpenAI Batch API](https://platform.openai.com/docs/guides/batch) — v0.2.x/v0.3.0 후속
- [Anthropic Message Batches API](https://docs.claude.com/en/docs/build-with-claude/batch-processing) — v0.2.x/v0.3.0 후속
- [Gemini API Pricing — Batch 50%](https://ai.google.dev/gemini-api/docs/pricing) — M12 비용 가시화
