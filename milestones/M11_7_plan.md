# M11.7 Plan — mood label noise cleanup (v0.2.6 candidate)

## 0. 본 plan 의 위치

- 상위 spec: [`docs/superpowers/specs/2026-05-22-m11-7-mood-noise-cleanup.md`](../docs/superpowers/specs/2026-05-22-m11-7-mood-noise-cleanup.md)
- 전제: [PR #26](https://github.com/v0o0v/assetcache-mcp/pull/26) M11.6 main 머지 (`da4f169`)
- 본 plan 은 implement-ready.

## 1. 목표

M11.6 LIVE 검증의 mood 노이즈 2건 해소 ([M11_6_verification.md §3.1](./M11_6_verification.md)):

| # | 노이즈 | 해소 |
|---:|---|---|
| 1 | crown_icon (inventory_item) 에 mood=heroic/playful 합산 | A1 + A2 — mood OPTIONAL + inventory_item/ui_icon/tile/background mood 차단 |
| 2 | 시트 자산 5/5 가 mood=minimalist/neutral 일률 응답 | A1 — mood OPTIONAL ([] 응답 허용) |

## 2. 산출물

| # | 산출물 | 비고 |
|---:|---|---|
| 1 | `core/analyzer/messages.py` — 두 prompt 의 mood OPTIONAL + category 별 차단 가이드 | 무조건 |
| 2 | `tests/test_prompt_mood_optional.py` (신규) | 무조건, ~2 test |
| 3 | `tests/test_prompt_category_mood_exclusion.py` (신규) | 무조건, ~2 test |
| 4 | `tests/test_llm_backend_gemini_inventory_item_integration.py` 확장 — crown mood [] + spritesheet mood 다양화 옵트인 | 무조건, ~2 test |
| 5 | `milestones/M11_7_verification.md` — auto + 옵트인 + LIVE 결과 | 무조건 |

## 3. Phase 분할

### Phase 1 — prompt fix (A1 + A2) + 단위 test (red → green)

1. `tests/test_prompt_mood_optional.py` 작성 (red):
   - BATCH_IMAGE_PROMPT + BATCH_SPRITESHEET_PROMPT 둘 다 mood OPTIONAL 시그널 (`leave` + `[]` 또는 `optional`)
2. `tests/test_prompt_category_mood_exclusion.py` 작성 (red):
   - 두 prompt 모두 Guidance 블록에 `inventory_item` + `ui_icon` + `tile` + `background` + (mood 차단 키워드: do NOT include mood)
3. `core/analyzer/messages.py` 수정 (green):
   - BATCH_IMAGE_PROMPT: mood 줄 "or empty `[]` if no clear mood applies" 추가
   - BATCH_SPRITESHEET_PROMPT: mood 줄 동일 추가
   - 두 prompt Guidance 블록에 category 별 mood 차단 가이드 추가
4. 단위 test 통과 + 전체 회귀 1597 + 4 = 1601 baseline.

### Phase 2 — LIVE 검증

`scripts/drive_live_batch.py` 재실행 (M11.6 setup 그대로):

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
```
```powershell
Remove-Item -Recurse -Force "$env:TEMP\m11_7_verify_data" -ErrorAction SilentlyContinue
```
```powershell
New-Item -ItemType Directory -Path "$env:TEMP\m11_7_verify_data\library\m113_complex" -Force | Out-Null
```
```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" scripts/make_complex_sheets.py "$env:TEMP\m11_7_verify_data\library\m113_complex"
```
```powershell
$env:GEMINI_API_KEY = "AIza..."
```
```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" scripts/drive_live_batch.py "$env:TEMP\m11_7_verify_data"
```

**측정 목표**:
- crown_icon mood 라벨 = 0건 (M11.6 의 2건 → 0)
- 시트 5 자산 mood 라벨 분포 다양화 또는 빈 배열 (M11.6 의 일률 minimalist+neutral 패턴 차단)
- regression: crown=inventory_item ✓ + 시트 palette 5/5 ✓ + 'other' 0건 ✓

### Phase 3 — 옵트인 LIVE 확장 + 회귀 + PR

1. `tests/test_llm_backend_gemini_inventory_item_integration.py` 확장:
   - crown_icon → mood 라벨 = 빈 배열 단언 옵트인
   - spritesheet strip → mood 라벨이 빈 배열 또는 [minimalist, neutral] catch-all 패턴 아님 단언 옵트인
2. 전체 회귀 `pytest -q` 통과 (1597 + Phase 1 신규 = 1601).
3. `M11_7_verification.md` — auto + 옵트인 + LIVE 결과 표.
4. PR → main → tag v0.2.6 → Trusted Publishing 8회째 자동 (~30초).

## 4. 작업 시간 추정

- Phase 1: 0.5일 (prompt 작성 + 단위 test red→green)
- Phase 2: 0.3일 (LIVE 측정 + 결과 기록)
- Phase 3: 0.2일 (옵트인 + 회귀 + PR)
- **합계 ~1일**

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
git checkout -b feat/m11-7-mood-noise-cleanup
```
```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -q
```

→ baseline 1597 확인 후 Phase 1 (prompt fix TDD) 부터.
