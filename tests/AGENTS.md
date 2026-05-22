<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# tests

## Purpose
pytest 스위트. M11.7 baseline = **1601 passed + 1 skipped + 63 deselected**, 옵트인 마커 4 종 (`clip_integration` / `mcp_integration` / `e2e` / `llm_integration`) 은 default 에서 deselected. 모든 test 는 `_isolate_data_root` autouse fixture 가 `GAH_DATA_DIR` 을 `tmp_path_factory` 로 강제 격리해 사용자의 `%APPDATA%\AssetCacheMCP\` 를 절대 건드리지 않는다.

## Key Files
| File | Description |
|------|-------------|
| `conftest.py` | 공통 fixture — `qt_offscreen` (PySide6 헤드리스) + `_isolate_data_root` (production AppData 격리) + `qapp` + `tmp_appdata` + `library_root` + `make_pack` + `store` + `asset_factory` + M2 결정론 fixture builder (`tiny_pixel_32.png` / `short_sfx_1s.wav` 등 7종) + M3 `fake_embedder` + `populated_store` + `mcp_tool_deps` + M5 `deps_fixture` / `populated_deps` / `populated_client` |
| `__init__.py` | pytest 패키지 마커 |
| `test_store_m*.py`, `test_config_m*.py`, `test_mcp_tools_m*.py` | 마일스톤별 회귀 — `M{N}` suffix 가 어느 마일스톤에서 추가됐는지 표시. 새 마일스톤은 `..._m{N}.py` 신규 파일로 분리 |
| `test_web_*.py`, `test_web_routers_*.py` | M5 + 후속 마일스톤의 FastAPI 라우터 + 페이지 회귀 (40+ 파일) |
| `test_analyzer_*.py` | sprite / sound / spritesheet 분석기 회귀 |
| `test_mcp_integration.py` | `mcp_integration` 마커 — 실제 `python -m assetcache --mcp` subprocess 기동 |
| `test_prompt_*.py`, `test_batch_*.py` | M11.4~M11.7 sync↔batch prompt parity + mood OPTIONAL + category 별 mood 차단 + palette tone group |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `e2e/` | Playwright 헤드리스 Chromium e2e (`-m e2e` 옵트인) (see `e2e/AGENTS.md`) |
| `fixtures/` | 결정론 fixture 파일 (.gitignored, 첫 실행 시 conftest 가 생성) + Unity `.unitypackage` 빌더 (see `fixtures/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- **TDD red 단계** — 새 마일스톤은 항상 테스트 먼저. 한 번 돌려서 expected fail 확인 후 구현 시작 (CLAUDE.md §4.2).
- **autouse `_isolate_data_root`** — 모든 test 가 fresh `GAH_DATA_DIR` 자동 격리. 우회하려면 명시적 `monkeypatch.delenv("GAH_DATA_DIR")` 또는 `tmp_appdata` fixture override.
- **`qt_offscreen` autouse** — PySide6 가 헤드리스에서 import 되도록 `QT_QPA_PLATFORM=offscreen`. CI / sandbox 에서도 GUI 코드 import 가능.
- **마일스톤 명명** — `test_{모듈}.py` (기본) + `test_{모듈}_m{N}.py` (해당 마일스톤에서 추가). 변경된 기존 파일에 마일스톤 회귀 끼워 넣으면 추적 어려워짐.
- **Lazy import 패턴** — fixture 의 heavy import (numpy / Pillow / soundfile / respx / torch / PySide6) 는 함수 본문 안에. RED phase 에 미구현 모듈이 있어도 collection 깨지지 않는다.
- **검증용 fresh `--data-dir`** — 사용자 DB 안 건드리는 LIVE 검증 패턴 (project memory `project_verification_fresh_data_dir`).

### Testing Requirements
- 기본 회귀: `pytest -q` → `1601 passed, 1 skipped, 63 deselected` (M11.7 baseline).
- 옵트인 마커:
  - `pytest -m clip_integration` — 실제 CLIP 모델 다운로드(~600 MB)
  - `pytest -m mcp_integration` — `python -m assetcache --mcp` subprocess
  - `pytest -m e2e` — Playwright 헤드리스 Chromium (`tests/e2e/`)
  - `pytest -m llm_integration` — 실 LLM API key (Gemini/Claude/OpenAI/OpenRouter/HF)
- 자동 baseline 명령 (project memory): `& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -q 2>&1 | Tee-Object -FilePath .omc/m116_baseline.log | Select-Object -Last 30`

### Common Patterns
- `populated_store` (2 packs × 3 assets) — 검색/카드/모달/사이드패널 회귀의 공통 시드.
- `mcp_tool_deps` — MCP 도구 함수 단위 회귀 (full deps 합성, queue 옵션 override).
- `populated_client` — TestClient(FastAPI) + populated_deps 한 줄. HTTP 레벨 검증.
- `fake_embedder` — sha256 결정론 임베더로 Ollama 네트워크 우회.
- `respx.mock(assert_all_mocked=True)` — Ollama HTTP 호출 누락 검출 (silent 네트워크 hit 차단).
- Batch path 검증은 concurrency=0 + BatchManager/Poller 직접 instantiate 패턴 (project memory `project_batch_path_drive_pattern`).

## Dependencies

### Internal
- `src/assetcache/` — 회귀 대상.
- `pyproject.toml [tool.pytest.ini_options]` — `pythonpath = ["src"]` + `testpaths = ["tests"]` + 4 marker 정의 + `addopts` 의 `-m 'not ... and not ...'` 가 옵트인 마커 자동 deselect.

### External
- pytest>=8 + pytest-mock + pytest-asyncio + respx + pytest-playwright (e2e).
- 결정론 fixture 생성: numpy / Pillow / soundfile.

<!-- MANUAL: 회귀 baseline 숫자는 마일스톤마다 갱신 (M11.7 = 1601). 새 옵트인 마커 추가 시 pyproject.toml + 이 문서 + CLAUDE.md 셋 모두 갱신. -->
