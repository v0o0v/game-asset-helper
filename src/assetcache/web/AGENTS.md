<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# web

## Purpose
M5+ FastAPI 웹 GUI. 트레이 모드에서 uvicorn 백그라운드 스레드로 띄우고, 사용자는 트레이 메뉴 → "웹 UI 열기" 로 브라우저에서 접속. HTMX + Alpine.js + Jinja2 스택 (SPA 아님 — 부분 fragment 교체).

핵심 책임:
- 라이브러리 / 팩 / 프로젝트 / 라벨 admin / 분석 진행 / 설정 페이지 렌더링.
- `request_user_pick` (M5) — Claude Code 가 MCP 로 요청 → 사용자가 브라우저 카드 클릭 → SSE 로 결과 전달.
- i18n — ko/en 카탈로그 + `LocaleMiddleware` + Jinja2 `{{ _('...') }}`.
- 트레이 ↔ uvicorn worker thread Qt 시그널 마샬링 (`tray_bridge`).

## Key Files
| File | Description |
|------|-------------|
| `__init__.py` | 패키지 마커 |
| `app.py` | `build_app(deps)` 팩토리 — 라우터 14개 register + 정적 자원 mount + Jinja2 templates + lifespan (PendingPick cleanup 백그라운드 잡 5초 간격) |
| `server.py` | `WebServer` 클래스 — uvicorn 백그라운드 스레드 부팅 + 포트 race-free 확보 (`web_port_max_attempts`) + `actual_port` 노출 |
| `deps.py` | `WebDeps` 데이터클래스 — store + search + usage + registry + queue + config + paths + `pending_picks` + `library_root` + `tray_bridge` (Optional) |
| `i18n.py` | M8 — Babel gettext 카탈로그 (`ko`, `en`) + `_load_translations` + `_t(msgid, locale)` + Jinja2 통합 (`setup_jinja_i18n`) |
| `locale_middleware.py` | `LocaleMiddleware` — `Accept-Language` 헤더 + 쿠키 + URL 쿼리 → ContextVar locale 결정 |
| `tray_bridge.py` | M5 Phase 4D — `TrayBridge(QObject)` + `pickCountChanged = Signal(int)`. uvicorn worker thread 에서 emit → Qt main thread 슬롯 자동 마샬링 (AutoConnection → QueuedConnection) |
| `pending.py` | `PendingPickQueue` — `request_user_pick` 의 asyncio.Future + TTL + max_pending. cleanup 백그라운드 잡이 만료 항목 제거 |

## Subdirectories
| Directory | Purpose |
|-----------|---------|
| `routers/` | FastAPI router 14개 — pages / library / packs / picks / labels_admin / projects / feedback / saved_searches / sse / filters / analyzing / settings / unity_asset_store / updates / health (see `routers/AGENTS.md`) |
| `templates/` | Jinja2 템플릿 — base.html + 페이지별 + `_partial.html` 부분 fragment + settings/ + analyzing/ 서브 (see `templates/AGENTS.md`) |
| `static/` | css / js / vendor (HTMX + Alpine.js) (see `static/AGENTS.md`) |
| `locale/` | gettext 카탈로그 (`messages.pot` + `ko/LC_MESSAGES/messages.mo` + `en/LC_MESSAGES/messages.mo`) (see `locale/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- **PySide6 import 는 `tray_bridge.py` 안에서만** — 다른 web 모듈에서 PySide6 import 금지. `WebDeps.tray_bridge: Any | None` 으로 트랜지티브 의존 끊음. 헤드리스 CI / sandbox 에서도 web 패키지 import 가능해야 함.
- **HTMX fragment 패턴** — 페이지 전체 reload 대신 `hx-get` / `hx-post` 로 부분 교체. fragment 템플릿은 `_partial.html` / `_card_*.html` / `_results_*.html` 등 `_` prefix.
- **`response_class=HTMLResponse`** — 페이지 라우트 명시. JSON API 와 명확히 분리.
- **i18n msgid 추출** — 새 `{{ _('...') }}` / `_t('...')` 추가 후 `pybabel extract -F babel.cfg -o src/assetcache/web/locale/messages.pot src/` → `pybabel update ...` → `.po` 번역 → `pybabel compile -d src/assetcache/web/locale`.
- **`request.app.state.deps` / `request.app.state.templates`** — `build_app` 이 주입. 라우터에서 `Depends(...)` 없이 직접 접근.
- **lifespan cleanup** — PendingPick 만료 항목 5초 간격 청소. `cfg.claude_pick_timeout_seconds + 60` (grace) TTL.

### Testing Requirements
- `tests/test_web_*.py` (40+) — `populated_client` (TestClient + populated_deps) 패턴.
- `tests/test_web_routers_*.py` — 라우터 단위.
- `tests/test_i18n.py` — 카탈로그 로드 + 폴백.
- `tests/test_health_actual_port.py` — uvicorn 포트 race 회피.

### Common Patterns
- 라우터는 `prefix` 일관성 — pages 만 prefix 없음 (`/`, `/library`, `/packs`...), API 는 `/api/*`.
- 비동기 라우트는 `async def` — DB write 가 있을 땐 `store.write_lock` (동기 함수 안에서) 또는 `run_in_executor`.
- TestClient 는 lifespan 안 돌리므로 cleanup 잡 미동작 → pending 만료 테스트는 `cleanup_expired` 직접 호출.

## Dependencies

### Internal
- `../core/*` — store / search / usage / labels / pending / config / paths.
- `../tray.py` — TrayBridge 연결.

### External
- fastapi>=0.110, uvicorn[standard]>=0.27, jinja2>=3.1, python-multipart>=0.0.9, sse-starlette>=2, Babel>=2.14.
- PySide6 (tray_bridge 전용).

<!-- MANUAL: tray_bridge 외에서 PySide6 import 금지 — 헤드리스 import 안정성의 핵심. -->
