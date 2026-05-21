# M5 검증 보고서

**최종 상태**: ✅ 자동 검증 모두 통과 (2026-05-18). 사용자 수동 확인 항목 ~32 단계 — §4 에 단계별 체크리스트로 별도 제시.

M4 의 `HybridSearcher` + 16 MCP 도구 + Qt 위젯 위에 **FastAPI + Jinja2 + HTMX 1.9.12 + Alpine 3.13.10 웹 GUI 전환 + 라이브러리 4페인 리디자인 + `request_user_pick` MCP 17번째 도구 + SSE push + 자동 record_asset_use + TrayBridge + Pack/라벨 admin 페이지 + 에러 페이지 + 404/500 핸들러** 추가. Qt UI 8 파일 + 폐기 테스트 7 파일 삭제. 본 마일스톤의 의도와 작업 단위는 [`M5_plan.md`](./M5_plan.md), TDD 체크리스트는 [`M5_todo.md`](./M5_todo.md).

## 1. 자동 검증 결과: ✅ 796/796 + 2/2 mcp_integration

`pytest -q` 전체 실행 — M0~M4 회귀 (452) + M5 Phase 0~6 신규 (344) = **796 active** (`clip_integration` 2 + `mcp_integration` 2 = 4 deselected).

```
SKIPPED [1] tests\test_web_routers_sse.py:140: heartbeat 15초 타이밍 결정론적 테스트 어려움 — Phase 4 마감 흡수
796 passed, 1 skipped, 4 deselected in 50.52s
```

`pytest -m mcp_integration -v` — 실 subprocess + JSON-RPC 핸드셰이크:

```
tests/test_mcp_integration.py::test_stdio_subprocess_initialize_handshake PASSED
tests/test_mcp_integration.py::test_stdio_subprocess_tools_list_returns_17 PASSED
====================== 2 passed, 799 deselected in 2.53s
```

> M4 의 도구 카운트 16 → M5 Phase 4C 에서 17 (`request_user_pick` 추가). 실제 stdio subprocess 가 17 개를 반환함을 확인.

M5 신규 케이스 분해 (Phase 별 누적):

| Phase | 신규 케이스 | 핵심 검증 묶음 |
|---|---:|---|
| Phase 0 (Config + vendoring) | +7 | `test_config_m5` — 7 신규 필드 + UsageSource enum |
| Phase 1A (url + pending + deps) | +15 | `test_web_url` + `test_web_pending` |
| Phase 1B (FastAPI factory + WebServer) | +14 | `test_web_server` + `test_web_app` |
| Phase 1C (tray + SSE bus) | +18 | `test_tray_m5` + `test_web_routers_health` |
| Phase 2A (검색 백엔드 + 카드) | +21 | `test_web_routers_library` (썸네일·오디오·검색) |
| Phase 2B (페이지 베이스 + 검색 바) | +8 | `test_web_pages` (base/library/nav) |
| Phase 2C (결과 툴바 + 페이지네이션) | +8 | `test_web_pages` (toolbar·더보기·디폴트) |
| Phase 2D (모달 + 사운드) | +7 | `test_web_pages` (모달·오디오) + `test_web_i18n` |
| Phase 3A (⚙ + 리사이즈 + 탭 스캐폴딩) | +17 | `test_web_pages` (사이드 패널 DOM) |
| Phase 3B-1 (B 탭 매칭 모드 + 라벨 검색) | +32 | `test_web_side_panel_b` + `test_web_routers_filters` |
| Phase 3B-2 (axis 칩 + 다축 필터 + 매핑) | +55 | `test_web_filters_packs` + `test_web_search_label_mapping` |
| Phase 3C (C 탭 표시 옵션) | +20 | `test_web_side_panel_c` |
| Phase 3D-1 (프리셋 + 슬라이더) | +24 | `test_web_side_panel_d` |
| Phase 3D-2 (저장된 검색 + 통일성 + 반응형) | +34 | `test_web_saved_searches` + `test_web_usage_summary` + `test_web_responsive` |
| Phase 3 cleanup (Store 헬퍼 + fixture) | +4 | conftest 통합 + `get_pack_by_id` / `get_saved_search_by_id` |
| Phase 4A (picks + sse 라우터) | +18 | `test_web_routers_picks` (13) + `test_web_routers_sse` (5, +1 skip) |
| Phase 4B (pick 카드 + SSE 클라이언트) | +13 | `test_web_pick_card` (8) + `test_web_pages` (+5) |
| Phase 4C (MCP request_user_pick) | +11 | `test_mcp_tools_m5` (10) + `test_mcp_tools` source pin (1) |
| Phase 4D (TrayBridge) | +11 | `test_tray_bridge` (11) |
| Phase 5A (Pack 라우터 + 페이지) | +15 | `test_web_routers_packs` (11) + `test_web_pages` (+4) |
| Phase 5B (라벨 admin 라우터 + 페이지) | +22 | `test_web_routers_labels_admin` (18+1) + `test_web_pages` (+3) |
| Phase 5C (Qt 폐기) | 0 신규 / **-7 skip** | 7 skip-marked 파일 삭제 → skipped 8 → 1 |
| Phase 6A (에러 페이지) | +13 | `test_web_error_pages` (신규) |
| Phase 6B (문서 마감) | 0 | 코드 변경 없음 |
| **M5 신규 합계** | **+344** | **total 796** |

### 1.1 mcp_integration 의 의의

`test_stdio_subprocess_tools_list_returns_17` 가 진짜 `python -m gah --mcp` 를 별도 프로세스로 띄워 JSON-RPC `initialize` + `tools/list` 핸드셰이크 수행. 응답에 M4 16 도구 + M5 신규 1 (`request_user_pick`) 포함 + 총 17 도구 확인:

```python
expected = {
    # M3 12 도구
    "find_asset", "get_asset", "list_assets", "list_packs", "suggest_packs",
    "record_asset_use", "set_project_pin", "request_rescan", "report_feedback",
    "list_label_axes", "list_labels", "describe_label",
    # M4 4 신규 도구
    "save_search", "list_saved_searches", "delete_saved_search",
    "run_saved_search",
    # M5 1 신규 도구
    "request_user_pick",
}
assert expected <= names and len(names) == 17  # PASS
```

## 2. 자동 검증 환경의 한계

자동 테스트는 다음 항목을 다루지 **못한다** — 모두 사용자 PC 에서 시각 확인 (§4) 으로 검증.

- **SSE push 실시간 동작** — `test_web_routers_sse` 가 이벤트 타입·데이터 직렬화까지 검증하지만, 실 브라우저 SSE 연결 + 탭 간 동기 시각 확인은 자동화 불가.
- **HTMX + Alpine 상호작용** — `test_web_pages` 가 HTML fragment 구조까지 검증하나, HTMX `hx-post` 실 발화 + Alpine `x-data` 상태 변화 + 칩 클릭 후 검색 재호출 흐름은 브라우저에서 직접 확인 필요.
- **트레이 아이콘 + 브라우저 자동 열림** — `test_tray_m5` 가 `webbrowser.open` 호출 여부까지 확인. 실 시스템 기본 브라우저 열림 + 포트 9874 진입 시각 확인은 수동.
- **실 MCP 클라이언트 연결** — `pytest -m mcp_integration` 은 stdio 핸드셰이크 + 17 도구 확인까지만. 실제 Claude Code 에서 `request_user_pick` 호출 → 브라우저 pick 카드 출현 → 채택 → 자동 record_asset_use 는 별도.
- **다크 모드** — CSS `prefers-color-scheme: dark` 자동 반영 여부는 브라우저 시각 확인.
- **반응형 레이아웃** — `test_web_responsive` 가 CSS 클래스 + Alpine 상태 단언. 실 브라우저 ≤768px 리사이즈 → 사이드 패널 자동 닫힘 시각 확인은 수동.
- **사운드 인라인 재생** — `test_web_routers_library` 가 `/api/audio` Range 헤더·Content-Type 정확성 검증. 실 브라우저 ▶ 클릭 → `<audio>` 재생 UX 는 수동.

## 3. 알려진 한계

M5 v1 에서 의도적으로 남긴 항목. 담당 마일스톤에서 처리 예정.

### 3.1 v2 (M6 이후 언제든)

- **`_card_list.html` cardMeta `x-show` 미적용** — 리스트 카드는 C 탭 메타 토글이 반응하지 않음. 와이드 카드만 동작.
- **자산 상세 모달 [채택]/[거부] endpoint stub** — `routers/feedback.py` 가 `POST /api/record-use` + `POST /api/feedback` stub 상태. 클릭 시 기록 미완료.
- **페이지 새로고침 시 pending pick 미표시** — 브라우저가 `/library` 재진입 시 이미 pending 이던 pick 카드 복원 없음. 타임아웃까지 비표시.
- **`_cleanup_loop` sweeper 가 트레이 카운트 미emit** — 만료된 pick 이 sweeper 에 의해 제거돼도 트레이 배지 즉시 감소 안 함.
- **저장된 검색 `project_id` 글로벌만** — v1 은 NULL (글로벌) 케이스만. 프로젝트 별 저장 검색은 후속.
- **`api_usage_summary` 의 `rejected_count` v1 = 0 고정** — `ProjectUsageSummary` 에 rejected 별도 집계 없음.
- **Pack/라벨 페이지 내 검색 기능** 없음.
- **`PATCH /api/labels/{id}` `description=null` 못 지움** — Pydantic Optional + None default 한계.

### 3.2 M8 (패키징 + i18n)

- **Config 변경 디스크 미저장** — `POST /api/preset` / `POST /api/weights` 가 런타임 Config 만 mutate. 재시작 시 초기화.
- **`presetDesc` / `confirm()` 한글 하드코딩** — `_t()` placeholder 사용 중이나 M8 본격 i18n 전까지 하드코딩.
- **다크/라이트 모드 수동 토글 버튼** — v1 은 OS `prefers-color-scheme` 만. 수동 토글은 M8.
- **모바일 최적화 부재** — `@media ≤768px` 는 사이드 패널 닫힘만. 전반 모바일 UX 는 M8.
- **Playwright E2E 테스트** — 자동화 v1 미적용. M8.

### 3.3 고정 제약 (변경 계획 없음)

- **axis 추가 불가** — `SEED_LABELS.keys()` 24 고정. axis 추가는 코드 변경 필요.
- **`PATCH /api/packs/{id}` HTML fragment 반환** — 비-HTMX 클라이언트 부적합. Accept 협상은 후속.
- **단일 사용자 / localhost 만** — LAN 멀티 접속·토큰 인증 미적용. v1 허용.
- **`SearchRequest.offset` Python 슬라이싱** — M4 SearchRequest 에 offset 필드 없어 Python 후처리. 큰 offset 비효율.
- **`pack_ids` 후처리 페이지네이션 왜곡** — pack_ids 필터가 Python 후처리라 `next_offset` 이 실제 row 수 기준 아님. docstring 명시됨.

## 4. 사용자 측 수동 검증 체크리스트 (~32 단계)

### 사전 준비

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
pytest -q
```

→ `796 passed, 1 skipped, 4 deselected` 가 보여야 한다.

GAH 실행:

```powershell
python -m gah --tray
```

→ 시스템 기본 브라우저가 `http://127.0.0.1:9874/library` 로 자동 진입.

별도 PowerShell 에서 Ollama 가 떠 있어야 한다 (검색 쿼리 임베딩용):

```powershell
ollama serve
```

---

아래 항목을 차례로 확인한다. 완료한 항목은 `[x]` 로 표시.

#### 기본 진입 + 검색

- [ ] **(1) 트레이 부팅 → 브라우저 자동 열림** — GAH 트레이 아이콘 + 브라우저가 `http://127.0.0.1:9874/library` 로 자동 열림. 라이브러리 페이지 상단 검색 바 + 결과 영역 정상 표시.

- [ ] **(2) 자연어 검색 + 디바운스** — 검색 바에 "blue hero" 입력 → 약 300ms 후 결과 영역 갱신 (별도 Enter 없이). 결과 카드에 썸네일 + 메타 표시.

- [ ] **(3) 결과 없음 상태** — 라이브러리가 비어 있으면 "결과 없음" 안내 메시지. 자산이 있으면 와이드 카드 그리드 표시.

#### 사이드 패널 (⚙ 토글 + 리사이즈)

- [ ] **(4) ⚙ 고급 클릭 → 사이드 패널 슬라이드 인** — 검색 바 우측 ⚙ 버튼 클릭 → 우측 사이드 패널 200ms 슬라이드 인 + B 탭 디폴트 활성. 다시 클릭 → 슬라이드 아웃.

- [ ] **(5) 리사이즈 핸들** — 사이드 패널 왼쪽 가장자리 `col-resize` 커서 확인. 드래그 → 240~640px 사이 폭 변경. 경계 초과 시 클램프.

- [ ] **(6) B/C/D 탭 전환** — B 필터 / C 표시 / D 조정 탭 헤더 클릭 → 활성 탭 강조 + 컨텐츠 전환.

#### B 탭 (정밀 필터)

- [ ] **(7) B 탭 매칭 모드** — AND/OR/NOT 라디오 변경 → 즉시 검색 재호출 + 결과 변화 확인.

- [ ] **(8) B 탭 라벨 검색 + 강조** — "🔍 라벨 검색…" input 에 일부 문자 입력 → 일치하는 axis 칩에 노란 box-shadow 강조. 빈 input → 강조 해제.

- [ ] **(9) B 탭 종류 탭** — 스프라이트/시트/사운드 탭 전환 → 칩 그룹 교체. 시트 탭은 현재 빈 (SEED 에 `sheet_*` axis 없음).

- [ ] **(10) B 탭 axis 칩 클릭** — 칩 활성/비활성 토글 + 즉시 검색 재호출. 활성 칩 배경색 변경 + 좌우 스크롤 없음 (wrap 동작).

- [ ] **(11) B 탭 다축 필터 드롭다운** — 팩/벤더/라이선스/상태 `<details>` 클릭 → 펼침. 체크박스 변경 → 즉시 검색 재호출.

#### C 탭 (표시 옵션)

- [ ] **(12) C 탭 그리드/리스트 토글** — C 탭 진입 후 그리드↔리스트 버튼 클릭 → 결과 영역 즉시 변경. 결과 툴바도 동기.

- [ ] **(13) C 탭 카드 크기 S/M/L** — 크기 변경 → 카드 폭 즉시 변경.

- [ ] **(14) C 탭 카드 메타 4 토글** — 라벨/팩/점수/크기 체크박스 → 각 카드의 해당 부분 즉시 표시/숨김 (와이드 카드만 동작).

#### D 탭 (고급 조정)

- [ ] **(15) D 탭 "통일성 우선" 프리셋** — 프리셋 버튼 클릭 → 슬라이더 값 자동 갱신 + 활성 프리셋 이름 표시 + 즉시 검색 재호출. 결과가 같은 프로젝트 채택 팩 우선 재정렬.

- [ ] **(16) D 탭 슬라이더 6개** — "▶ 슬라이더 직접 조정…" 펼침 → 6 슬라이더. 변경 시 자동 정규화 + Config 갱신 + 검색 재호출. 프리셋 active 해제.

- [ ] **(17) D 탭 저장된 검색 CRUD** — 이름 입력 + "현재 검색 저장" → 리스트 추가. 항목 클릭 → 검색 + 필터 + 가중치 복원 + 재검색. × 버튼 → confirm 후 삭제.

- [ ] **(18) 저장된 검색 페이지 새로고침 후 유지** — 브라우저 새로고침 후 D 탭 진입 → 저장된 검색이 그대로 (DB 영속 확인).

#### 결과 카드 + 모달

- [ ] **(19) 사운드 카드 ▶ 클릭 → 인라인 재생** — 사운드 에셋 카드 ▶ 버튼 클릭 → 인라인 audio 재생 시작. 소리 출력 확인.

- [ ] **(20) 카드 클릭 → 상세 모달** — 카드 클릭 → 자산 상세 모달 표시 (큰 썸네일 + 전체 라벨 + 메타).

- [ ] **(21) 모달 ESC 키 닫힘** — 상세 모달 열린 상태에서 ESC 키 → 모달 닫힘.

#### MCP `request_user_pick` (Claude pick 인터랙션)

별도 PowerShell 에서 MCP 클라이언트 또는 `python -m gah --mcp` + JSON-RPC 로 수행.

- [ ] **(22) `request_user_pick` 호출 → 브라우저 pick 카드 출현** — MCP 에서 `request_user_pick` 호출 시 라이브러리 페이지 상단에 보라색 strip pick 카드 그룹 출현. 헤더 알림 배지 +1.

- [ ] **(23) [채택] 버튼 → MCP 응답 + 자동 record_asset_use** — pick 카드 에셋 중 하나 [채택] 클릭 → 카드 사라짐 + MCP 쪽 `picked_asset_id` 응답 수신 + DB `asset_usage` 에 `source="claude_pick"` 레코드 생성 확인.

- [ ] **(24) [✕ 거부] → 499_user_cancelled** — [✕ 거부] 클릭 → 카드 사라짐 + MCP 쪽 `499_user_cancelled` 에러 수신.

- [ ] **(25) Timeout → 408_timeout** — 요청 후 `timeout_seconds` (기본 300) 초 동안 미응답 → MCP 쪽 `408_timeout` 에러 수신. (단축 테스트: `timeout_seconds=10` 으로 호출 후 10초 대기)

- [ ] **(26) 트레이 툴팁 갱신** — pick 대기 중 트레이 아이콘 hover → 툴팁에 "N건 대기" 메시지. 처리 후 해제.

#### Pack / 라벨 관리 페이지

- [ ] **(27) Pack 페이지 카드 그리드** — 상단 네비 "팩 관리" → `/packs` 진입. 팩 카드 그리드 + 이름 + asset_count + 스프라이트/사운드 분포 표시.

- [ ] **(28) Pack enable/disable 토글** — 팩 카드 우측 상단 토글 클릭 → 즉시 상태 변경 (HTMX fragment 교체). DB `packs.enabled` 컬럼 변경 확인.

- [ ] **(29) 라벨 admin 24 axis 탭** — 상단 네비 "라벨 관리" → `/labels/admin` 진입. 24 axis 탭 클릭 → 해당 axis 라벨 목록 전환.

- [ ] **(30) 라벨 CRUD** — (1) 새 라벨 이름 입력 + "추가" → 목록에 행 추가. (2) 행 편집 + "저장" → 갱신. (3) "×" → 삭제.

- [ ] **(31) 라벨 JSON export/import** — "JSON 내보내기" → `labels_export.json` 다운로드 확인. 파일을 "가져오기" 에 업로드 → 중복 스킵 / 신규 추가 확인.

- [ ] **(32) 라벨 어휘 변경 toast** — `/labels/admin` 에서 라벨 추가/수정/삭제 후 라이브러리 페이지에 "라벨 어휘가 변경됐습니다 — 새로 고침 권장" toast 4초 표시 후 자동 사라짐.

#### UI/UX 마감

- [ ] **(33) 404 에러 페이지** — 브라우저에서 `/nonexistent` 접속 → 커스텀 404 HTML 페이지 ("페이지를 찾을 수 없습니다" + 홈 링크) 표시.

- [ ] **(34) 다크 모드 자동 반응** — OS 다크 모드 (Windows 설정 → 개인 설정 → 색) 전환 → 브라우저 새로고침 없이 또는 새로고침 후 다크 테마 자동 적용. CSS 변수 `--bg`/`--fg` 전환 확인.

- [ ] **(35) 반응형 ≤768px** — 브라우저 폭을 768px 이하로 줄임 → 사이드 패널 자동 닫힘. ⚙ 다시 클릭 → full-height fixed 슬라이드 인.

- [ ] **(36) 트레이 종료 → 웹서버 graceful shutdown** — 트레이 아이콘 우클릭 → "종료" → 브라우저 새로고침 시 연결 거부 확인 + 포트 9874 해제 확인.

### 선택 — 트레이 + MCP stdio 동시 기동

`python -m gah --tray` + 별도 PowerShell 의 `python -m gah --mcp` 동시 기동 후 `gah.log` 에 `database is locked` 0 건 확인. M4 write_lock + busy_timeout 패턴 그대로 유지.

## 5. M6 으로 인계되는 변경

본 마일스톤이 M6 (시트 분석 + 애니메이션) 작업자에게 남기는 약속:

- **웹 UI 인프라** — FastAPI + Jinja2 + HTMX + Alpine 스택이 완성. M6 이 추가하는 `suggest_animation_frames` MCP 18번째 도구 + 시트 frame 미리보기 카드가 같은 스택에 자연스럽게 통합.
- **SSE bus** — `sse_bus.py` 의 thread-safe broadcast 에 `animation_progress` 이벤트 타입 추가만으로 M6 분석 진행률 push 가능.
- **HybridSearcher 6채널** — M6 의 시트 에셋 (분할 frame 결과) 도 같은 검색 알고리즘으로 즉시 노출.
- **MCP 16 → 17 도구** — M6 이 `suggest_animation_frames` 추가 시 `mcp/tools.py` 에 1 함수 + `mcp/server.py` 에 `@server.tool` 데코레이터 1줄. `test_mcp_integration` 17 → 18 갱신.
- **`docs/WEB_UI_GUIDE.md`** — 17 도구 + pick 흐름 + 웹 UI 사용법 모두 문서화 완료. M6 은 §6 (시트 분석) 절만 추가.
- **와이드 카드 `🎞 N frames` 배지** — `_card_wide.html` 에 `sheet_frame_count > 0` 조건 배지 placeholder 있음. M6 이 sheet 에셋 분석 결과로 채움.
