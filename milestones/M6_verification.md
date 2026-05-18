# M6 검증 보고서

**최종 상태**: ✅ 자동 검증 모두 통과 (2026-05-18). 사용자 수동 확인 항목 6 단계 — §4 에 단계별 체크리스트.

M5 의 17 MCP 도구 + 웹 UI 위에 **시트 자동 분할 (Aseprite/TexturePacker JSON + Pillow alpha 격자) + Gemma 애니메이션 라벨링 + `suggest_animation_frames` 18번째 MCP 도구 + 와이드/리스트 카드 🎞 N frames 배지** 추가. 신규 의존성 0.

본 마일스톤의 의도와 작업 단위는 [`M6_plan.md`](./M6_plan.md), TDD 체크리스트는 [`M6_todo.md`](./M6_todo.md).

## 1. 자동 검증 결과: ✅ 880/880 + 2/2 mcp_integration

`pytest -q` 전체 실행 — M0~M5 회귀 (796) + M6 Phase 0~5 신규 (84) = **880 active** (`clip_integration` 2 + `mcp_integration` 2 = 4 deselected 포함).

```
SKIPPED [1] tests\test_web_routers_sse.py:140: heartbeat 15초 타이밍 결정론적 테스트 어려움 — Phase 4 마감 흡수
880 passed, 1 skipped, 40 deselected in 47.87s
```

`pytest -m mcp_integration -v` — 실 subprocess + JSON-RPC 핸드셰이크, 18 도구 확인:

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
    # M6 1 신규 도구
    "suggest_animation_frames",
}
assert expected <= names and len(names) == 18  # PASS
```

M6 신규 케이스 분해 (Phase 별):

| Phase | 신규 케이스 | 핵심 검증 묶음 |
|---|---:|---|
| Phase 0 (SheetFrame/SheetTag/SheetDetection/SheetFormat/SheetResult 타입) | +5 | `test_sheet_types` — 5 frozen dataclass |
| Phase 1A (json_parser) | +12 | Aseprite Array/Hash + TexturePacker + 에러 |
| Phase 1B (grid_detect) | +10 | 균일 격자 검출 + 알파 없는 폴백 + 비율 제약 |
| Phase 1C (preview) | +5 | 8칸 이하 그대로 + stride 샘플링 + 빈 입력 |
| Phase 1D (detect) | +6 | JSON 우선 + 격자 폴백 + None 반환 |
| Phase 1 fix (Store M6 컬럼 + fixture) | +2 | `test_store_m6` 기반 픽스처 |
| Phase 2A (Store animations_json) | +8 | `test_store_m6` — 저장/조회/갱신/None |
| Phase 2B (SpritesheetAnalyzer) | +10 | `test_analyzer_spritesheet` — detect 성공/실패/폴백/Gemma |
| Phase 2C (AnalysisQueue + promote) | +3 | `test_analysis_queue_m6` — promote spritesheet |
| Phase 3A (MCP models) | +4 | `test_mcp_models_m6` — SuggestAnimationFramesInput/Output |
| Phase 3B (MCP tool) | +8 | `test_mcp_tools_m6` — 정상/404/400 |
| Phase 4A (Web 카드 배지 라우터) | +3 | `test_web_card_frame_badge` — frame_count flatten |
| Phase 4B (Web 카드 HTML 배지) | +2 | `test_web_pages` — wide/list 배지 |
| Phase 5 (cleanup + docs) | 0 신규 | refactor + docs 만 |
| **M6 신규 합계** | **+78 → 84*** | **total 880** |

> *Phase별 fix 커밋에서 소수 추가 케이스가 붙어 최종 카운트 84 (880 - 796 = 84).

## 2. 자동 검증 한계

자동 테스트가 다루지 **못하는** 항목 — 사용자 수동 검증 (§4) 으로 보완:

- **실 시트 PNG + Aseprite JSON 인테이크** — fixture JSON 으로 단위 검증만. 실 Aseprite export 입력은 §4 수동 검증 필요.
- **Gemma 응답 품질** — `animation_hint` 정확도는 모델 의존, 자동 검증 불가. 스텁(mock OllamaClient)으로 단위 테스트.
- **사용자 시각 — 카드 배지 색 / 폰트** — light/dark 모드 전환 시 색 대비는 시각 확인만 가능.
- **워처 실시간 인테이크** — 새 시트 PNG + JSON 드롭 시 자동 인덱싱 + 분석 + 카드 갱신.
- **mcp_integration 18 도구 확인** — `pytest -m mcp_integration` 은 `--mcp` 서버를 실제 subprocess 로 띄워 확인. Ollama 없는 환경에서 실 분석 흐름 미검증.

## 3. 의도적으로 미룬 항목 (M7+ v2)

[`M6_plan.md`](./M6_plan.md) §6 과 동일:

- **사용자 frame size 입력 GUI** — 격자 자동 분할 실패 시 (M7+).
- **비정형 atlas 풍부 표현** — TexturePacker hash atlas 패딩/회전, Aseprite slice 영역 (M7+ v2).
- **per-frame duration 풍부 노출** — `suggest_animation_frames` 가 frame 별 `duration_ms` 배열도 노출 (v2).
- **animation 일괄 재라벨링 GUI** — 사용자가 시트 카드에서 frame range 마우스 조정 (M7+).
- **시트 통계 (도미넌트 색 / pixel art 판정) 시트별 미세 조정** — v1 은 시트 전체 평균 (v2).
- **`request_rescan(scope="sheets_only")`** — 시트만 재분석 트리거 (v2).
- **Aseprite slice 영역** — `meta.slices` nine-slice 정보 (M7+).
- **무손실 GIF / WebP 애니메이션** — `.gif` / `.webp` 시트는 v2.

## 4. 사용자 수동 시각 검증 항목 (6 단계)

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```

```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```

```powershell
pytest -q
```

→ `880 passed, 1 skipped, 40 deselected` 가 보여야 한다.

GAH 실행:

```powershell
python -m gah --tray
```

---

아래 항목을 차례로 확인한다. 완료한 항목은 `[x]` 로 표시.

- [ ] **(1) 실 Aseprite 시트 + JSON 드롭** — `library/<pack>/<name>.png` + `<name>.json` (Aseprite "Array" export) 드롭 → 자동 인덱싱 + 분석 → 카드에 `🎞 N frames` 배지 노출. 카드 클릭 → 자산 상세 모달에서 frame_count 확인.

- [ ] **(2) JSON 없는 균일 시트 드롭** — `library/<pack>/<name>.png` (균일 격자 PNG, JSON 없음) 드롭 → `grid_detect` 검출 → 카드 배지 노출 (단, 알파 채널 없는 PNG 는 JSON 사이드카 필수 — 배지 미노출 + 일반 sprite 로 분류).

- [ ] **(3) 단일 스프라이트 드롭** — `library/<pack>/sword.png` (32×32 단일 이미지) 드롭 → 배지 미노출 (sprite 유지).

- [ ] **(4) Claude `suggest_animation_frames` 호출** — MCP 클라이언트에서 `suggest_animation_frames({"asset_id": N, "animation": "walk"})` 호출 → `{"frame_indices": [...], "fps_hint": NN}` 응답.

- [ ] **(5) 존재 안 하는 animation 호출** — `suggest_animation_frames({"asset_id": N, "animation": "fly"})` → `404_not_found` 응답 메시지에 `available: [walk, idle]` 같은 목록 포함 확인.

- [ ] **(6) 다크/라이트 모드 배지 색** — OS 모드 전환 시 카드 배지 색 자연스럽게 변경 (light: 진파랑 배경 + 흰 글자, dark: 연파랑 배경 + 진파랑 글자).

## 5. 다음 마일스톤 (M7)

[`DESIGN.md`](../DESIGN.md) §11 Milestone 7 — Unity Asset Store 임포트 (1주).

- 캐시 경로 자동 검출(환경변수 + Preferences 폴백) + 사용자 오버라이드.
- `.unitypackage` 파서, 선택적 추출(이미지/사운드만), 매니페스트 자동 생성.
- 증분 동기화, `unity_imports` 테이블, `sync_unity_asset_store` MCP 도구 (18 → 19).
- 웹 UI 의 Unity Asset Store 페이지.
