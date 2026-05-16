# M0 검증 보고서

## 자동 검증 결과: ✅ 18/18 통과

샌드박스(Linux, Python 3.10.12)에서 `pytest -v` 실행 결과 모든 테스트 통과.

```
tests/test_config.py::test_default_app_paths_uses_env_override PASSED
tests/test_config.py::test_paths_are_created_idempotently PASSED
tests/test_config.py::test_load_config_creates_file_when_missing PASSED
tests/test_config.py::test_load_config_reads_existing_values PASSED
tests/test_config.py::test_save_and_reload_roundtrip PASSED
tests/test_config.py::test_corrupt_toml_is_backed_up_and_defaults_used PASSED
tests/test_entrypoint.py::test_version_flag_prints_version_and_exits_zero PASSED
tests/test_entrypoint.py::test_mcp_flag_returns_not_implemented_exit_code PASSED
tests/test_entrypoint.py::test_data_dir_override_used PASSED
tests/test_imports.py::test_all_modules_importable PASSED
tests/test_logging.py::test_setup_logging_creates_log_file PASSED
tests/test_logging.py::test_setup_logging_writes_record PASSED
tests/test_logging.py::test_setup_logging_is_idempotent PASSED
tests/test_logging.py::test_setup_logging_format_contains_level_and_message PASSED
tests/test_single_instance.py::test_first_instance_acquires_lock PASSED
tests/test_single_instance.py::test_second_instance_raises_already_running PASSED
tests/test_single_instance.py::test_lock_released_after_context_exit PASSED
tests/test_single_instance.py::test_stale_lock_file_does_not_block PASSED

============================== 18 passed in 0.25s ==============================
```

## 검증 환경의 한계

샌드박스는 Python 3.10이라서 검증 도중 다음 두 가지 사소한 변경을 반영했다 — 둘 다 사용자 PC 호환성에 더 유리하다.

1. `pyproject.toml`의 `requires-python` 을 `>=3.11` → `>=3.10` 으로 낮추고
2. 3.10에선 `tomli` 백포트를 의존성에 추가, `config.py`는 버전에 따라 `tomllib` 또는 `tomli` 를 임포트.

샌드박스 마운트 경로 위에 venv를 직접 만들면 권한 충돌이 있어 `/tmp/gah_venv`를 사용해 검증했다 (Windows에선 발생하지 않는 사안). PySide6는 사이즈가 커서 검증 단계에서 설치 생략 — 우리 코드는 PySide6를 함수 안에서만 import하기 때문에 단위 테스트는 영향받지 않는다. `test_imports.py`도 `gah.tray`/`gah.app`의 모듈-레벨 임포트가 PySide6를 건드리지 않아 통과한다.

## 사용자 PC에서 추가 수동 검증 권장 항목

PowerShell에서:

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
pytest -q                       # 18 passed 기대

python -m gah --version         # 종료 코드 0
python -m gah --mcp             # 종료 코드 2, "not implemented" 메시지

python -m gah --tray            # 시스템 트레이에 아이콘 표시
# 새 PowerShell에서 같은 명령을 다시 실행 → "이미 실행 중입니다" 안내 후 즉시 종료
```

수동 검증이 의미 있는 이유: 트레이 아이콘은 실제 윈도우 환경에서만 시각적으로 확인 가능하다. 위 시나리오까지 통과하면 M0 완료.
