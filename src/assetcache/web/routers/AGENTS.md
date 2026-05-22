<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# routers

## Purpose
FastAPI 라우터 모듈. 페이지 (HTML 응답) 와 API (JSON / HTMX fragment) 가 책임 단위로 분리되어 있다. `app.py.build_app` 이 14개 router 를 register.

## Key Files
| File | Description |
|------|-------------|
| `__init__.py` | 패키지 마커 (router import 는 `app.py` 가 직접) |
| `pages.py` | `/`, `/library`, `/packs`, `/labels-admin`, `/projects/{id}` 등 HTML 페이지 진입 (base.html extend) |
| `library.py` | 라이브러리 검색 API — query + label_query + diversity + 카드 fragment |
| `packs.py` | 팩 enable/disable / 메타 / 카드 fragment |
| `picks.py` | M5 — `request_user_pick` 의 브라우저 측 — 카드 그리드 + 선택 POST → asyncio.Future resolve |
| `labels_admin.py` | 라벨 axis 인벤토리 (24 axis) + enable/disable + bulk migration. M11.8 mood 시드 비활성화 도구도 여기 |
| `projects.py` | 프로젝트 CRUD + active project 토글. `router_pages` + JSON API 분리 |
| `feedback.py` | `report_feedback` 웹 측 — 카드 negative 버튼 → 피드백 페널티 등록 |
| `saved_searches.py` | save / run / list / delete saved_search (MCP 도구의 GUI 측) |
| `sse.py` | Server-Sent Events — pending pick 도착 알림 + 분석 진행 갱신 |
| `filters.py` | 검색 필터 (kind / pack / label axis) 옵션 fetch |
| `analyzing.py` | M11.1 — `/analyzing` 페이지 + 분석 큐 진행 fragment (active / pending / done 카운트) |
| `settings.py` | 설정 페이지 — backend 선택 / API key / autostart / batch 옵션 / `_batch_card.html` partial |
| `unity_asset_store.py` | M7 — Unity 캐시 scan / 패키지 리스트 / 임포트 트리거 |
| `updates.py` | M10 Phase 2 — PyPI 신버전 체크 + `_pypi_update_banner.html` |
| `health.py` | `/health` 단순 OK + actual_port 노출 (e2e + 부팅 probe) |

## For AI Agents

### Working In This Directory
- **새 라우터 추가 시** — `app.py` 의 `from .routers import (...)` 와 `app.include_router(...)` 양쪽 모두 갱신.
- **HTML 응답** — `response_class=HTMLResponse` 명시 + `templates.TemplateResponse(request=request, name="...", context={...})`. context 에 `page` 키 넣으면 nav 활성 표시.
- **HTMX fragment** — full 페이지 라우트와 분리. fragment 라우트는 `_card_*.html` / `_results_*.html` 등 `_` prefix 템플릿 사용. 응답에 `<html><body>` 없이 fragment 만.
- **write 도구** — `store.write_lock` 안에서 트랜잭션. async 라우트에서 동기 lock 잡을 땐 짧게 끝낼 것 (긴 처리는 `run_in_executor`).
- **router prefix 컨벤션** — pages.py 는 prefix 없음. JSON / fragment API 는 `/api/...` 또는 도메인별 prefix (`/library/...`).
- **`labels_admin.py` M11.8** — mood 시드 `neutral`/`minimalist` 비활성화 마이그가 여기 도구. ⚠️ `palette.neutral` 절대 비활성화 X (M11.6 tone group 핵심).

### Testing Requirements
- `tests/test_web_routers_{name}.py` — 라우터별 회귀. `populated_client` fixture 가 TestClient + populated_deps 한 줄 셋업.
- HTMX fragment 는 응답 본문에 `<html>` 부재 + 기대 fragment 마크업 단언.

### Common Patterns
- `request.app.state.deps` 로 WebDeps 접근. 라우터 함수가 별도 dependency injection 안 받음.
- `_list_packs_dicts(deps.store)` 같은 헬퍼는 라우터 모듈 안에 두고 `from .packs import _list_packs_dicts` 로 import.
- 에러 페이지는 `error_fragment.html` / `error.html` 으로 통일.

## Dependencies

### Internal
- `../app.py` — register.
- `../deps.py` (WebDeps).
- `../../core/*` — store / search / usage / labels / suggest_packs / unity_import.
- `../pending.py` — picks 라우터.

### External
- fastapi, jinja2, sse-starlette (sse 라우터).

<!-- MANUAL: 라우터 수가 변하면 app.py 의 include_router 와 ../AGENTS.md 의 "라우터 14개" 도 같이 갱신. -->
