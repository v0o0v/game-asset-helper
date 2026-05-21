# M11.1 — Gemini Batch API + /analyzing dashboard (v0.2.1 후보)

> 상위 spec: [`docs/superpowers/specs/2026-05-20-gemini-batch-api-design.md`](../docs/superpowers/specs/2026-05-20-gemini-batch-api-design.md)
> plan: [`docs/superpowers/plans/2026-05-20-gemini-batch-api.md`](../docs/superpowers/plans/2026-05-20-gemini-batch-api.md)

## 한 줄 요약

Gemini Batch API (50% 비용, 24h SLO) — image + audio + embed 모든 modality + 임계값 30 + 사용자 토글 hybrid + 신규 `/analyzing` dashboard + M11 알려진 한계(`mark_asset_backends` write hook) 동시 해결. 회귀 1252 → 1426 (+174) + 옵트인 13 → 16.

## Phase 분할 (실제 commit 기준)

| Phase | 산출물 | 대표 commit | 누적 회귀 |
|---|---|---|---:|
| 0 | core/batch/types + LLMBackend.supports_batch Protocol | edd9ade, 75f2631 | 1262 |
| 1 | DB schema + Store CRUD + mark_asset_backends (M11 한계 해결) | 5e8279c~f8a23a9 | 1293 |
| 2 | GeminiBackend batch_chat/embed/get/cancel/download_file | 0963112~7b57c99 | 1306 |
| 3 | BatchManager + AnalysisQueue hook + Config + app wiring | b6ef3d6~c24e0d7 | 1340 |
| 4 | BatchPoller daemon + _poll_job + _handle_succeeded/terminal_failure | b45d9f1~8e37af2 | 1358 |
| 5 | /settings batch + /analyzing dashboard + Qt toggle + i18n 18 msgid | 4d45b65~2c2e1ea | 1420 |
| 6 | end-to-end + 옵트인 integration tests + docs | bb13522~present | 1426 + 3 옵트인 |

## 목표

- **Gemini Batch API 통합** — 대량 에셋 분석(임계값 30+ 동시 드롭)을 50% 비용으로 처리
- **hybrid 정책** — 1장 드롭은 interactive 유지, 30+ 드롭은 자동 batch. 사용자 토글(auto/forced_on/forced_off) 제공
- **M11 한계 해결** — `AnalysisQueue → mark_asset_backends` write hook (Phase 1)
- **/analyzing dashboard** — interactive 큐 + batch jobs + 최근 실패 현황 표시 (5초 자동 새로고침)
- **신규 의존성 0** — `google-genai` 이미 v0.2.0 에 포함

## 산출물

### 신설 모듈

- `src/assetcache/core/batch/__init__.py`
- `src/assetcache/core/batch/types.py` — `BatchJob`, `BatchState`, `BatchJobRecord` dataclass
- `src/assetcache/core/batch/manager.py` — `BatchManager` (try_submit 결정 + Gemini submit + rollback)
- `src/assetcache/core/batch/poller.py` — `BatchPoller` (daemon Thread, 30분 polling)
- `src/assetcache/core/analyzer/messages.py` — 분석기 공통 메시지 빌더 (Manager 재사용)

### DB 변경

- `batch_jobs` 테이블 (신설) — `id, gemini_batch_id, modality, state, asset_count, submitted_at, completed_at, expires_at, result_uri, error_msg`
- `assets` 테이블 — `batch_job_id INTEGER REFERENCES batch_jobs(id)` + `batch_state TEXT` 컬럼 추가

### Store API 신규 메서드 (9건)

| 메서드 | 역할 |
|---|---|
| `save_batch_job` | batch_jobs INSERT |
| `update_batch_job_state` | 상태 전이 + timestamps |
| `list_active_batch_jobs` | poller 루프용 |
| `get_batch_job` | id로 단건 조회 |
| `mark_assets_batch_queued` | assets.batch_state = 'queued' 일괄 |
| `mark_assets_batch_submitted` | assets.batch_state = 'submitted' + batch_job_id 연결 |
| `mark_asset_batch_state` | 단일 에셋 batch_state 갱신 |
| `fetch_pending_by_modality` | modality 별 pending asset 목록 |
| `list_assets_in_batch` | batch_job_id 기준 에셋 목록 |
| `list_recent_failures` | 최근 실패 에셋 목록 |
| `mark_asset_backends` | backend_image/audio/embed 일괄 갱신 (M11 한계 해결) |
| `count_pending_by_modality` | /analyzing summary 용 카운트 |
| `get_searchable_text` | asset_id → FTS 텍스트 (poller 결과 persist 용) |

### GeminiBackend 신규 메서드

- `batch_chat(requests, modality)` — JSONL 빌드 + Gemini Batch API 제출
- `batch_embed(texts)` — 텍스트 임베딩 배치 제출
- `batch_get(batch_id)` — 상태 조회
- `batch_cancel(batch_id)` — 취소
- `batch_download_file(uri)` — 결과 파일 다운로드
- `supports_batch()` — `True` 반환

### LLMBackend Protocol 변경

- `supports_batch() -> bool` 메서드 추가 (기본 구현 `return False`)

### BatchManager (`core/batch/manager.py`)

- `try_submit(modality, chain, store, config)` — toggle/chain/threshold 결정 + race lock + `_do_submit` 위임
- `_do_submit(assets, modality, backend)` — JSONL 빌드 + backend.batch_chat/embed + OSError 필터 + rollback
- `cancel(batch_job_id)` — Gemini 취소 + DB 상태 갱신

### BatchPoller (`core/batch/poller.py`)

- daemon Thread, 기본 30분 polling 간격
- `_poll_once()` — `list_active_batch_jobs` 순회
- `_poll_job(job)` — Gemini `batch_get` → state 매핑 + expiry 안전망
- `_handle_succeeded(job)` — JSONL 결과 파싱 + modality 별 persist + 부분 실패 시 interactive fallback
- `_handle_terminal_failure(job)` — DB 상태 'failed' + 에셋 interactive 재투입

### AnalysisQueue 변경

- `pending_by_modality(modality)` — modality 별 pending 에셋 조회
- `dequeue_assets(asset_ids)` — 큐에서 제거 (batch로 넘길 에셋 선점)
- `_skip_ids: set` — 이미 batch에 넘긴 에셋 worker skip
- `_try_batch_submit(modality)` — dequeue → BatchManager.try_submit 위임 hook
- `snapshot_queue()` — /analyzing A 섹션용 큐 스냅샷
- `set_batch_manager(manager)` — wiring

### Config 변경

- `BatchConfig` dataclass — `toggle: str` (auto/forced_on/forced_off) + `threshold: int` (기본 30) + `polling_interval_minutes: int` (기본 30)
- `[batch]` TOML 섹션 마이그레이션

### app.py 변경

- `BatchManager` + `BatchPoller` 인스턴스 생성 + AnalysisQueue 에 wiring

### 웹 라우터 신규

- `POST /settings/batch` — BatchConfig 저장
- `POST /settings/batch/jobs/<id>/cancel` — batch job 취소
- `GET /analyzing` — /analyzing dashboard (full page)
- `GET /analyzing/partial` — 5초 폴링용 partial HTML
- `POST /analyzing/batch/<id>/cancel` — batch job 취소 (dashboard 내)

### 템플릿 신규

- `templates/partials/_batch_card.html` — /settings 내 batch 카드
- `templates/analyzing/index.html` — /analyzing 전체 페이지
- `templates/analyzing/_partial.html` — 부분 새로고침 대상
- `templates/base.html` — nav link `_nav.html` 갱신

### Qt

- tray menu `Batch: <toggle>` action — 클릭 시 auto → forced_on → forced_off 순환

### i18n

18 신규 msgid (ko/en)

### 신규 테스트 (174건)

- unit: `test_batch_types.py`, `test_store_batch_schema.py`, `test_analysis_queue_backend_hook.py`, `test_analyzer_backend_used.py`, `test_gemini_backend_batch.py`, `test_batch_manager.py`, `test_batch_poller.py`, `test_web_settings_batch.py`, `test_web_analyzing.py`, `test_tray_batch_toggle.py`, `test_batch_i18n.py`
- end-to-end mock: `test_batch_end_to_end.py`
- 옵트인 integration: `test_llm_backend_gemini_batch_integration.py` (+3, 총 옵트인 16)

## 완료 조건

- [x] `pytest -q` → **1426 passed + 1 skipped + 56 deselected**
- [x] 옵트인 3건 — `pytest -m llm_integration tests/test_llm_backend_gemini_batch_integration.py`
- [x] /settings 에서 batch 카드 렌더링 확인 (수동)
- [x] /analyzing dashboard 렌더링 + 5초 자동 새로고침 확인 (수동)
- [x] tray batch toggle 순환 동작 확인 (수동)

## 신규 의존성

0 (`google-genai` 이미 v0.2.0 에 포함, `Babel` 이미 M8 dev dep)

## 알려진 한계 + 후속 계획

- Image/audio Gemini 결과 → labels 실제 파싱 미구현 (empty labels + mark ok). M12 candidate.
- 파일 크기 > 20MB inline 제한 — file destination batch 방식은 v0.2.x 후속.
- OpenAI/Anthropic Batch API — v0.3.0 candidate.
- 비용 가시화 (실 절감 추적) — M12.
- Embedding dim 변경 시 자동 re-embed — M12.
- 사용자가 진행 중 batch job 의 부분 cancel (asset 단위) — v0.2.x.

## 일정 (실제 소요)

~2일 (Phase 0~6 TDD 완료, 2026-05-21)
