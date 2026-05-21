# M11.6 Plan — BATCH_SPRITESHEET_PROMPT palette + 'other' fallback 정리 (v0.2.5 candidate)

## 0. 본 plan 의 위치

- 상위 spec: [`docs/superpowers/specs/2026-05-22-m11-6-spritesheet-palette-and-other-cleanup.md`](../docs/superpowers/specs/2026-05-22-m11-6-spritesheet-palette-and-other-cleanup.md)
- 전제: [PR #23](https://github.com/v0o0v/assetcache-mcp/pull/23) M11.5 main 머지 (`ed47403`) + [PR #24](https://github.com/v0o0v/assetcache-mcp/pull/24) 별→별도 정리 (`1be53ae`)
- 본 plan 은 **starter** — 다음 세션에서 implement.

## 1. 목표

M11.5 LIVE 검증의 별도 발견 2건 해소 ([M11_5_verification.md §3.1](./M11_5_verification.md)):

| # | 한계 | 해소 |
|---:|---|---|
| 1 | 시트 자산 palette 라벨 부재 (BATCH_SPRITESHEET_PROMPT 가 palette 미명시) | A1 — palette enum + tone group 가이드 + hex 금지 추가 |
| 2 | animation='other' fallback 라벨 합산 (prompt 가 'other' 를 valid 응답으로 받음) | A2-prompt — 두 prompt 에 "do NOT use 'other'" 명시.  필요 시 A2-filter (payload_parser drop) 추가 |

## 2. 산출물

| # | 산출물 | 비고 |
|---:|---|---|
| 1 | `core/analyzer/messages.py` — BATCH_SPRITESHEET_PROMPT palette + 'other' 금지 가이드 | 무조건 |
| 2 | `core/analyzer/messages.py` — BATCH_IMAGE_PROMPT 'other' 금지 가이드 추가 | 무조건 |
| 3 | `tests/test_batch_spritesheet_prompt_palette.py` (신규) | 무조건, ~3 test |
| 4 | `tests/test_prompt_no_other_fallback.py` (신규) | 무조건, ~2 test |
| 5 | `core/analyzer/payload_parser.py` — validate_*_payload 가 'other' axis 라벨 drop | A2-filter 채택 시 |
| 6 | `tests/test_payload_parser_other_drop.py` (신규) | A2-filter 채택 시, ~3 test |
| 7 | `tests/test_llm_backend_gemini_inventory_item_integration.py` 확장 — 시트 palette + 'other' 0건 옵트인 | 무조건, ~2 test |
| 8 | `milestones/M11_6_verification.md` — auto + 옵트인 + LIVE 결과 | 무조건 |

## 3. Phase 분할

### Phase 1 — prompt fix (A1 + A2-prompt) + 단위 test (red → green)

1. `tests/test_batch_spritesheet_prompt_palette.py` 작성 (red):
   - `BATCH_SPRITESHEET_PROMPT` 에 `palette` enum 6 토큰 노출
   - hex 금지 가이드 `do NOT use hex codes`
   - tone group 가이드 (warm/cool/monochrome/high_contrast/pastel/neutral)
2. `tests/test_prompt_no_other_fallback.py` 작성 (red):
   - `BATCH_IMAGE_PROMPT` + `BATCH_SPRITESHEET_PROMPT` 둘 다 `do NOT use "other"` 또는 동등 표현
3. `core/analyzer/messages.py` 수정 (green):
   - `BATCH_SPRITESHEET_PROMPT` palette 줄 + tone group 가이드 + hex 금지 추가
   - 두 prompt 에 'other' 금지 가이드 추가
4. 단위 test 통과 + 전체 회귀 1592 + 5 = 1597 baseline.

### Phase 2 — LIVE 검증

`scripts/drive_live_batch.py` 재실행 (M11.5 setup 그대로):

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```
```powershell
Remove-Item -Recurse -Force "$env:TEMP\m11_6_verify_data" -ErrorAction SilentlyContinue
```
```powershell
New-Item -ItemType Directory -Path "$env:TEMP\m11_6_verify_data\library\m113_complex" -Force | Out-Null
```
```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" scripts/make_complex_sheets.py "$env:TEMP\m11_6_verify_data\library\m113_complex"
```
```powershell
$env:GEMINI_API_KEY = "AIza..."
```
```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" scripts/drive_live_batch.py "$env:TEMP\m11_6_verify_data"
```

**측정 목표**:
- 시트 자산 5개 모두 palette 라벨 ≥ 1건
- animation axis 'other' 0건
- category axis 'other' 0건
- regression: crown=inventory_item ✓ + elemental_cyan=spritesheet ✓

### Phase 3 — A2-filter 분기 결정

* LIVE 'other' 0건 → A2-filter SKIP (prompt 만으로 충분)
* LIVE 'other' > 0 → A2-filter 진입 (payload_parser drop + 신규 test 3)

### Phase 4 — 옵트인 LIVE 테스트 확장 + 회귀 + PR

1. `tests/test_llm_backend_gemini_inventory_item_integration.py` 확장:
   - 시트 자산 1개 (예: hero_warrior PNG) 합성 → batch_chat 응답에 palette 라벨 포함 단언
   - 응답에 'other' 0건 단언
2. 전체 회귀 `pytest -q` 통과 (1592 + Phase 1/3 신규).
3. `M11_6_verification.md` — auto + 옵트인 + LIVE 결과 표.
4. PR → main → tag v0.2.5 → Trusted Publishing 7회째 자동 (~30초).

## 4. 작업 시간 추정

- Phase 1: 0.5일 (prompt 작성 + 단위 test red→green)
- Phase 2: 0.2일 (LIVE 측정 + 결과 기록)
- Phase 3: 0.2일 (분기 결정 — SKIP 이면 0)
- Phase 4: 0.1일 (PR + tag)
- **합계 ~1일** (A2-filter SKIP 케이스).  A2-filter 채택 시 +0.3일.

## 5. 시작 명령

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```
```powershell
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
```
```powershell
git checkout main
```
```powershell
git pull
```
```powershell
git checkout -b feat/m11-6-prompt-cleanup
```
```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -q
```

→ baseline 1592 확인 후 Phase 1 (prompt fix TDD) 부터.

## 6. 검증 결과 표 (M11_6_verification.md skeleton)

| # | 자산 | 기대 결과 | LIVE 결과 (TBD) | 평가 |
|---:|---|---|---|---|
| 1 | hero_warrior | palette 라벨 ≥ 1건 + animation 'other' 0건 | — | A1 + A2 효과 |
| 2 | mage_purple | 동일 | — | 동일 |
| 3 | knight_gold | 동일 | — | 동일 |
| 4 | monster_red | 동일 | — | 동일 |
| 5 | elemental_cyan | 동일 + animation 'other' 0건 (Gemma 가 'idle' 같은 enum 답변) | — | A2-prompt 효과 |
| 6 | crown_icon | category=inventory_item 유지 + palette warm/high_contrast 유지 | — | regression 0 |
