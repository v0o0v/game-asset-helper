# M5 todo

[M5_plan.md](./M5_plan.md) 에서 도출한 TDD 순서 체크리스트. 작업 단위 번호(§4.x) 는 plan 의 절을 그대로 가리킨다.

체크박스 진행 규칙 — M4 와 동일하지만 phase 단위 6 회 반복:

```
Phase 0 (의존성/Config/정적 자원)  →  A → B → C → D → 커밋들
Phase 1 (FastAPI 스캐폴딩)          →  A → B → C → D → 커밋들
Phase 2 (라이브러리 페이지)         →  A → B → C → D → 커밋들
Phase 3 (B/C/D 사이드 패널)         →  A → B → C → D → 커밋들
Phase 4 (Claude pick + SSE)         →  A → B → C → D → 커밋들
Phase 5 (Qt 폐기 + Pack/라벨 이식) →  A → B → C → D → 커밋들
Phase 6 (마감 + 검증)               →  D (verification + 인계)
```

A = 스캐폴딩 / 의존성. B = red (테스트 먼저). C = green (모듈 의존 순서대로 통과). D = 검증 / 회귀 / 커밋.

각 task 의 세부 step 은 plan §4 에 풀어 적혀 있다. 본 todo 는 task 단위만 추적한다.

---

## Phase 0 — 의존성 + Config + 정적 자원 (~0.5일)

### A. 브랜치 + 의존성

- [ ] `main` 에서 `feat/m5-web-gui` 브랜치 분기 (이미 분기됨 — 본 plan 작성 세션에서)
- [ ] `pyproject.toml` 신규 의존성 5 추가 + `pip install -e .[dev]` 실행 → import smoke 통과 (Task 0.1)
- [ ] 커밋: `deps(m5): FastAPI + uvicorn + Jinja2 + sse-starlette + python-multipart 추가`

### B. red — Config M5 필드

- [ ] `tests/test_config_m5.py` 작성 — 8 케이스 (Task 0.2 Step 1)
- [ ] `pytest tests/test_config_m5.py -v` → 8 FAIL 확인

### C. green — Config + UsageSource

- [ ] `src/gah/config.py` 에 7 필드 + `UsageSource` enum (Task 0.2 Step 3)
- [ ] `pytest tests/test_config_m5.py -v` → 8 passed
- [ ] `pytest -q` 회귀 → 452 + 8 = 460 passed
- [ ] 커밋: `feat(m5): Config 7 신규 필드 + UsageSource enum`

### D. 정적 자원 vendoring

- [ ] `mkdir src/gah/web/static/vendor` + HTMX 1.9.12 (core + sse ext) + Alpine 3.13.10 다운로드 (Task 0.3)
- [ ] SHA256 추출 → `README.md` 표에 박음
- [ ] 커밋: `deps(m5): HTMX 1.9.12 + Alpine 3.13.10 vendoring`

---

## Phase 1 — FastAPI 스캐폴딩 + 트레이 통합 (~1주)

### A. 스캐폴딩

- [ ] `src/gah/web/__init__.py` (빈 파일) 생성
- [ ] `tests/conftest.py` 에 `deps_fixture` 추가 (M5 fixture — store/searcher/usage/registry/config/paths/pending_picks 모두 mock 또는 in-memory)

### B. red — Phase 1 테스트들 (29 케이스 작성 후 일괄 fail)

- [ ] `tests/test_web_url.py` (5) — read/write/atomic/missing/invalid (Task 1.1)
- [ ] `tests/test_web_pending.py` (10) — register/resolve/cancel/double_resolve/max_pending/cleanup/snapshot/concurrent/lock (Task 1.2)
- [ ] `tests/test_web_app.py` (8) — build_app/health 200/mcp_tools_count=17/static/lifespan/라우터 9 등록/404/캐시 (Task 1.4)
- [ ] `tests/test_web_server.py` (6) — start/health/포트 폴백/max_attempts/stop/actual_port (Task 1.5)
- [ ] `tests/test_tray_m5.py` (5) — webbrowser.open/no labels menu/notify_user_pick/count=0/더블 클릭 (Task 1.6)
- [ ] `tests/test_app_m5.py` (6) — WebServer.start/stop/SSE wire/browser open/포트 폴백/종료 (Task 1.7)
- [ ] `pytest tests/test_web_*.py tests/test_tray_m5.py tests/test_app_m5.py -v` → 40 FAIL

### C. green — Phase 1 모듈 구현

(plan §4.1 의 task 순서 = 의존성 순서)

- [ ] `src/gah/web/url.py` 구현 → `test_web_url.py` 5 passed (Task 1.1)
- [ ] `src/gah/web/pending.py` 구현 → `test_web_pending.py` 10 passed (Task 1.2)
- [ ] `src/gah/web/deps.py` 구현 (Task 1.3)
- [ ] `src/gah/web/i18n.py` + `src/gah/web/routers/health.py` + 다른 8 라우터 빈 스텁 + `src/gah/web/app.py` 구현 → `test_web_app.py` 8 passed (Task 1.4)
- [ ] `src/gah/web/server.py` 구현 → `test_web_server.py` 6 passed (Task 1.5)
- [ ] `src/gah/tray.py` 수정 (`on_open_labels` 제거 + `notify_user_pick_request`) → `test_tray_m5.py` 5 passed (Task 1.6)
- [ ] `src/gah/web/sse_bus.py` 구현 + `src/gah/app.py` (`run_tray`) 수정 + Qt UI 테스트 4 파일 임시 skip 마크 → `test_app_m5.py` 6 passed (Task 1.7)

### D. 회귀 + 커밋 7개

- [ ] `pytest -q` → ~490 passed + ~30 skipped (Qt UI 테스트들)
- [ ] 커밋들 (Task 별 1 커밋, 총 7개):
  - `feat(m5): web.port 파일 R/W (MCP loopback URL 공유)`
  - `feat(m5): PendingPickQueue (asyncio.Future + lock + TTL cleanup)`
  - `feat(m5): WebDeps 의존성 묶음 데이터클래스`
  - `feat(m5): FastAPI 앱 팩토리 + lifespan + 9 라우터 스텁 + i18n passthrough`
  - `feat(m5): WebServer (uvicorn 별도 스레드 + 포트 폴백 + web.port 공유)`
  - `feat(m5): 트레이 메뉴 웹 GUI 진입 + notify_user_pick_request 신호`
  - `feat(m5): run_tray 가 WebServer 시작 + main_window 의존성 제거 (m4 GUI 테스트 skip)`

---

## Phase 2 — 라이브러리 페이지 (검색 + 결과) (~1주)

### A. 스캐폴딩

- [ ] 베이스 템플릿 + 정적 자원 mount 확인

### B. red — Phase 2 테스트들 (~25 케이스)

- [ ] `tests/test_web_routers_library.py` (14) — `/api/search`, `/ui/search-results`, `/api/thumbnail`, `/api/audio`, `/api/library`, `/ui/asset-detail`, 페이지네이션, 디폴트 상태, 정렬, label_query 통합, pack/kind 필터 (Task 2.1-2.11)
- [ ] `pytest tests/test_web_routers_library.py -v` → 14 FAIL

### C. green — Phase 2 모듈 + 템플릿

(plan §4.2 task 순서)

- [ ] `routers/library.py` — `/api/search` 구현 (Task 2.1)
- [ ] `routers/library.py` — `/ui/search-results` + `_card_wide.html` + `_card_list.html` + `_results_grid.html` (Task 2.2, 2.5)
- [ ] `routers/library.py` — `/api/thumbnail/{id}` (Task 2.3)
- [ ] `routers/pages.py` — `/library` 페이지 라우트 + `base.html` + `library.html` + `_nav.html` + `main.css` + `themes.css` (Task 2.4)
- [ ] `library.html` — 검색 바 + 디바운스 + 결과 영역 (Task 2.6)
- [ ] 결과 영역 — 그리드/리스트 토글 + 카드 크기 + 정렬 + 카운트 (Task 2.7)
- [ ] 페이지네이션 (더 보기 버튼) (Task 2.8)
- [ ] 디폴트 상태 (검색 비어 → 추가일↓) (Task 2.9)
- [ ] 카드 상세 모달 — `/ui/asset-detail/{id}` + `asset_detail.html` (Task 2.10)
- [ ] 사운드 ▶ — `/api/audio/{id}` + audio 태그 swap (Task 2.11)
- [ ] `pytest tests/test_web_routers_library.py -v` → 14 passed

### D. 회귀 + 시각 검증 + 커밋들

- [ ] `pytest -q` → ~520 passed
- [ ] 수동 시각 검증 — 디바운스 / 정렬 / 더 보기 / 모달 / 사운드 ▶
- [ ] 커밋들 (task 별):
  - `feat(m5): /api/search POST (JSON, HybridSearcher 위임)`
  - `feat(m5): /ui/search-results POST HTMX fragment + 와이드 카드 partial`
  - `feat(m5): /api/thumbnail (M4 lazy 256×256 PNG 재사용 + ETag)`
  - `feat(m5): 라이브러리 페이지 베이스 레이아웃 (base/nav/library + CSS 변수)`
  - `feat(m5): 와이드/리스트 카드 partial`
  - `feat(m5): 검색 바 + 300ms HTMX 디바운스 + ⚙ 고급 토글`
  - `feat(m5): 결과 툴바 (그리드/리스트/카드 크기 S/M/L/정렬/카운트)`
  - `feat(m5): 결과 페이지네이션 (더 보기 버튼)`
  - `feat(m5): 검색 비어 시 라이브러리 전체 추가일↓ (디폴트)`
  - `feat(m5): 카드 클릭 → 자산 상세 모달`
  - `feat(m5): 사운드 인라인 ▶ 재생`
  - `feat(m5): 라이브러리 페이지 검색+결과 통합 (디바운스+정렬+페이지네이션+모달)`

---

## Phase 3 — 우측 사이드 패널 B/C/D (~1.5주)

### A. 스캐폴딩

- [ ] `_side_panel_b.html` / `_side_panel_c.html` / `_side_panel_d.html` 빈 파일 생성 + base.html 에 include

### B. red — Phase 3 테스트들 (~22 케이스)

- [ ] `tests/test_web_routers_filters.py` (7) — `/api/filters/labels`, `/ui/chip-panel`, axis 분류, 칩 상태, 라벨 검색, `/api/filters/packs` (Task 3.6-3.9)
- [ ] `tests/test_web_routers_saved_searches.py` (8) — POST/GET/DELETE/run/UNIQUE/미존재 (Task 3.14)
- [ ] `tests/test_web_routers_feedback.py` (5) — POST 정상/positive/negative/unknown reason/누적 (Phase 3 의 페널티 학습 UI)
- [ ] `pytest tests/test_web_routers_filters.py tests/test_web_routers_saved_searches.py tests/test_web_routers_feedback.py -v` → 20 FAIL

### C. green — Phase 3 모듈 + 템플릿

(plan §4.3 task 순서 18개)

- [ ] ⚙ 고급 토글 + 슬라이드 인 transition (Task 3.1)
- [ ] 사이드 패널 리사이즈 핸들 (Task 3.2)
- [ ] B/C/D 탭 헤더 + 컨테이너 (Task 3.3)
- [ ] B 탭 — 매칭 모드 라디오 (Task 3.4)
- [ ] B 탭 — 라벨 검색 + 노란 강조 (Task 3.5)
- [ ] B 탭 — 종류 탭 (sprite/sheet/sound) + `/api/filters/labels` 분류 (Task 3.6)
- [ ] B 탭 — axis 칩 FlowLayout + 클릭 토글 (Task 3.7)
- [ ] B 탭 — 다축 필터 드롭다운 4개 + `/api/filters/packs` (Task 3.8)
- [ ] `/api/search` 가 selectedLabels + matchMode 통합 (Task 3.9)
- [ ] C 탭 — 표시 옵션 양방향 바인딩 (Task 3.10)
- [ ] C 탭 — 카드 메타 토글 (Task 3.11)
- [ ] D 탭 — 프리셋 3 + `/api/preset/{name}` (Task 3.12)
- [ ] D 탭 — 슬라이더 펼침 + `/api/weights` (Task 3.13)
- [ ] D 탭 — 저장된 검색 리스트 + CRUD (Task 3.14)
- [ ] D 탭 — 통일성/페널티 요약 + 상세 모달 (Task 3.15)
- [ ] 반응형 (≤768px 사이드 자동 닫힘) (Task 3.16)
- [ ] `pytest tests/test_web_routers_filters.py tests/test_web_routers_saved_searches.py tests/test_web_routers_feedback.py -v` → 20 passed

### D. 회귀 + 수동 시각 검증 + 커밋들

- [ ] `pytest -q` → ~560 passed
- [ ] 수동 시각 검증 — 4 페인 (정보 과부하 / 좌우 스크롤 / 섹션 불명 / 가중치 불가해) 해소
- [ ] 커밋들 (task 별 18개)

---

## Phase 4 — Claude `request_user_pick` + SSE push (~1주)

### A. 스캐폴딩

- [ ] `routers/picks.py` 와 `routers/sse.py` 의 빈 스텁 (이미 Phase 1 Task 1.4 에서 등록)
- [ ] MCP integration 마크 의 환경 변수 — `web.port` 파일을 paths.data_dir 에 미리 작성하는 fixture

### B. red — Phase 4 테스트들 (~30 케이스)

- [ ] `tests/test_web_routers_picks.py` (12) — `/internal/user-pick` long-poll resolved/timeout/cancel/max_pending/`/api/user-pick/{rid}` 정상/409/`/cancel`/미존재/automatic record/project_id null/candidates 11 → 422 (Task 4.1, 4.2, 4.4)
- [ ] `tests/test_web_routers_sse.py` (6) — text/event-stream/heartbeat/user_pick_request/analysis_progress/다수 클라이언트/연결 종료 (Task 4.3)
- [ ] `tests/test_mcp_tools_m5.py` (10) — tool_request_user_pick 정상/web.port 부재 → 503/408 패스스루/499 패스스루/ConnectError → 503/자동 record/project_id null/candidates max=10/min=1/timeout range (Task 4.8)
- [ ] `pytest tests/test_web_routers_picks.py tests/test_web_routers_sse.py tests/test_mcp_tools_m5.py -v` → 28 FAIL

### C. green — Phase 4 모듈 + 템플릿

(plan §4.4 task 순서)

- [ ] `routers/picks.py` — `/internal/user-pick` 구현 + SSE broadcast (Task 4.1)
- [ ] `routers/picks.py` — `/api/user-pick/{rid}` + `/cancel` (Task 4.2)
- [ ] `routers/sse.py` — `/sse/notifications` EventSourceResponse (Task 4.3)
- [ ] `routers/picks.py` — `/ui/pick-card/{rid}` + `_pick_card.html` (Task 4.4)
- [ ] `base.html` + `app.js` — SSE 클라이언트 + Alpine pickQueue (Task 4.5)
- [ ] `_nav.html` — 헤더 배지 (Task 4.6)
- [ ] `mcp/models.py` — `RequestUserPickRequest` + `RequestUserPickResult` (Task 4.7)
- [ ] `mcp/server.py` — `request_user_pick` 도구 등록 (16 → 17) (Task 4.7)
- [ ] `mcp/tools.py` — `tool_request_user_pick` HTTP loopback + 자동 record_asset_use (Task 4.8)
- [ ] `mcp/server.py` `run_stdio` — paths 전파 (Task 4.9)
- [ ] `web/app.py` + `tray.py` 의 bridge — 트레이 깜빡임 (Task 4.10)
- [ ] `tests/test_mcp_integration.py` 갱신 — 16 → 17 도구 (Task 4.11)
- [ ] `pytest tests/test_web_routers_picks.py tests/test_web_routers_sse.py tests/test_mcp_tools_m5.py -v` → 28 passed

### D. 회귀 + e2e 수동 + 커밋들

- [ ] `pytest -q` → ~590 passed
- [ ] `pytest -m mcp_integration -v` → 2 passed (17 도구)
- [ ] **End-to-end 수동 검증** — Claude Code 에서 `request_user_pick({candidates:[142,158,203], reason:"test", project_id:"D:/Unity/MyGame"})` → 브라우저 카드 → 채택 → Claude 응답 + 자동 record_asset_use 확인 (Task 4.13)
- [ ] 타임아웃 시나리오 수동 검증
- [ ] 거부 시나리오 수동 검증
- [ ] `docs/MCP_USAGE_GUIDE.md` 갱신 (Task 4.12)
- [ ] 커밋들 (task 별 13개)

---

## Phase 5 — Qt 위젯 폐기 + Pack/라벨 관리 웹 이식 (~0.5주)

### A. 스캐폴딩

- [ ] `routers/packs.py` 와 `routers/labels_admin.py` 빈 스텁 (Phase 1 에서 이미 등록)

### B. red — Phase 5 테스트들

- [ ] `tests/test_web_routers_packs.py` (7) — GET/HTML/PATCH enable/manual_override/미존재/카운트/kind 분포 (Task 5.1)
- [ ] `tests/test_web_routers_labels_admin.py` (9) — CRUD + import/export + signature SSE + HTML + 사용중 400 + 잘못된 axis (Task 5.3)
- [ ] `pytest tests/test_web_routers_packs.py tests/test_web_routers_labels_admin.py -v` → 16 FAIL

### C. green — Phase 5 모듈 + 템플릿 + 폐기

- [ ] `routers/packs.py` 구현 → 7 passed (Task 5.1)
- [ ] `templates/packs.html` + `_pack_card.html` (Task 5.2)
- [ ] `routers/labels_admin.py` 구현 → 9 passed (Task 5.3)
- [ ] `templates/labels_admin.html` (Task 5.4)
- [ ] **Qt UI 파일 7 + 테스트 4 파일 삭제** (Task 5.5):
  - `src/gah/ui/library_view.py`
  - `src/gah/ui/label_chip_panel.py`
  - `src/gah/ui/search_side_panel.py`
  - `src/gah/ui/filter_bar.py`
  - `src/gah/ui/main_window.py`
  - `src/gah/ui/pack_view.py`
  - `src/gah/ui/labels_admin.py`
  - `tests/test_library_search_ui.py`
  - `tests/test_library_search_ui_rich.py`
  - `tests/test_ui_smoke.py`
  - `tests/test_labels_admin_ui.py`
- [ ] Grep 으로 `from gah.ui` / `import.*main_window` 잔존 references 0 확인
- [ ] 상단 네비 + 페이지 라우트 (`/library`, `/packs`, `/labels/admin`) 통합 (Task 5.6)
- [ ] 트레이 메뉴 갱신 (Task 5.7) — 라벨 관리 항목 제거

### D. 회귀 + 커밋들

- [ ] `pytest -q` → ~580 passed + 0 skipped (Qt skip 마크 해제됨, 파일 삭제로 흡수)
- [ ] `pytest -m mcp_integration -v` → 2 passed (17 도구)
- [ ] 커밋들:
  - `feat(m5): Pack 페이지 백엔드 + 템플릿`
  - `feat(m5): 라벨 관리 페이지 백엔드 + 템플릿`
  - `feat(m5): Qt UI 위젯 7 파일 + 테스트 4 파일 폐기 (웹 UI 가 모두 대체)`
  - `feat(m5): 상단 네비게이션 + 4 페이지 라우트`
  - `chore(m5): 트레이 메뉴 — 라벨 관리 항목 제거`

---

## Phase 6 — 마감 + 검증 (~0.5주)

### D. 마감 + 검증 + 인계

- [ ] 다크/라이트 CSS 변수 + prefers-color-scheme (Task 6.1)
- [ ] 에러 페이지 404/500 (Task 6.2)
- [ ] `docs/WEB_UI_GUIDE.md` 작성 (Task 6.3, 한국어)
- [ ] `DESIGN.md` §3/§4.5/§4.8/§11 갱신 (Task 6.4)
- [ ] `README.md` 사용법 갱신 (Task 6.5)
- [ ] `CLAUDE.md` §2 진행 현황 + §8 다음 작업 (M6) 갱신 (Task 6.6)
- [ ] `HANDOFF.md` M5 완료 인계 (Task 6.7)
- [ ] `milestones/M5_verification.md` 작성 — 자동 + mcp_integration + 17 수동 체크리스트 (Task 6.8)
- [ ] 메모리 갱신 — `project_m5_web_gui_decision.md` "완료" 마크 + `project_m5_pending_pick_pattern.md` (선택, 신규) (Task 6.9)
- [ ] **사용자 수동 검증 17 단계 통과**
- [ ] PR 생성 — `gh pr create --title "M5 웹 GUI 전환 + Claude pick"` (한국어 본문, M5 spec 링크 + 시나리오 4개 + 검증 결과) (Task 6.10)

---

## E. M6 인계

M5 완료 시점에 다음 인계 작업 수행:

- [ ] M5 PR 머지 (사용자 검토 후)
- [ ] `feat/m5-web-gui` 브랜치 삭제
- [ ] `main` 으로 체크아웃 후 다음 마일스톤 (M6 시트 분석) 진입 준비
- [ ] `HANDOFF.md` 의 §5 "다음 세션 진입 절차" 가 M6 spec 작성으로 갱신
