# M11.8 검증 — mood 시드 `neutral`/`minimalist` 비활성화 (v0.2.7 candidate)

## 0. 본 문서의 위치

- 상위 spec: [`docs/superpowers/specs/2026-05-22-m11-8-mood-seed-disable.md`](../docs/superpowers/specs/2026-05-22-m11-8-mood-seed-disable.md)
- 상위 plan: [`M11_8_plan.md`](./M11_8_plan.md)
- 전제: [PR #27](https://github.com/v0o0v/assetcache-mcp/pull/27) M11.7 main 머지 (`04c205e`)
- 본 문서는 **Phase 1 시드 비활성화 (red→green) → Phase 2 prompt 동기화 (red→green) → Phase 3 LIVE 검증 → Phase 4 옵트인 + PR** 흐름의 결과를 누적한다.

## 1. 자동 검증 (Phase 1+2 green) — ✅ 2026-05-22

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -q
```

Result: **1612 passed + 1 skipped + 63 deselected in 80.53s** — M11.7 baseline 1601 + 신규 11 (Phase 1 disable 7 + Phase 2 prompt 4).

### 1.1 신규 단위 테스트

| 파일 | 테스트 수 | 검증 내용 |
|---|---:|---|
| `tests/test_label_registry_disabled_by_default.py` | 7 | `DISABLED_BY_DEFAULT == {"mood": {"neutral", "minimalist"}}` + fresh DB bootstrap disable + palette.neutral 보존 + 다른 mood 토큰 보존 + idempotency (user reenable 보존) + 기존 DB (M11.7 이전 상태) 첫 마이그 |
| `tests/test_prompt_mood_enum_excludes_neutral_minimalist.py` | 4 | BATCH_IMAGE_PROMPT + BATCH_SPRITESHEET_PROMPT 두 prompt 의 mood enum 에 `neutral`/`minimalist` 부재 + 다른 6 토큰 (heroic/dark/playful/calm/mysterious/intense) 보존 |

### 1.2 변경 파일

| 파일 | 변경 |
|---|---|
| `src/assetcache/core/labels.py` | `DISABLED_BY_DEFAULT` 상수 신설 + `LabelRegistry.bootstrap()` 가 항상 disable 패스 실행 (table empty/non-empty 무관) |
| `src/assetcache/core/store.py` | `_M11_8_META_SCHEMA` (meta key/value 테이블) + `_migrate_m11_8_meta_schema()` + `set_label_enabled_if_unchanged(axis, label, enabled)` helper (marker 기반 idempotent + user override 보존) |
| `src/assetcache/core/analyzer/messages.py` | BATCH_IMAGE_PROMPT + BATCH_SPRITESHEET_PROMPT 두 prompt mood enum 에서 `neutral`/`minimalist` 제거 (가이드라인 보존) |

## 2. LIVE 검증 셋업 (Phase 3 gate)

### 2.1 합성 자산 생성

M11.6/M11.7 setup 재사용 — 같은 6 자산 (hero_warrior/mage_purple/knight_gold/monster_red/elemental_cyan/crown_icon).

```powershell
Remove-Item -Recurse -Force "$env:TEMP\m11_8_verify_data" -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$env:TEMP\m11_8_verify_data\library\m113_complex" -Force | Out-Null
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" scripts/make_complex_sheets.py "$env:TEMP\m11_8_verify_data\library\m113_complex"
```

### 2.2 LIVE Gemini 배치 실행

```powershell
$env:GEMINI_API_KEY = "AIza..."
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" scripts/drive_live_batch.py "$env:TEMP\m11_8_verify_data"
```

## 3. LIVE 결과 표 — ✅ 2026-05-22

driver: `scripts/drive_live_batch.py` (Qt tray 우회).  Gemini batch inline destination.

batch_jobs:

| job_id | modality | state | asset_count | success | failure |
|---:|---|---|---:|---:|---:|
| 1 | chat_image | succeeded | 1 | 1 | 0 |
| 2 | chat_spritesheet | succeeded | 5 | 5 | 0 |

| # | 자산 | M11.7 mood (변경 전) | M11.8 LIVE mood | 평가 |
|---:|---|---|---|---|
| 1 | hero_warrior (sheet) | minimalist, neutral | **(빈 mood)** | ✅ A3 완벽 — catch-all 두 토큰 모두 제거 |
| 2 | mage_purple (sheet) | neutral | **calm** (1 토큰) | ✅ neutral 제거, calm 으로 이동 |
| 3 | knight_gold (sheet) | (빈) | **(빈 mood)** | ✅ M11.7 빈 유지 |
| 4 | monster_red (sheet) | neutral | **calm** (1 토큰) | ✅ neutral 제거, calm 으로 이동 |
| 5 | elemental_cyan (sheet) | neutral | **calm** (1 토큰) | ✅ neutral 제거, calm 으로 이동 |
| 6 | crown_icon (inventory_item) | (빈, A2 효과) | **(빈 mood)** | ✅ M11.7 A2 보존 |

**측정 목표 달성**:
- 시트 5/5 mood='neutral' = **0건** ✅ (M11.7 의 4/5 → **0/5**)
- 시트 5/5 mood='minimalist' = **0건** ✅ (M11.7 의 1/5 → **0/5**)
- 시트 mood 토큰 총량: M11.7 의 5 → M11.8 의 3 (모두 calm)

**부수 효과 — `calm` 으로 이동 (3/5 시트)**:
- Gemini 가 catch-all 'neutral'/'minimalist' 차단 후 다음 안전 mood 로 'calm' 선택
- "캐릭터 자산에 mood 라벨 채우려는 경향" 자체는 잔존 — M11.9+ 후보: 'calm' 도 disable 또는 mood OPTIONAL 가이드 강화

### 3.1 회귀 check (M11.6/M11.7 효과 보존)

| 항목 | M11.7 결과 | M11.8 LIVE | 평가 |
|---|---|---|---|
| crown_icon category | inventory_item | **inventory_item** ✅ | M11.4 보존 |
| crown_icon palette | high_contrast, warm | **high_contrast, warm** ✅ | M11.6 보존 |
| crown_icon mood ([]) | 빈 (A2 효과) | **빈 mood** ✅ | M11.7 A2 보존 |
| 시트 5/5 palette ≥ 1건 | 5/5 (high_contrast/cool/warm) | **5/5** ✅ (cool+neutral/cool/warm/warm/high_contrast) | M11.6 A1 보존 |
| **palette.neutral 라벨링** | (M11.6 의 hero=cool+neutral 동일) | **hero_warrior 에 cool+neutral** ✅ | **palette.neutral 절대 유지 검증 ✅** |
| 'other' fallback | 0/6 | **0/6** ✅ | M11.6 A2-prompt 보존 |
| animation 라벨 (frameTags 있는 자산) | hero idle/walk/attack/hurt + mage cast/idle/walk | **동일** ✅ | M11.3 보존 |
| kind 분류 (sprite/spritesheet) | crown=sprite + 5 시트=spritesheet | **동일** ✅ | M11.3 보존 |

## 4. Phase 4 — 옵트인 LIVE 확장 + PR — ✅ 2026-05-22

`tests/test_llm_backend_gemini_inventory_item_integration.py` 확장 (`pytestmark = pytest.mark.llm_integration`, 기본 deselect):

* `test_spritesheet_response_has_no_neutral_or_minimalist_mood` — 시트 strip 응답 mood 에 'neutral' + 'minimalist' 0건 단언 (M11.8 신규)
* 기존 옵트인 6 PASSED 회귀 (M11.5 strict 2 + M11.6 신규 2 + M11.7 신규 2)

옵트인 LIVE 결과 (gemini-2.5-flash, 2026-05-22):

```
tests/test_llm_backend_gemini_inventory_item_integration.py::test_crown_classified_as_inventory_item_not_character PASSED
tests/test_llm_backend_gemini_inventory_item_integration.py::test_ui_button_classified_as_ui_icon_not_character PASSED
tests/test_llm_backend_gemini_inventory_item_integration.py::test_spritesheet_response_has_palette_label_from_tone_group PASSED
tests/test_llm_backend_gemini_inventory_item_integration.py::test_spritesheet_response_does_not_use_other_fallback PASSED
tests/test_llm_backend_gemini_inventory_item_integration.py::test_crown_icon_response_has_no_mood_labels PASSED
tests/test_llm_backend_gemini_inventory_item_integration.py::test_ui_button_response_has_no_mood_labels PASSED
tests/test_llm_backend_gemini_inventory_item_integration.py::test_spritesheet_response_has_no_neutral_or_minimalist_mood PASSED

7 passed in 44.12s
```

→ Gemini 가 시트 strip 응답에 mood='neutral' / 'minimalist' 0 토큰.  M11.8 A3 효과가 옵트인 1회 통과 확인.

PR → main → tag v0.2.7 → Trusted Publishing OIDC 6회째 자동 (~30초, M11.4~M11.7 의 v0.2.3~v0.2.6 publish 누적 deliver).

## 5. 알려진 한계 (M11.8 범위 밖)

| 항목 | 상태 | 후속 |
|---|---|---|
| 사용자가 `mood.neutral` 을 admin UI 로 enable 복원 시 LIVE 응답 분포 | 사용자 자율 — 강제 안 함 (meta 마커가 user override 존중) | — |
| `palette.neutral` 응답이 시트 자산에서 보일 가능성 (M11.6 의 hero=cool+neutral) | 정상 — tone group enum 유지 | — |
| `mood` enum 의 다른 catch-all 토큰 (`calm`?) | M11.9+ 후보 | LIVE 응답 분포 모니터링 후 결정 |

## 6. 현재 진행 상태 (2026-05-22)

| Phase | 상태 |
|---|---|
| 1 — 시드 비활성화 TDD (DISABLED_BY_DEFAULT + meta 마커) | ✅ green, 1601 baseline → 1608 (+7) |
| 2 — prompt 동기화 TDD (두 prompt mood enum) | ✅ green, 1608 → 1612 (+4) |
| 3 — LIVE 검증 (gate) | ✅ 시트 5/5 mood neutral/minimalist **0/5** 달성.  crown mood [] + palette 5/5 + 'other' 0/6 + palette.neutral 잔존 모두 회귀 0 |
| 4 — 옵트인 LIVE 확장 + PR | ✅ 신규 옵트인 1 PASSED (시트 mood neutral/minimalist 0건, 합산 7/7). 회귀 1612 + 옵트인 deselect 64 |
