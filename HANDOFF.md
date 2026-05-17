# HANDOFF — Cowork → Claude Code (또는 다음 세션)

**마지막 인계 시각**: 2026-05-17 (M5 Phase 0~4 완료 시점)
**마지막 완료 마일스톤**: M4 (검색 UX 풍부화) — ✅ 머지됨 ([PR #5](https://github.com/v0o0v/game-asset-helper/pull/5))
**진행 중 마일스톤**: **M5 — 웹 GUI 전환 + 라이브러리 리디자인 + Claude pick** (~5.5주, 약 73% 진행)
**현재 브랜치**: `feat/m5-web-gui` (main 위 **59 commit**, 미머지)
**다음 작업**: **Phase 5 (Qt 위젯 폐기 + Pack/라벨 관리 웹 이식) — [`milestones/M5_plan.md`](milestones/M5_plan.md) §4.5, ~0.5주**

이 문서는 작업이 중단될 때 다음 세션이 "현재 어디까지 와 있는가" 를 한 번에 파악하도록 작성된 스냅샷이다. 마일스톤 또는 phase 가 하나 끝날 때마다 이 문서를 갱신한다.

## 1. 한 줄 요약

M4 가 main 으로 머지된 후 M5 spec ([`docs/superpowers/specs/2026-05-17-m5-web-gui-and-library-redesign.md`](docs/superpowers/specs/2026-05-17-m5-web-gui-and-library-redesign.md)) + plan ([`milestones/M5_plan.md`](milestones/M5_plan.md), 2097 줄 6 phase 75 task) + todo 작성 → `feat/m5-web-gui` 브랜치 분기 후 `superpowers:subagent-driven-development` 스킬로 **Phase 0 (의존성/Config/vendoring) + Phase 1 (FastAPI 스캐폴딩 + WebServer + 트레이 통합 + SSE bus) + Phase 2 (라이브러리 페이지: 검색 + 결과 + 카드 + 상세 모달 + 사운드 + 페이지네이션) + Phase 3 (우측 사이드 패널 B/C/D — 매칭 모드 + 라벨 검색 + 종류 탭 + axis 칩 + 다축 필터 + 표시 옵션 + 카드 메타 + 프리셋 + 슬라이더 + 저장된 검색 + 통일성 요약 + 반응형) + Phase 4 (Claude `request_user_pick` MCP 17번째 도구 + SSE push + 브라우저 pick 카드 + TrayBridge Qt 시그널 브리지 + 자동 record_asset_use) 완료**. 누적 59 commit, **746 passed + 8 skipped + 4 deselected**. Qt UI 위젯 7 파일 + 테스트 4 파일은 Phase 5 폐기 예정이라 임시 module-level skip 적용. 다음 세션 = Phase 5 (Qt 폐기 + Pack/라벨 관리 웹 이식) → Phase 6 (마감 + verification).

## 2. 검증된 사실 (M5 Phase 0~4 시점)

자동 — `pytest -q` 결과 **746 passed + 8 skipped + 4 deselected** (Phase 3 end 692 대비 +54 신규 — Phase 4 의 16 commit 누적).

| 영역 | 새 케이스 | 비고 |
|---|---:|---|
| M0~M4 베이스라인 | 452 | M4 PR #5 머지 시점 |
| Phase 0~2 누적 | +54 | (Phase 5 폐기 7 파일 ~50 skip 후 baseline 506) |
| Phase 3A — ⚙ 토글 + 리사이즈 핸들 + B/C/D 탭 스캐폴딩 | +17 | `test_web_pages.py` 보강 |
| Phase 3B-1 — B 탭 매칭 모드 + 라벨 검색 + 종류 탭 + axis 분류 | +32 | `test_web_side_panel_b.py` 신규 |
| Phase 3B-2 — axis 칩 + 다축 필터 + SearchRequest 매핑 | +55 | `test_web_filters_packs.py` + `test_web_search_label_mapping.py` 신규 |
| Phase 3C — C 탭 표시 옵션 + 카드 메타 토글 | +20 | `test_web_side_panel_c.py` 신규 |
| Phase 3D-1 — 프리셋 3 + 슬라이더 6 + Config 갱신 | +24 | `test_web_side_panel_d.py` 신규 |
| Phase 3D-2 — 저장된 검색 + 통일성 모달 + 반응형 | +34 | `test_web_saved_searches.py` + `test_web_usage_summary.py` + `test_web_responsive.py` 신규 |
| Phase 3 cleanup — Store 헬퍼 + fixture 통합 | +4 | conftest 통합 + get_pack_by_id / get_saved_search_by_id |
| **Phase 3 합계** | **+186 신규** | total 692 |
| Phase 4A — picks + sse 라우터 | +18 | `test_web_routers_picks.py` 13, `test_web_routers_sse.py` 5 (+1 skip) |
| Phase 4B — pick 카드 + library 페이지 보강 | +13 | `test_web_pick_card.py` 8, `test_web_pages.py` +5 |
| Phase 4B fix — json-enc | +1 | `test_web_pages.py` +1 |
| Phase 4C — MCP `request_user_pick` 도구 | +10 | `test_mcp_tools_m5.py` 10 |
| Phase 4C cleanup — source=manual pin | +1 | `test_mcp_tools.py` +1 |
| Phase 4D — TrayBridge | +11 | `test_tray_bridge.py` 11 |
| **Phase 4 합계** | **+54 신규** | total 746 (+1 skip = 8) |

`pytest -m mcp_integration -v` — 2/2 (**17 도구**, Phase 4C 에서 갱신 완료).

수동 — Phase 4 끝 시점부터 사용자가 시각 검증 가능 (수동 검증 항목은 §9.5 별도 정리):

```powershell
python -m gah --tray
```

→ 트레이 아이콘 + 브라우저 자동 열림 (http://127.0.0.1:9874/library). 라이브러리 페이지 + 검색 + 결과 + 카드 + 상세 모달 + 사운드 ▶ + **우측 사이드 패널 ⚙ + B 탭 (매칭 모드/라벨 검색/종류 탭/axis 칩/다축 필터) + C 탭 (표시 옵션 양방향/카드 메타 토글) + D 탭 (프리셋 3개/슬라이더 6개 펼침/저장된 검색 CRUD/통일성 상세 모달) + 사이드 패널 리사이즈 핸들 (240~640px) + 반응형 (≤768px 자동 닫힘 + 슬라이드)** + **Phase 4: MCP `request_user_pick` 호출 시 브라우저에 보라색 pick 카드 출현 + 헤더 배지 갱신 + 트레이 아이콘 툴팁 갱신** 시각 확인 가능.

## 3. 환경 (재현용)

| 항목 | 값 |
|---|---|
| OS | Windows 10 |
| Python | python.org 3.12 (`C:\Users\v0o0v\AppData\Local\Programs\Python\Python312\python.exe`) |
| venv | `C:\Users\v0o0v\.venvs\gah\` |
| 작업 폴더 | `D:\ClaudeCowork\game-asset-helper\game-asset-helper\` |
| 런타임 데이터 | `C:\Users\v0o0v\AppData\Roaming\GameAssetHelper\` |
| 라이브러리 루트 | `%APPDATA%\GameAssetHelper\library\` |
| 메타 DB | `%APPDATA%\GameAssetHelper\metadata.db` (WAL, 21+5=26 객체) |
| CLIP 캐시 | `%APPDATA%\GameAssetHelper\cache\clip\` |
| 스펙트로그램 캐시 | `%APPDATA%\GameAssetHelper\cache\spectrograms\` |
| **신규 M5: web.port 파일** | `%APPDATA%\GameAssetHelper\web.port` (MCP server ↔ FastAPI 포트 공유, Phase 1A 완료) |
| **신규 M5 Phase 4: MCP 도구 수** | 17 도구 (`request_user_pick` 추가 — Phase 4C 완료) |

**금기**: Microsoft Store Python, Cowork 작업 폴더 내부 venv.

M5 신규 의존성 (`pyproject.toml`):

- `fastapi>=0.110`, `uvicorn[standard]>=0.27` (transitive `websockets`, `httptools`, `watchfiles`)
- `jinja2>=3.1`, `python-multipart>=0.0.9`, `sse-starlette>=2`

vendoring (`src/gah/web/static/vendor/`):

- `htmx.min.js` 1.9.12
- `htmx-sse.min.js` 1.9.12
- `alpine.min.js` 3.13.10

기존 venv 그대로 사용 시:

```powershell
pip install -e D:\ClaudeCowork\game-asset-helper\game-asset-helper[dev]
```

→ `pyproject.toml` 의 신규 5 의존성 + transitives 자동 설치.

## 4. 새 세션에서 바로 이어가는 방법

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
git status
```

→ `On branch feat/m5-web-gui` + 59 (또는 그 이상 — 본 인계 커밋 포함) commits ahead of main + clean.

```powershell
git log --oneline -10
```

→ 최상단 본 인계 커밋 + 그 아래 Phase 4D (TrayBridge + MCP_USAGE_GUIDE 갱신) + Phase 4C cleanup (httpx.TransportError 통합 + source=manual pin + 408 동적) + Phase 4C (request_user_pick MCP 도구 + 17 도구 등록) + Phase 4B (pick-card + json-enc + 배지 CSS) + Phase 4A (picks/sse 라우터) + Phase 3 cleanup 등.

```powershell
pytest -q
```

→ `746 passed, 8 skipped, 4 deselected`. m4 GUI 7 파일은 Phase 5 폐기 예정이라 module-level skip.

선택 — 사용자 직접 시각 검증:

```powershell
python -m gah --tray
```

→ 브라우저로 라이브러리 페이지 진입. 검색 + 결과 + 카드 + 모달 + 사운드 + **사이드 패널 ⚙ + B/C/D 탭 + 리사이즈 + 반응형** 시각 확인.

## 5. 다음 세션 진입 절차 (Phase 5 시작)

### 5.1 환경 복원 + 회귀 검증

§4 의 4 명령 (Activate.ps1 / cd / git status / pytest -q) 실행. **746 passed** 확인.

### 5.2 Phase 5 작업 진입

[`milestones/M5_plan.md`](milestones/M5_plan.md) §4.5 = **Phase 5 — Qt 위젯 폐기 + Pack/라벨 관리 웹 이식 (~0.5주)**. 핵심:

- **Qt UI 7 파일 실 삭제** — `test_labels_admin_ui.py`, `test_library_search_ui.py`, `test_library_search_ui_rich.py`, `test_progress_debounce.py`, `test_progress_statusbar.py`, `test_ui_smoke.py`, `test_ui_smoke_m2.py` (현재 module-level skip → 실 삭제 후 총 pytest 카운트 변동 예상).
- **Pack 페이지 (`/packs`)** 백엔드 + 프론트엔드 (현재 빈 stub 라우터만 + nav 링크 404).
- **라벨 관리 페이지 (`/labels/admin`)** 백엔드 + 프론트엔드 (현재 빈 stub 라우터만 + nav 링크 404).

### 5.3 Phase 5 시작 전 처리할 follow-up (Phase 3~4 review 잔여)

다음 Phase 5 또는 Phase 6 (마감) 가 자연 흡수:

1. **`_card_list.html` 에 `cardMeta` `x-show` 바인딩 미적용** — Phase 2 가 만든 리스트 카드 partial 이 `x-show="$store.search.cardMeta.*"` 를 적용 안 함 (와이드 카드만 적용). 리스트 뷰에서 토글이 부분적으로만 동작. Phase 6 (마감) 가 흡수.

2. **자산 상세 모달 [채택]/[거부] 버튼 endpoint** — `POST /api/record-use` + `POST /api/feedback` 호출. Phase 4 의 `record_asset_use(source="claude_pick")` 인프라 활용하여 Phase 5 또는 Phase 6 에서 채움.

3. **`_modal_usage.html` / asset_detail 의 ESC 키 dismiss 미지원** — 클릭/X 버튼만. Phase 6 마감 흡수.

4. **`_card_wide.html` div 의 keyboard accessibility** — `hx-trigger="click"` 만 — `role="button"` + `tabindex="0"` 부재. Phase 6 마감 흡수.

5. **`presetDesc` JS 객체 리터럴의 한글 하드코딩** — Alpine inline JS 라 Jinja `_()` 적용 불가. M8 (i18n) 이 본격 처리.

6. **`confirm()` 메시지 한국어 하드코딩** — Alpine inline JS 한계. M8 흡수.

7. **`@media (max-width: 768px)` 의 `style*="display: none"` 속성 선택자** — Alpine x-show 가 인라인 `display: none` 적용에 의존. 약간 fragile 하나 동작 OK.

8. **페이지 새로고침 시 기존 pending pick 미표시** — 브라우저 진입 시 `/api/user-pick/pending` 폴링 없음. SSE 구독 후 신규 이벤트만 표시. Phase 6 마감 흡수.

### 5.4 새 세션이 자동 로드하는 메모리

다음 메모리가 자동 컨텍스트 로드:

- 마일스톤 수동 검증 항목 표시 방식 (feedback)
- PR/커밋 한글 (feedback)
- 가능한 한 직접 실행 (feedback)
- M2 분석 클라이언트 백엔드 추상화 (project)
- Ollama 멀티모달 API 형식 실측 (project)
- 모델 출력 듀얼 언어 + GUI i18n (project)
- 라벨 가중치 + CLIP v1 편입 (project)
- 검색 UX 전용 마일스톤 M4 신설 (project)
- GAH 배포 전략 — torch CUDA/CPU 통합 빌드 (project)
- M2.1 분석 큐 병렬화 패치 (project)
- M5 신규 — 웹 GUI 전환 결정 (project)
- M5 Phase 0~3 진행 완료 (project)
- M5 Phase 4 완료 (project — Phase 4 완료 시점에 갱신됨)
- M5 subagent-driven-development 워크플로 (project)

### 5.5 M5 진행 현황 (한눈에)

| Phase | 상태 | 핵심 산출물 | commit |
|---|---|---|---:|
| plan/todo | ✅ | spec → plan 2097 줄 + todo | 1 |
| Phase 0 (의존성/Config/vendoring) | ✅ | FastAPI 5 의존성 + Config 7 필드 + UsageSource enum + HTMX/Alpine 정적 자원 | 3 |
| Phase 1A (web/url + pending + deps) | ✅ | `web.port` R/W, PendingPickQueue (asyncio.Future + lock + TTL), WebDeps | 4 (race fix 1 포함) |
| Phase 1B (FastAPI factory + WebServer) | ✅ | `build_app` lifespan, uvicorn 별 스레드, 포트 폴백 9874→9883 | 2 |
| Phase 1C (tray + run_tray + health) | ✅ | 트레이 메뉴 → 브라우저, MainWindow 의존성 0, SSE bus, m4 GUI 7 파일 skip | 3 |
| Phase 2A (검색 백엔드 + 카드) | ✅ | `/api/search`, `/ui/search-results`, `/api/thumbnail`, 와이드/리스트 카드 partial | 4 (bug fix 1 포함) |
| Phase 2B (페이지 베이스 + 검색 바) | ✅ | base/library/nav, CSS 변수 light/dark, 검색 바 300ms 디바운스, ⚙ 토글 | 1 |
| Phase 2C (결과 툴바 + 페이지네이션 + 디폴트) | ✅ | view/size/sort 툴바, 더 보기 버튼, 빈 검색 → 라이브러리 추가일↓ 폴백 | 3 |
| Phase 2D (모달 + 사운드 + 통합) | ✅ | `/ui/asset-detail`, `/api/audio`, `/ui/audio-player`, 모달 CSS | 3 |
| Phase 2 fix (toolbar 중복) | ✅ | `_results_grid.html` ↔ `_results_cards_only.html` 분리 + library.html dead x-data 정리 | 1 |
| Phase 3A (⚙ + 리사이즈 + B/C/D 스캐폴딩) | ✅ | 슬라이드 transition + resizeHandle (Alpine 마우스 240~640) + 3 partial + .side-tabs | 4 (sticky 정정 fix 1 포함) |
| Phase 3B-1 (B: 매칭 모드 + 라벨 검색 + 종류 탭) | ✅ | match-mode 라디오 + label-filter-input + .chip.matched + kind-tabs + `/api/filters/labels` + axis prefix 분류 | 3 |
| Phase 3B-2 (B: axis 칩 + 다축 + SearchRequest 매핑) | ✅ | axis-group/chip-flow FlowLayout + toggleLabel + 다축 필터 4 details + `/api/filters/packs` + hidden input + labels→LabelFilter 룩업 + match_mode 분배 + pack_ids 후처리 | 3 |
| Phase 3C (C: 표시 옵션 + 카드 메타) | ✅ | viewMode/cardSize/sort 양방향 + cardMeta 4 체크박스 | 1 |
| Phase 3D-1 (D: 프리셋 + 슬라이더) | ✅ | `POST /api/preset/{name}` + `POST /api/weights` + Config mutate + applyPreset/syncWeights | 1 |
| Phase 3D-2 (D: 저장된 검색 + 통일성 + 반응형) | ✅ | saved_searches 라우터 CRUD + savedSearches() Alpine + `/api/usage/summary` + `/ui/usage/detail` + `_modal_usage.html` + 768px 슬라이드 + resize 리스너 | 3 |
| Phase 3 cleanup | ✅ | Store.get_pack_by_id + Store.get_saved_search_by_id + endpoint raw SQL 제거 + dead code + pack_ids docstring + populated_deps 6파일 → conftest 통합 | 3 |
| Phase 4A (picks + sse 라우터) | ✅ | `/internal/user-pick` long-poll + `/api/user-pick/{rid}` (응답/거부) + `/sse/notifications` (sse-starlette) | 4 |
| Phase 4B (pick 카드 + SSE 클라이언트) | ✅ | `_pick_card.html` partial + `GET /ui/pick-card/{rid}` + htmx-sse + Alpine pickQueue store + app.js + 헤더 배지 CSS + `htmx-json-enc` vendoring | 5 |
| Phase 4C (MCP request_user_pick) | ✅ | `tool_request_user_pick` + httpx loopback + 자동 `record_asset_use(source="claude_pick")` + 17 도구 등록 | 5 |
| Phase 4D (TrayBridge + 문서) | ✅ | `TrayBridge(QObject)` uvicorn→Qt 시그널 브리지 + MCP_USAGE_GUIDE 17번째 도구 갱신 | 2 |
| **Phase 5** (Qt 폐기 + Pack/라벨 이식) | **다음** | 7 파일 삭제 + Pack/labels admin 웹 페이지 | 0 |
| Phase 6 (마감 + verification) | 대기 | 다크모드 토글 / 에러 페이지 / WEB_UI_GUIDE / verification | 0 |
| Final review | 대기 | 전체 변경 review | 0 |

## 6. 마일스톤 재정렬 (변경 없음)

| 신규 # | 이름 | 일정 | 상태 |
|---:|---|---:|---|
| M0~M3 | (변경 없음) | — | ✅ 완료 (main) |
| M4 | 검색 UX 풍부화 (Qt 위젯) | 1.5주 | ✅ 완료 (main, M5 가 Qt 위젯 폐기 예정) |
| **M5** | **웹 GUI 전환 + 라이브러리 리디자인 + Claude pick** | **5.5주** | **🔄 진행 중 (~73%)** |
| M6 | 시트 분석 + 애니메이션 | 1주 | 대기 |
| M7 | Unity Asset Store 임포트 | 1주 | 대기 |
| M8 | 패키징 + i18n | 1주 | 대기 |

## 7. M5 spec §13 의 5 열린 질문 — 결정 적용 결과

| # | spec 질문 | plan §3 결정 | Phase 0~2 적용 결과 |
|---|---|---|---|
| Q1 | FastAPI 같은 프로세스 vs subprocess | 같은 프로세스 + 별 스레드 | ✅ `WebServer` 가 `threading.Thread` 로 uvicorn 별 스레드 실행. Qt main thread 와 충돌 X. |
| Q2 | WebSocket vs SSE | SSE (sse-starlette) | ✅ `web/sse_bus.py` thread-safe broadcast 구현. `/sse/notifications` 라우터 Phase 4A 에서 완전 구현. |
| Q3 | Qt 폐기 시점 | M5 안 (Phase 5) | 🔄 진행 중 — Phase 1C 가 m4 7 파일 모듈 skip + Phase 5 가 삭제. |
| Q4 | 자동 `record_asset_use` | 자동 호출 (source='claude_pick') | ✅ Phase 4C 완료 — `tool_request_user_pick` 가 pick 성공 시 `record_asset_use(source="claude_pick")` 자동 호출. `UsageSource.CLAUDE_PICK` enum 은 Phase 0 에서 정의. |
| Q5 | i18n 백엔드 | v1 placeholder `_t()`, 본격은 M8 | ✅ `web/i18n.py` 의 `_t()` passthrough + Jinja2 `_` 글로벌 등록. 모든 사용자 노출 문자열은 `{{ _("...") }}` 로 감싸 둠. |

신규 결정 적용 결과:

- **MCP↔FastAPI HTTP loopback** — `/internal/user-pick` long-poll ✅ Phase 4A 완료. `web.port` 파일 R/W (Phase 1A) 가 인프라.
- **포트 폴백** — `web_port` 부터 `web_port_max_attempts` (10) 회 시도. ✅ `WebServer._find_available_port` 구현 완료.
- **PendingPick TTL/한도** — TTL = `claude_pick_timeout_seconds + 60s`, max_pending = 20. ✅ `PendingPickQueue.cleanup_expired` (Phase 1A) + lifespan 의 cleanup 잡 (Phase 1B) + API 라우터 Phase 4A 등록.

## 8. M5 Phase 0~4 의 의도적으로 미룬 항목

Phase 4~6 가 채움:

- **자산 상세 모달 [채택]/[거부] 버튼 endpoint** — Phase 5 또는 Phase 6 (`routers/feedback.py` 현재 빈 stub, Phase 4 의 `record_asset_use` 인프라 활용)
- **Pack 페이지 (`/packs`) + 라벨 관리 페이지 (`/labels/admin`)** — Phase 5 (현재 빈 stub 라우터만 + nav 의 링크는 404)
- **Qt UI 파일 7개 + 테스트 4 파일 실 삭제** — Phase 5 (현재 module-level skip)
- **다크모드 사용자 토글** — Phase 6 (현재 OS prefers-color-scheme 자동만)
- **`WEB_UI_GUIDE.md` 작성** — Phase 6
- **`M5_verification.md`** — Phase 6 끝

## 9. 알려진 한계 / 주의사항

### 9.1 Phase 3~4 reviewer 가 남긴 follow-up (Phase 5 또는 후속 phase 가 흡수)

§5.3 의 8 follow-up (`_card_list.html` cardMeta 미적용 / 채택·거부 버튼 stub / 모달 ESC / 키보드 accessibility / presetDesc i18n / confirm() i18n / 768px 미디어 쿼리 fragility / 페이지 새로고침 pending pick) + Phase 5 폐기 예정 7 파일 skip 마크 유지.

### 9.2 v1 알려진 한계 (M6 이상에서 개선)

- **`SearchRequest.offset` 미지원** — M4 가 만든 SearchRequest 에 offset 필드 없음. `_do_search` 가 `count = body.count + body.offset` 으로 fetch 후 Python 슬라이싱. 큰 offset 에선 비효율 — M6 또는 후속 phase 에서 SearchRequest 확장 권장.
- **`pack_ids` 후처리 페이지네이션 왜곡** — `_do_search` 가 SearchRequest 결과를 Python 후처리로 `pack_ids` 필터하므로, `next_offset` 이 Searcher 가 본 row 수가 아니라 필터 후 row 수 기준. 페이지네이션이 조기 종료될 수 있음. docstring 명시 완료. M6 이후 `SearchRequest.pack_ids` 매핑 또는 `fetch_count` 오버페치 로 개선 권장.
- **`store.list_assets(limit=10_000)`** — 디폴트 상태 폴백에서 사용. 매우 큰 라이브러리 (1만+) 에선 비효율 — M6 또는 후속 phase 에서 `count_assets` 기반 동적 limit 으로 개선.
- **m4 7 파일 skip** — Phase 5 가 파일 자체 삭제 시 skip 마크도 같이 사라짐. 이때 `pytest -q` 통과 카운트가 변동 (skip → 0, total 도 감소).
- **autoplay** — `_audio_player.html` 의 `<audio autoplay>` 는 사용자 클릭 후라 브라우저 정책 통과.
- **저장된 검색 — `project_id` v1 글로벌만** — Saved searches 의 project_id 가 NULL (글로벌) 케이스만 v1 지원. project 별 저장 검색은 후속 phase 에서 처리.
- **`api_usage_summary` 의 `rejected_count` v1 = 0 고정** — `ProjectUsageSummary` 가 rejected 별도 필드 없어 v1 단순화. 후속 phase 에서 갱신 권장.
- **Config 변경 디스크 미저장** — `POST /api/preset/{name}` / `POST /api/weights` 가 런타임 Config 만 mutate. 다음 부팅 시 디폴트 복귀. M8 (패키징) 시 사용자 설정 영속화 정책 결정.

### 9.3 환경 / 기술 한계

- **WebDeps `frozen=True` + Config mutate** — `deps.config` 자체는 frozen WebDeps 의 참조라 교체 불가지만, `Config` dataclass 가 frozen 이 아니므로 `deps.config.weight_* = ...` 직접 할당으로 갱신. HybridSearcher 가 `hybrid()` 호출마다 `self.config.weight_*` 를 매번 읽으므로 즉시 반영. 단일 워커 단일 event loop 환경 가정 (uvicorn 기본).
- **fixture 6 파일 중복 → conftest 통합 완료** (Phase 3 cleanup).

### 9.4 Phase 4 신규 의존성 / 변경

신규 의존성 없음 — Phase 0 의 5 의존성 + `httpx` (pyproject.toml 추가, MCP server 측 loopback 호출용). 신규 정적 자원: `src/gah/web/static/vendor/htmx-json-enc.js` (v1.9.12, 360 bytes). Phase 4 신규 모듈: `src/gah/web/routers/picks.py` (4 endpoint), `src/gah/web/routers/sse.py`, `src/gah/web/tray_bridge.py` (PySide6 의존 격리), `src/gah/web/static/js/app.js` (SSE handlers), `src/gah/web/templates/_pick_card.html`.

**`RecordAssetUseRequest.source` 디폴트 변경** — Phase 4C silent behavioral change: MCP 도구 레이어에서 `record_asset_use` 호출 시 `source="manual"` 이 디폴트로 기록됨 (이전 "explicit"). `test_record_asset_use_default_source_is_manual` 로 pin. 직접 `UsageTracker.record_explicit()` 호출 경로는 영향 없음.

### 9.5 Phase 4 알려진 한계 (Phase 5/6 가 흡수)

- **페이지 새로고침 시 기존 pending pick 미표시** — 브라우저가 `/library` 진입 시 `/api/user-pick/pending` 같은 endpoint 없음. 페이지 로드 후 SSE 구독 이후 등록되는 pick 만 카드 표시. 로드 전에 이미 pending 이던 pick 은 타임아웃까지 비표시. Phase 6 마커.
- **`_cleanup_loop` sweeper 가 트레이 카운트 미emit** — sweeper 로 만료된 pick 은 트레이 배지 카운트를 즉시 감소 안 함. 다음 pick 액션 (수락/거부/신규) 때 갱신. spec 에서 선택 사항으로 명시.
- **`color-mix()` CSS** — Chromium 111+, Firefox 113+, Safari 16.2+. Windows 10 Edge 는 정상 동작.
- **`notif-badge` 색상 하드코딩 보라** — 추후 알림 유형 (분석 오류 등) 추가 시 all-purple 이 됨. Phase 6 에서 선택자 분기 권장.

### 9.6 사용자 수동 시각 검증 항목 (Phase 3~4 시점)

[`milestones/M5_plan.md`](milestones/M5_plan.md) §4.3 Task 3.18 + 자동 검증 불가 항목:

1. **사이드 패널 ⚙ 토글** — 검색 바 우측 ⚙ 버튼 클릭 → 우측 사이드 패널 200ms 슬라이드 인 (오른쪽 → 왼쪽). 다시 클릭 → 슬라이드 아웃.
2. **리사이즈 핸들** — 사이드 패널 왼쪽 가장자리에 col-resize 커서. 드래그 → 240~640px 사이 폭 변경. 경계 초과 시 클램프.
3. **B/C/D 탭 전환** — B 필터 / C 표시 / D 조정 탭 헤더 클릭 → 활성 탭 강조 + 컨텐츠 전환.
4. **B 탭 매칭 모드** — AND/OR/NOT 라디오 변경 시 즉시 검색 재호출. 결과 변화 확인.
5. **B 탭 라벨 검색** — "🔍 라벨 검색…" input 에 일부 문자 입력 → 일치하는 axis 칩에 노란 box-shadow 강조. 빈 input → 강조 해제.
6. **B 탭 종류 탭** — 스프라이트/시트/사운드 탭 전환 시 칩 그룹 교체. 시트는 빈 (현재 SEED 에 sheet_* axis 없음).
7. **B 탭 axis 칩 클릭** — 칩 활성/비활성 토글 + 즉시 검색 재호출. 활성 칩은 var(--chip-active) 배경.
8. **B 탭 다축 필터 4 드롭다운** — 팩/벤더/라이선스/상태 details summary 클릭 펼침. 체크박스 변경 시 즉시 검색 재호출 (상태 제외 — frontend 만).
9. **C 탭 표시 옵션 양방향** — C 탭의 그리드/리스트/카드 크기 S/M/L 클릭 → 결과 영역 즉시 변경 + 결과 툴바와 동기. sort 변경 → 서버 재호출.
10. **C 탭 카드 메타 토글** — 라벨/팩/점수/크기 4 체크박스 → 각 카드의 해당 부분 즉시 표시/숨김. (와이드 카드만 동작 — 리스트 카드는 후속 phase 처리)
11. **D 탭 프리셋 3 버튼** — 균형/통일성 우선/참신성 클릭 시 활성 표시 + 설명 문구 + 슬라이더 값 자동 갱신 + 즉시 검색 재호출. 다음 검색 결과 가중치 반영.
12. **D 탭 슬라이더 6개** — `▶ 슬라이더 직접 조정…` 펼침 → 6 슬라이더 (의미/키워드/라벨/통일성/신선도/피드백). 변경 시 자동 정규화 + Config 갱신 + 검색 재호출. preset active 해제.
13. **D 탭 저장된 검색 CRUD** — 빈 input 에 이름 입력 + `+ 현재 검색 저장` → 리스트에 추가. 항목 클릭 → 검색 + 필터 + 가중치 복원 + 재검색. × 버튼 → confirm() 후 삭제.
14. **D 탭 통일성 요약** — 채택 상위 팩 개수 + 거부 카운트 표시 (v1 은 빈 글로벌이라 0). `상세 보기` 클릭 → 모달 (현재는 비어있음 안내).
15. **반응형 ≤768px** — 브라우저 폭을 768px 이하로 줄임 → 사이드 패널 자동 닫힘 + 다시 ⚙ 클릭 시 fixed full-height + 슬라이드.
16. **다크 모드** — OS 다크 모드 (Windows 설정) 전환 시 자동 반영 (변수 var(--*) + prefers-color-scheme).
17. **저장된 검색 페이지 새로고침 후에도 유지** — DB 영속 (`saved_searches` 테이블).

**Phase 4 추가 항목** (MCP `request_user_pick` 시각 검증 — `python -m gah --mcp` + MCP 클라이언트로 `request_user_pick` 호출 필요):

18. **브라우저 pick 카드 출현** — MCP 가 `request_user_pick` 호출 시 라이브러리 페이지 상단에 보라색 strip pick 카드 그룹 출현. 여러 개의 에셋 카드가 그룹으로 표시.
19. **헤더 배지 갱신** — pick 카드 출현 시 헤더 알림 배지 (보라) 숫자 +1. 카드 처리 후 감소.
20. **[채택] 버튼 동작** — pick 카드 에셋 중 하나 클릭 [채택] → 카드 그룹 사라짐 + MCP 쪽 `request_user_pick` 반환 + DB `usage_records` 에 `source="claude_pick"` 레코드 생성 확인.
21. **[✕ 거부] 버튼 동작** — [✕ 거부] 클릭 → 카드 그룹 사라짐 + MCP 쪽 `McpToolError("499_user_cancelled")` 수신.
22. **타임아웃** — 요청 후 `timeout_seconds` 초 동안 미응답 시 MCP 측 `McpToolError("408_timeout")` 수신.
23. **트레이 툴팁** — pick 대기 중 트레이 아이콘 툴팁에 "N건 대기" 메시지 표시. 처리 후 해제.

## 10. 문서 맵

- [`README.md`](./README.md) — 사용자용 시작 안내
- [`CLAUDE.md`](./CLAUDE.md) — Claude 작업 가이드 (§2 진행 현황 표 + §8 다음 작업)
- [`HANDOFF.md`](./HANDOFF.md) — 이 파일, 마일스톤/phase 경계 인계
- [`DESIGN.md`](./DESIGN.md) — 전체 아키텍처·스키마·MCP 명세
- [`milestones/M5_plan.md`](./milestones/M5_plan.md) — M5 의 6 phase 75 task plan
- [`milestones/M5_todo.md`](./milestones/M5_todo.md) — TDD 체크리스트
- [`milestones/`](./milestones/) — 이전 마일스톤들의 plan/todo/verification
- [`docs/MCP_USAGE_GUIDE.md`](./docs/MCP_USAGE_GUIDE.md) — Phase 4D 에서 17번째 도구(`request_user_pick`) + Claude 의사결정 흐름 갱신 완료
- [`docs/superpowers/specs/2026-05-17-m5-web-gui-and-library-redesign.md`](./docs/superpowers/specs/2026-05-17-m5-web-gui-and-library-redesign.md) — M5 spec 원본

## 11. 갱신 규칙

이 문서는 다음 시점에 반드시 업데이트한다.

1. Phase 또는 마일스톤이 완료될 때 (§1 한 줄 요약, §2 검증 결과, §5 다음 작업).
2. 환경 결정이 바뀔 때 (§3).
3. 새 금기·주의사항이 발견될 때 (§9).

내용을 누적하기보다 **현재 시점의 진실만** 적는다. 과거 이력은 git log 에 맡긴다.
