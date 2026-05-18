# HANDOFF — Cowork → Claude Code (또는 다음 세션)

**마지막 인계 시각**: 2026-05-18 (M6 머지 + 후속 patch 8 적용 완료)
**마지막 완료 마일스톤**: **M6 — 시트 분석 + 애니메이션** — ✅ 완료, [PR #7](https://github.com/v0o0v/game-asset-helper/pull/7) main 머지됨 + 수동 검증 중 발견된 회귀 8건도 main 에 반영 완료
**현재 브랜치**: `main` (origin/main 과 sync), working tree clean
**다음 작업**: **M7 — Unity Asset Store 임포트** (~1주) — spec/plan/todo 부터 시작

이 문서는 작업이 중단될 때 다음 세션이 "현재 어디까지 와 있는가" 를 한 번에 파악하도록 작성된 스냅샷이다. 마일스톤 또는 phase 가 하나 끝날 때마다 이 문서를 갱신한다.

## 1. 한 줄 요약

M6 (시트 분석 + 애니메이션) 가 1 세션 안에 전 phase 완료 → [PR #7](https://github.com/v0o0v/game-asset-helper/pull/7) main 머지. 그 후 사용자 수동 검증 중 회귀 8건 (썸네일 분기/모달/큐 라우팅/aggregate 레이스/Gemma str split/Ollama cold-start 등) 발견 → 모두 fix + 회귀 테스트 추가 후 main 에 누적. 최종 **887 passed + 1 skipped + 40 deselected** (M6 spec 결정 +84 + 후속 patch test +7). MCP 18 도구. 신규 의존성 0. 다음 작업 = M7 (Unity Asset Store 임포트) spec/plan 부터.

## 2. 검증된 사실 (M6 완료 + 후속 patch 적용)

자동 — `pytest -q` 결과 **887 passed + 1 skipped + 40 deselected** (M5 end 796 대비 +91 신규: M6 spec +84, 후속 patch test +7).

| 영역 | 신규 케이스 | 비고 |
|---|---:|---|
| M0~M5 베이스라인 | 796 | M5 완료 시점 |
| Phase 0 (Sheet 타입 5 dataclass) | +5 | `test_sheet_types` |
| Phase 1A (json_parser) | +12 | Aseprite Array/Hash + TexturePacker |
| Phase 1B (grid_detect) | +10 | 균일 격자 + 알파 없는 폴백 |
| Phase 1C (preview) | +5 | 8칸 이하 그대로 + stride |
| Phase 1D (detect) | +6 | JSON 우선 + 격자 폴백 + None |
| Phase 1 fix | +2 | Store M6 컬럼 + fixture |
| Phase 2A (Store animations_json) | +8 | 저장/조회/갱신/None |
| Phase 2B (SpritesheetAnalyzer) | +10 | detect 성공/실패/폴백/Gemma |
| Phase 2C (AnalysisQueue promote) | +3 | sprite → spritesheet promote |
| Phase 3A (MCP models) | +4 | Input/Output models |
| Phase 3B (MCP tool) | +8 | 정상/404/400 |
| Phase 4A (Web 카드 라우터) | +3 | frame_count flatten |
| Phase 4B (Web 카드 HTML 배지) | +2 | wide/list 배지 존재 |
| Phase 5 (cleanup + docs) | 0 | refactor + docs 만 |
| **M6 spec 합계** | **+84** | M6 PR #7 (main 머지) |
| 후속 patch — spritesheet 썸네일 회귀 | +1 | `test_spritesheet_kind_generates_thumbnail` |
| 후속 patch — Gemma str→char split 방어 | +2 | `test_gemma_returns_string_not_array_normalized` 외 |
| 후속 patch — Ollama cold-start retry | +4 | `TestColdStartRetry` 4건 (ReadTimeout/ConnectError/4xx no-retry/native succeeds) |
| **후속 patch 합계** | **+7** | M6 머지 후 main 직접 누적 |
| **최종 누적** | **+91** | **total 887** |

`pytest -m mcp_integration -v` — 2/2 (**18 도구** 확인, Phase 3 에서 갱신).

수동 — 사용자 시각 검증 가능 (수동 검증 항목은 `milestones/M6_verification.md` §4):

```powershell
python -m gah --tray
```

→ 트레이 아이콘 + 브라우저 자동 열림 (http://127.0.0.1:9874/library). M5 기능 전체 + **M6 신규: 시트 PNG + Aseprite JSON 드롭 → `🎞 N frames` 배지 + `suggest_animation_frames` MCP 호출**.

## 3. 환경 (재현용)

| 항목 | 값 |
|---|---|
| OS | Windows 10 |
| Python | python.org 3.12 (`C:\Users\v0o0v\AppData\Local\Programs\Python\Python312\python.exe`) |
| venv | `C:\Users\v0o0v\.venvs\gah\` |
| 작업 폴더 | `D:\ClaudeCowork\game-asset-helper\game-asset-helper\` |
| 런타임 데이터 | `C:\Users\v0o0v\AppData\Roaming\GameAssetHelper\` |
| 라이브러리 루트 | `%APPDATA%\GameAssetHelper\library\` |
| 메타 DB | `%APPDATA%\GameAssetHelper\metadata.db` (WAL, `sprite_meta.animations_json` M6 에서 추가) |
| **M6: sheet 패키지** | `src/gah/core/sheet/` (json_parser/grid_detect/preview/detect 4 모듈) |
| **M6: MCP 도구 수** | 18 도구 (`suggest_animation_frames` 추가) |
| **M6: 수동 테스트 helper** | `tools/setup_m6_test.py` (비균일 시트 → Aseprite JSON 자동 생성), `tools/inspect_m6.py` (DB 진단 + 재분석 reset) |

**금기**: Microsoft Store Python, Cowork 작업 폴더 내부 venv.

M6 신규 의존성: 없음 (Pillow/numpy 이미 M2 에서 사용).

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

→ `On branch main` + `Your branch is up to date with 'origin/main'` + clean.

```powershell
git log --oneline -5
```

→ 최상단에 Ollama cold-start retry / Gemma str split 방어 / aggregate race fix 등 후속 patch + M6 PR #7 머지 commit.

```powershell
pytest -q
```

→ `887 passed, 1 skipped, 40 deselected`.

선택 — 사용자 직접 시각 검증:

```powershell
python -m gah --tray
```

→ 브라우저로 라이브러리 페이지 진입. M6 시트 PNG + JSON 드롭 → 카드 배지 + 모달 라벨 칩 확인.

## 5. 다음 세션 진입 절차 (M7 시작)

### 5.1 환경 복원 + 회귀 검증

§4 의 명령 (Activate.ps1 / cd / git status / pytest -q) 실행. **887 passed** 확인.

### 5.2 M7 spec 작성

M7 — Unity Asset Store 임포트 (~1주). spec → plan → todo → TDD 순서:

1. `docs/superpowers/specs/YYYY-MM-DD-m7-unity-asset-store-import.md` — brainstorming 결과
2. `milestones/M7_plan.md` — 작업 단위 + 코드 스니펫 + step-by-step
3. `milestones/M7_todo.md` — TDD 체크리스트
4. 테스트 먼저(red phase), 구현(green phase), `milestones/M7_verification.md` 순서

M7 핵심 (DESIGN.md §11 Milestone 7):
- 캐시 경로 자동 검출 (`ASSETSTORE_CACHE_PATH` 환경변수 + Unity Editor Preferences 폴백 + 사용자 오버라이드)
- `.unitypackage` 파서 (tar.gz 아카이브) + 선택적 추출 (이미지/사운드만, 메타 자동 생성)
- 증분 동기화 (mtime 비교)
- `unity_imports` 테이블 (자산 origin 추적)
- `sync_unity_asset_store` MCP 도구 (18 → **19**)
- 웹 UI 의 Unity Asset Store 페이지 (사용자가 임포트 트리거 + 진행 상황 SSE)
- 비공식 publisher 패널 경로는 skeleton 만 (기본 비활성)

권장 워크플로:
- `superpowers:brainstorming` → 옵션 비교 + 결정
- `superpowers:writing-plans` → M7_plan.md
- `superpowers:subagent-driven-development` → phase 별 sonnet implementer + haiku reviewer (M5/M6 검증된 패턴)

### 5.4 새 세션이 자동 로드하는 메모리

- 마일스톤 수동 검증 항목 표시 방식 (feedback)
- PR/커밋 한글 (feedback)
- 가능한 한 직접 실행 (feedback)
- M2 분석 클라이언트 백엔드 추상화 (project)
- Ollama 멀티모달 API 형식 실측 (project)
- 모델 출력 듀얼 언어 + GUI i18n (project)
- 라벨 가중치 + CLIP v1 편입 (project)
- 검색 UX 전용 마일스톤 M4 신설 (project)
- GAH 배포 전략 — torch CUDA/CPU 통합 빌드 (project)
- M5 신규 — 웹 GUI 전환 결정 (project)
- M5 전체 완료 (project — `project_m5_complete.md`)
- M5 Claude pending-pick 패턴 (project)

## 6. 마일스톤 재정렬

| 신규 # | 이름 | 일정 | 상태 |
|---:|---|---:|---|
| M0~M3 | (변경 없음) | — | ✅ 완료 (main) |
| M4 | 검색 UX 풍부화 | 1.5주 | ✅ 완료 (main, [PR #5](https://github.com/v0o0v/game-asset-helper/pull/5)) |
| M5 | 웹 GUI 전환 + 라이브러리 리디자인 + Claude pick | 5.5주 | ✅ 완료 (main 머지됨) |
| M6 | 시트 분석 + 애니메이션 | 1주 | ✅ 완료 (main 머지됨, [PR #7](https://github.com/v0o0v/game-asset-helper/pull/7)) + 후속 patch 8건 main 직접 누적 |
| **M7** | **Unity Asset Store 임포트** | **1주** | **대기 (다음)** |
| M8 | 패키징 + i18n | 1주 | 대기 |

## 7. M6 Phase 진행 현황 (한눈에)

| Phase | 상태 | 핵심 산출물 | 신규 케이스 |
|---|---|---|---:|
| spec/plan/todo | ✅ | 스펙 + M6_plan.md + M6_todo.md | 0 |
| Phase 0 (타입) | ✅ | `SheetFrame`/`SheetTag`/`SheetDetection`/`SheetFormat`/`SheetResult` 5 frozen dataclass | +5 |
| Phase 1A (json_parser) | ✅ | Aseprite Array/Hash + TexturePacker 자동 판별 | +12 |
| Phase 1B (grid_detect) | ✅ | Pillow alpha 행/열 합으로 균일 격자 검출 | +10 |
| Phase 1C (preview) | ✅ | 8칸 그리드 합성, 초과 시 stride 샘플링 | +5 |
| Phase 1D (detect) | ✅ | JSON 우선 + 격자 폴백 + None 반환 | +6 |
| Phase 1 fix | ✅ | Store M6 컬럼 추가 + fixture 기반 정비 | +2 |
| Phase 2A (Store) | ✅ | `sprite_meta.animations_json` 컬럼 + `get_sprite_meta` + `update_asset_kind` | +8 |
| Phase 2B (SpritesheetAnalyzer) | ✅ | detect → preview → Gemma → animations_json 저장 + 폴백 | +10 |
| Phase 2C (AnalysisQueue) | ✅ | spritesheet 라우팅 + kind promote | +3 |
| Phase 3A (MCP models) | ✅ | `SuggestAnimationFramesInput`/`Output` Pydantic | +4 |
| Phase 3B (MCP tool) | ✅ | `tool_suggest_animation_frames` 18번째 도구 + 404/400 매핑 | +8 |
| Phase 4A (Web 라우터) | ✅ | library router `_row_to_dict` + `_asset_row_to_dict` frame_count flatten | +3 |
| Phase 4B (Web 카드 HTML) | ✅ | `_card_wide.html` + `_card_list.html` `🎞 N frames` 배지 + light/dark CSS | +2 |
| Phase 5 (cleanup + docs) | ✅ | store migration lock + JSON 디코드 견고성 + 주석 + DESIGN/MCP_USAGE/CLAUDE/HANDOFF 갱신 | 0 |
| **M6 전체** | **✅ 완료** | **880 passed + 1 skipped, 18 MCP 도구, 신규 의존성 0** | **+84** |

## 8. 의도적으로 미룬 항목 (M7+ v2)

M6 v1 에서 채우지 않고 남긴 항목:

- **사용자 frame size 입력 GUI** — 격자 자동 분할 실패 시 안내 GUI (M7+)
- **비정형 atlas 풍부 표현** — TexturePacker hash atlas 패딩/회전, Aseprite slice 영역 (M7+ v2)
- **per-frame duration 풍부 노출** — `suggest_animation_frames` 가 frame 별 `duration_ms` 배열 추가 노출 (v2)
- **animation 일괄 재라벨링 GUI** — 사용자가 시트 카드에서 frame range 마우스 조정 (M7+)
- **시트 통계 시트별 미세 조정** — v1 은 시트 전체 평균 (v2)
- **`request_rescan(scope="sheets_only")`** — 시트만 재분석 트리거 (v2)
- **무손실 GIF / WebP 애니메이션** — `.gif` / `.webp` 시트 (v2)

## 9. 알려진 한계 / 주의사항

### 9.1 M6 v1 알려진 한계

- **알파 채널 없는 PNG 시트** — JSON 사이드카 없으면 일반 `sprite` 로 분류. `grid_detect` 가 alpha=0 픽셀에 의존하므로.
- **비균일 atlas** — Aseprite Hash 는 파싱하지만 불균일 `x/y/w/h` 가 올 경우 frame 분할 정확도 낮음 — v2.
- **Gemma cold-start 후 OllamaError** — cold-start retry (max_retries 회 exponential backoff) 가 흡수하지만 timeout_seconds 가 너무 짧으면 통과 못할 수 있음. 그래도 시트 분석 자체는 JSON 사이드카로 완성 (state="partial").
- **mcp_integration 18 도구 확인** — 실 Ollama subprocess 없는 CI 환경에서 analyze 흐름은 partial 상태로 저장됨.

### 9.1.1 M6 후속 patch 8건 (main 직접 누적)

M6 PR #7 머지 후 수동 검증 중 발견된 회귀들 — 모두 main 에 직접 commit + 회귀 테스트 추가:

| Commit | 내용 |
|---|---|
| `5149c71` | `tools/setup_m6_test.py` — 비균일 시트 → Aseprite JSON 자동 생성 helper |
| `022f4d5` | `store.count_pending_assets` — `fetchone()` None 방어 (트레이 부팅 race) |
| `3d39f4a` | spritesheet 카드도 썸네일 노출 — `_card_wide/list.html` 분기에 spritesheet 추가, `ensure_thumbnail` kind 체크 확장 |
| `c546090` | 자산 상세 모달 + 라벨 + 재분석 라우팅 3건 — `ui_asset_detail`/`asset_detail.html` 의 spritesheet 분기 + `SpritesheetAnalyzer` 가 JSON frameTags 라벨도 `LabelScore` INSERT + `_analyze_one` 의 라우팅이 `kind in ('sprite', 'spritesheet')` |
| `bbd27ac` | `tools/inspect_m6.py` — DB 진단 + `--reset` 으로 재분석 트리거 |
| `fd7def3` | `pack_aggregate` read 도 `write_lock` 안에서 — `sqlite3.InterfaceError: bad parameter or other API misuse` 방어 |
| `6e359f6` | Gemma 가 `"run"` 같은 단일 문자열로 `animation_hint` 응답 시 character split 방어 (`hints` 정규화) |
| `0b2d427` | `OllamaClient.chat` 의 transport error retry — `ReadTimeout`/`ConnectError`/`ConnectTimeout`/`RemoteProtocolError`/`PoolTimeout` 에 backoff 후 max_retries 재시도 (cold-start 모델 로딩 흡수) |

### 9.2 환경 / 기술 한계 (M5 에서 이월)

- **WebDeps `frozen=True` + Config mutate** — `deps.config` 자체는 frozen 이지만 `Config` dataclass 가 mutable 이라 `deps.config.weight_* = ...` 직접 할당으로 갱신. 단일 워커 환경 가정.
- **`SearchRequest.offset` Python 슬라이싱** — 큰 offset 비효율 — 후속 phase.
- **`pack_ids` 후처리 페이지네이션 왜곡** — docstring 명시 완료, 후속 phase 에서 개선.

### 9.3 알려진 이슈 (공통)

- **Cowork 작업 폴더에 venv 만들기 금지** — venv 는 `%USERPROFILE%\.venvs\gah`.
- **Microsoft Store Python 금지** — `%APPDATA%` 가상화 경로 불일치.
- **Cowork `mcp__workspace__bash` 부팅 실패** — Claude Desktop 재시작으로 해결.

## 10. 문서 맵

- [`README.md`](./README.md) — 사용자용 시작 안내
- [`docs/WEB_UI_GUIDE.md`](./docs/WEB_UI_GUIDE.md) — 웹 UI 사용자 가이드 (M5 Phase 6B 신규)
- [`CLAUDE.md`](./CLAUDE.md) — Claude 작업 가이드 (§2 진행 현황 표 + §8 다음 작업 M7)
- [`HANDOFF.md`](./HANDOFF.md) — 이 파일, 마일스톤/phase 경계 인계
- [`DESIGN.md`](./DESIGN.md) — 전체 아키텍처·스키마·MCP 명세 (§4.2.2/§6.6/§11 M6 완료 표시)
- [`milestones/M6_plan.md`](./milestones/M6_plan.md) — M6 의 5 phase plan
- [`milestones/M6_todo.md`](./milestones/M6_todo.md) — TDD 체크리스트
- [`milestones/M6_verification.md`](./milestones/M6_verification.md) — M6 최종 검증 문서
- [`milestones/M5_verification.md`](./milestones/M5_verification.md) — M5 최종 검증 문서
- [`milestones/`](./milestones/) — 이전 마일스톤들의 plan/todo/verification
- [`docs/MCP_USAGE_GUIDE.md`](./docs/MCP_USAGE_GUIDE.md) — Phase 5 에서 18번째 도구(`suggest_animation_frames`) + 카운트 18 갱신 완료
- [`docs/superpowers/specs/2026-05-18-m6-sheet-and-animation-design.md`](./docs/superpowers/specs/2026-05-18-m6-sheet-and-animation-design.md) — M6 spec 원본

## 11. 갱신 규칙

이 문서는 다음 시점에 반드시 업데이트한다.

1. Phase 또는 마일스톤이 완료될 때 (§1 한 줄 요약, §2 검증 결과, §5 다음 작업).
2. 환경 결정이 바뀔 때 (§3).
3. 새 금기·주의사항이 발견될 때 (§9).

내용을 누적하기보다 **현재 시점의 진실만** 적는다. 과거 이력은 git log 에 맡긴다.
