# M5 — 웹 GUI 전환 + 라이브러리 리디자인 + Claude pick 인터랙션 (구현 계획)

> **에이전트 작업자에게**: REQUIRED SUB-SKILL: `superpowers:subagent-driven-development` (권장) 또는 `superpowers:executing-plans` 로 task 단위 구현. Step 은 `- [ ]` 체크박스로 추적. 본 plan 은 [`M4_plan.md`](./M4_plan.md) 와 같은 한국어 마일스톤 표준 형식이며, [`docs/superpowers/specs/2026-05-17-m5-web-gui-and-library-redesign.md`](../docs/superpowers/specs/2026-05-17-m5-web-gui-and-library-redesign.md) (이하 "M5 spec") 의 10 결정 + 13 섹션을 작업 단위까지 1:1 로 옮긴 것이다. spec §13 의 5 개 열린 질문은 본 plan §3 에서 확정한다.

**목표** — Qt 데스크톱 UI 를 폐기하고 FastAPI + HTMX + Alpine.js 로컬 웹 GUI 로 전환. 라이브러리 페이지를 옵션 C 레이아웃 (상단 자연어 검색 + ⚙ 고급 토글 + 우측 슬라이드 B/C/D) 으로 리디자인. 신규 MCP `request_user_pick` 으로 Claude 가 후보 자산 중 사용자가 직접 고르도록 요청하고 동기 long-poll (5분) 로 응답을 받음.

**아키텍처** — 트레이 Qt 프로세스가 부팅 시 `uvicorn.Server` 를 별도 스레드(또는 `asyncio` 이벤트루프)에서 시작 → 트레이 메뉴 "메인 창 열기" → `webbrowser.open("http://127.0.0.1:9874")` → 시스템 브라우저로 사용자 진입. MCP server 는 그대로 별도 프로세스로 두고, `request_user_pick` 만 HTTP loopback (`POST http://127.0.0.1:9874/internal/user-pick`) 으로 트레이 측 FastAPI 의 in-process pending-pick 큐에 등록 + long-poll 응답 대기. M4 백엔드 (Store / HybridSearcher / ConsistencyScorer / UsageTracker / LabelRegistry / label_query / thumbnails / suggest_packs / mcp 16 도구) 100% 보존.

**기술 스택** — Python 측 `fastapi>=0.110` / `uvicorn[standard]>=0.27` / `jinja2>=3.1` / `python-multipart>=0.0.9` / `sse-starlette>=2` (FastAPI SSE). 프런트엔드는 HTMX 1.9 + Alpine.js 3 (vendoring, ~30KB). Qt PySide6 는 트레이 백그라운드 + 분석 큐만 유지. 빌드 도구 없음 (TypeScript / webpack / vite 도입 안 함).

---

## 1. 목표 (시나리오)

M5 가 끝나면 다음 네 시나리오가 정상 동작한다.

### 1.1 시스템 브라우저로 GAH 진입

사용자가 GAH 트레이 아이콘을 더블 클릭 또는 메뉴 "메인 창 열기" → 시스템 기본 브라우저가 `http://127.0.0.1:9874` 진입 → 라이브러리 페이지 (디폴트). 페이지는 상단 자연어 검색 바 + ⚙ 고급 + 결과 영역 (와이드 카드 그리드, 라이브러리 전체 추가일↓) + 우측 사이드 패널 (⚙ 클릭 시 슬라이드 인). 사이드 패널은 B (정밀 필터) / C (표시 옵션) / D (고급 조정) 3 탭. 다크 모드는 OS prefers-color-scheme 자동 적용.

### 1.2 자연어 + 칩 + 슬라이더로 풍부 검색

검색 바에 `어두운 BGM 짧은 거` 입력 → 300ms 디바운스 후 HTMX 가 `POST /ui/search-results` 호출 → 결과 영역 부분 갱신. 우측 ⚙ 클릭 → B 탭 펼침 → `dark` 칩 선택 → 결과 갱신. C 탭 → 리스트 뷰 토글 + 카드 크기 L. D 탭 → 프리셋 "통일성 우선" 클릭 → 6 슬라이더 + Config 동시 갱신 → 결과 재검색 → 같은 프로젝트에서 채택한 팩이 상위로. 저장된 검색 목록에 "전투 BGM 다크" 클릭 → 검색 바 + 필터 + 슬라이더 모두 복원.

### 1.3 Claude → 사용자 선택 (`request_user_pick`)

Claude Code 가 MCP 도구 `request_user_pick` 호출:

```jsonc
{
  "candidates": [142, 158, 203, 311, 425],
  "reason": "전투 BGM 다크한 거 5개 후보 — 사용자가 골라줘",
  "project_id": "D:/Unity/MyGame",
  "timeout_seconds": 300
}
```

→ MCP server (별도 프로세스) 가 `POST http://127.0.0.1:9874/internal/user-pick` 으로 트레이 측 FastAPI 의 pending-pick 큐에 등록 + `asyncio.Future` 대기. FastAPI 가 SSE 로 활성 브라우저 탭에 `user_pick_request` 이벤트 push → 라이브러리 페이지 상단에 "🤖 Claude 요청" 카드 배지 + 결과 영역에 5 후보 카드 (보라색 좌측 띠). 사용자가 158 카드 클릭 + [채택] 버튼 → `POST /api/user-pick/{rid}` → Future.set_result → MCP server 가 long-poll 응답 받음 → 자동 `record_asset_use(project_id, 158, source='claude_pick', context=reason)` → Claude 에 응답:

```jsonc
{
  "picked_asset_id": 158,
  "picked_at": 1747500900,
  "user_note": null
}
```

5분 안에 응답 없으면 `408_timeout`, 사용자 [✕ 거부] 누르면 `499_user_cancelled`.

### 1.4 Qt 위젯 폐기 + Pack/라벨 관리 웹 이식

M4 의 Qt 위젯 4개 + main_window.py + pack_view.py + labels_admin.py + 테스트 2 파일이 모두 삭제. Pack 페이지 (`/packs`) 가 팩 리스트 + enable/disable 토글 + 자산 수 + 매니페스트 요약 노출. 라벨 관리 페이지 (`/labels/admin`) 가 24 axis 별 라벨 추가/편집/삭제 + import/export JSON. 상단 네비게이션 (`라이브러리 / 팩 / 라벨 관리`) 으로 페이지 전환.

세부:

- **FastAPI 부팅** — 트레이 Qt main thread 의 옆에서 `uvicorn.Server.serve()` 가 별도 스레드 + 별도 asyncio 이벤트루프로 실행. graceful shutdown 은 트레이 종료 시 `server.should_exit=True` 후 `thread.join(timeout=5)`.
- **포트 폴백** — `Config.web_port` (기본 9874) 가 점유 중이면 9875..9884 순차 시도. MCP server (별도 프로세스) 는 같은 `Config.web_port` 를 읽어 loopback 대상 URL 을 결정 (포트 충돌 시 양쪽이 같은 폴백 결과를 봐야 하므로 실 사용 포트를 `paths.data_dir / "web.port"` 파일에 atomic write + MCP server 가 그 파일 읽음).
- **SSE 채널** — `/sse/notifications` 1 엔드포인트 통합. 이벤트 타입 = `user_pick_request` / `user_pick_resolved` (다른 탭 자동 갱신용) / `analysis_progress` (M2/M2.1 의 `queue.progressChanged` 가 발화) / `pack_changed` (워처 이벤트).
- **자동 `record_asset_use`** — Claude pick 응답 후 GAH 가 자동 호출 (source 신규 enum `'claude_pick'`). Claude 가 따로 호출 안 해도 통일성 학습이 진행.
- **i18n 준비** — M5 의 모든 사용자 노출 문자열은 `_t("한국어 텍스트")` placeholder 함수로 감싸 둠 (반환값 = 인자 그대로). M8 에서 본격 i18n 백엔드 도입 시 일괄 치환.
- **다크 모드** — CSS 변수 (`--bg`, `--fg`, `--accent`, `--border`) 만으로 light/dark 둘 다 지원. `@media (prefers-color-scheme: dark)` 자동. v1 은 OS 따라가기만, 사용자 토글은 M8.

## 2. 산출물

### 2.1 코드 모듈

| 파일/디렉터리 | 책임 | 상태 |
|---|---|---|
| `src/gah/config.py` (수정) | M5 신규 필드 — `web_host: str = "127.0.0.1"`, `web_port: int = 9874`, `web_port_max_attempts: int = 10`, `claude_pick_timeout_seconds: int = 300`, `claude_pick_max_pending: int = 20`, `web_open_browser_on_start: bool = True`, `web_log_requests: bool = False`. 신규 enum `UsageSource` (`'manual'`/`'mcp'`/`'claude_pick'`) — M3 의 `record_asset_use` 의 자동 추적 source 필드를 enum 으로 격상. | 수정 |
| `src/gah/core/store.py` (수정) | `record_asset_use` 의 source 인자가 enum (또는 str validator) 로 격상 — `'claude_pick'` 신규 허용. `asset_uses` 테이블에 `source` 컬럼이 이미 있으므로 스키마 변경 없음. `usage_summary_for_project(project_id) -> dict` 신규 — 통일성/페널티 요약 모달용 (채택 팩 top-3 + 거부 자산 수 + 윈도우 내). | 수정 |
| `src/gah/web/__init__.py` | 빈 패키지 마커. | 신규 |
| `src/gah/web/server.py` | `WebServer` 클래스 — `start()` / `stop()`. 내부에서 `uvicorn.Config` + `uvicorn.Server` 를 자기 asyncio 이벤트루프로 별도 스레드 실행. 포트 폴백 로직 (`_find_available_port`). 실 사용 포트를 `paths.data_dir / "web.port"` 파일에 atomic write. 종료 시 `server.should_exit=True` + `thread.join(timeout=5)`. | 신규 |
| `src/gah/web/app.py` | FastAPI app factory — `build_app(deps: WebDeps) -> FastAPI`. lifespan = pending-pick 큐 cleanup 잡 시작/정지. 라우터 등록 (api/ui/sse/internal/static). 글로벌 dependency = `WebDeps` (store/searcher/usage/registry/queue/config/paths). | 신규 |
| `src/gah/web/deps.py` | `WebDeps` 데이터클래스 (frozen) — store/searcher/usage/registry/queue/config/paths + `pending_picks: PendingPickQueue`. FastAPI `Depends` 로 라우터에 주입. | 신규 |
| `src/gah/web/pending.py` | `PendingPickQueue` — `dict[str, PendingPick]` + lock. `PendingPick(request_id, candidates, reason, project_id, created_at, future: asyncio.Future, status)`. 메서드 `register(req) -> PendingPick`, `resolve(rid, picked_asset_id, user_note) -> bool`, `cancel(rid, reason) -> bool`, `expire(rid) -> bool`, `snapshot() -> list[dict]`, `cleanup_expired(now, ttl) -> int`. | 신규 |
| `src/gah/web/routers/library.py` | `/api/search` POST (JSON 응답) + `/ui/search-results` POST (HTML fragment, HTMX target). `/api/library` GET (디폴트 — 검색 없음 시 추가일↓ 페이지네이션). `/api/thumbnail/{asset_id}` GET (lazy 256×256 PNG). `/ui/asset-detail/{id}` GET (HTML 모달 fragment). `/api/audio/{asset_id}` GET (사운드 stream — Range 헤더 지원). | 신규 |
| `src/gah/web/routers/filters.py` | `/api/filters/labels` GET (axis 별 라벨 카탈로그 + 매칭 카운트). `/ui/chip-panel` GET (B 탭 칩 HTML fragment, axis 분류 sprite/sheet/sound). `/api/filters/packs` GET (pack 다축 필터용 catalog). | 신규 |
| `src/gah/web/routers/saved_searches.py` | `/api/saved-searches` GET/POST, `/api/saved-searches/{id}` DELETE, `/api/saved-searches/run/{id}` POST. 모두 기존 store 메서드 호출 위임. | 신규 |
| `src/gah/web/routers/feedback.py` | `/api/feedback` POST — query_id + asset_id + reason. UsageTracker / Store 위임. | 신규 |
| `src/gah/web/routers/packs.py` | `/api/packs` GET, `/ui/packs` GET (HTML 페이지), `/api/packs/{pack_id}` PATCH (enable/disable/manual_override). | 신규 |
| `src/gah/web/routers/labels_admin.py` | `/api/labels` GET (전체 카탈로그), `/api/labels` POST (신규 라벨 추가), `/api/labels/{label_id}` PATCH/DELETE, `/ui/labels/admin` GET (HTML 페이지), `/api/labels/import` POST, `/api/labels/export` GET. | 신규 |
| `src/gah/web/routers/picks.py` | `/internal/user-pick` POST (MCP loopback 진입점 — long-poll). `/api/user-pick/{rid}` POST (사용자 응답 — picked_asset_id + user_note). `/api/user-pick/{rid}/cancel` POST (사용자 거부). `/ui/pick-card/{rid}` GET (HTML fragment for SSE 또는 초기 로드). `/internal/user-pick/snapshot` GET (트레이 측 상태 디버그용). | 신규 |
| `src/gah/web/routers/sse.py` | `/sse/notifications` GET — `EventSourceResponse` (sse-starlette). 이벤트 타입 union `user_pick_request` / `user_pick_resolved` / `analysis_progress` / `pack_changed`. heartbeat 15초. | 신규 |
| `src/gah/web/routers/health.py` | `/api/health` GET — `{status, uptime, version, port, mcp_tools_count, pending_picks}`. MCP server 가 부팅 직후 호출해 트레이 가용 여부 검증. | 신규 |
| `src/gah/web/templates/base.html` | Jinja2 베이스 레이아웃 — `<html>`, head (csrf token 자리, htmx + alpine 로드, 자체 CSS), header (네비 + 알림 배지), main block, footer (분석 큐 진행 미니바). | 신규 |
| `src/gah/web/templates/library.html` | 라이브러리 페이지 — 상단 검색 바 + ⚙ 토글 + 결과 영역 (그리드/리스트) + 우측 사이드 패널 (B/C/D 탭). Alpine `x-data` 컴포넌트 1개 (`libraryPage`). | 신규 |
| `src/gah/web/templates/_card_wide.html` | 와이드 카드 partial — 썸네일 60×60 좌 + 텍스트 우 + 메타 (라벨 칩, 팩 이름, 크기, 점수). 사운드 → 🔊 아이콘 + ▶ 재생 버튼. 스프라이트시트 → `🎞 N frames` 배지 (M6 추가 후 활성). | 신규 |
| `src/gah/web/templates/_card_list.html` | 리스트 뷰 partial — 카드 풀폭, 메타 더 많이. | 신규 |
| `src/gah/web/templates/_pick_card.html` | Claude 요청 카드 — 보라색 좌측 띠 + 🤖 배지 + 후보 5 자산 + [채택] / [✕ 거부]. | 신규 |
| `src/gah/web/templates/_side_panel_b.html` | B 탭 (정밀 필터) — AND/OR/NOT 라디오 + 라벨 검색 input + 종류 탭 (sprite/sheet/sound) + axis 칩 (FlowLayout CSS) + 다축 필터 드롭다운 4개. | 신규 |
| `src/gah/web/templates/_side_panel_c.html` | C 탭 (표시 옵션) — 그리드/리스트 / 카드 크기 S/M/L / 정렬 / 카드 메타 토글. Alpine 양방향 바인딩. | 신규 |
| `src/gah/web/templates/_side_panel_d.html` | D 탭 (고급 조정) — 프리셋 3 버튼 + 슬라이더 펼침 + 저장된 검색 리스트 + 통일성/페널티 요약 + "상세 보기" 모달 트리거. | 신규 |
| `src/gah/web/templates/packs.html` | Pack 페이지 — 팩 카드 그리드 + enable/disable 토글 + 자산 수 + 매니페스트 요약. | 신규 |
| `src/gah/web/templates/labels_admin.html` | 라벨 관리 페이지 — 24 axis 탭 + 라벨 추가/편집/삭제 + import/export. | 신규 |
| `src/gah/web/templates/asset_detail.html` | 자산 상세 모달 — 큰 썸네일 + 라벨 전체 + 메타 + 채택 버튼 + 거부 버튼 + Gemma description (있을 때만). | 신규 |
| `src/gah/web/templates/_modal_usage.html` | 통일성/페널티 상세 모달 — 채택 팩 top-N + 거부 자산 리스트 + 윈도우 내 카운트. | 신규 |
| `src/gah/web/templates/_nav.html` | 상단 네비 + 알림 배지 (`🤖 Claude 요청 N`) — 모든 페이지 공통. | 신규 |
| `src/gah/web/static/css/main.css` | 자체 CSS — CSS 변수 (light/dark), grid/list 레이아웃, 카드, 사이드 패널 슬라이드, 칩 wrap (flex-wrap). 모바일 미디어 쿼리 (≤768px 사이드 자동 닫힘). | 신규 |
| `src/gah/web/static/css/themes.css` | CSS 변수 정의 (`--bg`, `--fg`, `--accent`, `--border`, `--card-bg`, `--chip-bg`, `--chip-active`, `--purple-strip`) + `@media (prefers-color-scheme: dark)`. | 신규 |
| `src/gah/web/static/vendor/htmx.min.js` | HTMX 1.9 vendoring (CDN 의존 없음). | 신규 |
| `src/gah/web/static/vendor/htmx-sse.min.js` | HTMX SSE extension. | 신규 |
| `src/gah/web/static/vendor/alpine.min.js` | Alpine.js 3 vendoring. | 신규 |
| `src/gah/web/static/js/app.js` | 자체 JS — Alpine 글로벌 stores (`pickQueue`, `notifications`), HTMX 이벤트 핸들러, 사이드 패널 리사이즈 (mouse drag). | 신규 |
| `src/gah/web/i18n.py` | `_t(text: str) -> str` placeholder (M8 까지 그대로 반환). Jinja2 환경에 `_` 글로벌로 등록. | 신규 |
| `src/gah/mcp/models.py` (수정) | 신규 모델 — `RequestUserPickRequest(candidates: list[int] min=1 max=10, reason: str|None, project_id: str|None, timeout_seconds: int default 300 ge=10 le=1800)` + `RequestUserPickResult(picked_asset_id: int, picked_at: int, user_note: str|None)`. 에러 코드 enum 확장 (`'408_timeout'`, `'499_user_cancelled'`, `'503_no_ui_available'`). | 수정 |
| `src/gah/mcp/tools.py` (수정) | 신규 함수 `tool_request_user_pick(deps, req) -> RequestUserPickResult` — `httpx.Client.post(f"{web_url}/internal/user-pick", json=...)` + 5분 timeout. 503 (서버 다운) 시 `503_no_ui_available` 응답. 408 (FastAPI 측 timeout) / 499 (사용자 거부) 패스스루. 응답 200 시 자동으로 `tool_record_asset_use` 도 호출 (source='claude_pick'). | 수정 |
| `src/gah/mcp/server.py` (수정) | `register_all_tools` 에 `request_user_pick` 추가 (16 → **17** 도구). `INSTRUCTIONS` 갱신 — 흐름 §13.1 에 7번째 단계 "Claude pick: when uncertain among ~5 candidates, call request_user_pick instead of picking automatically; GAH will show the user a wide-card chooser and return the picked id within 5 minutes". `run_stdio()` 가 `paths.data_dir / "web.port"` 를 읽어 `web_url` 결정. 파일이 없거나 stale 시 `request_user_pick` 호출만 503 + 다른 도구는 정상 (별도 프로세스라 가능). | 수정 |
| `src/gah/web/url.py` | `read_web_port(paths) -> int | None` + `write_web_port(paths, port)`. atomic write (`port.tmp` → rename). MCP server 와 트레이 양쪽이 사용. | 신규 |
| `src/gah/tray.py` (수정) | `on_open_main` 콜백을 `lambda: webbrowser.open(web_url)` 로 변경 (run_tray 가 web_url 주입). `on_open_labels` 메뉴 항목 폐기 (라벨 관리는 웹 페이지 `/labels/admin`). `notify_user_pick_request(count)` 새 함수 — Qt thread-safe signal 로 트레이 아이콘 깜빡임. | 수정 |
| `src/gah/app.py` (수정) | `run_tray` — main_window 의존성 제거. WebServer 시작 + URL 결정 + 트레이 wiring. `queue.progressChanged` 가 `WebServer` 의 broadcast 큐로도 push (SSE 갱신). `queue.analysisFinished` 도. 종료 시 WebServer.stop() + queue.stop() + watcher.stop(). | 대대적 수정 |
| `src/gah/ui/__init__.py` (수정) | 빈 패키지 마커로 축소 (M4 의 import 들 모두 제거). | 수정 |
| `src/gah/ui/library_view.py` | **삭제** — 웹 UI 가 대체 | 삭제 |
| `src/gah/ui/label_chip_panel.py` | **삭제** | 삭제 |
| `src/gah/ui/search_side_panel.py` | **삭제** | 삭제 |
| `src/gah/ui/filter_bar.py` | **삭제** | 삭제 |
| `src/gah/ui/labels_admin.py` | **삭제** (라벨 관리 다이얼로그 — M2 신규) | 삭제 |
| `src/gah/ui/main_window.py` | **삭제** (QMainWindow + 탭) | 삭제 |
| `src/gah/ui/pack_view.py` | **삭제** | 삭제 |
| `tests/test_library_search_ui.py` | **삭제** (M3 검색 박스 디바운스) | 삭제 |
| `tests/test_library_search_ui_rich.py` | **삭제** (M4 풍부 UX 14 케이스) | 삭제 |
| `tests/test_ui_smoke.py` | **삭제** (M1 메인 윈도우 smoke) | 삭제 |
| `tests/test_labels_admin_ui.py` | **삭제** (M2 라벨 관리 다이얼로그) | 삭제 |
| `tests/test_main_window_progress.py` | **삭제** (M2 메인 윈도우 progress) — 만약 존재. (확인 후 결정) | 삭제 (조건부) |
| `docs/MCP_USAGE_GUIDE.md` (수정) | §1 신규 17번째 도구 `request_user_pick` 추가 (요청/응답 JSON 예시 + timeout/거부 시나리오). §6 신규 — Claude 의 의사 결정 흐름 (자동 pick vs `request_user_pick` 분기 기준). 16 → 17 도구. | 수정 |
| `docs/WEB_UI_GUIDE.md` | **신규** — 사용자용 웹 UI 가이드. 진입 방법 + 라이브러리 페이지 사용법 + B/C/D 탭 + 단축키 + 다크 모드. 한국어. | 신규 |
| `DESIGN.md` (수정) | §3 아키텍처 그림 갱신 (Qt → FastAPI + 브라우저 + MCP loopback). §4.5 MCP 도구 표 — 17번째 추가. §4.8 트레이 GUI → "트레이 + 웹 UI" 로 제목 변경 + 본문 갱신. §5 SQL 스키마 변경 없음 (asset_uses.source 컬럼 재사용). §11 M5 항목 갱신 (실제로 한 일 정리). | 수정 |
| `README.md` (수정) | "사용법" 섹션 — 트레이 메뉴 "메인 창 열기" → 브라우저로 변경 안내. 스크린샷 placeholder. | 수정 |
| `CLAUDE.md` (수정) | §2 진행 현황 표 — M5 행 (대기 → 진행 → 완료). §3 사용자 환경 — 브라우저 요구사항 (Chrome/Firefox/Edge 최신). §8 "다음 작업" 갱신. | 수정 (M5 끝에) |
| `HANDOFF.md` (수정) | M5 완료 인계 — 자동 테스트 통과 카운트 + 4 시나리오 + 다음 작업 (M6 시트 분석). | 수정 (M5 끝에) |
| `pyproject.toml` (수정) | M5 신규 의존성 5 개. | 수정 |
| `milestones/M5_todo.md` | TDD 체크리스트 (본 plan §4 의 task 1:1 매핑). | 신규 |
| `milestones/M5_verification.md` | M5 끝에 작성. 자동 `pytest -v` 결과 + 수동 검증 체크리스트 + 알려진 한계. | 신규 |

### 2.2 테스트

| 파일 | 케이스 수 | 핵심 검증 |
|---|---:|---|
| `tests/test_config_m5.py` | ~7 | `web_host="127.0.0.1"` 기본 / `web_port=9874` / `web_port_max_attempts=10` / `claude_pick_timeout_seconds=300` / `web_open_browser_on_start=True` / TOML 왕복 / `UsageSource` enum (`manual`/`mcp`/`claude_pick`) 만 허용 |
| `tests/test_web_url.py` | ~5 | `write_web_port(paths, 9874)` → 파일 존재 + 내용 `"9874\n"` / `read_web_port` 정상 / 파일 부재 시 None / atomic (tmp 파일 잔존 X) / 잘못된 내용 시 None + 로그 |
| `tests/test_web_server.py` | ~6 | `WebServer.start()` 가 별도 스레드에서 uvicorn 시작 / `/api/health` 200 응답 / 포트 점유 시 다음 포트 폴백 / `web.port` 파일에 실 포트 write / `stop()` 후 thread.is_alive() False / max_attempts 초과 시 RuntimeError |
| `tests/test_web_app.py` | ~8 | `build_app(deps)` 가 FastAPI 인스턴스 반환 / lifespan 시작/정지 / 라우터 12 등록 / `/api/health` (mcp_tools_count=17) / 정적 자원 `/static/vendor/htmx.min.js` 200 / `/static/css/main.css` 200 / 디폴트 캐시 헤더 / 404 핸들러 |
| `tests/test_web_pending.py` | ~10 | `PendingPickQueue.register(req)` → request_id (uuid4) + 신규 PendingPick / `resolve(rid, picked)` → future.set_result + status='resolved' / 미존재 rid → False / `cancel(rid)` → future.set_exception(`UserCancelledError`) / 이미 resolved 후 resolve → False / TTL 초과 후 `cleanup_expired` → status='expired' + future.cancel / 동시 register 20 까지 OK / 21번째 → `MaxPendingExceeded` / `snapshot()` 정렬 (LIFO 최신순) / lock 동시성 |
| `tests/test_web_routers_library.py` | ~14 | `/api/search` POST query='blue hero' → HybridSearcher 결과 JSON / `/ui/search-results` POST → HTML fragment with 카드들 / `/api/library?limit=50` → 추가일↓ 50개 / `/api/thumbnail/{id}` sprite → 200 PNG + ETag / sound → 404 / `/api/audio/{id}` Range 헤더 지원 / 디폴트 (query 비어 + 필터 0) → 추가일↓ / `label_query` 통합 (검색 바 텍스트 → label_query) / 정렬 추가일↑/이름↑/크기↓ / `/ui/asset-detail/{id}` HTML 모달 / 페이지네이션 (offset/limit) / 잘못된 id → 404 / pack_id 필터 / kind 필터 |
| `tests/test_web_routers_filters.py` | ~7 | `/api/filters/labels` 24 axis 카탈로그 + 매칭 카운트 / `/ui/chip-panel` HTML fragment (axis 분류 sprite/sheet/sound 분리) / axis 분류 prefix 매칭 (`sound_*` / `sheet_*` / 나머지) / 칩 활성/비활성 클래스 / 라벨 검색 substring 매칭 / `/api/filters/packs` 카탈로그 + 자산 수 / 빈 카탈로그 처리 |
| `tests/test_web_routers_saved_searches.py` | ~8 | `/api/saved-searches` POST 정상 + UNIQUE 중복 400 / GET (project_id 별 + global) / DELETE 정상 + 미존재 404 / `run/{id}` POST → find_asset 결과 / last_used 갱신 / 미존재 id 404 / query_json 직렬화 왕복 / project_id null (global) |
| `tests/test_web_routers_feedback.py` | ~5 | `/api/feedback` POST positive → store insert + 200 / negative + asset 펜덤 / unknown reason → 400 / query_id 미존재 → 400 / 같은 자산 중복 → 누적 |
| `tests/test_web_routers_packs.py` | ~7 | `/api/packs` GET → 팩 리스트 + 자산 수 / `/ui/packs` HTML / `/api/packs/{id}` PATCH enable=False → store 갱신 / manual_override / 미존재 id 404 / 카운트 정확 / kind 분포 |
| `tests/test_web_routers_labels_admin.py` | ~9 | `/api/labels` GET 전체 / POST 신규 라벨 + axis 검증 / PATCH description 수정 / DELETE 정상 + 사용 중 → 400 / `/api/labels/import` JSON → bulk insert + signature 변경 / `/api/labels/export` GET → JSON / `/ui/labels/admin` HTML / signature 변경 시 SSE notification / 잘못된 axis 400 |
| `tests/test_web_routers_picks.py` | ~12 | `/internal/user-pick` POST → request_id 발급 + 200 long-poll (mock future.set_result 후 응답) / 5분 timeout → 408 / 사용자 응답 → picked_asset_id + picked_at 정확 / `/api/user-pick/{rid}` 정상 → SSE `user_pick_resolved` push / `/api/user-pick/{rid}/cancel` → 499 / 미존재 rid → 404 / 이미 resolved 후 또 응답 → 409 / 동시 21 요청 → max_pending 503 / `/ui/pick-card/{rid}` HTML / 자동 record_asset_use 호출 검증 / project_id 누락 → record_asset_use 스킵 (warning) / candidates 11개 → 422 (max=10) |
| `tests/test_web_routers_sse.py` | ~6 | `/sse/notifications` GET → text/event-stream 200 / heartbeat 15초 이내 (mocked clock) / `user_pick_request` 이벤트 push / `analysis_progress` 이벤트 push / 연결 중단 시 graceful / 여러 클라이언트 동시 broadcast |
| `tests/test_mcp_tools_m5.py` | ~10 | `tool_request_user_pick` 정상 → httpx loopback POST + 200 응답 → RequestUserPickResult / web.port 파일 없음 → 503_no_ui_available / FastAPI 408 → 패스스루 / FastAPI 499 → 패스스루 / httpx ConnectError → 503 / 자동 `record_asset_use` 호출 (source='claude_pick') 검증 / project_id 없으면 record 스킵 + warning / candidates max 10 검증 (Pydantic) / candidates min 1 / timeout_seconds 10~1800 범위 |
| `tests/test_mcp_integration.py` (수정 — 옵트인 `mcp_integration` 마크) | 0 신규 (기존 2 갱신) | `tools/list` 응답 16 → 17 도구 (`request_user_pick` 포함). `initialize` 핸드셰이크 그대로. |
| `tests/test_tray_m5.py` | ~5 | `make_tray_icon(on_open_main=cb)` 더블 클릭 → `webbrowser.open(url)` 호출 / 메뉴 "메인 창 열기" 클릭 → 동일 / `notify_user_pick_request(count)` → 트레이 아이콘 깜빡임 시그널 발화 / `on_open_labels` 메뉴 항목 부재 (M5 가 제거) / 트레이 종료 → qapp.quit |
| `tests/test_app_m5.py` | ~6 | `run_tray` 가 main_window 의존성 없이 부팅 / WebServer 시작 후 `/api/health` 200 / `queue.progressChanged` 시그널 → SSE broadcast 호출 / 종료 시 WebServer.stop() 호출 / 포트 폴백 (9874 점유 → 9875) / `web_open_browser_on_start=True` 시 webbrowser.open 호출 |
| `tests/test_web_i18n.py` | ~3 | `_t("한국어")` → `"한국어"` (passthrough) / Jinja2 `{{ _("...") }}` 렌더링 / placeholder 호환 |

**합계 ~128 신규 active 케이스** + 옵트인 0 신규 (기존 2 갱신). 폐기되는 Qt UI 테스트 ~3 파일 (~120 케이스 추정 — `test_library_search_ui.py` ~7 / `test_library_search_ui_rich.py` ~17 / `test_ui_smoke.py` ~5 / `test_labels_admin_ui.py` ~5 / 기타 메인 윈도우 ~10 = ~44 케이스. 정확 카운트는 Phase 5 task 5.6 에서 측정 후 회귀 갱신).

폐기 후 합 = 452 (M0~M4) - ~44 (Qt UI 폐기) + 128 (M5 신규) = ~536 active. 정확 수는 verification 에서 확인.

## 3. 핵심 결정사항 (spec §13 의 5 개 열린 질문 + 신규 결정)

### 3.1 FastAPI vs subprocess (spec Q1)

**결정** — **같은 프로세스 + 별도 스레드** (`threading.Thread`).

- `WebServer.start()` 가 별도 스레드에서 새 asyncio 이벤트루프 생성 → `uvicorn.Config(app, host, port, loop="asyncio")` + `uvicorn.Server` 의 `serve()` 코루틴 실행. Qt main thread 의 이벤트루프와 충돌 X (각자 다른 thread/loop).
- 같은 프로세스라 in-process pending-pick 큐 공유 자연스러움. PySide6 import 가 글로벌이라 별도 스레드에서 Qt 시그널 발화 시 `QMetaObject.invokeMethod(... Qt.QueuedConnection)` 로 main thread 마샬링.
- 종료 = `server.should_exit=True` 후 `thread.join(timeout=5)`. graceful shutdown.
- 단점 — 임포트 시간 + 메모리. 트레이 부팅이 ~0.5 초 늘어남. PyInstaller 패키징은 단일 exe 라 단순 (M8).
- subprocess 대안은 stdin/stdout/HTTP 로 분리 — 격리는 좋지만 양 프로세스 관리 + 통신 복잡도 ↑. v1 은 같은 프로세스.

### 3.2 SSE vs WebSocket (spec Q2)

**결정** — **SSE (Server-Sent Events)**.

- GAH 는 server → client push 만 (양방향 X). SSE 가 단순 (HTTP keep-alive + 자동 재연결).
- HTMX SSE extension (`hx-ext="sse"` + `sse-connect="/sse/notifications"` + `sse-swap="user_pick_request"`) native 지원.
- 의존성 = `sse-starlette>=2` (FastAPI 친화). uvicorn 만으로는 부족.
- 이벤트 타입 — `user_pick_request` / `user_pick_resolved` / `analysis_progress` / `pack_changed` / `labels_signature_changed`. event field + data JSON.
- heartbeat 15초 (`event: ping`). 재연결은 HTMX 가 자동 + `Last-Event-ID` 사용 (서버는 무시 — idempotent push).
- 향후 양방향 필요 시 (e.g. 사용자 → 서버 typing indicator) WebSocket 추가. v1 은 SSE.

### 3.3 Pack/라벨 관리 폐기 시점 (spec Q3)

**결정** — **M5 안에서 모두 폐기 + 웹 이식**. Phase 5 (0.5주) 에 포함.

- M5 끝 시점에 PySide6 import 는 `src/gah/tray.py` + `src/gah/app.py` 의 트레이 부팅만 남음. UI 위젯 클래스 0개. `src/gah/ui/` 디렉터리는 빈 `__init__.py` 만 두거나 통째로 삭제.
- 분석 큐 진행률은 트레이 툴팁 (M2.1 그대로) + SSE broadcast (M5 신규) 둘 다 유지. 사용자가 브라우저 열어두면 SSE, 안 열어두면 트레이 툴팁만.
- 라벨 관리 페이지 = M2 의 `labels_admin.py` 다이얼로그를 `/labels/admin` 웹 페이지로. 24 axis 탭 + 라벨 CRUD + JSON import/export.
- Pack 페이지 = M1 의 `pack_view.py` 테이블을 `/packs` 웹 페이지로 (카드 그리드 + enable/disable 토글).

### 3.4 자동 `record_asset_use` (spec Q4)

**결정** — **자동 호출**. source='claude_pick' 으로 마킹.

- `tool_request_user_pick` 의 응답 200 직후 `tool_record_asset_use(asset_id=picked, project_id=req.project_id, source='claude_pick', context=req.reason)` 호출.
- `project_id` 가 null 이면 record 스킵 + warning log (통일성 학습 무관한 일회성 호출이라 그래도 OK).
- Claude 가 같은 자산을 별도로 `record_asset_use` 호출하면 idempotent — `asset_uses` 테이블에 두 행 (source 가 다름) 들어가지만 통일성 계산은 `LATEST_USES_PER_PROJECT` 윈도우 기반이라 영향 작음. 추가 dedup 은 M6+.
- source enum 확장 — `'manual'` (M3 신규 - UI 명시) / `'mcp'` (Claude 가 record_asset_use 명시 호출) / `'claude_pick'` (M5 신규 - request_user_pick 자동) / `'implicit_top1'` (M3 미사용 — Config OFF).

### 3.5 i18n 백엔드 (spec Q5)

**결정** — **v1 한국어 하드코딩 + `_t()` placeholder 만**. 본격 i18n 은 M8.

- `src/gah/web/i18n.py` 가 `_t(text: str) -> str` 함수 export. 현재 구현은 그대로 반환 (passthrough). Jinja2 환경에 `_` 글로벌로 등록 → 템플릿에서 `{{ _("자연어 검색…") }}` 가능.
- M5 의 모든 사용자 노출 문자열 — 템플릿은 `{{ _("...") }}`, Python 응답은 `_t("...")` 로 감싸 둠.
- M8 에서 babel + Jinja2-i18n 또는 단순 JSON 변환기 (`{lang: {key: text}}`) 도입 시 일괄 치환.

### 3.6 MCP server ↔ FastAPI 통신 (신규 결정)

**결정** — **HTTP loopback POST** (`http://127.0.0.1:9874/internal/user-pick`). MCP server (별도 프로세스) 가 long-poll 응답 대기.

- MCP server 는 stdio 라 포트 없음. 트레이 측 FastAPI 의 실 사용 포트를 `paths.data_dir / "web.port"` 파일로 공유. MCP server 가 `run_stdio()` 시작 시 한 번 읽음.
- `tool_request_user_pick` 가 `httpx.Client.post(url, timeout=timeout_seconds + 10)` 호출. FastAPI 측에서 future 가 resolve 될 때까지 응답 안 보냄 (long-poll). 응답 = picked_asset_id JSON 또는 408/499 에러.
- 트레이가 안 떠 있으면 (web.port 파일 없거나 stale, 또는 httpx ConnectError) → `503_no_ui_available` 응답. Claude 가 fallback 으로 자동 pick 또는 사용자에게 별도 채널 (텍스트) 로 물어봄.

### 3.7 포트 폴백 정책 (신규)

**결정** — `Config.web_port` (기본 9874) 가 점유 중이면 +1 씩 `web_port_max_attempts` (10) 회 시도. 성공 시 `paths.data_dir / "web.port"` 에 atomic write. 실패 시 RuntimeError + 트레이 메뉴에 "웹 UI 시작 실패" 표시 + 분석 큐는 계속 동작 (MCP server 도 stdio 만 사용한다면 계속 동작).

### 3.8 PendingPick TTL + 동시성 한도 (신규)

**결정** —

- TTL = `Config.claude_pick_timeout_seconds` (300, 즉 5분) + 60초 grace. 그 후 cleanup 잡이 자동 cancel + 큐에서 제거.
- 동시성 한도 = `Config.claude_pick_max_pending` (20). 초과 시 `503_too_many_pending` 응답 (MCP 측에서 `503_no_ui_available` 과 별도 코드).
- cleanup 잡 = FastAPI lifespan 에서 시작하는 백그라운드 코루틴, 5초 마다 expired 검사.

### 3.9 그 외 spec §12 미룬 항목 재확인

| 항목 | M5 처리 |
|---|---|
| 다크 모드 토글 UI | OS 따라가기만. 사용자 토글 X (M8) |
| 모바일 / 반응형 | ≤768px 사이드 패널 자동 닫힘만. 전반적 모바일 최적화 X (M7+) |
| 인증 / 멀티 사용자 | 단일 사용자, localhost 만. 토큰 X (M7+) |
| e2e 자동화 (Playwright) | 옵션 — 본 plan 에서 0 시나리오 (백엔드 + 단위만). M6+ |
| 풍부 Pack/라벨 관리 UX | 최소 이식만 (CRUD + 토글). M7 |
| 사용자 자리비움 감지 | 단순 5분 timeout 만 v1 |
| `request_user_pick` batch 모드 | 단일 선택만 v1 |

---

## 4. 작업 단위

작업은 phase 순서대로 진행하고, 각 phase 의 task 는 표시된 순서대로 (앞 task 가 뒤 task 의 빌딩 블록). 각 task 는 **테스트 먼저 → 구현 → 통과 → 커밋** 사이클을 지킨다. Step 은 `- [ ]` 체크박스로 추적 — `M5_todo.md` 가 같은 체크박스를 들고 있어 진행 상태 동기화 가능.

### 4.0 Phase 0 — 의존성 + Config + 정적 자원 (~0.5일)

#### Task 0.1 — pyproject.toml 신규 의존성 추가

**Files:** Modify `pyproject.toml`

- [ ] **Step 1**: `[project]` `dependencies` 에 5 줄 추가:

```toml
"fastapi>=0.110",
"uvicorn[standard]>=0.27",
"jinja2>=3.1",
"python-multipart>=0.0.9",
"sse-starlette>=2",
```

- [ ] **Step 2**: `pip install -e D:\ClaudeCowork\game-asset-helper\game-asset-helper[dev]` 실행 → 5 신규 패키지 + uvicorn[standard] 의 transitive (`websockets`, `httptools`) 설치.

- [ ] **Step 3**: `python -c "import fastapi, uvicorn, jinja2, sse_starlette; print('ok')"` → `ok`.

- [ ] **Step 4**: 커밋 — `deps(m5): FastAPI + uvicorn + Jinja2 + sse-starlette + python-multipart 추가`.

#### Task 0.2 — Config 에 M5 필드 + UsageSource enum

**Files:** Modify `src/gah/config.py`. Create `tests/test_config_m5.py`.

- [ ] **Step 1: 실패 테스트** — 7 신규 필드 기본값 + `UsageSource` enum 3 값 (manual/mcp/claude_pick) — 8 케이스.

- [ ] **Step 2: 실패 확인** — `pytest tests/test_config_m5.py -v` → 8 FAIL `AttributeError`.

- [ ] **Step 3: 구현** — `Config` 에 7 신규 필드:

```python
# M5 fields
web_host: str = "127.0.0.1"
web_port: int = 9874
web_port_max_attempts: int = 10
claude_pick_timeout_seconds: int = 300
claude_pick_max_pending: int = 20
web_open_browser_on_start: bool = True
web_log_requests: bool = False
```

신규 `UsageSource(str, Enum)`:

```python
class UsageSource(str, Enum):
    MANUAL = "manual"
    MCP = "mcp"
    CLAUDE_PICK = "claude_pick"
```

- [ ] **Step 4: 통과** — `pytest tests/test_config_m5.py -v` → 8 passed.

- [ ] **Step 5: 회귀** — `pytest -q` → 452 + 8 = 460 passed (config 6채널 회귀 0).

- [ ] **Step 6: 커밋** — `feat(m5): Config 7 신규 필드 + UsageSource enum`.

#### Task 0.3 — HTMX + Alpine vendoring

**Files:** Create `src/gah/web/static/vendor/{htmx.min.js,htmx-sse.min.js,alpine.min.js,README.md}`.

- [ ] **Step 1: 디렉터리 + 다운로드** — `mkdir -p src/gah/web/static/vendor` + `Invoke-WebRequest` 3 회로 HTMX 1.9.12 (core + sse ext) + Alpine 3.13.10 (cdn min).

- [ ] **Step 2: SHA256 기록** — `Get-FileHash` 3 회 → README 표에 박음.

- [ ] **Step 3: README 작성** — 출처/버전/SHA256/업데이트 절차 (한국어). PyInstaller 패키징은 M8 .

- [ ] **Step 4: 커밋** — `deps(m5): HTMX 1.9.12 + Alpine 3.13.10 vendoring (오프라인 지원)`.

---

### 4.1 Phase 1 — FastAPI 스캐폴딩 + 트레이 통합 (~1주)

#### Task 1.1 — `web/url.py` web.port 파일 R/W

**Files:** Create `src/gah/web/__init__.py` (빈), `src/gah/web/url.py`. Test `tests/test_web_url.py` (5 케이스 §2.2).

- [ ] **Step 1: 실패 테스트** — `write_web_port(tmp, 9874)` → 파일 존재 + 내용 "9874\n" / `read_web_port` 정상 / 파일 부재 → None / atomic (tmp 파일 잔존 X) / 잘못된 내용 → None + 로그.

- [ ] **Step 2**: `pytest tests/test_web_url.py -v` → 5 FAIL `ModuleNotFoundError`.

- [ ] **Step 3: 구현** — `web/url.py`:

```python
def write_web_port(data_dir: Path, port: int) -> None:
    tmp = data_dir / "web.port.tmp"
    final = data_dir / "web.port"
    tmp.write_text(f"{port}\n", encoding="utf-8")
    os.replace(tmp, final)

def read_web_port(data_dir: Path) -> int | None:
    final = data_dir / "web.port"
    if not final.exists():
        return None
    try:
        return int(final.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        log.warning("web.port 파일 파싱 실패")
        return None
```

- [ ] **Step 4**: `pytest tests/test_web_url.py -v` → 5 passed.

- [ ] **Step 5: 커밋** — `feat(m5): web.port 파일 R/W (MCP loopback URL 공유)`.

#### Task 1.2 — `web/pending.py` PendingPickQueue

**Files:** Create `src/gah/web/pending.py`. Test `tests/test_web_pending.py` (10 케이스).

- [ ] **Step 1: 실패 테스트** — register 신규 PendingPick / resolve future / 미존재 rid → False / cancel `UserCancelledError` / 더블 resolve False / max_pending 초과 `MaxPendingExceeded` / cleanup_expired TTL / snapshot LIFO / 동시 register 20 OK / 21번째 raise / lock 동시성. 모두 `@pytest.mark.asyncio` (pytest-asyncio M2 의존).

- [ ] **Step 2**: `pytest tests/test_web_pending.py -v` → 10 FAIL.

- [ ] **Step 3: 구현** — `pending.py` (~150 줄). 핵심:

```python
class UserCancelledError(Exception): ...
class MaxPendingExceeded(Exception): ...

@dataclass
class PendingPick:
    request_id: str
    candidates: list[int]
    reason: str | None
    project_id: str | None
    created_at: float
    status: str  # "pending" | "resolved" | "cancelled" | "expired"
    future: asyncio.Future  # asyncio.get_running_loop().create_future() at register time

class PendingPickQueue:
    def __init__(self, max_pending: int = 20) -> None:
        self._items: dict[str, PendingPick] = {}
        self._lock = threading.RLock()
        self._max = max_pending

    def register(self, candidates, reason, project_id) -> PendingPick:
        with self._lock:
            if len(self._items) >= self._max:
                raise MaxPendingExceeded()
            rid = uuid.uuid4().hex
            loop = asyncio.get_event_loop()
            fut = loop.create_future()
            p = PendingPick(rid, list(candidates), reason, project_id, time.time(), "pending", fut)
            self._items[rid] = p
            return p

    def resolve(self, rid, picked_asset_id, user_note) -> bool:
        with self._lock:
            p = self._items.get(rid)
            if p is None or p.status != "pending":
                return False
            p.status = "resolved"
            p.future.get_loop().call_soon_threadsafe(
                p.future.set_result,
                {"picked_asset_id": picked_asset_id, "user_note": user_note, "picked_at": int(time.time())},
            )
            return True

    def cancel(self, rid, reason) -> bool: ...
    def expire(self, rid) -> bool: ...
    def snapshot(self) -> list[dict]: ...
    def cleanup_expired(self, now, ttl) -> int: ...
```

- [ ] **Step 4**: `pytest tests/test_web_pending.py -v` → 10 passed.

- [ ] **Step 5: 커밋** — `feat(m5): PendingPickQueue (asyncio.Future + lock + TTL cleanup)`.

#### Task 1.3 — `web/deps.py` WebDeps 데이터클래스

**Files:** Create `src/gah/web/deps.py` (~30 줄). 테스트 불필요 (데이터클래스만).

- [ ] **Step 1: 구현** — frozen dataclass:

```python
@dataclass(frozen=True)
class WebDeps:
    store: Store
    search: HybridSearcher
    usage: UsageTracker
    registry: LabelRegistry
    queue: Any | None
    config: Config
    paths: AppPaths
    pending_picks: PendingPickQueue
```

- [ ] **Step 2: 커밋** — `feat(m5): WebDeps 의존성 묶음 데이터클래스`.

#### Task 1.4 — `web/app.py` FastAPI factory + lifespan + i18n stub

**Files:** Create `src/gah/web/app.py`, `src/gah/web/i18n.py`, `src/gah/web/routers/__init__.py`, `src/gah/web/routers/health.py`. Test `tests/test_web_app.py` (8 케이스).

- [ ] **Step 1: 실패 테스트** — `build_app(deps)` 가 FastAPI / `/api/health` 200 + `mcp_tools_count=17` / `/static/vendor/htmx.min.js` 200 / `/static/css/main.css` 200 (Task 0.3 + 본 task 가 디렉터리 마운트만) / lifespan 시작/정지 / 라우터 9 등록 / 404 핸들러 / 캐시 헤더.

- [ ] **Step 2: 실패** — `pytest tests/test_web_app.py -v` → 8 FAIL.

- [ ] **Step 3: 구현** — `app.py` factory (lifespan = cleanup_expired 루프 시작), `i18n.py` (passthrough `_t` + Jinja 글로벌 `_`), `routers/health.py` (`/api/health`), 나머지 8 라우터는 빈 `APIRouter()` 스텁만.

- [ ] **Step 4**: `pytest tests/test_web_app.py -v` → 8 passed.

- [ ] **Step 5: 회귀** — `pytest -q` → ~478 passed.

- [ ] **Step 6: 커밋** — `feat(m5): FastAPI 앱 팩토리 + lifespan + 9 라우터 스텁 + i18n passthrough`.

#### Task 1.5 — `web/server.py` WebServer 부팅/종료

**Files:** Create `src/gah/web/server.py`. Test `tests/test_web_server.py` (6 케이스).

- [ ] **Step 1: 실패 테스트** — start → web.port 파일 + thread 시작 / `/api/health` 200 / 포트 9874 점유 → 9875 폴백 / 10 포트 모두 점유 → RuntimeError / stop → thread 종료 / actual_port 속성.

- [ ] **Step 2: 실패** — `pytest tests/test_web_server.py -v` → 6 FAIL.

- [ ] **Step 3: 구현** — `WebServer`:

```python
class WebServer:
    def __init__(self, deps: WebDeps) -> None: ...
    def start(self) -> None:
        port = self._find_available_port()
        app = build_app(self.deps)
        config = uvicorn.Config(app, host=self.deps.config.web_host, port=port, log_level="warning", loop="asyncio", lifespan="on")
        self._server = uvicorn.Server(config)
        self.actual_port = port
        write_web_port(self.deps.paths.data_dir, port)
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="GAH-WebServer")
        self.thread.start()

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._server.serve())
        loop.close()

    def _find_available_port(self) -> int:
        for offset in range(self.deps.config.web_port_max_attempts):
            port = self.deps.config.web_port + offset
            with socket.socket() as s:
                try:
                    s.bind((self.deps.config.web_host, port)); return port
                except OSError: continue
        raise RuntimeError(...)

    def stop(self, timeout=5.0) -> None:
        if self._server is not None: self._server.should_exit = True
        if self.thread is not None: self.thread.join(timeout=timeout)
```

- [ ] **Step 4**: `pytest tests/test_web_server.py -v` → 6 passed.

- [ ] **Step 5: 회귀** — `pytest -q` → ~484 passed.

- [ ] **Step 6: 커밋** — `feat(m5): WebServer (uvicorn 별도 스레드 + 포트 폴백 + web.port 공유)`.

#### Task 1.6 — 트레이 wiring 변경 (`tray.py`)

**Files:** Modify `src/gah/tray.py`. Test `tests/test_tray_m5.py` (5 케이스).

- [ ] **Step 1: 실패 테스트** — `on_open_main` 콜백이 `webbrowser.open(url)` 호출 검증 / 메뉴 "라벨 관리…" 부재 / `notify_user_pick_request(tray, count)` 툴팁 갱신 + property `_pick_count=count` / count=0 → 디폴트 툴팁 / 더블 클릭 → on_open_main.

- [ ] **Step 2: 실패** — `pytest tests/test_tray_m5.py -v` → 5 FAIL.

- [ ] **Step 3: 구현** — `make_tray_icon` 시그니처에서 `on_open_labels` 매개변수 제거. 신규 `notify_user_pick_request(tray, count)`:

```python
def notify_user_pick_request(tray, count: int) -> None:
    from PySide6.QtCore import QCoreApplication
    def _tr(s): return QCoreApplication.translate("Tray", s)
    if count > 0:
        tray.setToolTip(_tr("Game Asset Helper — Claude 요청 {n}건").format(n=count))
        tray.setProperty("_pick_count", count)
    else:
        tray.setToolTip(_tr("Game Asset Helper"))
        tray.setProperty("_pick_count", 0)
```

- [ ] **Step 4**: `pytest tests/test_tray_m5.py -v` → 5 passed.

- [ ] **Step 5: 커밋** — `feat(m5): 트레이 메뉴 웹 GUI 진입 + notify_user_pick_request 신호`.

#### Task 1.7 — `app.py` (`run_tray`) — WebServer 시작 + main_window 의존성 제거

**Files:** Modify `src/gah/app.py`. Create `src/gah/web/sse_bus.py`. Test `tests/test_app_m5.py` (6 케이스).

- [ ] **Step 1: 실패 테스트** — WebServer.start/stop 호출 검증 / SSE bus 가 progressChanged 신호로 broadcast / browser.open 호출 / `web_open_browser_on_start=False` 시 미호출 / 포트 폴백 (9874 점유 → 9875) / 종료 흐름.

- [ ] **Step 2: 실패** — `pytest tests/test_app_m5.py -v` → 6 FAIL.

- [ ] **Step 3: `web/sse_bus.py` 구현** — broadcast bus:

```python
"""Qt 시그널 → SSE broadcast 의 thread-safe pivot.

put_nowait 는 broadcaster (보통 Qt main thread) 에서 호출되는데,
asyncio.Queue 가 다른 이벤트루프 (uvicorn thread) 에 살기 때문에
call_soon_threadsafe 로 마샬링한다.
"""
_subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []

def broadcast(event: str, data: dict) -> None:
    for loop, q in list(_subscribers):
        def _put(): q.put_nowait({"event": event, "data": data})
        loop.call_soon_threadsafe(_put)

def subscribe() -> asyncio.Queue:
    loop = asyncio.get_running_loop()
    q = asyncio.Queue(maxsize=100)
    _subscribers.append((loop, q))
    return q

def unsubscribe(q: asyncio.Queue) -> None: ...
```

- [ ] **Step 4: `app.py` 수정** — `run_tray` 가 main_window 의존성 제거:

```python
def run_tray(paths, config, argv=None) -> int:
    from PySide6.QtWidgets import QApplication
    import webbrowser
    from .tray import make_tray_icon, update_tray_tooltip
    from .web.server import WebServer
    from .web.deps import WebDeps
    from .web.pending import PendingPickQueue
    from .web.sse_bus import broadcast

    qapp = QApplication(list(argv or sys.argv))
    qapp.setQuitOnLastWindowClosed(False)

    # store/registry/scanner/queue/searcher/usage — 기존 동일
    # ... (이 plan §4.1 의 task 1.7 step 4 부록 — 전체 구현 코드)

    pending = PendingPickQueue(max_pending=config.claude_pick_max_pending)
    deps = WebDeps(store=store, search=searcher, usage=usage, registry=registry,
                   queue=queue, config=config, paths=paths, pending_picks=pending)
    web = WebServer(deps)
    web.start()
    url = f"http://{config.web_host}:{web.actual_port}"

    tray = make_tray_icon(qapp, on_open_main=lambda: webbrowser.open(url))
    queue.progressChanged.connect(lambda snap: update_tray_tooltip(tray, snap))
    queue.progressChanged.connect(lambda snap: broadcast("analysis_progress", snap.to_dict()))

    if config.web_open_browser_on_start:
        webbrowser.open(url)

    log.info("GAH tray ready (url=%s)", url)
    rc = qapp.exec()

    web.stop(); queue.stop(); watcher.stop(); store.close()
    return rc
```

- [ ] **Step 5: m4 GUI 테스트 임시 skip** — `test_library_search_ui*.py` / `test_ui_smoke.py` / `test_labels_admin_ui.py` 가 main_window 의존 → Phase 5 가 폐기할 때까지 `pytest.skip("M5 Phase 5 폐기 예정")` 마크. Grep 으로 import 깨진 파일 식별 후 모듈 단위 skip.

```python
# tests/test_library_search_ui.py (그리고 _rich, test_ui_smoke 등)
import pytest
pytestmark = pytest.mark.skip(reason="M5 Phase 5 가 폐기 예정 — main_window 제거")
```

- [ ] **Step 6**: `pytest tests/test_app_m5.py -v` → 6 passed.

- [ ] **Step 7: 회귀** — `pytest -q` → ~490 passed + ~30 skipped (m4 GUI 테스트들).

- [ ] **Step 8: 커밋** — `feat(m5): run_tray 가 WebServer 시작 + main_window 의존성 제거 (m4 GUI 테스트 skip)`.

---

### 4.2 Phase 2 — 라이브러리 페이지 (검색 + 결과) (~1주)

#### Task 2.1 — `/api/search` POST (JSON)

**Files:** Modify `src/gah/web/routers/library.py`. Test `tests/test_web_routers_library.py` (`/api/search` 부분).

- [ ] **Step 1: 실패 테스트** — POST `{"query": "blue hero", "count": 10, "project_id": null}` → 200 JSON with `results: [...]` + `score_breakdown` 키들 / `label_query="character AND pixel_art"` 전달 → 파서 호출 → SearchRequest 통합 / `pack_ids` 필터 / `diversity="mmr"` / 잘못된 `diversity="bogus"` → 422.

- [ ] **Step 2: 실패** — `pytest tests/test_web_routers_library.py::test_api_search* -v` → 4 FAIL.

- [ ] **Step 3: 구현** — `routers/library.py`:

```python
from pydantic import BaseModel
class SearchBody(BaseModel):
    query: str = ""
    label_query: str | None = None
    project_id: str | None = None
    pack_ids: list[int] | None = None
    kind: str | None = None
    diversity: str = "none"
    diversity_lambda: float | None = None
    count: int = 20
    offset: int = 0
    sort: str = "score"  # score|added_desc|added_asc|name_asc|name_desc|size_desc|size_asc

router = APIRouter(prefix="/api", tags=["library"])

@router.post("/search")
def api_search(body: SearchBody, request: Request) -> dict:
    deps: WebDeps = request.app.state.deps
    req = SearchRequest(
        query=body.query, label_query=body.label_query,
        project_id=body.project_id, pack_ids=body.pack_ids, kind=body.kind,
        diversity=body.diversity, diversity_lambda=body.diversity_lambda,
        count=body.count, offset=body.offset,
    )
    res = deps.search.hybrid(req)
    rows = [_row_to_dict(r) for r in res.rows]
    rows = _apply_sort(rows, body.sort)
    return {"query_id": res.query_id, "total": res.total, "rows": rows}
```

- [ ] **Step 4**: `pytest tests/test_web_routers_library.py::test_api_search* -v` → 4 passed.

- [ ] **Step 5: 커밋** — `feat(m5): /api/search POST (JSON, HybridSearcher 위임)`.

#### Task 2.2 — `/ui/search-results` POST (HTML fragment for HTMX)

**Files:** Modify `routers/library.py`. Create `web/templates/_card_wide.html`, `_card_list.html`, `_results_grid.html`.

- [ ] **Step 1: 실패 테스트** — POST → text/html 200 + 응답에 `<div class="card-wide"` 또는 `<div class="card-list"` / 카드 카운트 = body.count / `view_mode="list"` → list partial / Alpine `x-data` 누락 (partial 라 root 없음).

- [ ] **Step 2: 구현** — `routers/library.py` 신규 라우트:

```python
@router.post("/ui/search-results", response_class=HTMLResponse)
def ui_search_results(body: SearchBody, request: Request, view_mode: str = "grid"):
    # api_search 와 동일 호출 → 결과 dict
    # templates.TemplateResponse("_results_grid.html" or "_card_list.html", {...})
```

`_results_grid.html` 가 카드들 forEach + Alpine 양방향 바인딩 hooks. 카드 partial 은 단일 row 받음.

- [ ] **Step 3**: `pytest tests/test_web_routers_library.py::test_ui_search_results* -v` → 4 passed.

- [ ] **Step 4: 커밋** — `feat(m5): /ui/search-results POST HTMX fragment + 와이드 카드 partial`.

#### Task 2.3 — `/api/thumbnail/{asset_id}` (lazy 256×256 PNG)

**Files:** Modify `routers/library.py`. Reuse `core/thumbnails.py` (M4).

- [ ] **Step 1: 실패 테스트** — sprite 자산 → 200 PNG + `Content-Type: image/png` + ETag / sound 자산 → 404 / 미존재 id → 404 / 캐시 hit → ETag 일치 시 304 Not Modified.

- [ ] **Step 2: 구현**:

```python
@router.get("/thumbnail/{asset_id}")
def api_thumbnail(asset_id: int, request: Request):
    deps = request.app.state.deps
    asset = deps.store.get_asset(asset_id)
    if asset is None or asset.kind != "sprite":
        raise HTTPException(404)
    path = ensure_thumbnail(asset.path, deps.paths.cache_dir, asset_id, max_size=256)
    if path is None: raise HTTPException(404)
    etag = f'"{path.stat().st_mtime_ns}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    return FileResponse(path, media_type="image/png", headers={"ETag": etag})
```

- [ ] **Step 3**: `pytest tests/test_web_routers_library.py::test_api_thumbnail* -v` → 4 passed.

- [ ] **Step 4: 커밋** — `feat(m5): /api/thumbnail (M4 lazy 256×256 PNG 재사용 + ETag)`.

#### Task 2.4 — 라이브러리 페이지 베이스 레이아웃 (`base.html` + `library.html`)

**Files:** Create `web/templates/base.html`, `library.html`, `_nav.html`, `web/static/css/main.css`, `themes.css`.

- [ ] **Step 1: `base.html` 작성** — html5 + viewport + 자체 CSS + HTMX + Alpine 로드 + nav block + main block + footer block. Alpine global stores 초기화 스크립트:

```html
<script>
document.addEventListener('alpine:init', () => {
    Alpine.store('search', {query: '', viewMode: 'grid', cardSize: 'm', sort: 'added_desc', cardMeta: {labels:true, pack:true, score:false, size:false}});
    Alpine.store('advanced', {open: false, activeTab: 'b', sidePanelWidth: 320});
    Alpine.store('pickQueue', {items: []});
    Alpine.store('notifications', {pickCount: 0});
});
</script>
```

- [ ] **Step 2: `_nav.html`** — 헤더 + 라이브러리/팩/라벨 관리 링크 + 알림 배지 (`x-show="$store.notifications.pickCount > 0"`).

- [ ] **Step 3: `library.html`** — `{% extends "base.html" %}` + main block 안에 검색 바 + ⚙ 토글 + 결과 영역 placeholder + 사이드 패널 placeholder. Alpine `x-data="libraryPage()"`.

- [ ] **Step 4: `main.css` + `themes.css`** — CSS 변수 (light/dark), grid/list 레이아웃, 카드, 사이드 패널 슬라이드 transition 200ms, 칩 wrap (flex-wrap), 모바일 미디어 쿼리 (≤768px 사이드 자동 닫힘).

- [ ] **Step 5: `/library` 라우트 등록** — `routers/library.py`:

```python
@router.get("/library", response_class=HTMLResponse)
def page_library(request: Request):
    deps = request.app.state.deps
    return request.app.state.templates.TemplateResponse(
        "library.html", {"request": request, "deps": deps},
    )

# 디폴트 / 도 library 로
@router.get("/", response_class=HTMLResponse)
def page_root(request: Request):
    return RedirectResponse("/library")
```

prefix 가 `/api` 라 별도 router (또는 별도 router 추가). `routers/pages.py` 신규 — `/` `/library` `/packs` `/labels/admin` HTML 페이지만.

- [ ] **Step 6: 수동 시각 검증** — `python -m gah --tray` 후 브라우저에서 `/library` 접근 → 빈 페이지 + 헤더 + 검색 바 보임.

- [ ] **Step 7: 커밋** — `feat(m5): 라이브러리 페이지 베이스 레이아웃 (base/nav/library + CSS 변수)`.

#### Task 2.5 — 와이드 카드 partial (`_card_wide.html`)

**Files:** Create/Modify `web/templates/_card_wide.html`.

- [ ] **Step 1: 작성** — 와이드 카드 (썸네일 60×60 좌 + 텍스트 우):

```html
<div class="card-wide" data-asset-id="{{ row.asset_id }}" hx-get="/ui/asset-detail/{{ row.asset_id }}" hx-target="#asset-detail-modal" hx-trigger="click">
  <div class="card-thumb">
    {% if row.kind == "sprite" %}
      <img src="/api/thumbnail/{{ row.asset_id }}" loading="lazy" alt="{{ row.name }}" />
    {% elif row.kind == "sound" %}
      <span class="sound-icon">🔊</span>
    {% endif %}
  </div>
  <div class="card-body">
    <div class="card-title">
      {{ row.name }}
      {% if $store.search.cardMeta.score %}<span class="score">{{ "%.2f"|format(row.score) }}</span>{% endif %}
    </div>
    {% if $store.search.cardMeta.labels %}
      <div class="card-labels">{{ row.matched_labels[:3]|join(" · ") }}</div>
    {% endif %}
    {% if $store.search.cardMeta.pack %}
      <div class="card-meta">{{ row.pack_name }}{% if row.kind == "sprite" %} · {{ row.width }}×{{ row.height }}{% endif %} · {{ row.size_kb }}KB</div>
    {% endif %}
    {% if row.kind == "sound" %}
      <button class="play-btn" hx-get="/api/audio/{{ row.asset_id }}" hx-target="next .audio-slot" hx-swap="innerHTML">▶ 재생</button>
      <div class="audio-slot"></div>
    {% endif %}
  </div>
</div>
```

(주의: Jinja2 + Alpine 혼용 — `$store.search.cardMeta` 는 Jinja 의 `{% if %}` 가 아니라 Alpine 의 `x-show` 로 가야 한다. 단순화: 카드 메타 토글은 partial 이 항상 모두 렌더링하고 Alpine `x-show` 로 가시성만 조절.)

수정된 partial — meta 토글은 `x-show`:

```html
<div class="card-meta-row" x-show="$store.search.cardMeta.labels">
  {{ row.matched_labels[:3]|join(" · ") }}
</div>
```

- [ ] **Step 2: `_card_list.html`** — 풀폭 + 더 많은 메타 + 같은 클릭 동작.

- [ ] **Step 3: 자동 테스트** — `_card_wide.html` 가 sprite/sound/sheet 각각 정상 렌더 (3 케이스, Jinja2 직접 호출).

- [ ] **Step 4: 커밋** — `feat(m5): 와이드/리스트 카드 partial (Jinja2 + Alpine x-show 메타 토글)`.

#### Task 2.6 — 검색 바 + 300ms 디바운스

**Files:** Modify `web/templates/library.html`.

- [ ] **Step 1: 작성** — 검색 바:

```html
<form class="search-bar" hx-post="/ui/search-results" hx-target="#results" hx-trigger="keyup changed delay:300ms from:input, submit" hx-include="this">
  <input type="search" name="query" placeholder="{{ _('자연어 검색…  (예: 어두운 BGM 짧은 거)') }}" x-model="$store.search.query" />
  <button type="button" @click="$store.advanced.open = !$store.advanced.open" :class="{'active': $store.advanced.open}">⚙ {{ _('고급') }}</button>
</form>
<div id="results" hx-trigger="load" hx-post="/ui/search-results" hx-include="form.search-bar"></div>
```

- [ ] **Step 2: 수동 시각 검증** — 검색 바 타이핑 → 300ms 후 결과 영역 갱신 / ⚙ 클릭 → 사이드 패널 토글 시각화.

- [ ] **Step 3: 커밋** — `feat(m5): 검색 바 + 300ms HTMX 디바운스 + ⚙ 고급 토글`.

#### Task 2.7 — 결과 영역 그리드/리스트 토글 + 카드 크기 + 정렬 + 카운트

**Files:** Modify `web/templates/library.html`, `_results_grid.html`.

- [ ] **Step 1: 툴바 작성** — 결과 영역 위:

```html
<div class="results-toolbar">
  <div class="view-toggle">
    <button @click="$store.search.viewMode='grid'" :class="{'active': $store.search.viewMode==='grid'}">🖼 {{ _('그리드') }}</button>
    <button @click="$store.search.viewMode='list'" :class="{'active': $store.search.viewMode==='list'}">≡ {{ _('리스트') }}</button>
  </div>
  <div class="size-toggle">
    <button @click="$store.search.cardSize='s'" :class="{'active': $store.search.cardSize==='s'}">S</button>
    <button @click="$store.search.cardSize='m'" :class="{'active': $store.search.cardSize==='m'}">M</button>
    <button @click="$store.search.cardSize='l'" :class="{'active': $store.search.cardSize==='l'}">L</button>
  </div>
  <select x-model="$store.search.sort" @change="htmx.trigger('form.search-bar', 'submit')">
    <option value="score">{{ _('점수↓') }}</option>
    <option value="added_desc">{{ _('추가일↓') }}</option>
    ...
  </select>
  <div class="result-count">{{ _('총 {n} 자산').replace('{n}', $store.lastResult.total) }}</div>
</div>
```

- [ ] **Step 2: CSS** — `.card-wide.card-s` (40×40 썸네일) / `.card-m` (60×60) / `.card-l` (96×96). `.view-mode-grid` flex-wrap / `.view-mode-list` 한 줄.

- [ ] **Step 3: 자동 테스트** — Alpine 변경 → 카드 클래스 갱신 (수동 시각 + DOM snapshot 1 케이스).

- [ ] **Step 4: 커밋** — `feat(m5): 결과 툴바 (그리드/리스트/카드 크기 S/M/L/정렬/카운트)`.

#### Task 2.8 — 페이지네이션 (더 보기 버튼)

**Files:** Modify `routers/library.py`, `_results_grid.html`.

- [ ] **Step 1: 응답에 `next_offset` 추가** — count + offset 으로 페이지네이션. `total > offset + count` 시 next_offset 채움.

- [ ] **Step 2: 더 보기 버튼**:

```html
<div x-show="nextOffset !== null">
  <button hx-post="/ui/search-results" hx-target="#results" hx-swap="beforeend" hx-include="form.search-bar" hx-vals='{"offset": nextOffset}'>{{ _('더 보기') }}</button>
</div>
```

- [ ] **Step 3: 자동 테스트** — `offset=50, count=50` 응답 / `total=100` 시 `next_offset=null`.

- [ ] **Step 4: 커밋** — `feat(m5): 결과 페이지네이션 (더 보기 버튼)`.

#### Task 2.9 — 디폴트 상태 (검색 비어 → 라이브러리 전체 추가일↓)

**Files:** Modify `routers/library.py` (`SearchBody` 의 query="" + 필터 0 시 raw store 쿼리로 폴백).

- [ ] **Step 1: 분기 로직** — `body.query == "" and body.label_query is None and not body.pack_ids and body.kind is None` → `store.list_assets(sort=body.sort or "added_desc", limit, offset)` 호출 + score 채움 안 함 (UI 가 안 보이도록 cardMeta.score 디폴트 False).

- [ ] **Step 2: 자동 테스트** — `POST /ui/search-results {}` → 전체 라이브러리 추가일↓ 50 row.

- [ ] **Step 3: 커밋** — `feat(m5): 검색 비어 시 라이브러리 전체 추가일↓ (디폴트 페이지)`.

#### Task 2.10 — 카드 상세 모달 (`/ui/asset-detail/{id}`)

**Files:** Modify `routers/library.py`. Create `web/templates/asset_detail.html`.

- [ ] **Step 1: 라우트 + 템플릿** — 모달 안에 큰 썸네일 + 라벨 전체 (axis 별) + 메타 + Gemma description (있을 때) + [채택] + [거부] 버튼.

```python
@router.get("/ui/asset-detail/{asset_id}", response_class=HTMLResponse)
def ui_asset_detail(asset_id: int, request: Request):
    deps = request.app.state.deps
    asset = deps.store.get_asset_detail(asset_id)  # 라벨 + 메타 + description 포함
    if asset is None: raise HTTPException(404)
    return request.app.state.templates.TemplateResponse(
        "asset_detail.html", {"request": request, "asset": asset},
    )
```

`Store.get_asset_detail` 가 없으면 신규 메서드 추가 (M4 의 get_asset + asset_labels + asset_meta 조인 — store 헬퍼).

- [ ] **Step 2: `library.html` 에 모달 컨테이너** — `<dialog id="asset-detail-modal"><!-- swap target --></dialog>` + Alpine show 트리거.

- [ ] **Step 3: 자동 테스트** — 200 HTML + 라벨/메타/description 포함 / 미존재 → 404.

- [ ] **Step 4: 커밋** — `feat(m5): 카드 클릭 → 자산 상세 모달 (라벨/메타/Gemma description)`.

#### Task 2.11 — 사운드 인라인 ▶ 재생 (`/api/audio/{asset_id}`)

**Files:** Modify `routers/library.py`.

- [ ] **Step 1: 라우트** — `FileResponse` + media_type 자산 mime + Range 헤더 지원 (uvicorn FileResponse 가 자동).

```python
@router.get("/api/audio/{asset_id}")
def api_audio(asset_id: int, request: Request):
    deps = request.app.state.deps
    asset = deps.store.get_asset(asset_id)
    if asset is None or asset.kind != "sound": raise HTTPException(404)
    mime = mimetypes.guess_type(asset.path)[0] or "application/octet-stream"
    return FileResponse(asset.path, media_type=mime)
```

- [ ] **Step 2: 카드의 ▶ 버튼이 audio 태그 swap**:

```html
<button class="play-btn" hx-get="/ui/audio-player/{{ row.asset_id }}" hx-target="next .audio-slot">▶</button>
<div class="audio-slot"></div>
```

`/ui/audio-player/{id}` → `<audio controls autoplay src="/api/audio/{id}"></audio>` partial.

- [ ] **Step 3: 자동 테스트** — `/api/audio/{id}` 200 stream / sprite id → 404 / Range 헤더 응답.

- [ ] **Step 4: 커밋** — `feat(m5): 사운드 인라인 ▶ 재생 (audio 태그 swap)`.

#### Task 2.12 — 결과 영역 풍부 통합 (디바운스 + 정렬 + 페이지네이션 결합)

**Files:** Modify `web/templates/library.html` (final wire-up).

- [ ] **Step 1: 검색 바 + 툴바 + 결과 영역 + 모달 통합** — 모든 컴포넌트가 `<form class="search-bar">` 에 hx-include 됨. 정렬 변경 → 자동 재검색. 카드 메타 토글은 Alpine 만으로 (재검색 안 함).

- [ ] **Step 2: 수동 시각 검증** — 디바운스 → 정렬 변경 → 더 보기 → 카드 클릭 → 모달 → 닫기 흐름 확인.

- [ ] **Step 3: 커밋** — `feat(m5): 라이브러리 페이지 검색+결과 통합 (디바운스+정렬+페이지네이션+모달)`.

#### Task 2.13 — Phase 2 회귀 + 커밋 압축

- [ ] **Step 1**: `pytest -q` → ~520 passed + skipped.
- [ ] **Step 2: 커밋 압축 불필요** — git log 가 history.

---

### 4.3 Phase 3 — 우측 사이드 패널 B/C/D (~1.5주)

#### Task 3.1 — ⚙ 고급 토글 + 슬라이드 인 transition

**Files:** Modify `library.html`, `main.css`.

- [ ] **Step 1**: 사이드 패널 컨테이너:

```html
<aside class="side-panel" x-show="$store.advanced.open" x-transition.duration.200ms :style="{width: $store.advanced.sidePanelWidth + 'px'}">
  ...
</aside>
```

CSS — `.side-panel` `transform: translateX(...)` transition.

- [ ] **Step 2**: 커밋 — `feat(m5): 사이드 패널 ⚙ 토글 + 200ms 슬라이드 인 transition`.

#### Task 3.2 — 사이드 패널 리사이즈 핸들 (드래그)

**Files:** Modify `library.html`, `js/app.js`.

- [ ] **Step 1**: Alpine 컴포넌트 `resizeHandle`:

```js
function resizeHandle() {
  return {
    dragging: false,
    startDrag(e) { this.dragging = true; this.startX = e.clientX; this.startW = Alpine.store('advanced').sidePanelWidth; },
    onDrag(e) { if (this.dragging) Alpine.store('advanced').sidePanelWidth = Math.max(240, Math.min(640, this.startW + (this.startX - e.clientX))); },
    stopDrag() { this.dragging = false; },
  };
}
```

HTML — `<div class="resize-handle" x-data="resizeHandle()" @mousedown.prevent="startDrag" @mousemove.window="onDrag" @mouseup.window="stopDrag"></div>`.

- [ ] **Step 2: 수동 시각 검증** — 드래그 → 사이드 패널 너비 [240, 640] 범위 변경.

- [ ] **Step 3: 커밋** — `feat(m5): 사이드 패널 리사이즈 핸들 (Alpine 마우스 드래그 240~640)`.

#### Task 3.3 — B/C/D 탭 헤더 + 컨테이너

**Files:** Modify `library.html`. Create `_side_panel_b.html`, `_side_panel_c.html`, `_side_panel_d.html`.

- [ ] **Step 1**: 탭 헤더 + 탭 컨테이너:

```html
<nav class="side-tabs">
  <button @click="$store.advanced.activeTab='b'" :class="{active: $store.advanced.activeTab==='b'}">{{ _('B 필터') }}</button>
  <button @click="$store.advanced.activeTab='c'">{{ _('C 표시') }}</button>
  <button @click="$store.advanced.activeTab='d'">{{ _('D 조정') }}</button>
</nav>
<div class="side-tab-content" x-show="$store.advanced.activeTab==='b'">{% include "_side_panel_b.html" %}</div>
<div class="side-tab-content" x-show="$store.advanced.activeTab==='c'">{% include "_side_panel_c.html" %}</div>
<div class="side-tab-content" x-show="$store.advanced.activeTab==='d'">{% include "_side_panel_d.html" %}</div>
```

- [ ] **Step 2: 커밋** — `feat(m5): 사이드 패널 B/C/D 탭 헤더 + 컨테이너`.

#### Task 3.4 — B 탭: 매칭 모드 (AND/OR/NOT 라디오)

**Files:** Modify `_side_panel_b.html`.

- [ ] **Step 1**: 라디오:

```html
<fieldset class="match-mode">
  <label><input type="radio" name="match_mode" value="all" x-model="$store.search.matchMode" checked />{{ _('AND') }}</label>
  <label><input type="radio" name="match_mode" value="any" x-model="$store.search.matchMode" />{{ _('OR') }}</label>
  <label><input type="radio" name="match_mode" value="none" x-model="$store.search.matchMode" />{{ _('NOT') }}</label>
</fieldset>
```

- [ ] **Step 2**: 라디오 변경 시 form.search-bar submit 트리거 (`@change="htmx.trigger('form.search-bar','submit')"`).

- [ ] **Step 3: 커밋** — `feat(m5): B 탭 매칭 모드 라디오 (AND/OR/NOT)`.

#### Task 3.5 — B 탭: 라벨 검색 input (substring 매칭 + 노란 강조)

**Files:** Modify `_side_panel_b.html`, `main.css`.

- [ ] **Step 1**: input + Alpine state:

```html
<input type="search" x-model="$store.b.labelFilter" placeholder="{{ _('🔍 라벨 검색…') }}" />
```

- [ ] **Step 2: 칩 강조** — 각 칩에 `:class="{matched: $store.b.labelFilter && label.toLowerCase().includes($store.b.labelFilter.toLowerCase())}"`.

- [ ] **Step 3: CSS** — `.chip.matched { box-shadow: 0 0 0 2px yellow; }`.

- [ ] **Step 4: 커밋** — `feat(m5): B 탭 라벨 검색 input + 매칭 칩 노란 강조`.

#### Task 3.6 — B 탭: 종류 탭 (sprite/sheet/sound)

**Files:** Modify `_side_panel_b.html`. Modify `routers/filters.py` (`/api/filters/labels` 가 axis 분류).

- [ ] **Step 1: 분류 로직** — `routers/filters.py`:

```python
def _classify_axis(axis_id: str) -> str:
    if axis_id.startswith("sound_"): return "sound"
    if axis_id.startswith("sheet_"): return "sheet"
    return "sprite"
```

`/api/filters/labels` 응답이 `{sprite: [axis...], sheet: [...], sound: [...]}` 분리.

- [ ] **Step 2: 종류 탭 HTML**:

```html
<nav class="kind-tabs">
  <button @click="$store.b.kindTab='sprite'">{{ _('스프라이트') }}</button>
  <button @click="$store.b.kindTab='sheet'">{{ _('시트') }}</button>
  <button @click="$store.b.kindTab='sound'">{{ _('사운드') }}</button>
</nav>
```

- [ ] **Step 3: 자동 테스트** — 분류가 sound_* / sheet_* / 나머지 정확.

- [ ] **Step 4: 커밋** — `feat(m5): B 탭 종류 탭 + axis prefix 기반 분류`.

#### Task 3.7 — B 탭: axis 칩 FlowLayout + 카운트

**Files:** Modify `_side_panel_b.html`, `routers/filters.py`, `main.css`.

- [ ] **Step 1: `/api/filters/labels`** — 각 라벨에 현재 검색 컨텍스트의 매칭 카운트 포함 (option). v1 은 카운트 없이 라벨 목록만.

- [ ] **Step 2: 칩 HTML**:

```html
<template x-for="axis in $store.b.labelsByKind[$store.b.kindTab]" :key="axis.id">
  <div class="axis-group">
    <h4 x-text="axis.label_ko"></h4>
    <div class="chip-flow">
      <template x-for="label in axis.labels" :key="label.id">
        <button class="chip" :class="{active: $store.b.selectedLabels.includes(label.id), matched: $store.b.labelFilter && label.label_ko.toLowerCase().includes($store.b.labelFilter.toLowerCase())}" @click="toggleLabel(label.id)" x-text="label.label_ko"></button>
      </template>
    </div>
  </div>
</template>
```

CSS — `.chip-flow { display: flex; flex-wrap: wrap; gap: 4px; }`. **좌우 스크롤 금지** (spec §4.4.1) — `overflow-x: hidden`.

- [ ] **Step 3: 칩 클릭 → 검색 재호출** — `toggleLabel(id)` 가 `$store.b.selectedLabels` 갱신 + `htmx.trigger('form.search-bar','submit')`.

- [ ] **Step 4: 자동 테스트** — `/api/filters/labels` 분류 / axis 분류 / `_side_panel_b.html` 렌더 (Jinja).

- [ ] **Step 5: 커밋** — `feat(m5): B 탭 axis 칩 FlowLayout (flex-wrap) + 클릭 토글`.

#### Task 3.8 — B 탭: 다축 필터 드롭다운 4개

**Files:** Modify `_side_panel_b.html`. Modify `routers/filters.py` (`/api/filters/packs`).

- [ ] **Step 1: 드롭다운 4개** — 팩(다중 선택 select 또는 체크박스 풀다운), 상태(전체/완료/대기/실패), 라이선스, 벤더.

- [ ] **Step 2: `/api/filters/packs`** — 팩 카탈로그 + 자산 수 + license + vendor 집합.

- [ ] **Step 3**: 변경 시 form submit 트리거.

- [ ] **Step 4: 자동 테스트** — `/api/filters/packs` 응답 정확 / 빈 카탈로그 처리.

- [ ] **Step 5: 커밋** — `feat(m5): B 탭 다축 필터 (팩 다중 + 상태/라이선스/벤더)`.

#### Task 3.9 — `/api/search` 가 selectedLabels + matchMode 통합

**Files:** Modify `routers/library.py`.

- [ ] **Step 1**: `SearchBody` 에 `labels: list[int] | None = None`, `match_mode: str = "all"` 추가 → SearchRequest 의 `labels_all` / `labels_any` / `labels_none` 으로 매핑.

- [ ] **Step 2: 자동 테스트** — selectedLabels=[1,2,3] + match_mode="all" → labels_all 매핑 / "any" → labels_any / "none" → labels_none.

- [ ] **Step 3: 커밋** — `feat(m5): /api/search 가 selectedLabels + matchMode → SearchRequest 매핑`.

#### Task 3.10 — C 탭: 표시 옵션 양방향 바인딩

**Files:** Modify `_side_panel_c.html`.

- [ ] **Step 1**: 그리드/리스트 / 카드 크기 S/M/L / 정렬 — 모두 Alpine `$store.search.*` 와 양방향. 결과 툴바와 자동 동기.

```html
<div class="opt-group">
  <h4>{{ _('결과 표시 형식') }}</h4>
  <button @click="$store.search.viewMode='grid'" :class="{active: $store.search.viewMode==='grid'}">🖼 {{ _('그리드') }}</button>
  <button @click="$store.search.viewMode='list'" :class="{active: $store.search.viewMode==='list'}">≡ {{ _('리스트') }}</button>
</div>
<!-- 카드 크기 / 정렬 — 동일 -->
```

- [ ] **Step 2: 커밋** — `feat(m5): C 탭 표시 옵션 양방향 바인딩 (그리드/리스트/크기/정렬)`.

#### Task 3.11 — C 탭: 카드 메타 토글

**Files:** Modify `_side_panel_c.html`.

- [ ] **Step 1**: 4 체크박스 (라벨/팩/점수/크기) → `$store.search.cardMeta` 갱신 → 카드의 `x-show` 즉시 반영.

- [ ] **Step 2: 커밋** — `feat(m5): C 탭 카드 메타 토글 (라벨/팩/점수/크기)`.

#### Task 3.12 — D 탭: 프리셋 3 버튼 (균형/통일성/참신성)

**Files:** Modify `_side_panel_d.html`. Modify `routers/library.py` (`POST /api/preset/{name}` — Config 가중치 갱신).

- [ ] **Step 1**: 프리셋 표 — Config 가중치 정의 (예시):

| 프리셋 | semantic | keyword | label | consistency | recency | feedback |
|---|---:|---:|---:|---:|---:|---:|
| balanced | 0.35 | 0.10 | 0.20 | 0.20 | 0.05 | 0.10 |
| consistency | 0.25 | 0.05 | 0.20 | **0.40** | 0.05 | 0.05 |
| novelty | 0.40 | 0.15 | 0.20 | **0.05** | 0.10 | 0.10 |

- [ ] **Step 2**: HTML — 3 버튼 + 현재 선택 표시 + 1줄 설명:

```html
<div class="preset-row">
  <button @click="applyPreset('balanced')" :class="{active: $store.d.activePreset==='balanced'}">{{ _('균형') }}</button>
  <button @click="applyPreset('consistency')">{{ _('통일성 우선') }}</button>
  <button @click="applyPreset('novelty')">{{ _('참신성') }}</button>
</div>
<p class="preset-desc" x-text="$store.d.presetDesc"></p>
```

`applyPreset(name)` → `POST /api/preset/{name}` → Config 갱신 + form submit 재검색.

- [ ] **Step 3: 자동 테스트** — `/api/preset/balanced` POST → Config.weight_* 갱신 + 응답 가중치 dict.

- [ ] **Step 4: 커밋** — `feat(m5): D 탭 프리셋 3개 (균형/통일성/참신성) + Config 즉시 갱신`.

#### Task 3.13 — D 탭: 슬라이더 펼침 (6 슬라이더)

**Files:** Modify `_side_panel_d.html`. Modify `routers/library.py` (`POST /api/weights`).

- [ ] **Step 1**: details/summary 또는 Alpine 토글:

```html
<details>
  <summary>{{ _('▶ 슬라이더 직접 조정…') }}</summary>
  <div class="sliders">
    <label>{{ _('의미 (semantic)') }}<input type="range" min="0" max="100" x-model.number="$store.weights.semantic" @change="syncWeights()" /></label>
    ... 5 more (keyword/label/consistency/recency/feedback)
  </div>
</details>
```

`syncWeights()` → 정규화 (합 = 1.0) + `POST /api/weights` + 재검색.

- [ ] **Step 2: 자동 테스트** — `/api/weights` POST → Config 갱신.

- [ ] **Step 3: 커밋** — `feat(m5): D 탭 슬라이더 펼침 (6 채널 + 자동 정규화)`.

#### Task 3.14 — D 탭: 저장된 검색 리스트 + CRUD

**Files:** Modify `_side_panel_d.html`. M4 의 `routers/saved_searches.py` 활용.

- [ ] **Step 1**: 리스트:

```html
<ul class="saved-searches" x-data="{ items: [] }" x-init="fetchSaved()">
  <template x-for="ss in items" :key="ss.id">
    <li @click="loadSaved(ss)" @contextmenu.prevent="showCtx(ss, $event)">
      <span x-text="ss.name"></span>
      <small x-text="relativeTime(ss.last_used_at)"></small>
    </li>
  </template>
</ul>
<button @click="saveCurrent()">{{ _('+ 현재 검색 저장') }}</button>
```

`loadSaved(ss)` → `POST /api/saved-searches/run/{ss.id}` → 응답으로 검색 바 + 필터 + 슬라이더 복원.

- [ ] **Step 2: `routers/saved_searches.py` (M4 백엔드 그대로)**

- [ ] **Step 3: 자동 테스트** — 8 케이스 (§2.2 `test_web_routers_saved_searches.py`).

- [ ] **Step 4: 커밋** — `feat(m5): D 탭 저장된 검색 리스트 + 저장/삭제/실행`.

#### Task 3.15 — D 탭: 통일성/페널티 요약 + 상세 모달

**Files:** Modify `_side_panel_d.html`. Create `_modal_usage.html`. Modify `core/store.py` (`usage_summary_for_project`).

- [ ] **Step 1: Store 메서드 신규** — `usage_summary_for_project(project_id: int|None) -> dict`:

```python
{
  "top_packs": [{"pack": "pack_a", "uses": 12}, ...],
  "rejected_count": 2,
  "window_seconds": 2_592_000,
}
```

- [ ] **Step 2: 라우트** — `GET /api/usage/summary?project_id=...` + `GET /ui/usage/detail?project_id=...` (모달 HTML).

- [ ] **Step 3: D 탭 표시** — 간단 텍스트 + "상세 보기" 버튼이 모달 트리거.

- [ ] **Step 4: 자동 테스트** — `usage_summary_for_project` 정확 / `/api/usage/summary` 응답.

- [ ] **Step 5: 커밋** — `feat(m5): D 탭 통일성/페널티 요약 + 상세 모달`.

#### Task 3.16 — 반응형 (768px 이하 사이드 자동 닫힘)

**Files:** Modify `main.css`.

- [ ] **Step 1**: 미디어 쿼리:

```css
@media (max-width: 768px) {
  .side-panel { position: fixed; right: 0; top: 0; height: 100%; box-shadow: -4px 0 16px rgba(0,0,0,0.2); }
  .side-panel:not(.open) { transform: translateX(100%); }
}
```

- [ ] **Step 2: JS** — 화면 폭 변경 watch → 768px 이하 시 `$store.advanced.open=false`.

- [ ] **Step 3: 커밋** — `feat(m5): 반응형 (≤768px 사이드 패널 자동 닫힘 + 모달 전환)`.

#### Task 3.17 — Phase 3 회귀

- [ ] `pytest -q` → ~560 passed + skipped.

#### Task 3.18 — Phase 3 수동 시각 검증

- [ ] 사용자가 브라우저에서 검색 / 칩 / 슬라이더 / 저장된 검색 / 다축 필터 / 카드 크기 / 정렬 시각 검증. 4 페인 (정보 과부하 / 좌우 스크롤 / 섹션 불명 / 가중치 불가해) 해소 확인. M5_verification.md 의 §4 에 단계별 체크리스트로 별도 제시 (메모리 `feedback_milestone_manual_verification_format`).

---

### 4.4 Phase 4 — Claude `request_user_pick` + SSE push (~1주)

이 phase 가 M5 의 핵심 신규 기능. MCP server (별도 프로세스) → 트레이 측 FastAPI 의 HTTP loopback long-poll → SSE 브라우저 push → 사용자 클릭 → MCP 응답.

#### Task 4.1 — `/internal/user-pick` POST (MCP loopback long-poll)

**Files:** Modify `src/gah/web/routers/picks.py`. Test `tests/test_web_routers_picks.py` (12 케이스).

- [ ] **Step 1: 실패 테스트 (3 핵심)** — POST 정상 → request_id + 200 (mock future.set_result 후) / 5분 timeout → 408 / candidates 11개 → 422 / project_id null 도 OK.

```python
@pytest.mark.asyncio
async def test_internal_user_pick_resolved(deps_fixture, async_client):
    # 별도 task 에서 0.2s 후 resolve
    async def _resolver():
        await asyncio.sleep(0.2)
        snapshot = deps_fixture.pending_picks.snapshot()
        assert len(snapshot) == 1
        rid = snapshot[0]["request_id"]
        deps_fixture.pending_picks.resolve(rid, picked_asset_id=158, user_note=None)
    asyncio.create_task(_resolver())
    r = await async_client.post("/internal/user-pick", json={"candidates": [142,158,203], "reason": "test", "project_id": None, "timeout_seconds": 5})
    assert r.status_code == 200
    assert r.json()["picked_asset_id"] == 158
```

- [ ] **Step 2: 구현** — `routers/picks.py`:

```python
from pydantic import BaseModel, Field

class InternalPickRequest(BaseModel):
    candidates: list[int] = Field(min_length=1, max_length=10)
    reason: str | None = None
    project_id: str | None = None
    timeout_seconds: int = Field(default=300, ge=10, le=1800)

router = APIRouter(tags=["picks"])

@router.post("/internal/user-pick")
async def internal_user_pick(req: InternalPickRequest, request: Request) -> dict:
    deps: WebDeps = request.app.state.deps
    try:
        pending = deps.pending_picks.register(req.candidates, req.reason, req.project_id)
    except MaxPendingExceeded:
        raise HTTPException(status_code=503, detail={"code": "503_too_many_pending"})

    # SSE broadcast
    from ..sse_bus import broadcast
    broadcast("user_pick_request", {
        "request_id": pending.request_id,
        "candidates": req.candidates,
        "reason": req.reason,
        "project_id": req.project_id,
    })

    # 트레이 알림
    _notify_tray_pick_count(deps, +1)

    try:
        result = await asyncio.wait_for(pending.future, timeout=req.timeout_seconds)
        # 자동 record_asset_use (Phase 4 Task 4.10)
        _auto_record_asset_use(deps, pending, result)
        return result
    except asyncio.TimeoutError:
        deps.pending_picks.expire(pending.request_id)
        raise HTTPException(status_code=408, detail={"code": "408_timeout"})
    except UserCancelledError:
        raise HTTPException(status_code=499, detail={"code": "499_user_cancelled"})
    finally:
        _notify_tray_pick_count(deps, -1)
```

- [ ] **Step 3**: `pytest tests/test_web_routers_picks.py::test_internal* -v` → 핵심 3 passed.

- [ ] **Step 4: 커밋** — `feat(m5): /internal/user-pick POST long-poll (5분 timeout + MaxPending)`.

#### Task 4.2 — `/api/user-pick/{rid}` POST (사용자 응답) + `/cancel`

**Files:** Modify `routers/picks.py`.

- [ ] **Step 1: 실패 테스트** — 정상 응답 → future.set_result / SSE `user_pick_resolved` push / 미존재 rid → 404 / 이미 resolved 후 또 응답 → 409 / cancel → 499 응답.

- [ ] **Step 2: 구현**:

```python
class UserPickBody(BaseModel):
    picked_asset_id: int
    user_note: str | None = None

@router.post("/api/user-pick/{rid}")
def api_user_pick(rid: str, body: UserPickBody, request: Request) -> dict:
    deps = request.app.state.deps
    ok = deps.pending_picks.resolve(rid, body.picked_asset_id, body.user_note)
    if not ok:
        snap = {p["request_id"]: p for p in deps.pending_picks.snapshot()}
        if rid not in snap: raise HTTPException(404)
        raise HTTPException(409, detail={"code": "409_already_resolved"})
    from ..sse_bus import broadcast
    broadcast("user_pick_resolved", {"request_id": rid, "picked_asset_id": body.picked_asset_id})
    return {"ok": True}

@router.post("/api/user-pick/{rid}/cancel")
def api_user_pick_cancel(rid: str, request: Request) -> dict:
    deps = request.app.state.deps
    ok = deps.pending_picks.cancel(rid, reason="user_cancelled")
    if not ok: raise HTTPException(404)
    from ..sse_bus import broadcast
    broadcast("user_pick_resolved", {"request_id": rid, "cancelled": True})
    return {"ok": True}
```

- [ ] **Step 3**: 4 케이스 passed.

- [ ] **Step 4: 커밋** — `feat(m5): /api/user-pick {rid} 응답/거부 + SSE user_pick_resolved 발화`.

#### Task 4.3 — `/sse/notifications` SSE 엔드포인트

**Files:** Create `src/gah/web/routers/sse.py`. Test `tests/test_web_routers_sse.py` (6 케이스).

- [ ] **Step 1: 실패 테스트** — `/sse/notifications` GET → text/event-stream 200 / `user_pick_request` 이벤트 push / heartbeat 15초 (mocked clock) / 여러 클라이언트 broadcast / 연결 종료 → unsubscribe.

- [ ] **Step 2: 구현**:

```python
from sse_starlette.sse import EventSourceResponse
from ..sse_bus import subscribe, unsubscribe
import asyncio, json

router = APIRouter(prefix="/sse", tags=["sse"])

@router.get("/notifications")
async def sse_notifications(request: Request):
    q = subscribe()
    async def event_stream():
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield {"event": msg["event"], "data": json.dumps(msg["data"])}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}  # heartbeat
                if await request.is_disconnected(): break
        finally:
            unsubscribe(q)
    return EventSourceResponse(event_stream())
```

- [ ] **Step 3**: 6 케이스 passed.

- [ ] **Step 4: 커밋** — `feat(m5): /sse/notifications (sse-starlette + subscribe/unsubscribe + heartbeat)`.

#### Task 4.4 — `/ui/pick-card/{rid}` HTML fragment + `_pick_card.html`

**Files:** Create `web/templates/_pick_card.html`. Modify `routers/picks.py`.

- [ ] **Step 1: `_pick_card.html`** — 보라색 좌측 띠 + 🤖 배지 + 후보 5 자산 카드 + [채택] / [✕ 거부]:

```html
<div class="pick-card-group" data-rid="{{ rid }}">
  <div class="pick-header">
    <span class="badge">🤖 {{ _('Claude 요청') }}</span>
    <span class="reason">{{ reason or _('후보 중 골라줘') }}</span>
    <button class="cancel" hx-post="/api/user-pick/{{ rid }}/cancel" hx-target="closest .pick-card-group" hx-swap="outerHTML">✕ {{ _('거부') }}</button>
  </div>
  <div class="pick-candidates">
    {% for asset in candidates %}
      <div class="card-wide purple-strip" data-asset-id="{{ asset.id }}">
        <!-- 일반 와이드 카드와 동일 + [채택] 버튼 -->
        <button class="adopt" hx-post="/api/user-pick/{{ rid }}" hx-vals='{"picked_asset_id": {{ asset.id }}}' hx-ext="json-enc" hx-target="closest .pick-card-group" hx-swap="outerHTML">{{ _('채택') }}</button>
      </div>
    {% endfor %}
  </div>
</div>
```

- [ ] **Step 2: 라우트** — `GET /ui/pick-card/{rid}` → 후보 asset 메타 fetch + render.

- [ ] **Step 3: 커밋** — `feat(m5): Claude 요청 카드 partial (보라색 띠 + 🤖 배지 + 채택/거부)`.

#### Task 4.5 — SSE 클라이언트 (HTMX hx-ext + Alpine pickQueue store)

**Files:** Modify `web/templates/base.html`, `web/static/js/app.js`.

- [ ] **Step 1: SSE 구독** — base.html:

```html
<div hx-ext="sse" sse-connect="/sse/notifications">
  <div sse-swap="user_pick_request" hx-on::sse-message="onPickRequest(event.detail)"></div>
  <div sse-swap="user_pick_resolved" hx-on::sse-message="onPickResolved(event.detail)"></div>
</div>
```

- [ ] **Step 2: JS handlers** — `app.js`:

```js
window.onPickRequest = (msg) => {
  const data = JSON.parse(msg.data);
  Alpine.store('pickQueue').items.unshift(data);
  Alpine.store('notifications').pickCount = Alpine.store('pickQueue').items.length;
  // 결과 영역 상단에 _pick_card.html fetch 후 insert
  htmx.ajax('GET', `/ui/pick-card/${data.request_id}`, {target: '#pick-cards', swap: 'afterbegin'});
};

window.onPickResolved = (msg) => {
  const data = JSON.parse(msg.data);
  Alpine.store('pickQueue').items = Alpine.store('pickQueue').items.filter(x => x.request_id !== data.request_id);
  Alpine.store('notifications').pickCount = Alpine.store('pickQueue').items.length;
  // DOM 의 해당 pick-card 자동 swap-out (htmx 가 응답 받은 쪽에서)
};
```

- [ ] **Step 3: `library.html` 에 `#pick-cards` 컨테이너** — 결과 영역 위:

```html
<div id="pick-cards"></div>
```

- [ ] **Step 4: 커밋** — `feat(m5): SSE 클라이언트 + Alpine pickQueue store + 결과 영역 상단 카드`.

#### Task 4.6 — 헤더 배지 카운트

**Files:** Modify `_nav.html`.

- [ ] **Step 1**: 알림 배지:

```html
<span class="notif-badge" x-show="$store.notifications.pickCount > 0">
  🤖 {{ _('Claude 요청') }} (<span x-text="$store.notifications.pickCount"></span>)
</span>
```

- [ ] **Step 2: 커밋** — `feat(m5): 헤더 알림 배지 (Claude 요청 카운트)`.

#### Task 4.7 — `request_user_pick` MCP 모델 + 도구 등록

**Files:** Modify `src/gah/mcp/models.py`. Modify `src/gah/mcp/server.py`.

- [ ] **Step 1: 모델 추가** — `models.py`:

```python
class RequestUserPickRequest(_BaseModel):
    candidates: list[int] = Field(min_length=1, max_length=10)
    reason: str | None = None
    project_id: str | None = None
    timeout_seconds: int = Field(default=300, ge=10, le=1800)

class RequestUserPickResult(_BaseModel):
    picked_asset_id: int
    picked_at: int
    user_note: str | None = None
```

- [ ] **Step 2: 도구 등록 — `server.py` `register_all_tools`**:

```python
@server.tool(description="후보 자산들 중 사용자가 직접 고르도록 요청한다. 5분 long-poll. GAH 의 웹 UI 가 떠 있어야 동작.")
def request_user_pick(req: m.RequestUserPickRequest) -> m.RequestUserPickResult:
    return t.tool_request_user_pick(deps, req)
```

`INSTRUCTIONS` 갱신 — 7번째 단계 추가 (Claude 가 ~5 후보 중 확신 없을 때 호출).

- [ ] **Step 3: 자동 테스트** — `tests/test_mcp_tools_m5.py` 의 시그니처 + Pydantic 검증 케이스.

- [ ] **Step 4: 커밋** — `feat(m5): MCP request_user_pick 도구 등록 (16 → 17 도구)`.

#### Task 4.8 — `tool_request_user_pick` 구현 (HTTP loopback)

**Files:** Modify `src/gah/mcp/tools.py`.

- [ ] **Step 1: 실패 테스트** — `tests/test_mcp_tools_m5.py` 의 10 케이스 (§2.2). 핵심: web.port 파일 부재 → 503 / loopback 200 → RequestUserPickResult / 408 패스스루 / 499 패스스루 / ConnectError → 503 / 자동 record_asset_use 호출 검증.

- [ ] **Step 2: 구현**:

```python
def tool_request_user_pick(deps: ToolDeps, req: m.RequestUserPickRequest) -> m.RequestUserPickResult:
    from ..web.url import read_web_port
    port = read_web_port(deps.paths.data_dir) if deps.paths else None
    if port is None:
        raise McpError("503_no_ui_available", "GAH 웹 UI 가 떠 있지 않습니다. 트레이 모드로 GAH 를 실행해주세요.")
    url = f"http://{deps.config.web_host}:{port}/internal/user-pick"
    try:
        with httpx.Client(timeout=req.timeout_seconds + 10) as c:
            r = c.post(url, json=req.model_dump(exclude_none=False))
        if r.status_code == 200:
            result = m.RequestUserPickResult(**r.json())
            _auto_record_asset_use(deps, req, result)
            return result
        if r.status_code == 408: raise McpError("408_timeout", "사용자가 5분 안에 응답하지 않았습니다.")
        if r.status_code == 499: raise McpError("499_user_cancelled", "사용자가 거부했습니다.")
        if r.status_code == 503: raise McpError("503_too_many_pending", "Pending 요청이 너무 많습니다.")
        raise McpError(f"{r.status_code}_unknown", r.text)
    except httpx.ConnectError:
        raise McpError("503_no_ui_available", "GAH 웹 UI 연결 실패.")

def _auto_record_asset_use(deps, req, result) -> None:
    if req.project_id is None:
        log.info("request_user_pick: project_id 없음 → record_asset_use 스킵")
        return
    try:
        record_req = m.RecordAssetUseRequest(
            asset_id=result.picked_asset_id,
            project_id=req.project_id,
            query_id=None,
            context=req.reason,
            source="claude_pick",
        )
        tool_record_asset_use(deps, record_req)
    except Exception as e:
        log.warning("자동 record_asset_use 실패: %s", e)
```

- [ ] **Step 3: `RecordAssetUseRequest` 에 `source` 필드 추가** — `models.py` (현재 source 없으면 신규):

```python
class RecordAssetUseRequest(_BaseModel):
    ...
    source: str = "manual"  # "manual" | "mcp" | "claude_pick" | "implicit_top1"
```

`tool_record_asset_use` 가 source 를 `store.record_asset_use(..., source=req.source)` 로 전달.

- [ ] **Step 4**: `pytest tests/test_mcp_tools_m5.py -v` → 10 passed.

- [ ] **Step 5: 회귀** — `pytest -m mcp_integration -v` → 2 passed (17 도구).

- [ ] **Step 6: 커밋** — `feat(m5): tool_request_user_pick + httpx loopback + 자동 record_asset_use (source=claude_pick)`.

#### Task 4.9 — MCP `run_stdio` 가 web.port 읽기

**Files:** Modify `src/gah/mcp/server.py`.

- [ ] **Step 1: `run_stdio()` 갱신** — paths 만 받음 (config.web_host + 파일 read 는 tool 호출 시점에).

```python
# build_server 에 paths 주입 — 이미 시그니처에 있음 (M3)
server = build_server(store=store, search=search, usage=usage, registry=registry, queue=None, config=cfg, paths=paths)
```

`ToolDeps.paths` 가 `tool_request_user_pick` 에서 `read_web_port(paths.data_dir)` 호출.

- [ ] **Step 2: 자동 테스트** — paths.data_dir/web.port 가 없으면 503 / 있으면 loopback 성공.

- [ ] **Step 3: 커밋** — `feat(m5): MCP run_stdio paths 전파 + web.port 동적 읽기`.

#### Task 4.10 — 트레이 아이콘 깜빡임 (Qt thread-safe signal)

**Files:** Modify `src/gah/web/routers/picks.py` (notify_tray 헬퍼). Modify `src/gah/app.py` (signal 연결).

- [ ] **Step 1: in-process signal 구조**

`app.py` 에서 PendingPickQueue 가 count 변경 시 broadcast 하도록 hook 추가, 또는 SSE bus 가 `user_pick_request` / `user_pick_resolved` 이벤트를 동시에 Qt main thread 의 slot 으로 푸시. 가장 단순: `notify_tray_pick_count` 헬퍼 가 `_subscribers` 리스트 같은 thread-safe 채널로 Qt 시그널 발화.

```python
# app.py
class _TrayBridge(QObject):
    pickCountChanged = Signal(int)

bridge = _TrayBridge()
bridge.pickCountChanged.connect(lambda n: notify_user_pick_request(tray, n))

# routers/picks.py 가 bridge 를 deps.tray_bridge 로 받아 emit
```

- [ ] **Step 2: `WebDeps` 에 `tray_bridge: Optional[QObject]` 추가** — 트레이가 없는 환경 (MCP 단독) 에선 None.

- [ ] **Step 3: 자동 테스트** — `bridge.pickCountChanged.emit(3)` → `notify_user_pick_request(tray, 3)` 호출 (mock tray).

- [ ] **Step 4: 커밋** — `feat(m5): 트레이 아이콘 깜빡임 (Qt signal bridge + PendingPickQueue hook)`.

#### Task 4.11 — MCP integration test 갱신 (16 → 17 도구)

**Files:** Modify `tests/test_mcp_integration.py` (옵트인 `mcp_integration` 마크).

- [ ] **Step 1**: `tools/list` 응답 검증 16 → **17**. `request_user_pick` 포함 확인.

- [ ] **Step 2**: `pytest -m mcp_integration -v` → 2 passed.

- [ ] **Step 3: 커밋** — `test(m5): mcp_integration 17 도구 (request_user_pick) 검증 갱신`.

#### Task 4.12 — `docs/MCP_USAGE_GUIDE.md` 갱신

**Files:** Modify `docs/MCP_USAGE_GUIDE.md`.

- [ ] **Step 1**: §1 도구 표 16 → 17 (request_user_pick row 추가). §6 신규 — Claude 의 의사 결정 흐름 (자동 pick vs request_user_pick 분기 기준). 한국어. 5분 timeout / 거부 / 503 시나리오.

- [ ] **Step 2: 커밋** — `docs(m5): MCP_USAGE_GUIDE — request_user_pick + Claude 분기 기준 (16 → 17)`.

#### Task 4.13 — Phase 4 통합 수동 검증 (end-to-end)

- [ ] Claude Code 에서 `request_user_pick({candidates: [142,158,203], reason: "test", project_id: "D:/Unity/MyGame"})` 호출 → 브라우저에 카드 노출 → 채택 → Claude 응답 + 자동 record_asset_use 확인. timeout / 거부 시나리오도 수동 검증.

---

### 4.5 Phase 5 — Qt 위젯 폐기 + Pack/라벨 관리 웹 이식 (~0.5주)

#### Task 5.1 — Pack 페이지 백엔드 (`/api/packs` + `/ui/packs`)

**Files:** Modify `src/gah/web/routers/packs.py`. Test `tests/test_web_routers_packs.py` (7 케이스).

- [ ] **Step 1: 실패 테스트** — `/api/packs` GET → 팩 리스트 + 자산 수 + license + vendor / `/ui/packs` HTML / PATCH enable=False → store 갱신 / manual_override / 미존재 404 / 카운트 정확 / kind 분포.

- [ ] **Step 2: 구현** — Store `list_packs_with_stats(...)` 호출 위임. PATCH 는 `Pack` row 수정 + asset 재인덱싱 트리거 안 함 (분석 큐 자율 동작).

- [ ] **Step 3**: 7 케이스 passed.

- [ ] **Step 4: 커밋** — `feat(m5): Pack 페이지 백엔드 (/api/packs + /ui/packs + PATCH enable)`.

#### Task 5.2 — Pack 페이지 템플릿 (`packs.html`)

**Files:** Create `web/templates/packs.html`, `_pack_card.html`.

- [ ] **Step 1**: 팩 카드 그리드 — 매니페스트 요약 (이름/벤더/라이선스/팩 크기/자산 수/state) + 토글 버튼 enable/disable.

```html
<div class="pack-grid">
  {% for pack in packs %}
    <div class="pack-card">
      <h3>{{ pack.name }}</h3>
      <p>{{ pack.vendor or _('알 수 없음') }} · {{ pack.license or '?' }}</p>
      <p>{{ pack.kind_summary }} · {{ pack.asset_count }}{{ _('개') }}</p>
      <button hx-patch="/api/packs/{{ pack.id }}" hx-vals='{"enabled": {{ not pack.enabled|lower }}}' hx-target="closest .pack-card" hx-swap="outerHTML">
        {{ _('비활성') if pack.enabled else _('활성') }}
      </button>
    </div>
  {% endfor %}
</div>
```

- [ ] **Step 2: 커밋** — `feat(m5): Pack 페이지 템플릿 (카드 그리드 + enable/disable 토글)`.

#### Task 5.3 — 라벨 관리 페이지 백엔드 (`/api/labels` + `/ui/labels/admin`)

**Files:** Create/Modify `src/gah/web/routers/labels_admin.py`. Test `tests/test_web_routers_labels_admin.py` (9 케이스).

- [ ] **Step 1: 실패 테스트** — GET 전체 / POST 신규 + axis 검증 / PATCH description / DELETE 정상 + 사용 중 400 / import JSON / export GET → JSON / HTML 페이지 / signature 변경 SSE / 잘못된 axis 400.

- [ ] **Step 2: 구현** — `LabelRegistry` 메서드 위임 (add/update/delete/import/export/signature). signature 변경 시 SSE `labels_signature_changed` broadcast.

- [ ] **Step 3**: 9 케이스 passed.

- [ ] **Step 4: 커밋** — `feat(m5): 라벨 관리 페이지 백엔드 (CRUD + import/export + SSE signature)`.

#### Task 5.4 — 라벨 관리 페이지 템플릿 (`labels_admin.html`)

**Files:** Create `web/templates/labels_admin.html`.

- [ ] **Step 1**: 24 axis 탭 + axis 별 라벨 리스트 + 신규 라벨 추가 폼 + 편집/삭제 + import (파일 업로드) + export (JSON 다운로드).

- [ ] **Step 2: 커밋** — `feat(m5): 라벨 관리 페이지 템플릿 (24 axis 탭 + CRUD UI)`.

#### Task 5.5 — Qt UI 파일 4 + main_window + pack_view + labels_admin 삭제

**Files:**
- Delete: `src/gah/ui/library_view.py`
- Delete: `src/gah/ui/label_chip_panel.py`
- Delete: `src/gah/ui/search_side_panel.py`
- Delete: `src/gah/ui/filter_bar.py`
- Delete: `src/gah/ui/main_window.py`
- Delete: `src/gah/ui/pack_view.py`
- Delete: `src/gah/ui/labels_admin.py`
- Delete: `tests/test_library_search_ui.py`
- Delete: `tests/test_library_search_ui_rich.py`
- Delete: `tests/test_ui_smoke.py`
- Delete: `tests/test_labels_admin_ui.py`
- Modify: `src/gah/ui/__init__.py` (빈 marker 또는 디렉터리 통째로 삭제)

- [ ] **Step 1: 파일 삭제**

```powershell
Remove-Item src\gah\ui\library_view.py
Remove-Item src\gah\ui\label_chip_panel.py
Remove-Item src\gah\ui\search_side_panel.py
Remove-Item src\gah\ui\filter_bar.py
Remove-Item src\gah\ui\main_window.py
Remove-Item src\gah\ui\pack_view.py
Remove-Item src\gah\ui\labels_admin.py
Remove-Item tests\test_library_search_ui.py
Remove-Item tests\test_library_search_ui_rich.py
Remove-Item tests\test_ui_smoke.py
Remove-Item tests\test_labels_admin_ui.py
```

- [ ] **Step 2: `src/gah/ui/__init__.py` 정리** — Phase 1 task 1.7 에서 임시 skip 처리한 테스트 파일들도 함께 정리. `import gah.ui.main_window` 같은 references 가 코드에 남았는지 grep 확인.

- [ ] **Step 3: Grep 으로 잔존 import 확인**

```
Grep -r "from .ui" src/gah/
Grep -r "import.*main_window" src/gah/
Grep -r "ui.library_view" src/gah/
Grep -r "ui.labels_admin" src/gah/
```

남은 references 모두 제거. `app.py` 에서 `main_window` / `library_view` import 가 task 1.7 에서 이미 제거됐어야.

- [ ] **Step 4: 전체 회귀** — `pytest -q` → ~580 passed + ~3 skipped (Phase 5 skip 마크가 풀려 0 skip 되어야 정상). 회귀 0 건.

- [ ] **Step 5: 커밋** — `feat(m5): Qt UI 위젯 7 파일 + 테스트 4 파일 폐기 (웹 UI 가 모두 대체)`.

#### Task 5.6 — 상단 네비게이션 + 페이지 라우트

**Files:** Modify `web/templates/_nav.html`, `web/templates/base.html`. Create `web/routers/pages.py`.

- [ ] **Step 1: 네비게이션**:

```html
<nav class="top-nav">
  <a href="/library" :class="{active: location.pathname.startsWith('/library')}">{{ _('라이브러리') }}</a>
  <a href="/packs">{{ _('팩') }}</a>
  <a href="/labels/admin">{{ _('라벨 관리') }}</a>
</nav>
```

- [ ] **Step 2: `routers/pages.py`** — `/` (→ /library) / `/library` / `/packs` / `/labels/admin` HTML 페이지 라우트.

- [ ] **Step 3: 커밋** — `feat(m5): 상단 네비게이션 + 4 페이지 라우트`.

#### Task 5.7 — 트레이 메뉴 단순화 (라벨 관리 메뉴 항목 제거)

**Files:** Modify `src/gah/tray.py` (Task 1.6 에서 이미 시그니처 변경, 본 task 는 검증).

- [ ] **Step 1**: 트레이 메뉴 = [메인 창 열기] + [라이브러리 폴더 열기] + [종료]. "라벨 관리" 항목 없음 (`/labels/admin` 웹 페이지로 대체).

- [ ] **Step 2: 자동 테스트 갱신 (Task 1.6 의 5 케이스 중 해당)**

- [ ] **Step 3: 커밋** — `chore(m5): 트레이 메뉴 — 라벨 관리 항목 제거 (웹 페이지로 대체)`.

#### Task 5.8 — Phase 5 회귀

- [ ] `pytest -q` → ~580 passed. `pytest -m mcp_integration` → 2 passed. 17 도구 정상.

---

### 4.6 Phase 6 — 마감 + 검증 (~0.5주)

#### Task 6.1 — 다크/라이트 모드 (prefers-color-scheme 자동)

**Files:** Modify `web/static/css/themes.css`.

- [ ] **Step 1**: CSS 변수 — light 디폴트 + `@media (prefers-color-scheme: dark)` override:

```css
:root {
  --bg: #fafafa; --fg: #1a1a1a; --card-bg: #fff;
  --border: #e0e0e0; --accent: #3b82f6;
  --chip-bg: #f0f0f0; --chip-active: #3b82f6; --purple-strip: #8b5cf6;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #1a1a1a; --fg: #fafafa; --card-bg: #2a2a2a; --border: #3a3a3a; ... }
}
```

- [ ] **Step 2: 수동 시각 검증** — OS 다크/라이트 토글 → 페이지 자동 반응.

- [ ] **Step 3: 커밋** — `feat(m5): 다크/라이트 모드 CSS 변수 (prefers-color-scheme 자동)`.

#### Task 6.2 — 에러 페이지 (404, 500)

**Files:** Modify `web/app.py`. Create `templates/error.html`.

- [ ] **Step 1: FastAPI exception handlers** — 404/500 시 `error.html` 렌더 (HTMX 요청은 fragment, 풀 페이지는 베이스 레이아웃).

- [ ] **Step 2: 커밋** — `feat(m5): 에러 페이지 (404/500 + HTMX fragment 분기)`.

#### Task 6.3 — `docs/WEB_UI_GUIDE.md` 작성

**Files:** Create `docs/WEB_UI_GUIDE.md`.

- [ ] **Step 1: 한국어 가이드** — 진입 / 라이브러리 페이지 / B/C/D 탭 / 검색 문법 / 단축키 / 다크 모드 / Claude 요청 카드 시나리오. ~300줄.

- [ ] **Step 2: 커밋** — `docs(m5): 사용자용 웹 UI 가이드 (한국어)`.

#### Task 6.4 — `DESIGN.md` 갱신

**Files:** Modify `DESIGN.md`.

- [ ] **Step 1**: §3 아키텍처 그림 갱신 (Qt + FastAPI + 브라우저 + MCP loopback). §4.5 MCP 표 17 도구. §4.8 트레이 + 웹 UI. §11 M5 완료 항목 정리 + M5 가 미룬 항목 명시.

- [ ] **Step 2: 커밋** — `docs(m5): DESIGN.md §3/§4.5/§4.8/§11 갱신`.

#### Task 6.5 — `README.md` 갱신

**Files:** Modify `README.md`.

- [ ] **Step 1**: 사용법 — 트레이 메뉴 "메인 창 열기" → 브라우저 자동 진입. 스크린샷 placeholder.

- [ ] **Step 2: 커밋** — `docs(m5): README 사용법 — 웹 UI 진입 흐름 안내`.

#### Task 6.6 — `CLAUDE.md` §2 / §8 갱신

**Files:** Modify `CLAUDE.md`.

- [ ] **Step 1**: §2 진행 현황 표 — M5 행 "✅ 완료". §8 "다음 작업" → M6 시트 분석. 새 의존성 (FastAPI 등) 안내.

- [ ] **Step 2: 커밋** — `docs(m5): CLAUDE.md §2 진행 현황 + §8 다음 작업 (M6)`.

#### Task 6.7 — `HANDOFF.md` 갱신 (M5 완료 인계)

**Files:** Modify `HANDOFF.md`.

- [ ] **Step 1: §1 / §2 / §5 갱신** — 자동 테스트 통과 카운트 + 17 MCP 도구 + 시나리오 4개 + 다음 작업 (M6).

- [ ] **Step 2: 커밋** — `docs(m5): HANDOFF M5 완료 인계 — 17 도구 + 웹 UI + 폐기 7파일`.

#### Task 6.8 — `M5_verification.md` 작성

**Files:** Create `milestones/M5_verification.md`.

- [ ] **Step 1**: 표준 형식 (M2/M3/M4 verification 기반) — §1 자동 (`pytest -v` 출력) / §2 mcp_integration / §3 알려진 한계 / §4 사용자 수동 검증 체크리스트.

§4 수동 검증 — 단계별 체크리스트 (메모리 `feedback_milestone_manual_verification_format`):

```
[ ] (1) 트레이 부팅 → 시스템 브라우저 자동 진입 (또는 메뉴 클릭으로)
[ ] (2) 검색 바에 "blue hero" 입력 → 300ms 후 결과 갱신
[ ] (3) ⚙ 고급 클릭 → 사이드 패널 슬라이드 인 + B 탭 디폴트
[ ] (4) B 탭 — 칩 클릭 → 결과 갱신 + 좌우 스크롤 없음
[ ] (5) C 탭 — 그리드/리스트 토글 → 결과 영역 즉시 변경
[ ] (6) D 탭 — "통일성 우선" 프리셋 → 슬라이더 갱신 + 결과 재정렬
[ ] (7) 저장된 검색 — 저장 후 다른 검색 → 저장된 항목 클릭 → 복원
[ ] (8) 사운드 카드 ▶ 클릭 → 인라인 audio 재생
[ ] (9) 카드 클릭 → 모달 + 채택 버튼
[ ] (10) Claude Code 에서 request_user_pick 호출 → 카드 노출 → 채택 → Claude 응답 + 자동 record_asset_use 확인
[ ] (11) 거부 시나리오 — [✕ 거부] → 499_user_cancelled
[ ] (12) Timeout — 5분 미응답 → 408_timeout
[ ] (13) Pack 페이지 — 카드 그리드 + enable/disable 토글
[ ] (14) 라벨 관리 페이지 — 24 axis 탭 + 신규 라벨 + 삭제
[ ] (15) 다크 모드 OS 토글 → 웹 페이지 자동 반응
[ ] (16) 반응형 — 브라우저 폭 ≤768px → 사이드 자동 닫힘
[ ] (17) 트레이 종료 → 웹서버 graceful shutdown (포트 해제 확인)
```

- [ ] **Step 2: 커밋** — `docs(m5): M5_verification — 자동 + mcp_integration + 17 수동 체크리스트`.

#### Task 6.9 — 메모리 갱신

**Files:** `memory/MEMORY.md`, 신규 또는 갱신.

- [ ] **Step 1**: `project_m5_web_gui_decision.md` 갱신 — "완료" 마크 + 실제로 한 일 요약 (한 줄).

신규 메모리 (필요 시):
- `project_m5_pending_pick_pattern.md` — HTTP loopback long-poll + asyncio.Future 패턴 (M6+ 가 비슷한 패턴 쓸 때 참고).

- [ ] **Step 2: 커밋** — `chore(m5): 메모리 갱신 (M5 완료 + pending-pick 패턴)`.

#### Task 6.10 — Phase 6 회귀 + PR 생성

- [ ] **Step 1: 전체 회귀** — `pytest -q` → ~580 passed. `pytest -m mcp_integration -v` → 2 passed (17 도구).
- [ ] **Step 2: 사용자 수동 검증 17 단계 통과 확인**
- [ ] **Step 3: PR 생성** — `gh pr create --title "M5 웹 GUI 전환 + Claude pick" --body "..."` (한국어, M5 spec 링크 + 시나리오 4개 + 검증 결과)

---

## 5. 신규 의존성

`pyproject.toml` 의 `[project] dependencies` 에 5 줄 추가 (Phase 0 Task 0.1):

```toml
"fastapi>=0.110",
"uvicorn[standard]>=0.27",     # standard extra = httptools + websockets + watchfiles
"jinja2>=3.1",
"python-multipart>=0.0.9",     # form 데이터 (HTMX POST)
"sse-starlette>=2",            # FastAPI 친화 SSE
```

기존 의존성 그대로 재사용 — `httpx>=0.27` (M2, MCP loopback 에 사용), `pydantic>=2.6` (M2, FastAPI 모델), `Pillow>=10` (M2, thumbnail), `mcp>=1.27,<2` (M3, 도구 17 등록).

PyInstaller (M8) 패키징은 정적 자원 (`web/static/`) 을 wheel 안에 포함해야 — `pyproject.toml` `[tool.setuptools.package-data]` 갱신:

```toml
[tool.setuptools.package-data]
gah = ["web/static/**/*", "web/templates/**/*"]
```

이건 Task 0.3 / 1.4 시점에 같이 갱신.

## 6. DB 마이그레이션

**M5 는 신규 테이블 / 인덱스 / 컬럼 추가 없음**. M4 의 21+5=26 객체 그대로.

- `asset_uses.source` 컬럼은 M3 부터 존재 (`'manual'` / `'mcp'` / `'implicit_top1'`). M5 가 `'claude_pick'` 값을 새로 사용하지만 스키마 변경 X (TEXT 컬럼이라 enum 확장만).
- Config 의 `UsageSource` enum 은 새 값 추가 — 기존 데이터 (다른 source 값) 와 호환.

Migration 잡 불필요. `Store.initialize()` 의 `_M0_SCHEMA + _M1_SCHEMA + _M2_SCHEMA + _M3_SCHEMA + _M4_SCHEMA` 순차 실행 그대로.

## 7. 회귀 / 검증 전략

### 7.1 자동 회귀 — `pytest -q`

| 영역 | 케이스 수 | M5 영향 |
|---|---:|---|
| M0 (설정/로깅/single instance/CLI/imports) | 18 | 0 |
| M1 (워처/매니페스트/store/scanner) | 49 | 0 |
| M2 (분석 파이프라인 + label registry + queue) | 134 | 0 |
| M2.1 (큐 동시성 패치) | 17 | 0 |
| M3 (HybridSearcher 5채널 + 12 MCP) | 112 | 0 |
| M4 (label_query + 6채널 + saved_searches + feedback + 16 MCP) | 100 + 19 | 0 (Qt 위젯 회귀는 폐기로 흡수) |
| M5 web/config (config_m5 + web_url + web_pending + web_server + web_app + web_i18n) | ~40 | 신규 |
| M5 web/routers (library + filters + saved + feedback + packs + labels + picks + sse) | ~75 | 신규 |
| M5 mcp (mcp_tools_m5 + tray_m5 + app_m5) | ~21 | 신규 |
| **합계 (M5 끝)** | **~580 active** + 4 deselected | 기존 회귀 0 (Qt 폐기 흡수) |

`pytest -m mcp_integration -v` — 2/2 통과 (17 도구).

### 7.2 수동 검증

§4 Phase 6 Task 6.8 의 `M5_verification.md §4` 17 단계 체크리스트. 사용자가 단계별로 시각 확인 후 verification 의 체크박스에 표시. 미통과 항목은 알려진 한계로 §3 에 기록.

### 7.3 회귀 보호 — 폐기 흡수 검증

Phase 5 Task 5.5 에서 Qt 위젯 파일 7 + 테스트 4 삭제 후 `pytest -q` 가 회귀 0 으로 깨끗하게 떨어지는지 확인. 잔존 import (`from gah.ui.library_view`, `from gah.ui.main_window` 등) 가 한 곳도 남으면 안 됨 — Phase 5 Task 5.5 의 Step 3 grep 으로 검증.

## 8. 명확화 — 의도적으로 미룬 항목

다음 항목들은 M5 의 spec 또는 본 plan 에서 의도적으로 v1 범위 밖. 후속 마일스톤이 채움.

| 항목 | 미룸 마일스톤 | 이유 |
|---|---|---|
| 사용자 다크 모드 토글 UI | M8 | OS 따라가기만 v1 |
| 본격 모바일 최적화 | M7+ | ≤768px 사이드 자동 닫힘만 v1 |
| LAN 멀티 접속 + 토큰 인증 | M7+ | 로컬 단일 사용자만 v1 |
| Playwright e2e 자동화 | M6+ | 백엔드 + 단위만 v1 |
| Pack/라벨 관리 풍부 UX | M7 | 최소 CRUD 만 v1 |
| 사용자 자리비움 감지 → 자동 timeout 연장 | M5+ | 단순 5분 v1 |
| `request_user_pick` batch 모드 (한 번에 여러 그룹) | M6+ | 단일 선택만 v1 |
| `record_asset_use` 의 dedup (같은 자산 idempotent) | M6+ | 두 행 들어가도 통일성 계산은 윈도우 기반이라 영향 작음 |
| i18n 본격 (babel / gettext) | M8 | placeholder `_t()` 만 v1 |
| `assets.description` 컬럼 (Gemma description 영구 저장) | M6+ | 카드 모달은 분석 시 메모리만 조회 v1 |
| 결과 카드 hover 미리보기 / 키보드 단축키 / 비교 보기 | M7 | M5 의 마감 0.5주 안에 추가는 무리 |
| `cleanup_feedback_records` 잡 (윈도우 만료 행 정리) | M6+ | 검색 시 윈도우 필터만 v1 |
| `implicit_top1` 추정 (Config 기본 OFF) | M6+ | M3 부터 미룸. M5 도 그대로 OFF |
| Unity Asset Store 임포트 | M7 | 별도 마일스톤 |
| 시트 분석 + `suggest_animation_frames` | M6 | 별도 마일스톤 |

## 9. 자기 검토 메모

> writing-plans skill "Self-Review" 단계. 본 plan 을 fresh eyes 로 점검.

### 9.1 Spec coverage

- spec §1 배경 4 페인 → plan §1.2 의 시나리오 1.2 + plan §4.3 Phase 3 가 정밀 필터 / 결과 카드 / 사이드 패널 / 가중치 프리셋 으로 1:1 매핑 ✓
- spec §2 의 10 결정 → plan §3 + §4 의 각 task 가 1:1 매핑 ✓
- spec §3 아키텍처 → plan §1 + Task 1.4/1.5/4.1 ✓
- spec §4 라이브러리 탭 리디자인 → Phase 2 + Phase 3 ✓
- spec §5 Claude `request_user_pick` 흐름 9 단계 → Phase 4 Task 4.1-4.13 ✓
- spec §6 폐기/보존 경계 → Phase 5 Task 5.5 (7 파일 + 4 테스트 폐기) + plan §2.1 "보존" 행들 ✓
- spec §7 신규 의존성 5 → plan §5 ✓
- spec §8 테스트 전략 → plan §7 + 각 task 의 테스트 ✓
- spec §9 일정 5.5주 → plan §4 의 6 phase (0.5 + 1 + 1 + 1.5 + 1 + 0.5 + 0.5 ≈ 6주 — Phase 0 의 0.5일 + Phase 6 의 0.5주, 합 5.5~6주 범위) ✓
- spec §11 보안 → plan §1 + Task 1.5 (localhost only) ✓
- spec §12 미룬 항목 → plan §8 ✓
- spec §13 열린 질문 5 → plan §3.1-3.5 + §3.6-3.8 (신규 결정 3) ✓

### 9.2 Placeholder scan

- "TBD" / "implement later" / "fill in" 0 건. 모든 task 에 시그니처 + 코드 예시 포함 ✓
- "Add error handling" 같은 모호 표현 0 건 ✓
- "Similar to Task N" 류 자기참조 0 건 — 각 task 가 핵심 코드 직접 보여줌 ✓

### 9.3 Type consistency

- `PendingPick.future` (Task 1.2) ↔ `pending.future` (Task 4.1 `internal_user_pick`) ↔ `_auto_record_asset_use(deps, pending, result)` (Task 4.1) → pending 의 dataclass 시그니처 일관 ✓
- `WebDeps` 필드 (Task 1.3) ↔ 각 라우터에서 `request.app.state.deps` 로 접근 (Task 1.4) ✓
- `_t()` (Task 1.4) ↔ Jinja `{{ _(...) }}` (Phase 2 부터) ✓
- `UsageSource` enum (Task 0.2) ↔ `RecordAssetUseRequest.source` (Task 4.8) ↔ `tool_record_asset_use(source=...)` (Task 4.8) ✓
- `actual_port` (Task 1.5) ↔ `app.py` 의 `web.actual_port` (Task 1.7) ↔ `read_web_port` (Task 4.8) ✓
- `broadcast(event, data)` (Task 1.7 sse_bus) ↔ `routers/picks.py` 의 broadcast 호출 (Task 4.1) ↔ `routers/sse.py` 의 subscribe (Task 4.3) ✓

### 9.4 한국어 / 영어 규칙 (CLAUDE.md §4.1)

- 모든 문서 prose 한국어 ✓
- 파일/폴더 이름 영어 ✓
- 코드 식별자 영어 ✓
- 사용자 노출 문자열은 한국어 (`_t("자연어 검색…")` 패턴) ✓
- 커밋 메시지 — 한국어 본문 (CLAUDE.md §4.1 + 메모리 `feedback_korean_for_pr_and_commits`) ✓

### 9.5 명령 한 줄에 하나씩 (CLAUDE.md §4.3)

- Task 0.1 / 0.3 / 1.7 의 PowerShell 명령 모두 분리 줄 ✓
- `&&` 묶음 0 건 ✓

### 9.6 TDD 사이클 강제

- Phase 0~5 의 모든 신규 코드 task 가 "실패 테스트 → 실패 확인 → 구현 → 통과 확인 → 커밋" 5 단계 유지 ✓
- 일부 UI 시각 검증 task (Phase 2/3 의 수동 시각 검증 step) 는 자동 테스트 외 추가 단계 (CLAUDE.md §4.2) ✓
- Phase 6 의 docs / verification 은 코드 변경 0 이라 TDD 면제 ✓

### 9.7 메모리 일치성

- 자동 로드 메모리 11개 중 영향:
  - `feedback_milestone_manual_verification_format` → Task 6.8 §4 가 단계별 체크리스트로 별도 제시 ✓
  - `feedback_korean_for_pr_and_commits` → 모든 커밋 한국어 + PR description 한국어 (Task 6.10) ✓
  - `feedback_run_commands_directly` → Phase 0 의 pip install, 모든 pytest, gh pr create 모두 Claude 가 직접 실행 ✓
  - `project_m5_web_gui_decision` → 본 plan 이 그대로 풀어 씀 ✓
  - `project_output_language_strategy` → `_t()` placeholder 가 i18n 준비 (M8) ✓

### 9.8 잠재 리스크 (구현 시 주의)

1. **uvicorn 별도 스레드 + PySide6 메인 스레드 충돌** — Phase 1 Task 1.5 / 1.7 에서 Qt 시그널을 `QMetaObject.invokeMethod(Qt.QueuedConnection)` 로 마샬링. PySide6 의 QApplication 이 GUI thread 만 점유, uvicorn 이 다른 thread 의 별도 loop 이라 격리 가능. 단, `webbrowser.open` 은 어디서 호출하든 OK.
2. **MCP server 의 `paths.data_dir/web.port` 읽기 타이밍** — MCP server 가 `--mcp` 단독 실행 시 트레이가 안 떠 있을 수 있음. Task 4.8 의 `tool_request_user_pick` 만 503 으로 응답, 다른 도구는 정상 동작.
3. **PendingPickQueue 의 `asyncio.get_event_loop()`** — Python 3.10+ 에서 deprecated. Task 1.2 구현 시 `asyncio.get_running_loop()` 또는 `asyncio.get_event_loop_policy()` 사용. Pre-asyncio 코드 path 주의.
4. **HTMX hx-trigger `keyup changed delay:300ms`** — 한글 IME composing 중에 delay 가 reset 안 됨. 일부 환경에서 두 번 발화 가능. 수동 검증 단계에서 확인 + 필요 시 Alpine 디바운스 추가.
5. **SSE 의 `Last-Event-ID`** — sse-starlette 는 자동 처리, 재연결 시 미지원 이벤트는 무시. Task 4.3 의 broadcast 가 idempotent 인지 확인 — `user_pick_request` 는 한 번 push 되면 재발화 X (서버 측 state 가 single source).
6. **WebSocket 미사용 결정** — uvicorn[standard] 가 websockets 패키지를 transitive 로 끌고 옴. 사용 X 라도 ImportError 가 안 나는지 검증 (Task 0.1 의 import smoke).
7. **포트 9874 가 MCP server 의 미사용 `Config.mcp_port` 와 같음** — 충돌 없음 (MCP 는 stdio). 단 사용자 혼동 가능 — README 에 명시 (Task 6.5).

### 9.9 검토 끝

모든 spec 결정사항이 task 로 분해됐고, 폐기/보존 경계가 명확하며, TDD 사이클이 각 task 에 박혀 있다. 5.5주 일정 추정과 phase 일정 (0.5 + 1 + 1 + 1.5 + 1 + 0.5 + 0.5 = 6주) 가 살짝 over — Phase 0 의 0.5일을 Phase 1 안에 흡수하면 5.5주 ±. 위험 항목 7개 모두 구현 시점에 검증.

검토 끝.


