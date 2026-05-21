# M11.1 todo (모든 task 완료)

## Phase 0 — Skeleton (✅ 2 task)

- [x] 0.1 `core/batch/types.py` + `__init__.py` — `BatchJob`, `BatchState`, `BatchJobRecord` dataclass (commit: edd9ade)
- [x] 0.2 `LLMBackend.supports_batch()` Protocol — 기본 구현 `return False` (commit: 75f2631)

## Phase 1 — DB + Store CRUD + M11 한계 해결 (✅ 5 task)

- [x] 1.1 `batch_jobs` table + `assets.batch_job_id/batch_state` 컬럼 마이그레이션 (commit: 5e8279c)
- [x] 1.2 `Store.save_batch_job` + `update_batch_job_state` + `list_active_batch_jobs` + `get_batch_job` CRUD (commit: 65c7c80)
- [x] 1.3 `Store.mark_assets_batch_queued/submitted` + `mark_asset_batch_state` + `fetch_pending_by_modality` + `list_assets_in_batch` + `list_recent_failures` CRUD (commit: 6a9c9a4)
- [x] 1.4 `Store.count_pending_by_modality` + `get_searchable_text` batch query 메서드 (commit: b9a1248)
- [x] 1.5 `Store.mark_asset_backends` + `AnalyzerResult.backend_used` — M11 알려진 한계 write hook 동시 해결 (commit: f8a23a9)

## Phase 2 — Gemini batch SDK (✅ 3 task)

- [x] 2.1 `GeminiBackend.batch_chat` + `supports_batch = True` (commit: 0963112)
- [x] 2.2 `GeminiBackend.batch_embed` (commit: 9387b80)
- [x] 2.3 `GeminiBackend.batch_get` + `batch_cancel` + `batch_download_file` (commit: 7b57c99)

## Phase 3 — BatchManager (✅ 7 task)

- [x] 3.1+3.2 `BatchManager.try_submit` + `_do_submit` (commit: b6ef3d6)
- [x] 3.3 `core/analyzer/messages.py` 추출 + Manager 에서 재사용 (commit: 7a85987 + 35e9877 fix)
- [x] 3.4 `BatchManager.cancel` + `BackendRegistry.get_backend` (commit: a7badca)
- [x] 3.5 `Store.pending_by_modality` + `AnalysisQueue.pending_by_modality` (commit: 4a7f1d2)
- [x] 3.6 `AnalysisQueue.dequeue_assets` + `_skip_ids` worker skip (commit: 4e4f885)
- [x] 3.7 `BatchConfig` dataclass + `AnalysisQueue._try_batch_submit` hook + `app.py` wiring (commit: c24e0d7)

## Phase 4 — BatchPoller (✅ 4 task)

- [x] 4.1 `BatchPoller` skeleton — daemon Thread + run loop (commit: b45d9f1)
- [x] 4.2 `_poll_job` state 매핑 + expiry 안전망 (commit: 3714e59)
- [x] 4.3 `_handle_succeeded` — modality 별 persist + 부분 실패 fallback (commit: 51f8359)
- [x] 4.4 `_handle_terminal_failure` + `app.py` BatchPoller wiring + cfg fix (commit: 8e37af2)

## Phase 5 — UI (✅ 5 task)

- [x] 5.1 `/settings` batch 카드 + toggle/cancel POST routes (commit: 4d45b65)
- [x] 5.2 `/analyzing` dashboard sections A+B — summary + interactive 큐 (commit: 687a5ec)
- [x] 5.3 `/analyzing` sections C+D + cancel POST + nav link (commit: 9437180)
- [x] 5.4 Qt tray menu Batch mode 토글 (commit: 46dd6e6)
- [x] 5.5 i18n 18 msgid (ko/en) + `pybabel compile` (commit: 2c2e1ea)

## Phase 6 — Integration + Docs (✅ 3 task)

- [x] 6.1 end-to-end mock test — BatchManager→AnalysisQueue→BatchPoller 전체 흐름 (commit: bb13522)
- [x] 6.2 옵트인 Gemini Batch API integration tests (+3, 실 GEMINI_API_KEY, `llm_integration` 마커) (commit: 2b96e7a)
- [x] 6.3 docs (M11_1_plan.md + M11_1_todo.md + M11_1_verification.md) + HANDOFF/CLAUDE/DESIGN/README 갱신 + 최종 회귀 확인 (본 task, v0.2.1 후보 PR 대기)

## 회귀 진화

| Phase | 누적 회귀 | 증가 |
|---|---:|---:|
| baseline (M11 v0.2.0) | 1252 | — |
| Phase 0 완료 | 1262 | +10 |
| Phase 1 완료 | 1293 | +31 |
| Phase 2 완료 | 1306 | +13 |
| Phase 3 완료 | 1340 | +34 |
| Phase 4 완료 | 1358 | +18 |
| Phase 5 완료 | 1420 | +62 |
| Phase 6.1+6.2 완료 | 1426 | +6 |
| Phase 6.3 docs (최종) | **1426** (+ 3 옵트인) | 0 |
