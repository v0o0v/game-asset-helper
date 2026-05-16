# M1 todo

[M1_plan.md](./M1_plan.md) 에서 도출한 TDD 순서 체크리스트.

## A. 스캐폴딩 / 의존성

- [x] `pyproject.toml` — `watchdog>=4.0`을 `dependencies`에 추가
- [x] `src/gah/core/__init__.py` 빈 패키지 마커
- [x] `src/gah/ui/__init__.py` 빈 패키지 마커
- [x] `tests/conftest.py` — 픽스처 추가 (`library_root`, `make_pack`, `store`)

## B. 테스트 작성 (red phase)

먼저 모든 테스트를 작성하고 `pytest -q` 한 번 돌려서 새로 추가된 테스트만 모두 fail 하는지 확인. M0의 18개는 그대로 PASS.

### B.1 `tests/test_asset_kind.py` (4 케이스)
- [x] `test_png_jpg_webp_classified_as_sprite`
- [x] `test_wav_ogg_mp3_classified_as_sound`
- [x] `test_unknown_extension_returns_none`
- [x] `test_case_insensitive_extension`

### B.2 `tests/test_manifest.py` (8 케이스)
- [x] `test_pack_json_is_parsed_fully`
- [x] `test_pack_toml_is_parsed_fully`
- [x] `test_pack_json_preferred_when_both_present`
- [x] `test_missing_manifest_uses_heuristic_kenney_prefix`
- [x] `test_missing_manifest_uses_heuristic_kaykit_prefix`
- [x] `test_missing_manifest_unknown_prefix_returns_none_vendor`
- [x] `test_malformed_pack_json_falls_back_to_heuristic`
- [x] `test_unknown_keys_are_ignored`

### B.3 `tests/test_store.py` (12 케이스)
- [x] `test_initialize_creates_required_tables`
- [x] `test_pragma_journal_mode_is_wal`
- [x] `test_initialize_is_idempotent`
- [x] `test_upsert_pack_inserts_then_updates`
- [x] `test_upsert_pack_returns_stable_id`
- [x] `test_delete_pack_cascades_assets`
- [x] `test_upsert_asset_sets_pending_state`
- [x] `test_upsert_asset_with_same_hash_is_noop`
- [x] `test_upsert_asset_with_changed_hash_resets_analysis`
- [x] `test_delete_assets_outside_removes_missing_only`
- [x] `test_list_packs_returns_dataclasses`
- [x] `test_assets_for_pack_returns_in_path_order`

### B.4 `tests/test_pack_manager.py` (8 케이스)
- [x] `test_ingest_creates_pack_and_assets_from_manifest`
- [x] `test_ingest_without_manifest_uses_folder_heuristic`
- [x] `test_ingest_skips_unsupported_files`
- [x] `test_reingest_is_noop_when_unchanged`
- [x] `test_reingest_updates_hash_when_bytes_change`
- [x] `test_reingest_removes_deleted_files`
- [x] `test_ingest_handles_empty_pack`
- [x] `test_ingest_normalizes_relative_path_to_posix`

### B.5 `tests/test_scanner.py` (5 케이스)
- [x] `test_reconcile_adds_new_packs`
- [x] `test_reconcile_removes_vanished_packs`
- [x] `test_reconcile_no_changes_is_noop_report`
- [x] `test_reconcile_ignores_files_at_library_root`
- [x] `test_reconcile_runs_on_empty_library`

### B.6 `tests/test_watcher.py` (5 케이스, 디바운서만)
- [x] `test_debouncer_fires_after_window`
- [x] `test_debouncer_coalesces_within_window`
- [x] `test_debouncer_resets_window_on_new_event`
- [x] `test_debouncer_handles_multiple_packs_independently`
- [x] `test_debouncer_uses_injected_clock`

### B.7 `tests/test_ui_smoke.py` (3 케이스)
- [x] `test_main_window_can_be_constructed`
- [x] `test_pack_view_populates_from_store`
- [x] `test_library_view_populates_from_store`

빠진 회귀 방지 — 기존 `tests/test_config.py`도 새 필드(`watch_debounce_seconds`, `library_dir_override`) 추가 후 그대로 통과해야 한다(추가 단언 없이 PASS만 확인).

## C. 구현 (green phase)

각 모듈은 위 테스트들이 가리키는 만큼만 작성. 의존 순서대로:

- [x] `src/gah/core/asset_kind.py` — `classify(path)`, 상수
- [x] `src/gah/core/manifest.py` — `PackManifest`, `load_manifest(pack_dir)`
- [x] `src/gah/core/store.py` — `Store`, `PackRow`, `AssetRow`, 스키마 + CRUD
- [x] `src/gah/core/pack_manager.py` — `ingest_pack(store, pack_dir, library_root)`
- [x] `src/gah/core/scanner.py` — `reconcile_library(store, library_root)`, `ReconcileReport`
- [x] `src/gah/core/watcher.py` — `PackDebouncer` (그리고 `LibraryWatcher` 어댑터 — 단위 테스트 없음)
- [x] `src/gah/config.py` — `Config`에 `watch_debounce_seconds`, `library_dir_override` 추가
- [x] `src/gah/ui/main_window.py` — `MainWindow(store)` + `refresh()`
- [x] `src/gah/ui/pack_view.py` — `PackView(store)` + `refresh()`
- [x] `src/gah/ui/library_view.py` — `LibraryView(store)` + `refresh()`
- [x] `src/gah/app.py` — store 초기화, reconcile 1회, MainWindow + LibraryWatcher 연결
- [x] `src/gah/tray.py` — `make_tray_icon(qapp, on_open_main=None)` 시그니처 확장 + "메인 창 열기" 액션
- [x] `src/gah/__main__.py` — `app.run_tray`의 새 시그니처 호환

각 모듈을 구현할 때마다 해당 테스트 파일만 좁혀서 돌려 통과 확인 (`pytest tests/test_<x>.py -v`). 모두 끝나면 전체 `pytest -q`.

## D. 검증

- [x] `pytest -q` 전체 통과 (M0 회귀 없음 + M1 신규 모두 PASS) — 63 passed
- [ ] PowerShell에서 트레이 실행 → "메인 창 열기" → 빈 메인 윈도우 보임 *(사용자 수동)*
- [ ] `library\kenney_test\` 만들고 PNG 1~2개 복사 → 2초 안에 GUI 갱신, packs/assets 행 등록 *(사용자 수동)*
- [ ] `kenney_test` 폴더 삭제 → 재화해 후 GUI에서 사라짐 *(사용자 수동)*
- [ ] `metadata.db` 가 생성됐고 `sqlite3 ... ".tables"`에 packs/assets/tags/asset_tags 표시 *(사용자 수동)*

수동 검증 절차 자체는 [`M1_verification.md`](./M1_verification.md) §3 에 PowerShell 한 줄씩 풀어두었다.

## E. M2 인계

- [x] `milestones/M1_verification.md` 작성 — pytest 출력, 환경 한계, 사용자 수동 검증 결과
- [x] `HANDOFF.md` 갱신 — §1 한 줄 요약 / §2 검증 사실 / §5 M2 시작 절차
- [x] `CLAUDE.md` §2 진행 현황 표의 M1 상태 ✅ + §8을 M2 안내로 교체
- [x] `milestones/README.md` 의 마일스톤 표 갱신
