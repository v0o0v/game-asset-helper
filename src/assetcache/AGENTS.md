<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# assetcache

## Purpose
본 패키지 (`import assetcache`). M10 이전 명칭은 `gah` / Game Asset Helper. **두 가지 모드**가 단일 entrypoint 에 통합돼 있다:

1. **트레이 모드** (`assetcache` / `python -m assetcache --tray`) — PySide6 트레이 + FastAPI 웹 서버 + 코어 분석 큐 + 워처.
2. **MCP stdio 모드** (`assetcache-mcp` / `python -m assetcache --mcp`) — Claude Code 가 자식 프로세스로 spawn 하는 stdio MCP 서버. 트레이 프로세스와 SQLite WAL + busy_timeout 으로 공존.

## Key Files
| File | Description |
|------|-------------|
| `__init__.py` | `__version__` 정의 (현재 0.2.2) — `pyproject.toml`/`tag`/PyPI 와 동기화 필수 |
| `__main__.py` | CLI entrypoint — argparse → AppPaths 해소 → config 로드 → logging → SingleInstance → tray/mcp/version 분기. `main()` + `main_mcp()` (PyPI console scripts entry) |
| `app.py` | 트레이 모드 wiring — QApplication / AnalysisQueue / Analyzer / EmbeddingEncoder / Searcher / Store / Web 서버 / Unity boot scan |
| `config.py` | `Config` Pydantic 모델 + `AppPaths` (data/config/log/lock/web.port) + `default_app_paths()` (`--data-dir > GAH_DATA_DIR > platformdirs`) + `load_config()` |
| `tray.py` | PySide6 트레이 + `TrayController` + `_TrayBridge(QObject)` Qt Signal cross-thread + PyPI 신버전 알림 메뉴 |
| `logging_setup.py` | `setup_logging()` — 파일 + 콘솔 핸들러 설정 |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `core/` | 도메인 로직 — store / pack manager / scanner / watcher / analyzer / batch / llm / sheet / unity_import / updater (see `core/AGENTS.md`) |
| `mcp/` | MCP stdio 서버 + 20 도구 (see `mcp/AGENTS.md`) |
| `platform/` | Windows 단일 인스턴스 + 자동 시작 (see `platform/AGENTS.md`) |
| `web/` | FastAPI 웹 GUI (라우터·템플릿·정적 자원·i18n) (see `web/AGENTS.md`) |
| `ui/` | (Empty) — M5 에서 Qt 메인 윈도우 폐기 후 reserved namespace |

## For AI Agents

### Working In This Directory
- **PySide6 import 는 함수 스코프** — `app.py` 가 모듈 import 시 Qt platform plugin 을 요구하지 않도록 함수 안으로 미룬다. CLI `--version` 이나 unit test 가 헤드리스에서 깨지지 않는 핵심.
- **PyInstaller `--noconsole` 빌드는 `sys.stdout` / `sys.stderr` 가 `None`** — `__main__.py` 앞쪽이 None 을 `open(os.devnull, "w")` 로 대체한다. dev console 빌드에는 영향 없음.
- **`__version__` bump 시** — 항상 `pyproject.toml` `[project].version` 과 `src/assetcache/__init__.py` `__version__` 두 곳 모두 동기화. `git tag v0.x.y` 와도 일치 (Trusted Publishing 검증 키).
- **단일 인스턴스 락** — 트레이 모드만 `SingleInstance(paths.lock_path)` 사용. MCP stdio 는 매번 새 프로세스이므로 락 안 잡음 (WAL + busy_timeout 이 충돌 흡수).
- **`--data-dir` 우선순위** — CLI flag > 환경변수 `GAH_DATA_DIR` > `platformdirs.user_data_dir`. 환경변수 명은 M10 rename 후에도 `GAH_*` 유지 (사용자 환경 호환).

### Testing Requirements
- `tests/test_entrypoint.py` — CLI argparse / boot order.
- `tests/test_app_m5.py` — `app.run_tray()` smoke.
- `tests/test_config*.py` — config 로드 / 마이그레이션.
- `tests/test_tray*.py` — 트레이 이벤트.

### Common Patterns
- 모듈 간 의존: `__main__` → `app` (lazy) / `mcp.server` (lazy). `app` → `core.*` + `web.server`. `mcp` → `core.*`.
- exit code 컨벤션: `EXIT_OK=0`, `EXIT_ALREADY_RUNNING=0` (benign), `EXIT_NOT_IMPLEMENTED=2`, `EXIT_USAGE=64`.

## Dependencies

### Internal
- `core/` — 모든 도메인 로직.
- `mcp/` — stdio MCP 진입.
- `web/` — FastAPI 웹 서버.
- `platform/` — 단일 인스턴스 + 자동 시작.

### External
- PySide6 (트레이만), httpx, pydantic, mcp, fastapi, uvicorn, jinja2, sse-starlette, platformdirs, portalocker, tomli_w.

<!-- MANUAL: `gah` / `game_asset_helper` 잔존 식별자가 발견되면 모두 `assetcache` 로 정리 (M10 rename 잔존 검출 대상). 환경변수 `GAH_DATA_DIR` 만 의도적으로 유지. -->
