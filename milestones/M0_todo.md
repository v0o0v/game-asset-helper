# M0 todo

[M0_plan.md](./M0_plan.md) 에서 도출한 TDD 순서 체크리스트.

## A. 스캐폴딩

- [ ] `pyproject.toml` 작성 — 패키지 메타, 의존성, `[project.scripts]` 콘솔 스크립트
- [ ] `.gitignore` 작성
- [ ] `src/gah/__init__.py` — `__version__ = "0.0.1"`
- [ ] `src/gah/platform/__init__.py` 빈 패키지 마커
- [ ] `tests/__init__.py` 빈 패키지 마커
- [ ] `tests/conftest.py` — `tmp_appdata`, `qt_offscreen` 픽스처

## B. 테스트 작성 (red phase)

- [ ] `tests/test_config.py` — 6개 케이스
  - [ ] `test_default_app_paths_uses_env_override`
  - [ ] `test_load_config_creates_file_when_missing`
  - [ ] `test_load_config_reads_existing_values`
  - [ ] `test_save_and_reload_roundtrip`
  - [ ] `test_corrupt_toml_is_backed_up_and_defaults_used`
  - [ ] `test_paths_are_created_idempotently`
- [ ] `tests/test_logging.py` — 4개 케이스
  - [ ] `test_setup_logging_creates_log_file`
  - [ ] `test_setup_logging_writes_record`
  - [ ] `test_setup_logging_is_idempotent`
  - [ ] `test_setup_logging_format_contains_level_and_message`
- [ ] `tests/test_single_instance.py` — 4개 케이스
  - [ ] `test_first_instance_acquires_lock`
  - [ ] `test_second_instance_raises_already_running`
  - [ ] `test_lock_released_after_context_exit`
  - [ ] `test_stale_lock_file_does_not_block`
- [ ] `tests/test_entrypoint.py` — 3개 케이스
  - [ ] `test_version_flag_prints_version_and_exits_zero`
  - [ ] `test_mcp_flag_returns_not_implemented_exit_code`
  - [ ] `test_data_dir_override_used`
- [ ] `tests/test_imports.py` — 1개 케이스
  - [ ] `test_all_modules_importable`

## C. 구현 (green phase)

- [ ] `src/gah/config.py` — `AppPaths`, `Config`, `default_app_paths`, `load_config`, `save_config`, `ConfigError`
- [ ] `src/gah/logging_setup.py` — `setup_logging(log_path, level=...)`
- [ ] `src/gah/platform/single_instance.py` — `SingleInstance`, `AlreadyRunning`
- [ ] `src/gah/app.py` — `run_tray(app_paths, config)` (실 GUI는 지연 import)
- [ ] `src/gah/tray.py` — `make_tray_icon(qapp)` (지연 import)
- [ ] `src/gah/__main__.py` — argparse, 부팅 순서, `main()` 함수

## D. 검증

- [ ] `pytest -q` 전체 통과
- [ ] `python -m gah --version` 종료 코드 0 확인
- [ ] `python -m gah --mcp` 종료 코드 2 확인
- [ ] 수동 검증 항목 README에 기록 (트레이 동작 + 단일 인스턴스)

## E. M1 인계

- [ ] M1_plan.md에서 참조할 수 있도록 `Config`에 비워둔 필드 목록을 주석으로 정리
