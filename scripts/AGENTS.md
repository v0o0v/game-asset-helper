<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# scripts

## Purpose
빌드·LIVE 검증 보조 스크립트. 패키지에 포함되지 않으며 (`pyproject.toml` 의 setuptools.packages.find 가 `src/` 만 검색), 개발자가 직접 `python scripts/...` 로 실행한다.

## Key Files
| File | Description |
|------|-------------|
| `drive_live_batch.py` | LIVE 검증 — 실 LLM 백엔드로 batch 분석 시나리오 실행 (M11.4~M11.7 mood/palette 분석 검증에 재사용) |
| `generate_tray_ico.py` | `assets/tray.ico` 트레이 아이콘 PIL 생성 |
| `launch-tray-test.ps1` | LIVE 검증 — prod `config.toml` (API key / backend chains / 가중치) 만 fresh data-dir 로 복사 + 트레이 부팅.  매번 설정 재입력 없이 격리 환경 (`$env:TEMP\assetcache-test-<scenario>-data`) 에서 검증.  사용자 실 DB·라이브러리 안 건드림.  사용: `.\scripts\launch-tray-test.ps1 <scenario>` |
| `make_complex_sheets.py` | spritesheet 테스트 fixture 생성 (다양한 격자/색상 패턴) |

## For AI Agents

### Working In This Directory
- LIVE 검증은 비싼 (실 API 호출 + 시간) 동작이므로 마일스톤 plan 의 명시된 phase 에서만 실행.
- `drive_live_batch.py` 는 마일스톤 verification 단계에서 `python scripts/drive_live_batch.py --backend gemini ...` 형태로 호출.
- 아이콘 / fixture 생성 스크립트는 결과를 commit 에 포함 (재생성 의존성 회피).

### Testing Requirements
- 스크립트 자체에 대한 테스트 없음 — 산출물(`assets/tray.ico` / `tests/fixtures/sheets/*.json`) 이 정상이면 OK.

### Common Patterns
- pythonpath 의존 — `pyproject.toml` 의 `[tool.pytest.ini_options].pythonpath = ["src"]` 와 별개로 scripts 는 venv activate 후 `python -m scripts.{name}` 또는 `python scripts/{name}.py` 형태.

## Dependencies

### Internal
- `src/assetcache/core/batch/` (drive_live_batch).
- `src/assetcache/core/llm/backends/` (drive_live_batch).
- `src/assetcache/core/sheet/` (make_complex_sheets — 분석 대상 fixture).

### External
- `Pillow` (아이콘 / sheet 생성).
- 실 LLM SDK (Gemini / Claude / OpenAI 등 — drive_live_batch).

<!-- MANUAL: -->
