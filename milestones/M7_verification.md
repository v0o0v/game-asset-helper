# M7 — Unity Asset Store 임포트 + 프로젝트 워크플로 (검증)

**최종 상태**: ✅ 자동 검증 모두 통과 (2026-05-18). 사용자 수동 확인 항목 ~12 단계 — §4 에 단계별 체크리스트로 별도 제시.

M6 의 18 MCP 도구 + 887 passed 위에 **.unitypackage 파서/캐시 스캐너/임포터 + 활성 프로젝트 + 프로젝트 페이지 + 자산별 선호도 + MCP 2 신규 도구** 추가. 신규 의존성 없음. 본 마일스톤의 의도와 작업 단위는 [`M7_plan.md`](./M7_plan.md), TDD 체크리스트는 [`M7_todo.md`](./M7_todo.md).

## 1. 자동 테스트 결과

`pytest -q` → **1011 passed + 1 skipped + 40 deselected**

```
1011 passed, 1 skipped, 40 deselected in 63.07s
```

baseline 887 (M6 끝) + 124 신규 (M7) = **1011**.

`pytest -m mcp_integration -v` — 실 subprocess + JSON-RPC 핸드셰이크:

```
tests/test_mcp_integration.py::test_stdio_subprocess_initialize_handshake PASSED
tests/test_mcp_integration.py::test_stdio_subprocess_tools_list_returns_20 PASSED
2 passed in 2.68s
```

> M6 의 도구 카운트 18 → M7 에서 20 (`scan_unity_asset_store_cache` + `list_unity_packages` 추가). 실제 stdio subprocess 가 20 개를 반환함을 확인.

## 2. Phase 진행 현황

| Phase | 상태 | 핵심 산출물 | 신규 테스트 |
|---|---|---|---:|
| 0 — 스캐폴딩 | ✅ | types 7 dataclass + .unitypackage fixture + asset_factory | +7 |
| 1A — cache_paths | ✅ | 4단계 우선순위 검출 | +6 |
| 1B — unitypackage | ✅ | gzip+tarfile 파서 + 물리 복사 | +12 |
| 1C — scanner | ✅ | walk + state 머신 | +10 |
| 1D — importer + remote_optin | ✅ | extract + pack.json + skeleton | +11 |
| 2A — Store unity_imports + Config | ✅ | 마이그레이션 + 10 CRUD + Config 5 필드 | +15 |
| 2B — Store projects + tray + boot | ✅ | 사용/분포/선호도 + I-5 + 트레이 + 자동 스캔 | +14 |
| 3A — MCP models + tools | ✅ | 4 Pydantic + 2 도구 + import_url | +10 |
| 3B — MCP server 20 도구 | ✅ | INSTRUCTIONS + integration 20 도구 | 0 |
| 4A — Unity 라우터 + 6 endpoint | ✅ | scan/preview/import/skip/restore | +8 |
| 4B — Unity 페이지 HTML + CSS | ✅ | unity_asset_store.html + 상태 칩 + 사이드바 | 0 (4A 에 포함) |
| 5 — 활성 프로젝트 + 채택 (cross-cutting) | ✅ | 4 API + SSE + 글로벌 헤더 + 채택 버튼 | +13 |
| 6A — /projects 목록 | ✅ | projects_list.html + 활성 강조 | +4 |
| 6B — /projects/<id> 사용+분포 | ✅ | project_detail.html | +4 |
| 6C — 선호도 패널 | ✅ | _preference_panel.html + 정렬/검색/페이지네이션 | +5 |
| 7 — invariant + 문서 + verification | ✅ | I-1~I-5 회귀 + 문서 + verification | +5 |
| **M7 전체** | **✅** | **MCP 18 → 20, 신규 의존성 0** | **+124** |

## 3. 시나리오 검증 (spec §3)

| # | 시나리오 | 자동 검증 | 수동 검증 (사용자) |
|---|---|---|---|
| 3.1 | 첫 부팅 + 자동 스캔 | `test_app_unity_boot_scan` | `python -m gah --tray` 후 캐시 디렉터리 발견 확인 |
| 3.2 | 활성 프로젝트 선택 + 채택 | `test_web_active_project`, `test_web_card_adopt_button` | 헤더 드롭다운에서 새 프로젝트 생성 + 라이브러리 카드 채택 |
| 3.3 | Unity 패키지 미리보기 + 임포트 | `test_web_routers_unity`, `test_unity_importer` | `/unity-asset-store` 에서 미리보기 + 임포트 → library/ 에 추출 확인 |
| 3.4 | 사용자 "건너뜀" + 영구 + 되돌리기 | `test_unity_scanner::test_mtime_change_reverts_skipped_to_discovered` | 페이지에서 건너뜀 → 재스캔 후 유지 → 다시 후보로 |
| 3.5 | 캐시 업데이트 감지 | `test_unity_scanner::test_mtime_change_reverts_imported_to_discovered` | 사용자 Unity Hub 로 같은 패키지 v2 → mtime 변경 → 다시 임포트 안내 |
| 3.6 | 프로젝트별 선호도 시각화 | `test_web_routers_projects`, `test_isolation_invariants::test_i5_project_preferences_isolated` | `/projects/<id>` 페이지에서 자산별 선호도 패널 확인 |

## 4. 사용자 수동 검증 항목

- [ ] `python -m gah --tray` 실행 → 트레이 + 브라우저 자동 열림
- [ ] 트레이 메뉴에 "Unity 캐시 스캔" 항목 표시
- [ ] 사이드바 메뉴에 "프로젝트" + "Unity Asset Store" 항목 추가됨
- [ ] 글로벌 헤더 우상단에 활성 프로젝트 드롭다운 표시
- [ ] "+ 새 프로젝트" 모달 동작 + 활성 프로젝트 자동 설정
- [ ] 라이브러리 카드 "채택" 버튼이 활성 프로젝트 없을 때 disabled
- [ ] `/unity-asset-store` 페이지 진입 시 발견 목록 표시
- [ ] 미리보기 / 임포트 / 건너뜀 / 다시 후보로 액션 모두 동작
- [ ] 임포트 후 `library/<pack_name>/` 에 자산 파일 복사됨 (원본 .unitypackage 보존)
- [ ] `/projects` 페이지 진입 → 활성 프로젝트 강조 + 통계 표시
- [ ] `/projects/<id>` 진입 → 사용 이력 표 + 채택 팩 분포 + 자산별 선호도 패널 모두 표시
- [ ] 선호도 패널 정렬 4종 + 검색 + 페이지네이션 모두 동작

## 5. 알려진 한계 / 의도적 미룬 항목

(spec §8 그대로 + 본 마일스톤 중 발견된 추가 사항)

- publisher 패널 실제 HTTP 구현 (v2 — 현재 skeleton 만)
- 자동 동기화 스케줄러 (M8)
- 캐시에서 사라진 .unitypackage 자동 제거 (v2)
- 다중 캐시 경로 (v2)
- UPM .tgz 임포트 (v2)
- 사용자 별칭 매핑 GUI (v2)
- get_active_project / set_active_project / get_project_preferences MCP 도구 (v2)
- PSD/TGA 확장자 임포트 (v2)
- 라이브러리 카드 직접 피드백 입력 UI (v2)
- 임포트 완료 후 unity_imports 자동 되돌림 (v2 — 라이브러리 페이지에서 일반 팩 삭제 우회)

## 6. MCP 도구 변경

M6 18 도구 → M7 **20 도구**:

| # | 도구 이름 | 신규 여부 |
|---:|---|---|
| 1~18 | 기존 도구 (M3~M6) | 유지 |
| 19 | `scan_unity_asset_store_cache(force?, filter?)` | M7 신규 |
| 20 | `list_unity_packages(state?, filter?, include_preview?, offset, limit)` | M7 신규 |

임포트 도구는 의도적으로 추가하지 않음 — 사용자 통제 보존. 웹 UI의 "임포트" 버튼만이 1차 경로.

## 7. 격리 불변식 (I-1~I-5)

`tests/test_isolation_invariants.py` 에 5 케이스로 고정:

| 불변식 | 설명 | 상태 |
|---|---|---|
| I-1 | discovered 패키지 자산이 assets 테이블에 미존재 | ✅ |
| I-2 | preview 는 unity_imports.preview_* 만 갱신 | ✅ |
| I-3 | library router 가 unity_imports 미참조 | ✅ |
| I-4 | unity_asset_store router 가 library API 미호출 | ✅ |
| I-5 | project_A 피드백/사용이 project_B 점수에 미반영 | ✅ |
