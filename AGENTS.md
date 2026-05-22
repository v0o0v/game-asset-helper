<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# assetcache-mcp

## Purpose
**AssetCacheMCP** — Unity 게임 개발 중 Claude Code 같은 MCP 클라이언트가 보유 에셋(2D 스프라이트 / 스프라이트 시트 / 사운드 / Unity Asset Store `.unitypackage`)을 자연어로 요청하면 가장 적합한 후보를 돌려주는 **MCP 서버 + 윈도우즈 트레이 상주 앱**.

- 1차 배포 채널 — **PyPI**: `pipx install assetcache-mcp` / `uv tool install assetcache-mcp`
- 2차 배포 채널 — PyInstaller `--onefile` `.exe` (GitHub Releases, 옵션)
- 핵심 기술 — FastAPI 웹 UI + PySide6 트레이 + Ollama Gemma 4 (멀티 LLM 백엔드 6종) + SQLite WAL + watchdog
- 라이선스 — MIT
- PyPI 페이지 — https://pypi.org/project/assetcache-mcp/

## Key Files
| File | Description |
|------|-------------|
| `CLAUDE.md` | Claude/AI 에이전트가 새 세션에서 가장 먼저 읽어야 할 프로젝트 가이드 |
| `DESIGN.md` | 전체 아키텍처 / MCP 도구 명세 / 데이터 스키마 / ADR |
| `HANDOFF.md` | 현재 인계 스냅샷 (다음 세션이 "어디까지 왔는지" 한 번에 파악) |
| `README.md` | 일반 사용자용 안내 (PyPI 페이지로도 표시됨) |
| `LICENSE` | MIT 라이선스 |
| `pyproject.toml` | PyPI 패키지 메타·런타임/dev 의존성·콘솔 스크립트(`assetcache`, `assetcache-mcp`)·pytest 설정 |
| `uv.lock` | uv 잠금 파일 (재현 가능한 dev 환경) |
| `babel.cfg` | i18n 메시지 추출 설정 (`pybabel extract`) |
| `assetcache.spec` | PyInstaller `.spec` (단일 exe 빌드용, M8) |
| `.gitignore` | git ignore 룰 |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `.github/` | GitHub Actions workflows (PyPI Trusted Publishing) (see `.github/AGENTS.md`) |
| `assets/` | 패키지 정적 자원 (트레이 아이콘 등) (see `assets/AGENTS.md`) |
| `docs/` | 사용자/개발자 문서 + superpowers spec·plan 아카이브 (see `docs/AGENTS.md`) |
| `milestones/` | 마일스톤 plan/todo/verification 3종 세트 + ROADMAP / HISTORY (see `milestones/AGENTS.md`) |
| `scripts/` | LIVE 검증·빌드 보조 스크립트 (see `scripts/AGENTS.md`) |
| `src/` | Python 소스 (`assetcache` 패키지) (see `src/AGENTS.md`) |
| `tests/` | pytest 스위트 — 1601 passed + 옵트인 마커 (see `tests/AGENTS.md`) |
| `tools/` | 개발자용 일회성 inspection 스크립트 (see `tools/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- **새 세션 진입 시** [`CLAUDE.md`](./CLAUDE.md) → [`HANDOFF.md`](./HANDOFF.md) → [`DESIGN.md`](./DESIGN.md) → [`milestones/`](./milestones/) 순서로 읽는다.
- **문서는 한글, 파일·폴더명은 영어** (CLAUDE.md §4.1). PR description / 커밋 메시지 / GitHub 노출 문서도 한글.
- **마일스톤 사이클은 TDD 5단계**: plan → todo → red test → green impl → verification (CLAUDE.md §4.2). 코드 먼저 쓰고 테스트 끼워 맞추지 않는다.
- **venv 는 저장소 바깥** (`%USERPROFILE%\.venvs\gah\`). 작업 폴더 내부에 venv 만들면 권한 충돌.
- **Microsoft Store Python 금지**. `C:\Users\v0o0v\AppData\Local\Programs\Python\Python312\` 정식 Python 사용.
- **워크트리 사용 금지** — 메인 저장소에서 직접 branch checkout (memory feedback `feedback_no_worktrees`).
- **`&&` 체이닝 금지** — PowerShell 5.1 미지원. 사용자에게 명령 안내 시 한 줄에 하나씩 분리.

### Testing Requirements
- 기본 회귀: `pytest -q` → `1601 passed, 1 skipped, 63 deselected` (M11.7 baseline).
- 옵트인 마커 (`pyproject.toml [tool.pytest.ini_options].markers`):
  - `clip_integration` — 실제 CLIP 모델 다운로드 (~600 MB)
  - `mcp_integration` — `python -m assetcache --mcp` subprocess
  - `e2e` — Playwright 헤드리스 Chromium
  - `llm_integration` — 실 LLM API key 필요
- venv 활성화: `& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"`
- 자동 baseline 명령(프로젝트 메모리): `& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -q 2>&1 | Tee-Object -FilePath .omc/m116_baseline.log | Select-Object -Last 30`
- Lint: `ruff check`

### Common Patterns
- **`src/` layout** — 패키지가 `src/assetcache/` 아래에 있고 `pyproject.toml` 의 `[tool.setuptools] package-dir = { "" = "src" }` 로 매핑.
- **WAL SQLite** + `busy_timeout=5000` + `store.write_lock` 로 GUI ↔ MCP stdio 동시 접근.
- **Layered analyzer chain** — sync (`SpriteAnalyzer` / `SoundAnalyzer` / `SpritesheetAnalyzer`) + async batch (`BatchManager` / `BatchPoller`) 둘 다 동일 JSON 스키마.
- **6 backend LLM** — `core/llm/backends/{ollama, gemini, claude, openai_backend, openrouter, huggingface}.py`, modality 별 chain 으로 자동 fallback.
- **Trusted Publishing OIDC** — tag push → GitHub Actions 자동 publish (`.github/workflows/publish.yml`). 평균 ~30초.

## Dependencies

### External (runtime, pyproject.toml `[project].dependencies`)
- **GUI/트레이**: `PySide6>=6.6`
- **파일시스템**: `watchdog>=4.0`, `portalocker>=2.8`, `platformdirs>=4.2`, `tomli_w>=1.0`
- **분석**: `Pillow>=10`, `numpy>=1.26`, `librosa>=0.10`, `soundfile>=0.12`, `httpx>=0.27`, `pydantic>=2.6`, `open_clip_torch>=2.24`, `torch>=2.2`, `matplotlib>=3.8`
- **검색/MCP**: `mcp>=1.27,<2`
- **웹 GUI**: `fastapi>=0.110`, `uvicorn[standard]>=0.27`, `jinja2>=3.1`, `python-multipart>=0.0.9`, `sse-starlette>=2`
- **i18n**: `Babel>=2.14`
- **멀티 LLM**: `google-genai>=0.1`, `anthropic>=0.40`, `openai>=1.50`, `huggingface_hub>=0.24`

### External (dev only, `[project.optional-dependencies].dev`)
- `pytest>=8.0`, `pytest-mock>=3.12`, `pytest-asyncio>=0.23`, `respx>=0.20`, `pytest-playwright>=0.4`, `pyinstaller>=6`, `build`, `twine`

### Runtime data (저장소 바깥)
- `%APPDATA%\AssetCacheMCP\` — 사용자 런타임 데이터 (library / metadata.db / config.toml / web.port / 로그)
- `%APPDATA%\AssetCacheMCP\library\` — 사용자 에셋 팩 드롭 위치

<!-- MANUAL: 프로젝트 한글 정책 / venv 위치 / 워크트리 금지 / Microsoft Store Python 금지는 변하지 않는 사용자 환경 제약이다. -->
