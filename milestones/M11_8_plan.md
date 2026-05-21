# M11.8 Plan — mood 시드 `neutral`/`minimalist` 비활성화 (v0.2.7 candidate)

## 0. 본 plan 의 위치

- 상위 spec: [`docs/superpowers/specs/2026-05-22-m11-8-mood-seed-disable.md`](../docs/superpowers/specs/2026-05-22-m11-8-mood-seed-disable.md)
- 전제: [PR #27](https://github.com/v0o0v/assetcache-mcp/pull/27) M11.7 main 머지 (`04c205e`)
- 본 plan 은 **starter** — 다음 세션에서 implement.

## 1. 목표

M11.7 LIVE 의 catch-all 잔존 해소 ([M11_7_verification.md §3.1](./M11_7_verification.md)):

| # | 한계 | 해소 |
|---:|---|---|
| 1 | 시트 4/5 자산에 mood='neutral' 잔존 | A3-mood-neutral — 시드 `mood.neutral` `is_enabled=0` |
| 2 | 시트 1/5 자산에 mood='minimalist' 잔존 | A3-mood-minimalist — 시드 `mood.minimalist` `is_enabled=0` |
| 3 | prompt 가 'neutral'/'minimalist' enum 노출 | A3-prompt — 두 prompt mood 줄에서 두 토큰 제거 |

⚠️ **palette.neutral 은 절대 유지** (M11.6 tone group enum 핵심).

## 2. 산출물

| # | 산출물 | 비고 |
|---:|---|---|
| 1 | `core/labels.py` — `DISABLED_BY_DEFAULT` 상수 + bootstrap 적용 | 무조건 |
| 2 | `core/store.py` — `set_label_enabled_if_unchanged` helper + `disabled_by_default_signature` 마커 | 무조건 |
| 3 | `core/analyzer/messages.py` — 두 prompt mood enum 에서 neutral/minimalist 제거 | 무조건 |
| 4 | `tests/test_label_registry_disabled_by_default.py` (신규) | 무조건, ~5 test |
| 5 | `tests/test_prompt_mood_enum_excludes_neutral_minimalist.py` (신규) | 무조건, ~2 test |
| 6 | `tests/test_llm_backend_gemini_inventory_item_integration.py` 확장 — 시트 strip mood 'neutral' 0건 옵트인 | 무조건, ~1 test |
| 7 | `milestones/M11_8_verification.md` — auto + 옵트인 + LIVE 결과 | 무조건 |

## 3. Phase 분할

### Phase 1 — 시드 비활성화 + migration TDD (red → green)

1. `tests/test_label_registry_disabled_by_default.py` 작성 (red):
   - `DISABLED_BY_DEFAULT["mood"] == {"neutral", "minimalist"}`
   - bootstrap 후 `mood.neutral` `is_enabled=0`
   - bootstrap 후 `mood.minimalist` `is_enabled=0`
   - `palette.neutral` 은 `is_enabled=1` 유지 (axis 격리)
   - idempotent — 사용자가 enable=1 로 복원 후 bootstrap 재호출 시 변경 없음
2. `core/store.py` 에 `set_label_enabled_if_unchanged` helper + `meta.disabled_by_default_signature` 마커 추적 (green).
3. `core/labels.py` 에 `DISABLED_BY_DEFAULT` 상수 + bootstrap 후처리 (green).
4. 단위 test 통과.

### Phase 2 — prompt 동기화 TDD (red → green)

1. `tests/test_prompt_mood_enum_excludes_neutral_minimalist.py` 작성 (red):
   - BATCH_IMAGE_PROMPT mood 줄에 'neutral' 부재 + 'minimalist' 부재
   - BATCH_SPRITESHEET_PROMPT 동일
   - 다른 mood 토큰 (heroic, dark, playful, calm, mysterious, intense) 보존
2. `core/analyzer/messages.py` 의 두 prompt mood 줄 수정 (green).
3. 단위 test 통과 + 전체 회귀 1601 + 7 = 1608 baseline.

### Phase 3 — LIVE 검증

`scripts/drive_live_batch.py` 재실행 (M11.7 setup 그대로):

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
Remove-Item -Recurse -Force "$env:TEMP\m11_8_verify_data" -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$env:TEMP\m11_8_verify_data\library\m113_complex" -Force | Out-Null
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" scripts/make_complex_sheets.py "$env:TEMP\m11_8_verify_data\library\m113_complex"
$env:GEMINI_API_KEY = "AIza..."
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" scripts/drive_live_batch.py "$env:TEMP\m11_8_verify_data"
```

**측정 목표**:
- 시트 5/5 mood='neutral' = **0건** (M11.7 의 4/5 → 0)
- 시트 5/5 mood='minimalist' = **0건** (M11.7 의 1/5 → 0)
- 회귀: crown mood [] + palette 5/5 + 'other' 0건 모두 유지

### Phase 4 — 옵트인 확장 + 회귀 + PR

1. `tests/test_llm_backend_gemini_inventory_item_integration.py` 확장 — 시트 strip 응답 mood 에 'neutral'/'minimalist' 0건 단언 옵트인 1 추가.
2. 전체 회귀 `pytest -q` 통과 (1601 + Phase 1+2 신규 7 = 1608).
3. `M11_8_verification.md` — auto + 옵트인 + LIVE 결과 표.
4. PR → main → tag v0.2.7 → Trusted Publishing 자동 (~30초).

## 4. 작업 시간 추정

- Phase 1: 0.5일 (시드 마이그 + helper + 단위 test red→green)
- Phase 2: 0.2일 (prompt 동기화 + 단위 test)
- Phase 3: 0.2일 (LIVE 측정 + 결과 기록)
- Phase 4: 0.1일 (옵트인 + PR)
- **합계 ~1일**

## 5. 시작 명령

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\Activate.ps1"
cd D:\ClaudeCowork\game-asset-helper\game-asset-helper
git checkout main
git pull
git checkout -b feat/m11-8-mood-seed-disable
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -q
```

→ baseline 1601 확인 후 Phase 1 (시드 마이그 TDD) 부터.

## 6. 검증 결과 표 (M11_8_verification.md skeleton)

| # | 자산 | M11.7 mood | M11.8 기대 | LIVE 결과 (TBD) |
|---:|---|---|---|---|
| 1 | hero_warrior | minimalist, neutral (2) | 빈 또는 heroic/dark/intense 등 | — |
| 2 | mage_purple | neutral (1) | 빈 또는 mysterious 등 | — |
| 3 | knight_gold | (빈) | 빈 유지 또는 heroic | — |
| 4 | monster_red | neutral (1) | 빈 또는 dark/intense 등 | — |
| 5 | elemental_cyan | neutral (1) | 빈 또는 mysterious | — |
| 6 | crown_icon | (빈) | 빈 유지 (A2 보존) | — |
