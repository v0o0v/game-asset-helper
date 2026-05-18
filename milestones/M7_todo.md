# M7 todo

[M7_plan.md](./M7_plan.md) 에서 도출한 TDD 순서 체크리스트. 작업 단위 번호(§4.x) 는 plan 의 절을 그대로 가리킨다.

체크박스 진행 규칙 — phase 단위 5 회 반복:

```
Phase 0 (스캐폴딩 + fixtures)             →  A → B → C → D
Phase 1A (cache_paths)                    →  B → C → D
Phase 1B (unitypackage)                   →  B → C → D
Phase 1C (scanner)                        →  B → C → D
Phase 1D (importer + remote_optin)        →  B → C → D
Phase 2A (Store unity_imports + Config)   →  B → C → D
Phase 2B (Store projects + 트레이 + 부팅) →  B → C → D
Phase 3A (MCP 모델 + 도구)                →  B → C → D
Phase 3B (MCP server 20 도구)             →  D
Phase 4A (Unity 라우터)                   →  B → C → D
Phase 4B (Unity 페이지 UI)                →  D
Phase 5 (활성 프로젝트 + 채택)            →  B → C → D
Phase 6A (/projects 라우터)               →  B → C → D
Phase 6B (/projects/<id> 사용+분포)       →  B → C → D
Phase 6C (선호도 패널)                    →  B → C → D
Phase 7 (invariant + 문서 + verification) →  B → C → D
```

A = 스캐폴딩. B = red (테스트 먼저). C = green (구현). D = 회귀 / 커밋.

각 task 의 세부 step 은 plan §4 에 풀어 적혀 있다. 본 todo 는 task 단위만 추적한다. 모든 phase 끝나면 `pytest -q` 가 **~1008 passed** 가 되어야 한다.

---

## Phase 0 — 스캐폴딩 + 테스트 fixtures (~0.5일)

### A. 브랜치 + 패키지 마커

- [ ] `feat/m7-unity-asset-store-import` 브랜치 확인 (또는 main 위 작업)
- [ ] `src/gah/core/unity_import/__init__.py` 생성 — 빈 패키지 마커 (Task 0.1)
- [ ] 임포트 smoke 통과
- [ ] 커밋: `scaffold(m7): core/unity_import 패키지 마커`

### B. red — 데이터클래스

- [ ] `tests/test_unity_import_types.py` 7 케이스 작성 (Task 0.2 Step 1)
- [ ] `pytest tests/test_unity_import_types.py -v` → 7 FAIL

### C. green — types.py 구현

- [ ] `src/gah/core/unity_import/types.py` 7 frozen dataclass (Task 0.2 Step 3)
- [ ] `pytest tests/test_unity_import_types.py -v` → 7 passed
- [ ] `pytest -q` 회귀 → 887 + 7 = 894 passed
- [ ] 커밋: `feat(m7): unity_import 데이터클래스 7종`

### D. fixtures

- [ ] `tests/fixtures/unity/make_unitypackage.py` 작성 (Task 0.3)
- [ ] fixture import smoke
- [ ] 커밋: `test(m7): .unitypackage fixture helper`
- [ ] `tests/conftest.py` `asset_factory` fixture 추가 (Task 0.4)
- [ ] 회귀 `pytest -q` → 894 passed
- [ ] 커밋: `test(m7): conftest asset_factory fixture`

---

## Phase 1A — cache_paths.py (~0.5일)

> 의존: Phase 2A Task 2.1 (Config 신규 필드) 가 먼저. 본 plan 은 **Task 2.1 → Task 1.1** 순서.

### B. red

- [ ] `tests/test_unity_cache_paths.py` 6 케이스 작성 (Task 1.1)
- [ ] 6 FAIL

### C. green

- [ ] `src/gah/core/unity_import/cache_paths.py` 구현
- [ ] 6 passed

### D. 회귀 + 커밋

- [ ] `pytest -q` → 900 passed
- [ ] 커밋: `feat(m7): unity_import/cache_paths — 4단계 우선순위 검출`

---

## Phase 1B — unitypackage.py (~1일)

### B. red

- [ ] `tests/test_unity_unitypackage.py` 12 케이스 (Task 1.2)
- [ ] 12 FAIL

### C. green

- [ ] `src/gah/core/unity_import/unitypackage.py` 구현
- [ ] 12 passed

### D. 회귀 + 커밋

- [ ] `pytest -q` → 912 passed
- [ ] 커밋: `feat(m7): unity_import/unitypackage — tarfile+gzip 파서 + 물리 복사`

---

## Phase 1C — scanner.py (~1일)

> 의존: Phase 2A Task 2.2 (Store unity_imports CRUD).

### B. red

- [ ] `tests/test_unity_scanner.py` 10 케이스 (Task 1.3)
- [ ] 10 FAIL

### C. green

- [ ] `src/gah/core/unity_import/scanner.py` 구현
- [ ] 10 passed

### D. 회귀 + 커밋

- [ ] `pytest -q` → 922 passed
- [ ] 커밋: `feat(m7): unity_import/scanner — 캐시 walk + state 머신`

---

## Phase 1D — importer.py + remote_optin.py skeleton (~1일)

### B. red

- [ ] `tests/test_unity_importer.py` 8 케이스 (Task 1.4)
- [ ] `tests/test_unity_remote_optin.py` 3 케이스 (Task 1.5)
- [ ] 11 FAIL

### C. green

- [ ] `src/gah/core/unity_import/importer.py` 구현
- [ ] `src/gah/core/unity_import/remote_optin.py` 구현
- [ ] 11 passed

### D. 회귀 + 커밋

- [ ] `pytest -q` → 933 passed
- [ ] 커밋: `feat(m7): unity_import/importer — tarfile.extract + pack.json`
- [ ] 커밋: `feat(m7): unity_import/remote_optin — v2 skeleton`

---

## Phase 2A — Store unity_imports + Config (~0.5일)

### B. red

- [ ] `tests/test_store_m7_config.py` 5 케이스 (Task 2.1)
- [ ] `tests/test_store_m7_unity.py` 10 케이스 (Task 2.2)
- [ ] 15 FAIL

### C. green

- [ ] `src/gah/config.py` 5 신규 필드 + backward compat (Task 2.1)
- [ ] `src/gah/core/store.py` unity_imports CRUD 추가 (Task 2.2)
- [ ] `src/gah/core/store.py` record_asset_use enum `+"user_web"` (Task 2.3)
- [ ] 15 + 1 passed

### D. 회귀 + 커밋

- [ ] `pytest -q` → 949 passed
- [ ] 커밋: `feat(m7): Config 신규 5 필드`
- [ ] 커밋: `feat(m7): Store unity_imports 테이블 + CRUD`
- [ ] 커밋: `feat(m7): record_asset_use source "user_web" 추가`

---

## Phase 2B — Store projects 쿼리 + 트레이 + 부팅 자동 스캔 (~0.5일)

### B. red

- [ ] `tests/test_store_m7_projects.py` 10 케이스 (Task 2.4)
- [ ] 10 FAIL

### C. green

- [ ] `src/gah/core/store.py` projects 관련 5 메서드 추가 (Task 2.4)
- [ ] 10 passed

### D. 트레이 + 부팅 자동 스캔 + 회귀 + 커밋

- [ ] `src/gah/app.py` 부팅 자동 스캔 hook (Task 2.5)
- [ ] `src/gah/tray.py` "Unity 캐시 스캔" + 현재 프로젝트 서브메뉴 (Task 2.5)
- [ ] `pytest -q` → 959 passed
- [ ] 커밋: `feat(m7): Store projects 쿼리 (활성/목록/사용/분포/선호도)`
- [ ] 커밋: `feat(m7): 부팅 자동 스캔 + 트레이 Unity 메뉴`

---

## Phase 3A — MCP 모델 + 도구 (~0.5일)

### B. red

- [ ] `tests/test_mcp_tools_m7.py` 10 케이스 (Task 3.1)
- [ ] 10 FAIL

### C. green

- [ ] `src/gah/mcp/models.py` 4 Pydantic 추가
- [ ] `src/gah/mcp/tools.py` 2 도구 함수 추가
- [ ] 10 passed

### D. 회귀 + 커밋

- [ ] `pytest -q` → 969 passed
- [ ] 커밋: `feat(m7): MCP scan + list 도구 (19, 20번째) + 모델`

---

## Phase 3B — MCP server 등록 20 도구 + integration (~0.5일)

### D

- [ ] `src/gah/mcp/server.py` `register_all_tools` 2 도구 추가 + INSTRUCTIONS 갱신 (Task 3.2)
- [ ] 로그 `tools=20` 갱신
- [ ] `tests/test_mcp_integration.py` 갱신 — `tools/list` 20 도구 검증 (Task 3.3)
- [ ] `pytest -m mcp_integration -v` → 2 passed
- [ ] `pytest -q` → 969 passed (회귀 0)
- [ ] 커밋: `feat(m7): MCP server 등록 20 도구 + INSTRUCTIONS Unity 워크플로`

---

## Phase 4A — /unity-asset-store 라우터 + 6 endpoint (~1일)

### B. red

- [ ] `tests/test_web_routers_unity.py` 8 케이스 (Task 4.1)
- [ ] 8 FAIL

### C. green

- [ ] `src/gah/web/routers/unity_asset_store.py` 라우터 + 6 endpoint 구현
- [ ] `src/gah/web/app.py` 라우터 등록
- [ ] 8 passed

### D. 회귀 + 커밋

- [ ] `pytest -q` → 977 passed
- [ ] 커밋: `feat(m7): /unity-asset-store 라우터 + 6 endpoint`

---

## Phase 4B — Unity 페이지 HTML + 사이드바 + CSS (~0.5일)

### D

- [ ] `src/gah/web/templates/unity_asset_store.html` 작성 (Task 4.2)
- [ ] `src/gah/web/templates/_unity_package_row.html` 작성
- [ ] `src/gah/web/templates/base.html` 사이드바 메뉴 2개 추가
- [ ] `src/gah/web/static/css/main.css` 상태 칩 + Unity 표 CSS
- [ ] `src/gah/web/static/css/themes.css` light/dark 변수
- [ ] `pytest -q` → 977 passed (회귀 0)
- [ ] 커밋: `feat(m7): Unity Asset Store 페이지 HTML + 상태 칩 + 사이드바`

---

## Phase 5 — 활성 프로젝트 컨텍스트 + 채택 통합 (~1일)

> Cross-cutting. 가장 큰 phase.

### B. red

- [ ] `tests/test_web_active_project.py` 8 케이스 (Task 5.1)
- [ ] `tests/test_web_card_adopt_button.py` 5 케이스 (Task 5.3)
- [ ] 13 FAIL

### C. green

- [ ] `src/gah/web/routers/projects.py` 활성 프로젝트 API 4개 + SSE broadcast (Task 5.1)
- [ ] `src/gah/web/templates/_header_project_dropdown.html` (Task 5.2)
- [ ] `src/gah/web/templates/_modal_new_project.html` (Task 5.2)
- [ ] `src/gah/web/templates/base.html` 헤더 fragment 포함 (Task 5.2)
- [ ] `src/gah/web/routers/library.py` 채택 버튼 + 검색 project_id 주입 (Task 5.3)
- [ ] `src/gah/web/routers/feedback.py` 활성 프로젝트 주입 (Task 5.3)
- [ ] `src/gah/web/routers/picks.py` 사용자 채택 source="claude_pick" + 활성 프로젝트 (Task 5.3)
- [ ] `src/gah/web/templates/_card_wide.html` / `_card_list.html` 채택 버튼 갱신 (Task 5.3)
- [ ] 13 passed

### D. 회귀 + 커밋

- [ ] `pytest -q` → 990 passed
- [ ] 커밋: `feat(m7): 활성 프로젝트 API + SSE broadcast + 채택 endpoint`
- [ ] 커밋: `feat(m7): 글로벌 헤더 드롭다운 + 새 프로젝트 모달`
- [ ] 커밋: `feat(m7): 라이브러리 카드 채택 + 검색/피드백/픽 활성 프로젝트 연동`

---

## Phase 6A — /projects 라우터 + 페이지 (~0.5일)

### B. red

- [ ] `tests/test_web_routers_projects.py` 4 케이스 (Task 6.1)
- [ ] 4 FAIL

### C. green

- [ ] `src/gah/web/routers/projects.py` `/projects` GET 추가
- [ ] `src/gah/web/templates/projects_list.html` 작성
- [ ] 4 passed

### D. 회귀 + 커밋

- [ ] `pytest -q` → 994 passed
- [ ] 커밋: `feat(m7): /projects 목록 페이지 + 활성 프로젝트 강조`

---

## Phase 6B — /projects/<id> 사용 이력 + 채택 팩 분포 (~0.5일)

### B. red

- [ ] `tests/test_web_routers_projects.py` 4 추가 케이스 (Task 6.2)
- [ ] 4 FAIL

### C. green

- [ ] `src/gah/web/routers/projects.py` `/projects/<id>` GET 추가
- [ ] `src/gah/web/templates/project_detail.html` 작성 (헤더 + 사용 + 분포 부분만)
- [ ] 4 passed

### D. 회귀 + 커밋

- [ ] `pytest -q` → 998 passed
- [ ] 커밋: `feat(m7): /projects/<id> 상세 페이지 + 사용 이력 + 채택 팩 분포`

---

## Phase 6C — /projects/<id> 자산별 선호도 패널 (~1일)

### B. red

- [ ] `tests/test_web_routers_projects.py` 5 추가 케이스 (Task 6.3)
- [ ] 5 FAIL

### C. green

- [ ] `src/gah/web/routers/projects.py` `/projects/<id>/preferences.json` API 추가
- [ ] `src/gah/web/templates/_preference_panel.html` 작성
- [ ] `src/gah/web/templates/project_detail.html` 의 선호도 패널 include 활성
- [ ] `src/gah/web/static/css/main.css` 선호도 막대 스타일
- [ ] `src/gah/web/static/css/themes.css` 점수 색상 변수
- [ ] 5 passed

### D. 회귀 + 커밋

- [ ] `pytest -q` → 1003 passed
- [ ] 커밋: `feat(m7): 자산별 선호도 패널 + 정렬/검색/페이지네이션 + 점수 막대`

---

## Phase 7 — 격리 invariant + 문서 마감 + verification (~0.5일)

### B. red

- [ ] `tests/test_isolation_invariants.py` 5 케이스 (Task 7.1)
- [ ] 5 FAIL 또는 일부 passed (이미 격리되어 있으면)

### C. fix (실패 시)

- [ ] 실패한 invariant 의 원인 (라이브러리 라우터의 unity_imports 참조 등) 수정
- [ ] 5 passed

### D. 회귀 + 문서 + verification + 커밋

- [ ] `pytest -q` → 1008 passed
- [ ] 커밋: `test(m7): I-1~I-5 격리 invariant 회귀 테스트`
- [ ] `DESIGN.md` §4.9 / §5.4 / §6.11 / §11 M7 완료 표시 + §4.10 활성 프로젝트 신규 절
- [ ] `CLAUDE.md` §2 M7 완료 + §8 다음 M8
- [ ] `HANDOFF.md` 전체 갱신 (M7 완료 인계)
- [ ] `docs/MCP_USAGE_GUIDE.md` 19, 20번째 도구 + Unity 워크플로 예시
- [ ] 커밋: `docs(m7): DESIGN/CLAUDE/HANDOFF/MCP_USAGE_GUIDE 완료 + 갱신`
- [ ] `milestones/M7_verification.md` 작성 (자동 검증 + 시나리오 + 수동 검증 + 알려진 한계)
- [ ] 커밋: `docs(m7): M7_verification.md — 최종 검증 결과`

---

## 종료 조건

다음 모두 만족하면 M7 완료:

- [ ] `pytest -q` → **~1008 passed + 1 skipped** (정확 수는 verification 에서)
- [ ] `pytest -m mcp_integration -v` → 2 passed (도구 카운트 20)
- [ ] 시나리오 §1.1 ~ §1.6 모두 자동 또는 수동 검증
- [ ] I-1 ~ I-5 격리 invariant 회귀 테스트 모두 통과
- [ ] DESIGN.md / CLAUDE.md / HANDOFF.md / MCP_USAGE_GUIDE.md 갱신 완료
- [ ] `milestones/M7_verification.md` 작성 완료
- [ ] 신규 의존성 0 (pyproject.toml 변경 없음)
- [ ] (옵션) PR 생성 → main 머지 → 후속 patch 처리 (M6 패턴)
