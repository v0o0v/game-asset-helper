# M6 todo

[M6_plan.md](./M6_plan.md) 에서 도출한 TDD 순서 체크리스트. 작업 단위 번호(§4.x) 는 plan 의 절을 그대로 가리킨다.

체크박스 진행 규칙 — phase 단위 5 회 반복 (M5 보다 작음):

```
Phase 0 (스캐폴딩 + fixtures)            →  A → B → C → 커밋들
Phase 1 (JSON parser + grid + preview)   →  A → B → C → D → 커밋들
Phase 2 (Analyzer + Store)               →  A → B → C → 커밋들
Phase 3 (MCP 도구 18번째)                →  A → B → C → 커밋들
Phase 4 (Web 카드 배지)                  →  A → B → C → 커밋들
Phase 5 (문서 + verification)            →  D
```

A = 스캐폴딩. B = red (테스트 먼저). C = green (모듈 의존 순서대로 통과). D = 검증 / 회귀 / 커밋.

각 task 의 세부 step 은 plan §4 에 풀어 적혀 있다. 본 todo 는 task 단위만 추적한다.

---

## Phase 0 — 스캐폴딩 + 테스트 fixtures (~0.5일)

### A. 브랜치 + 패키지 마커

- [ ] `feat/m6-sheet-animation` 브랜치 확인 (이미 분기됨)
- [ ] `src/gah/core/sheet/__init__.py` 생성 — 빈 패키지 마커 (Task 0.1)
- [ ] 임포트 smoke 통과
- [ ] 커밋: `scaffold(m6): core/sheet 패키지 마커`

### B. red — 데이터클래스

- [ ] `tests/test_sheet_types.py` 5 케이스 작성 (Task 0.2 Step 1)
- [ ] `pytest tests/test_sheet_types.py -v` → 5 FAIL

### C. green — types.py 구현

- [ ] `src/gah/core/sheet/types.py` 5 데이터클래스 (Task 0.2 Step 3)
- [ ] `pytest tests/test_sheet_types.py -v` → 5 passed
- [ ] `pytest -q` 회귀 → 796 + 5 = 801 passed
- [ ] 커밋: `feat(m6): sheet 데이터클래스 5종`

### D. fixtures

- [ ] `tests/fixtures/sheets/` 디렉터리 + 3 JSON fixture 작성 (Task 0.3)
- [ ] `pytest -q` → 801 passed (회귀 0)
- [ ] 커밋: `test(m6): Aseprite/TexturePacker JSON fixtures`

---

## Phase 1 — JSON parser + grid_detect + preview (~1.5일)

### A. red — 테스트 ~33 케이스 작성

- [ ] `tests/test_sheet_json_parser.py` 12 케이스 (Task 1.1)
- [ ] `tests/test_sheet_grid_detect.py` 10 케이스 (Task 1.2)
- [ ] `tests/test_sheet_preview.py` 5 케이스 (Task 1.3)
- [ ] `tests/test_sheet_detect.py` 6 케이스 (Task 1.4)
- [ ] 일괄 `pytest tests/test_sheet_*.py -v` → 33 FAIL `ModuleNotFoundError`

### B. green — 모듈 4개 구현 (의존성 순서)

- [ ] `src/gah/core/sheet/json_parser.py` (Task 1.1) → 12 passed
- [ ] `src/gah/core/sheet/grid_detect.py` (Task 1.2) → 10 passed
- [ ] `src/gah/core/sheet/preview.py` (Task 1.3) → 5 passed
- [ ] `src/gah/core/sheet/detect.py` (Task 1.4) → 6 passed

### C. 회귀

- [ ] `pytest -q` → 801 + 33 = 834 passed

### D. 커밋 4개

- [ ] `feat(m6): sheet/json_parser — Aseprite + TexturePacker 자동 감지`
- [ ] `feat(m6): sheet/grid_detect — Pillow alpha 행/열 합 격자 추정`
- [ ] `feat(m6): sheet/preview — 8칸 1행 합성 + 선형 stride`
- [ ] `feat(m6): sheet/detect — JSON 사이드카 + grid 오케스트레이션`

---

## Phase 2 — SpritesheetAnalyzer + Store 마이그레이션 (~1일)

### A. red — Store + Analyzer 테스트

- [ ] `tests/test_store_m6.py` 8 케이스 (Task 2.1)
- [ ] `tests/test_analyzer_spritesheet.py` 10 케이스 (Task 2.2)
- [ ] 일괄 → 18 FAIL

### B. green — Store 먼저, Analyzer 다음

- [ ] `src/gah/core/store.py` 수정 (Task 2.1) — `animations_json` 컬럼 + `get_sprite_meta` + `update_asset_kind`
- [ ] `pytest tests/test_store_m6.py -v` → 8 passed
- [ ] `src/gah/core/analyzer/spritesheet.py` (Task 2.2)
- [ ] `src/gah/core/analyzer/__init__.py` export
- [ ] `pytest tests/test_analyzer_spritesheet.py -v` → 10 passed

### C. 큐 통합 + 회귀

- [ ] `src/gah/core/analysis_queue.py` `__init__` + `_analyze_one` + `_persist` 수정 (Task 2.3)
- [ ] `src/gah/app.py` `run_tray` 에 SpritesheetAnalyzer 인스턴스 + queue 주입
- [ ] 기존 `tests/test_analysis_queue*.py` fixture 에 `spritesheet=` 인자 추가
- [ ] `pytest -q` 회귀 → 834 + 18 = 852 passed

### D. 커밋 3개

- [ ] `feat(m6): Store animations_json 컬럼 + get_sprite_meta + update_asset_kind`
- [ ] `feat(m6): SpritesheetAnalyzer + Gemma animation_hint`
- [ ] `feat(m6): AnalysisQueue + app.py 가 SpritesheetAnalyzer 라우팅 + kind promote`

---

## Phase 3 — MCP 도구 18번째 `suggest_animation_frames` (~1일)

### A. red — Pydantic 모델 + 도구 함수

- [ ] `src/gah/mcp/models.py` 의 `SuggestAnimationFramesRequest/Result` 추가 (Task 3.1)
- [ ] `tests/test_mcp_tools_m6.py` 12 케이스 (Task 3.2)
- [ ] `pytest tests/test_mcp_tools_m6.py -v` → 12 FAIL

### B. green — 도구 함수 + 서버 등록

- [ ] `src/gah/mcp/tools.py` 에 `tool_suggest_animation_frames` (Task 3.2)
- [ ] `pytest tests/test_mcp_tools_m6.py -v` → 12 passed
- [ ] `src/gah/mcp/server.py` 의 `register_all_tools` 에 18번째 도구 등록 + log 갱신 + INSTRUCTIONS 갱신 (Task 3.3)
- [ ] `tests/test_mcp_integration.py` 의 expected 셋 + 카운트 갱신 (17 → 18)

### C. 회귀

- [ ] `pytest -q` → 852 + 12 = 864 passed
- [ ] `pytest -m mcp_integration -v` → 2/2 (18 도구 stdio 응답)

### D. 커밋 3개

- [ ] `feat(m6): mcp models SuggestAnimationFrames{Request,Result}`
- [ ] `feat(m6): tool_suggest_animation_frames + 404/400 에러 매핑`
- [ ] `feat(m6): MCP suggest_animation_frames 18번째 도구 + INSTRUCTIONS 갱신`

---

## Phase 4 — Web 와이드/리스트 카드 🎞 N frames 배지 (~0.5일)

### A. red — 카드 배지 테스트

- [ ] `tests/test_web_card_frame_badge.py` 5 케이스 (Task 4.3 Step 1)
- [ ] `pytest tests/test_web_card_frame_badge.py -v` → 5 FAIL

### B. green — search + router + template

- [ ] `src/gah/core/search.py` `_hydrate_meta` spritesheet 분기 (Task 4.1)
- [ ] `src/gah/web/routers/library.py` `_row_to_dict` + `_asset_row_to_dict` 갱신 (Task 4.2)
- [ ] `src/gah/web/templates/_card_wide.html` 배지 (Task 4.3 Step 3)
- [ ] `src/gah/web/templates/_card_list.html` 배지 (Task 4.3 Step 4)
- [ ] `src/gah/web/static/css/main.css` `.frame-badge` 클래스 (Task 4.3 Step 5)
- [ ] `src/gah/web/static/css/themes.css` light/dark 변수 (Task 4.3 Step 5)
- [ ] `pytest tests/test_web_card_frame_badge.py -v` → 5 passed

### C. 회귀

- [ ] `pytest -q` → 864 + 5 = 869 passed

### D. 커밋 3개

- [ ] `feat(m6): search._hydrate_meta — spritesheet frame_count 노출`
- [ ] `feat(m6): library router — frame_count flatten`
- [ ] `feat(m6): 와이드/리스트 카드 🎞 N frames 배지 + light/dark CSS`

---

## Phase 5 — 문서 마감 + verification (~0.5일)

### D. 문서 갱신 + 인계

- [ ] `DESIGN.md` §4.2.2 + §6.6 + §11 M6 완료 표시 (Task 5.1)
- [ ] `docs/MCP_USAGE_GUIDE.md` 18번째 도구 + Unity AnimationClip 예시 (Task 5.2)
- [ ] `milestones/M6_verification.md` 작성 (Task 5.3)
- [ ] `CLAUDE.md` §2 진행 현황 + §8 다음 작업 (Task 5.4)
- [ ] `HANDOFF.md` M6 완료 인계 (Task 5.4)
- [ ] 커밋: `docs(m6): DESIGN/MCP_USAGE_GUIDE/CLAUDE/HANDOFF + M6_verification — 마감`

---

## 최종 회귀

- [ ] `pytest -q` → `869 passed, 1 skipped, 4 deselected` 또는 +1~2 (오차 허용)
- [ ] `pytest -m mcp_integration -v` → 2/2
- [ ] `git log --oneline -20` → spec 1 + plan 1 + phase 별 ~15 커밋
- [ ] (선택) `python -m gah --tray` + 시트 자산 시각 검증

## 메모리 갱신

- [ ] `project_m6_complete.md` (project) 작성 — 브랜치 + 테스트 카운트 + 18 도구 + 다음 M7
