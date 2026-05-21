# M11.7 검증 — mood label noise cleanup (v0.2.6 candidate)

## 0. 본 문서의 위치

- 상위 spec: [`docs/superpowers/specs/2026-05-22-m11-7-mood-noise-cleanup.md`](../docs/superpowers/specs/2026-05-22-m11-7-mood-noise-cleanup.md)
- 상위 plan: [`M11_7_plan.md`](./M11_7_plan.md)
- 전제: [PR #26](https://github.com/v0o0v/assetcache-mcp/pull/26) M11.6 main 머지 (`da4f169`)
- 본 문서는 **Phase 1 prompt fix (red→green) → Phase 2 LIVE 검증 → Phase 3 옵트인 LIVE 확장 + PR** 흐름의 결과를 누적한다.

## 1. 자동 검증 (Phase 1 green) — ✅ 2026-05-22

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -q
```

Result: **1601 passed + 1 skipped + 61 deselected in 96.00s** — M11.6 baseline 1597 + 신규 4 (Phase 1 prompt fix red→green).

### 1.1 신규 단위 테스트

| 파일 | 테스트 수 | 검증 내용 |
|---|---:|---|
| `tests/test_prompt_mood_optional.py` | 2 | 두 prompt 의 mood 줄에 'optional' + '[]' + 'no clear mood' 시그널 |
| `tests/test_prompt_category_mood_exclusion.py` | 2 | 두 prompt Guidance 에 4 정적 category + mood 차단 가이드 |

### 1.2 변경 파일

| 파일 | 변경 |
|---|---|
| `src/assetcache/core/analyzer/messages.py` | A1: 두 prompt mood 줄에 "optional, leave [] if no clear mood applies".  A2: Guidance 블록에 "Do NOT include mood values for inventory_item / ui_icon / tile / background" |
| `tests/test_prompt_mood_optional.py` | 신규 |
| `tests/test_prompt_category_mood_exclusion.py` | 신규 |

## 2. LIVE 검증 셋업 (Phase 2 gate)

### 2.1 합성 자산 생성

M11.6 setup 재사용 — 같은 6 자산 (hero_warrior/mage_purple/knight_gold/monster_red/elemental_cyan/crown_icon).

```powershell
Remove-Item -Recurse -Force "$env:TEMP\m11_7_verify_data" -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$env:TEMP\m11_7_verify_data\library\m113_complex" -Force | Out-Null
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" scripts/make_complex_sheets.py "$env:TEMP\m11_7_verify_data\library\m113_complex"
```

### 2.2 LIVE Gemini 배치 실행

```powershell
$env:GEMINI_API_KEY = "AIza..."
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" scripts/drive_live_batch.py "$env:TEMP\m11_7_verify_data"
```

## 3. LIVE 결과 표 — ✅ 2026-05-22

driver: `scripts/drive_live_batch.py` (Qt tray 우회).  Gemini batch inline destination.

batch_jobs:

| job_id | modality | state | asset_count | success | failure |
|---:|---|---|---:|---:|---:|
| 1 | chat_image | succeeded | 1 | 1 | 0 |
| 2 | chat_spritesheet | succeeded | 5 | 5 | 0 |

| # | 자산 | M11.6 mood (변경 전) | M11.7 mood (LIVE 결과) | 평가 |
|---:|---|---|---|---|
| 1 | hero_warrior | minimalist, neutral | **minimalist, neutral** | A1 효과 X (변화 없음) |
| 2 | mage_purple | minimalist, neutral | **neutral** (1 토큰) | A1 효과 일부 |
| 3 | knight_gold | minimalist, neutral | **(빈 mood)** ✅ | A1 효과 완전 |
| 4 | monster_red | minimalist, neutral | **neutral** (1 토큰) | A1 효과 일부 |
| 5 | elemental_cyan | minimalist, neutral | **neutral** (1 토큰) | A1 효과 일부 |
| 6 | **crown_icon** (inventory_item) | **heroic, playful** (2 토큰) | **(빈 mood)** ✅ | **A2 효과 완벽** |

**mood 토큰 총량 비교**:
- M11.6: 시트 5/5 × 2 토큰 = **10 토큰** + crown 2 토큰 = **합계 12**
- M11.7: 시트 1×0 + 3×1 + 1×2 = **5 토큰** + crown 0 = **합계 5**
- **감소율: 58%** (12 → 5).

**A2 (category 별 mood 차단) 효과**: ✅ **LIVE 통과** — crown_icon (inventory_item) mood 0 토큰. M11.6 의 heroic/playful 완전 차단.

**A1 (mood OPTIONAL) 효과**: ⚠️ **부분 효과** — 시트 5/5 중 1/5 (knight_gold) 빈 mood, 3/5 단일 'neutral', 1/5 (hero) 여전히 'minimalist+neutral'.  Gemini 가 catch-all 'neutral' 을 응답하는 경향 잔존 — M11.8 (A3 시드 비활성화) 또는 M12 (모델 업그레이드) 후보.

### 3.1 별도 발견 (M11.7 범위 밖)

| 항목 | 상태 | 후속 |
|---|---|---|
| 시트 4/5 자산에 mood='neutral' 잔존 | A1 prompt 가이드만으로는 catch-all 'neutral' 차단 불충분.  Gemini 가 character 자산에 mood 응답을 안전 차원에서 채우는 경향 | M11.8 후보 (A3 시드 `neutral` 비활성화) 또는 M12 (모델 업그레이드) |

### 3.2 Regression check

| 항목 | M11.6 결과 | M11.7 LIVE | 평가 |
|---|---|---|---|
| crown_icon category | inventory_item | **inventory_item** ✅ | regression 0 |
| crown_icon palette | high_contrast, warm | **high_contrast, warm** ✅ | regression 0 |
| 시트 5/5 palette ≥ 1건 | 5/5 | **5/5** ✅ (high_contrast, cool, warm) | M11.6 A1 보존 |
| 'other' fallback | 0/6 | **0/6** ✅ | M11.6 A2-prompt 보존 |
| kind/frame_count/animations | M11.5 와 동일 | **동일** ✅ | M11.3/M11.4 보존 |

## 4. Phase 3 — 옵트인 LIVE 확장 — ✅ 2026-05-22

`tests/test_llm_backend_gemini_inventory_item_integration.py` 확장 (`pytestmark = pytest.mark.llm_integration`, 기본 deselect):

* `test_crown_icon_response_has_no_mood_labels` — crown_icon (inventory_item) 응답 → category 가 inventory_item/item 분류된 케이스에 한해 mood 라벨 len = 0 단언
* `test_ui_button_response_has_no_mood_labels` — ui_button (ui_icon) 응답 → category 가 ui_icon/ui 분류된 케이스에 한해 mood 라벨 len = 0 단언

옵트인 LIVE 결과 (gemini-2.5-flash, 2026-05-22):

```
tests/test_llm_backend_gemini_inventory_item_integration.py::test_crown_classified_as_inventory_item_not_character PASSED
tests/test_llm_backend_gemini_inventory_item_integration.py::test_ui_button_classified_as_ui_icon_not_character PASSED
tests/test_llm_backend_gemini_inventory_item_integration.py::test_spritesheet_response_has_palette_label_from_tone_group PASSED
tests/test_llm_backend_gemini_inventory_item_integration.py::test_spritesheet_response_does_not_use_other_fallback PASSED
tests/test_llm_backend_gemini_inventory_item_integration.py::test_crown_icon_response_has_no_mood_labels PASSED
tests/test_llm_backend_gemini_inventory_item_integration.py::test_ui_button_response_has_no_mood_labels PASSED

6 passed in 33.58s
```

→ Gemini 가 inventory_item / ui_icon 응답에 mood 라벨 0 토큰.  M11.7 A2 의 효과가 옵트인 1회 통과 확인.

PR → main → tag v0.2.6 → Trusted Publishing OIDC 8회째 자동 (~30초) 가 다음 단계.

## 5. 알려진 한계 (M11.7 범위 밖)

| 항목 | 상태 | 후속 |
|---|---|---|
| 시드 `minimalist`/`neutral` 비활성화 (A3) | LIVE A1+A2 효과 부족 시 진입 | M11.8 후보 |
| mood 응답 cap (5+ 토큰 일 때) | M12+ 범위 | — |
| Gemini 모델 업그레이드 (2.5-flash → 2.5-pro) | M12 별도 spec | — |

## 6. 현재 진행 상태 (2026-05-22)

| Phase | 상태 |
|---|---|
| 1 — prompt fix TDD (A1 + A2) | ✅ green, 1601 passed (+4) |
| 2 — LIVE 검증 (gate) | ✅ chat_image 1/1 + chat_spritesheet 5/5 success.  crown mood 2→0 토큰 (A2 완벽), 시트 mood 10→5 토큰 (A1 부분) |
| 3 — 옵트인 LIVE 확장 + PR | ✅ 신규 옵트인 2 PASSED (crown mood [] + ui_button mood [], 합산 6/6).  회귀 1601 + 옵트인 deselect 63 |
