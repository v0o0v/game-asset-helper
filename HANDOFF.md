# HANDOFF — Cowork → Claude Code (또는 다음 세션)

**마지막 인계 시각**: 2026-05-19 (M7 [PR #8](https://github.com/v0o0v/game-asset-helper/pull/8) main 머지 완료)
**마지막 완료 마일스톤**: **M7 — Unity Asset Store 임포트 + 프로젝트 워크플로** — ✅ 완료 (사용자 수동 검증 통과)
**현재 브랜치**: `main` (origin/main 과 sync, working tree clean)
**다음 작업**: **M8 — 패키징 + i18n** (1주) — `superpowers:brainstorming` → spec/plan 부터 시작

이 문서는 작업이 중단될 때 다음 세션이 "현재 어디까지 와 있는가"를 한 번에 파악하도록 작성된 스냅샷이다.

## 1. 한 줄 요약

M7 (Unity Asset Store 임포트 + 프로젝트 워크플로) **PR #8 main 머지 완료**. 7 phase + 후속 patch 19건 (수동 검증 중 발견된 회귀 / UX 개선) 누적. pytest **1002 passed + 1 skipped + 40 deselected** (M6 887 baseline + M7 +115). MCP 18 → **20 도구** (`scan_unity_asset_store_cache` + `list_unity_packages`). 격리 불변식 I-1~I-5 회귀 테스트 고정. 신규 의존성 0. 다음 = **M8 (패키징 + i18n)** spec/plan 부터.

수동 검증 결과 + 후속 patch 19 목록 + 시나리오는 [`milestones/M7_verification.md`](./milestones/M7_verification.md) §8~§9 참고.

## 2. 검증된 사실 (M7 완료)

자동 — `pytest -q` 결과 **1011 passed + 1 skipped + 40 deselected**

| Phase | 핵심 산출물 | 신규 테스트 |
|---|---|---:|
| 0 — 스캐폴딩 | types 7 dataclass + .unitypackage fixture + asset_factory | +7 |
| 1A — cache_paths | 4단계 우선순위 검출 | +6 |
| 1B — unitypackage | gzip+tarfile 파서 + 물리 복사 | +12 |
| 1C — scanner | walk + state 머신 | +10 |
| 1D — importer + remote_optin | extract + pack.json + skeleton | +11 |
| 2A — Store unity_imports + Config | 마이그레이션 + 10 CRUD + Config 5 필드 | +15 |
| 2B — Store projects + tray + boot | 사용/분포/선호도 + 트레이 + 자동 스캔 | +14 |
| 3A — MCP models + tools | 4 Pydantic + 2 도구 + import_url | +10 |
| 3B — MCP server 20 도구 | INSTRUCTIONS + integration 20 도구 | 0 |
| 4A — Unity 라우터 + 6 endpoint | scan/preview/import/skip/restore | +8 |
| 4B — Unity 페이지 HTML + CSS | unity_asset_store.html + 상태 칩 + 사이드바 | 0 (4A 에 포함) |
| 5 — 활성 프로젝트 + 채택 | 4 API + SSE + 글로벌 헤더 + 채택 버튼 | +13 |
| 6A — /projects 목록 | projects_list.html + 활성 강조 | +4 |
| 6B — /projects/<id> 사용+분포 | project_detail.html | +4 |
| 6C — 선호도 패널 | _preference_panel.html + 정렬/검색 | +5 |
| 7 — invariant + 문서 + verification | I-1~I-5 회귀 + 문서 + verification | +5 |
| **M7 전체** | **MCP 18 → 20, 신규 의존성 0** | **+124** |

`pytest -m mcp_integration -v` — 2/2 (**20 도구** 확인).

## 3. 환경 (재현용)

| 항목 | 값 |
|---|---|
| OS | Windows 10 |
| Python | python.org 3.12 (`C:\Users\v0o0v\AppData\Local\Programs\Python\Python312\python.exe`) |
| venv | `C:\Users\v0o0v\.venvs\gah\` |
| 작업 폴더 | `D:\ClaudeCowork\game-asset-helper\game-asset-helper\` |
| 런타임 데이터 | `C:\Users\v0o0v\AppData\Roaming\GameAssetHelper\` |
| 라이브러리 루트 | `%APPDATA%\GameAssetHelper\library\` |
| 메타 DB | `%APPDATA%\GameAssetHelper\metadata.db` (WAL, `unity_imports` + `projects` + `asset_usage` M7 에서 확장) |
| **M7: unity_import 패키지** | `src/gah/core/unity_import/` (types/cache_paths/unitypackage/scanner/importer/remote_optin) |
| **M7: MCP 도구 수** | 20 도구 (scan_unity_asset_store_cache + list_unity_packages 신규) |
| **M7: 격리 invariant 테스트** | `tests/test_isolation_invariants.py` (I-1~I-5) |

**금기**: Microsoft Store Python, Cowork 작업 폴더 내부 venv.

M7 신규 의존성: 없음.

기존 venv 그대로 사용 시:

```powershell
pip install -e D:\ClaudeCowork\game-asset-helper\game-asset-helper[dev]
```

→ 의존성 변경 없으므로 no-op (또는 소수 업데이트만).

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

→ `On branch feat/m7-unity-asset-store-import`, working tree clean.

```powershell
pytest -q
```

→ `1002 passed, 1 skipped, 40 deselected`.

## 5. 다음 세션 진입 절차 (M8 시작)

### 5.1 환경 복원 + 회귀 검증

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
git status
```

→ `On branch main` + `up to date with 'origin/main'` + working tree clean.

```powershell
pytest -q
```

→ `1002 passed, 1 skipped, 40 deselected` (M7 머지 결과).

### 5.2 M8 시작

1. `superpowers:brainstorming` 으로 M8 옵션 비교
2. `superpowers:writing-plans` 로 `milestones/M8_plan.md` 작성
3. `superpowers:subagent-driven-development` 로 phase 별 진행 (M5/M6/M7 검증된 패턴)

M8 핵심 (DESIGN.md §11 Milestone 8):
- **PyInstaller 단일 exe** — 일반 사용자 배포 (torch CUDA/CPU 통합 + 모든 의존성 단일 .exe)
- **웹 UI i18n** — Jinja2 + babel, `Config.ui_language` (현재 한국어 hardcoded)
- (선택) 다크/라이트 모드 토글 UI
- (선택) 자동 동기화 스케줄러 (M7 의 부팅 1회 + 매일 자동 — M7 에서 v2 로 미룸)

### 5.3 다음 세션이 자동 로드하는 메모리

- [M8 시작 직전 상태 (2026-05-19)](./.claude/.../memory/project_m8_starting_state.md) — M7 PR #8 머지 완료, 1002 passed + 1 skipped + 40 deselected, MCP 20 도구. 다음 세션이 M8 spec/plan 부터.

(메모리 인덱스의 `project_m7_*` 시리즈는 main 머지 완료라 stale — `project_m8_starting_state.md` 만 active.)

## 6. 마일스톤 재정렬 (M7 완료)

| # | 이름 | 일정 | 상태 |
|---:|---|---:|---|
| M5 | 웹 GUI 전환 + 리디자인 + Claude pick | 5.5주 | ✅ 완료 |
| M6 | 시트 분석 + 애니메이션 | 1주 | ✅ 완료 |
| M7 | Unity Asset Store 임포트 | 1주 | ✅ 완료 |
| **M8** | **패키징 + i18n** | **1주** | **대기** |

## 7. 알려진 한계 / 의도적 미룬 항목

- publisher 패널 실제 HTTP 구현 (v2 — 현재 skeleton 만)
- 자동 동기화 스케줄러 (M8)
- 캐시에서 사라진 .unitypackage 자동 제거 (v2)
- 다중 캐시 경로 (v2)
- UPM .tgz 임포트 (v2)
- get_active_project / set_active_project / get_project_preferences MCP 도구 (v2)
- PSD/TGA 확장자 임포트 (v2)
- 임포트 완료 후 unity_imports 자동 되돌림 (v2)
- 라이브러리 카드 직접 피드백 입력 UI (v2)
