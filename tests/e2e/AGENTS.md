<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# e2e

## Purpose
M5 Phase 6+ Playwright 헤드리스 Chromium e2e 스위트. 실제 FastAPI + uvicorn 백그라운드 스레드 + 실 sprite/sound 파일 시드 + Ollama 없는 fake embedder 로 페이지·라우터·인터랙션을 검증. **기본 회귀에서 제외** — `pytest -m e2e` 로 옵트인.

## Key Files
| File | Description |
|------|-------------|
| `__init__.py` | pytest 패키지 마커 |
| `conftest.py` | 세션 공유 `e2e_library_root` (실 `hero.png` + `jump.wav` 시드) + `e2e_web_server` (uvicorn 백그라운드 thread + 포트 race 회피 + 부팅 5초 대기) + `e2e_url` (base URL) + `_FakeEmbedder` (sha256 결정론) |
| `test_e2e_library.py` | `/library` 페이지 — 검색 바 + 결과 카드 + 사이드 패널 |
| `test_e2e_packs.py` | `/packs` 페이지 — 팩 카드 그리드 + enable/disable 토글 |
| `test_e2e_labels_admin.py` | `/labels-admin` 페이지 — 라벨 axis 인벤토리 + enable/disable |
| `test_e2e_other_pages.py` | `/`, `/projects`, `/projects/{id}`, error 페이지 등 |

## For AI Agents

### Working In This Directory
- **모든 e2e 는 `@pytest.mark.e2e`** — pyproject 의 default addopts 가 `-m 'not e2e'` 라 옵트인 명시 전엔 자동 deselect.
- **session 스코프 fixture** — `e2e_web_server` / `e2e_library_root` 는 세션 1회만 구동. 테스트 간 DB 상태 공유에 주의 (격리 필요한 시나리오는 별도 fixture).
- **분석은 생략** — Ollama 의존 회피. 자산은 `analysis_state="pending"` 상태로만 인덱싱 (`reconcile_library` 만 실행). pending 상태에서도 카드 / 썸네일 / 검색이 깨지지 않아야 한다.
- **포트 확보** — `socket.bind(("127.0.0.1", 0))` 으로 임의 free 포트 잡고, `cfg.web_port_max_attempts = 1` 로 그 포트만 시도해 race 회피.
- **부팅 타임아웃 5초** — `127.0.0.1:port` 에 TCP connect 시도 polling. 실패 시 RuntimeError + cleanup.
- **Playwright Chromium 헤드리스** — pytest-playwright fixture (`page`, `browser_name`) 자동 주입.

### Testing Requirements
- 실행: `pytest -m e2e`
- 첫 실행 시 Playwright 브라우저 설치 필요: `playwright install chromium`
- venv 활성화: `& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"`

### Common Patterns
- `page.goto(f"{e2e_url}/library")` → DOM 검증 (`page.locator(...).text_content()` 등).
- 각 테스트는 짧고 페이지 단위로 분리 — 전체 시나리오 줄로 묶지 않는다 (실패 격리 + 재현 용이).
- `_FakeEmbedder` 가 sha256 결정론이라 검색 결과 순서가 안정적 — 단언이 깨지지 않는다.

## Dependencies

### Internal
- `assetcache.web.server.WebServer` / `build_app` — 진짜 라우터 wiring.
- `assetcache.core.scanner.reconcile_library` — 라이브러리 스캔.
- `tests/conftest.py` 의 fixture (재사용 X — e2e 는 자체 conftest 로 격리).

### External
- pytest-playwright>=0.4 (Chromium 헤드리스).
- numpy / Pillow / soundfile (fixture 시드 생성).

<!-- MANUAL: e2e 는 회귀 안정성 vs 속도 트레이드오프 — 시나리오 추가 시 session 공유 가능한 fixture 인지 먼저 확인. -->
