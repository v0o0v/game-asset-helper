<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-22 | Updated: 2026-05-22 -->

# milestones

## Purpose
TDD 5단계 사이클 (plan → todo → red test → green impl → verification) 의 산출물. 각 마일스톤 M{N} 마다 `M{N}_plan.md` / `M{N}_todo.md` / `M{N}_verification.md` 3종 세트.

## Key Files (상위 인덱스 + 현재 상태)
| File | Description |
|------|-------------|
| `README.md` | 마일스톤 디렉터리 안내 |
| `ROADMAP.md` | 전체 마일스톤 정렬 + future (M12~M18) |
| `HISTORY.md` | M0~M11.7 완료분 아카이브 (PR / 회귀 / 산출물 / 머지 commit) |
| `M11_8_plan.md` | **다음 implement 대상** — mood 시드 `neutral`/`minimalist` 비활성화 (v0.2.7 candidate) |
| `M11_7_*.md` | M11.7 — mood OPTIONAL + category 별 mood 차단 (PR #27 머지, v0.2.6 보류) |
| `M11_6_*.md` | M11.6 — BATCH_SPRITESHEET_PROMPT palette + 'other' fallback 정리 (PR #26 머지, v0.2.5 보류) |
| `M11_5_*.md` | M11.5 — LIVE validation + acceptable set strict (PR #23/#24 머지, v0.2.4 보류) |
| `M11_4_*.md` | M11.4 — grid_detect 강화 + LLM 분류 정확도 (PR #21 머지, v0.2.3 보류) |
| `M11_3_*.md` | M11.3 — Detection Cache + 부수 patch (PR #20 머지, v0.2.2 publish 완료) |
| `M11_2_*.md` | M11.2 — Batch Spritesheet Modality (PR #19 머지) |
| `M11_1_*.md` | M11.1 — Gemini Batch API + /analyzing (PR #17/#18 머지, v0.2.1 publish 완료) |
| `M11_*.md` | M11 — Multi-backend LLM Architecture (PR #16 머지, v0.2.0 publish 완료) |
| `M10_*.md` | M10 — PyPI 배포 + AssetCacheMCP rename (PR #11/#12 머지) |
| `M0_*.md` ~ `M9_*.md` | 초기 ~ 자동 업데이트 (M9 path pivot) — 상세는 `HISTORY.md` |
| `M2.1_*.md` | M2 후속 병렬화 patch |

## For AI Agents

### Working In This Directory
- **마일스톤 시작 시** `M{N}_plan.md` + `M{N}_todo.md` 동시 작성. plan 에 목표·산출물·작업 단위·테스트 전략·검증 기준 명시.
- **TDD red phase** — 테스트 먼저 작성하고 한 번 돌려서 모두 실패하는지 확인. 그다음 구현.
- **verification 작성 시** — `pytest -v` 출력 + 사용자 수동 검증 항목 + 알려진 한계를 모두 적는다.
- **마일스톤 머지 후** `HISTORY.md` 에 PR # / 회귀 결과 / 산출물 / 머지 commit hash 한 줄 추가.
- 새 마일스톤은 ROADMAP 의 다음 항목 참조 + 사용자 합의 후 시작.

### Testing Requirements
- 각 마일스톤 plan 에 baseline + 신규 테스트 수 명시. M11.7 baseline = 1601 passed.
- 옵트인 마커 가 필요한 마일스톤은 plan 에 `pytest -m {marker}` 명령 명시.

### Common Patterns
- 파일명: `M{N}_plan.md` / `M{N}_todo.md` / `M{N}_verification.md`. 소수점 마일스톤은 `M11_4_plan.md` 처럼 underscore.
- plan 본문: 1) 목표 2) 산출물 3) 작업 단위 (Phase) 4) 테스트 전략 5) 검증 기준.
- todo: 체크박스 형식, TDD 순서 (red → green).
- verification: 자동 검증 (`pytest -q` 결과) + 사용자 수동 검증 (시나리오별 체크리스트) + 알려진 한계.
- **수동 검증 체크리스트** 는 마일스톤 끝나면 응답 본문에 단계별로 별도 제시 (memory feedback `feedback_milestone_manual_verification_format`).

## Dependencies

### Internal
- `../docs/superpowers/specs/` — spec 의 phase 분해 → plan.
- `../src/assetcache/` — 마일스톤 산출물 위치.
- `../tests/` — TDD 산출물.

### External
- 없음.

<!-- MANUAL: 새 마일스톤 시작 시 사용자 합의 절차 필요. ROADMAP.md 참조. -->
