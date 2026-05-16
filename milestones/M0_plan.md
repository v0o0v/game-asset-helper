# M0 — 뼈대 (구현 계획)

## 1. 목표

GAH 프로젝트의 뼈대를 만든다. 어떤 도메인 기능(워처, 분석, 검색, MCP, GUI 본 기능)도 포함하지 않는다. 다만 이후 모든 마일스톤이 의존할 공통 토대 — 설정 파일, 로깅, 단일 인스턴스 보장, 패키지 메타데이터, CLI 엔트리포인트, 빈 트레이 앱 셸 — 를 갖춘다.

M0가 끝나면 사용자는 `game-asset-helper --tray` 를 실행해 트레이 아이콘이 뜨고, 두 번째 실행은 조용히 종료되며, `%APPDATA%/GameAssetHelper/config.toml` 과 `logs/gah.log` 가 자동 생성되는 것을 확인할 수 있어야 한다.

## 2. 산출물

| 파일/디렉터리 | 책임 |
|---|---|
| `pyproject.toml` | 패키지 메타, 의존성, 콘솔 스크립트 엔트리(`game-asset-helper`) |
| `src/gah/__init__.py` | 버전 상수 |
| `src/gah/__main__.py` | `python -m gah` 진입점. argparse로 `--tray`, `--mcp`, `--version` 분기 |
| `src/gah/config.py` | TOML 기반 설정 로딩/저장, 기본값, AppData 경로 해석 |
| `src/gah/logging_setup.py` | 회전 파일 핸들러(10MB × 5) 설정 |
| `src/gah/platform/__init__.py` | 패키지 마커 |
| `src/gah/platform/single_instance.py` | 파일 락 기반 단일 인스턴스 컨텍스트 매니저 |
| `src/gah/app.py` | `QApplication` 생성/실행 함수 (실 GUI는 M5/M6에서 채움) |
| `src/gah/tray.py` | 트레이 아이콘 + 최소 메뉴 (`종료`만) |
| `tests/conftest.py` | 공통 픽스처(임시 AppData, 모킹) |
| `tests/test_config.py` | 설정 로딩/저장 테스트 |
| `tests/test_logging.py` | 로깅 핸들러 동작 테스트 |
| `tests/test_single_instance.py` | 단일 인스턴스 락 테스트 |
| `tests/test_entrypoint.py` | CLI 인자 파싱 스모크 테스트 |
| `tests/test_imports.py` | 모든 패키지 모듈 임포트 스모크 |
| `.gitignore` | `__pycache__`, `.venv`, `dist`, `build`, `*.egg-info` 등 |

## 3. 작업 단위와 책임

### 3.1 `config.py`

- `AppPaths` 데이터클래스: `data_dir`, `library_dir`, `cache_dir`, `db_path`, `config_path`, `log_path` 를 보관. 모두 `pathlib.Path`.
- `default_app_paths()` 함수: 윈도우즈에서 `%APPDATA%/GameAssetHelper/`. 테스트 환경에선 `GAH_DATA_DIR` 환경변수로 오버라이드 가능.
- `Config` 데이터클래스: `library_dir`, `ollama_url`, `model_image`, `model_audio`, `model_embed`, `mcp_port`, `consistency_weight`, `autostart`. 기본값 내장.
- `load_config(path) -> Config`: 파일 없으면 기본값으로 채우고 새로 저장. 손상된 TOML이면 명시적 `ConfigError` 던지고 백업본(`config.toml.bak`)을 만든 뒤 기본값으로 진행.
- `save_config(config, path)`: 원자적 쓰기(임시 파일 + `os.replace`).
- 모든 경로 생성은 `Path.mkdir(parents=True, exist_ok=True)` 로 멱등.

### 3.2 `logging_setup.py`

- `setup_logging(log_path, level)` 함수 하나. 다음 동작:
  - 루트 로거 레벨 설정.
  - `RotatingFileHandler(log_path, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')` 추가.
  - 콘솔(stderr) 핸들러는 INFO 이상.
  - 포맷: `%(asctime)s %(levelname)-8s %(name)s | %(message)s`.
  - 두 번 호출돼도 핸들러가 중복 추가되지 않도록 idempotent.

### 3.3 `platform/single_instance.py`

- `SingleInstance(lock_path)` 컨텍스트 매니저.
- 진입 시 `portalocker.Lock`로 배타 락 시도. 성공하면 락 파일에 현재 PID 기록.
- 실패 시 `AlreadyRunning` 예외를 던진다 (PID 정보 첨부).
- 종료 시 락 해제 + 락 파일 삭제(베스트 에포트). 비정상 종료로 남은 stale 파일은 다음 실행이 락 시도하면 자연스럽게 덮어 쓰인다.
- 윈도우/리눅스 양쪽에서 동작 (portalocker가 추상화).

### 3.4 `app.py` / `tray.py`

- `app.py`: `run_tray()` 함수 — `QApplication([])` 생성 → `tray.make_tray_icon()` → `app.exec()`.
- `tray.py`: `make_tray_icon(qapp) -> QSystemTrayIcon` — 임시 아이콘(빈 PNG 16×16을 in-memory 생성) + "종료" 액션만. 메뉴 클릭 시 `qapp.quit()`.
- 둘 다 모듈 임포트만으로는 PySide6 초기화를 트리거하지 않도록 함수 안에서만 import.
- 테스트에서는 함수 시그니처와 임포트 가능성만 검증.

### 3.5 `__main__.py`

- argparse:
  - `--tray` (기본 동작과 동일, 명시적으로 트레이 모드).
  - `--mcp` (M3에서 채움; M0에서는 "아직 구현되지 않음" 메시지 후 종료 코드 2).
  - `--version`.
  - `--data-dir PATH` (테스트/개발용 오버라이드, 환경변수보다 우선).
- 부팅 순서:
  1. 인자 파싱.
  2. AppPaths 결정.
  3. 디렉터리 생성.
  4. 로깅 셋업.
  5. 단일 인스턴스 락 시도. 실패 시 stderr에 안내 후 종료 코드 0.
  6. `run_tray()` 호출.
- 로그에 "GAH starting" / "GAH exiting" 마커.

## 4. 외부 의존성

| 패키지 | 용도 | 비고 |
|---|---|---|
| Python 3.10+ | 기본 | `tomllib`는 3.11+ 표준, 3.10에선 `tomli` 백포트 |
| `PySide6` | GUI | 트레이 아이콘 |
| `portalocker` | 파일 락 | 크로스플랫폼 |
| `tomli_w` | TOML 쓰기 | 읽기는 `tomllib` 표준 |
| `platformdirs` | AppData 경로 | 윈도우 외 환경에서도 일관성 |
| (dev) `pytest` | 테스트 러너 | |
| (dev) `pytest-mock` | 모킹 | |

PySide6는 사이즈가 크니 dev/optional 그룹은 아니고 메인 의존성으로 둔다.

## 5. 테스트 전략

### 5.1 단위 테스트 목록

**config**
- `test_default_app_paths_uses_env_override` — `GAH_DATA_DIR` 환경변수가 설정되면 그 경로를 사용한다.
- `test_load_config_creates_file_when_missing` — 파일이 없으면 기본값으로 새 파일을 만든다.
- `test_load_config_reads_existing_values` — 기존 TOML의 값을 정확히 읽는다.
- `test_save_and_reload_roundtrip` — 저장 후 다시 로드해도 값이 같다.
- `test_corrupt_toml_is_backed_up_and_defaults_used` — 손상된 TOML이면 `.bak` 백업 + 기본값 진행.
- `test_paths_are_created_idempotently` — 같은 경로 두 번 만들어도 에러 안 남.

**logging**
- `test_setup_logging_creates_log_file` — 호출 후 로그 파일이 생성된다.
- `test_setup_logging_writes_record` — `logger.info("hi")` 호출 결과가 파일에 들어간다.
- `test_setup_logging_is_idempotent` — 두 번 호출해도 핸들러가 1개씩만 (총 콘솔1+파일1).
- `test_setup_logging_format_contains_level_and_message` — 포맷 확인.

**single_instance**
- `test_first_instance_acquires_lock` — 컨텍스트 진입 성공.
- `test_second_instance_raises_already_running` — 첫 락 보유 상태에서 두 번째는 `AlreadyRunning` 예외.
- `test_lock_released_after_context_exit` — 첫 락이 풀리면 두 번째가 성공.
- `test_stale_lock_file_does_not_block` — 락 파일만 남고 프로세스가 죽은 시나리오(파일은 있지만 락은 풀린 상태)에서 새 진입 성공.

**entrypoint**
- `test_version_flag_prints_version_and_exits_zero` — `python -m gah --version` → 종료 코드 0, 출력에 버전.
- `test_mcp_flag_returns_not_implemented_exit_code` — M0에서는 `--mcp` 가 종료 코드 2.
- `test_data_dir_override_used` — `--data-dir`이 환경변수보다 우선.

**imports**
- `test_all_modules_importable` — `importlib.import_module` 로 모든 서브모듈 임포트 시도. PySide6는 `Qt` 플랫폼 플러그인 없이도 임포트만 가능해야 함.

### 5.2 테스트 인프라

- `conftest.py`:
  - `tmp_appdata` 픽스처: `tmp_path` 기반으로 가짜 AppData 디렉터리 + `monkeypatch.setenv('GAH_DATA_DIR', ...)`.
  - `qt_offscreen` autouse 픽스처: `monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')` — 샌드박스/CI에서 GUI 임포트 안전.
- GUI 실제 실행은 단위 테스트 범위 밖. M0에선 스모크(임포트 성공)만 본다. M6 마감 시점에 수동 검증 체크리스트로 처리.

### 5.3 검증 기준 (Definition of Done)

1. `pytest -q` 가 모두 통과한다 (예상 ~15개).
2. `python -m gah --version` 이 종료 코드 0으로 버전을 출력한다.
3. `python -m gah --mcp` 가 종료 코드 2로 "not implemented" 메시지를 낸다.
4. `python -m gah --tray --data-dir <임시경로>` 를 실제 윈도우즈에서 실행하면 트레이 아이콘이 뜨고, 같은 명령을 두 번째로 실행하면 "이미 실행 중" 메시지 후 즉시 종료된다. (이 마지막 항은 샌드박스에서 자동 검증 불가, 수동 검증 항목)
5. `%APPDATA%/GameAssetHelper/config.toml`, `logs/gah.log` 가 생성돼 있다.

## 6. 위험 요소와 완화

- **PySide6 임포트 비용** — Qt 플랫폼 플러그인이 없는 샌드박스에서 `QApplication([])` 인스턴스화 자체가 실패할 수 있다. `QT_QPA_PLATFORM=offscreen` 환경변수와 `xvfb`-not-required 방식을 쓴다. 단위 테스트는 PySide6를 실제로 실행하지 않고 import 가능성만 본다.
- **portalocker 윈도/리눅스 차이** — 라이브러리가 추상화하므로 양쪽 모두 같은 API. 다만 stale 락 처리는 OS별 동작이 살짝 다를 수 있어 테스트는 "락이 풀린 상태"만 다룬다(프로세스가 죽었을 때의 자동 복구는 portalocker가 처리).
- **TOML 손상 시 사용자 데이터 손실** — `.bak` 백업본을 항상 남긴다.

## 7. M0 이후 연결점

- `Config` 데이터클래스에는 M1+에서 채워질 필드 자리(예: `consistency_weight`, `mcp_port`)를 미리 둔다. 기본값만 채우고 실제 사용은 후속 마일스톤.
- `__main__.py`의 인자 파싱에 `--mcp` 자리를 미리 만들어 둠. M3에서 본체 구현.
- 로깅 모듈은 `gah.*` 네임스페이스의 모든 모듈이 `logging.getLogger(__name__)` 만으로 쓰면 된다.
