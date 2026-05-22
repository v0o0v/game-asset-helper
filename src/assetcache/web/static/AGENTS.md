<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# static

## Purpose
FastAPI `StaticFiles` 가 `/static/*` 으로 마운트하는 정적 자원. CSS + JS + 서드파티 vendor 번들. `pyproject.toml [tool.setuptools.package-data]` 가 `static/**/*` 를 패키지에 포함 → PyPI install 시에도 동작.

## Key Files (서브디렉터리별)

### `css/`
| File | Description |
|------|-------------|
| `main.css` | 메인 스타일시트 — 레이아웃 + 카드 + 모달 + 사이드 패널 |
| `themes.css` | 라이트 / 다크 테마 변수 + `[data-theme]` 셀렉터 |

### `js/`
| File | Description |
|------|-------------|
| `app.js` | 앱 부트스트랩 — HTMX/Alpine 후처리 + 모달 핸들러 |
| `theme.js` | 테마 토글 (localStorage 저장 + `[data-theme]` 적용) |

### `vendor/`
| File | Description |
|------|-------------|
| `htmx.min.js` | HTMX core |
| `htmx-sse.min.js` | HTMX SSE 확장 (pending pick + 분석 진행 알림) |
| `htmx-json-enc.js` | HTMX JSON encoding 확장 |
| `alpine.min.js` | Alpine.js |
| `README.md` | vendor 파일 출처 + 버전 추적 (수동 업그레이드 절차) |

## For AI Agents

### Working In This Directory
- **vendor 는 commit** — CDN 의존 회피 (오프라인 / 사내망 / Claude Code 도 자식 프로세스 부팅 안정성). 업그레이드 시 `vendor/README.md` 의 버전 기록 갱신.
- **CSS 변수** — `themes.css` 에 light/dark 토큰 정의. 컴포넌트 CSS 는 `var(--token-name)` 만 참조 — 직접 hex 색상 박지 X.
- **`theme.js`** — boot 시 localStorage 의 테마 적용 + 토글 핸들러 register. flash-of-unstyled 회피 위해 `<head>` 안쪽에서 일찍 로드.
- **JS 빌드 단계 없음** — TypeScript / bundler 미사용. ES module 직접 로드 + vendor 는 `min.js`. 복잡도 증가 시 빌드 도입 ADR 필요.
- **HTMX `hx-swap` 기본 `innerHTML`** — fragment 가 outer element 까지 갈아 끼우려면 `hx-swap="outerHTML"` 명시.

### Testing Requirements
- 정적 자원 회귀 별도 없음 — 라우터 테스트가 `/static/main.css` 200 응답까지만 확인.
- 시각 검증은 사용자 수동 (e2e Playwright 가 일부 페이지 스모크).

### Common Patterns
- 템플릿에서 참조: `<link rel="stylesheet" href="/static/css/main.css">` (FastAPI StaticFiles mount).
- vendor 파일은 절대 수정 X — 패치 필요 시 별도 wrapper JS 에서 augment.

## Dependencies

### Internal
- `../app.py` — `app.mount("/static", StaticFiles(directory=_static_dir()), name="static")`.
- `../templates/base.html` — `<link>` / `<script>` 참조.

### External
- HTMX 1.x, Alpine.js 3.x (vendor 파일 — 버전은 `vendor/README.md` 참조).

<!-- MANUAL: vendor 업그레이드 시 `vendor/README.md` 의 버전 + 출처 URL + SRI hash 갱신 권장. -->
