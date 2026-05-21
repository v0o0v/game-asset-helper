# M11.6 검증 — BATCH_SPRITESHEET_PROMPT palette + 'other' fallback 정리 (v0.2.5 candidate)

## 0. 본 문서의 위치

- 상위 spec: [`docs/superpowers/specs/2026-05-22-m11-6-spritesheet-palette-and-other-cleanup.md`](../docs/superpowers/specs/2026-05-22-m11-6-spritesheet-palette-and-other-cleanup.md)
- 상위 plan: [`M11_6_plan.md`](./M11_6_plan.md)
- 전제: [PR #23](https://github.com/v0o0v/assetcache-mcp/pull/23) M11.5 main 머지 (`ed47403`) + [PR #24](https://github.com/v0o0v/assetcache-mcp/pull/24) 별→별도 docs cleanup (`1be53ae`) + [PR #25](https://github.com/v0o0v/assetcache-mcp/pull/25) docs starter (`b0d3380`)
- 본 문서는 **Phase 1 prompt fix (red→green) → Phase 2 LIVE 검증 → Phase 3 A2-filter 분기 → Phase 4 옵트인 LIVE 확장 + PR** 흐름의 결과를 누적한다.

## 1. 자동 검증 (Phase 1 green) — ✅ 2026-05-22

```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" -m pytest -q
```

Result: **1597 passed + 1 skipped + 59 deselected in 76.98s** — M11.5 baseline 1592 + 신규 5 (Phase 1 prompt fix red→green).

### 1.1 신규 단위 테스트

| 파일 | 테스트 수 | 검증 내용 |
|---|---:|---|
| `tests/test_batch_spritesheet_prompt_palette.py` | 3 | tone group 6 토큰 + hex 금지 + JSON + animation_hint + palette 보존 |
| `tests/test_prompt_no_other_fallback.py` | 2 | 두 prompt 각각 "do NOT use 'other'" + 'other' literal 노출 |

### 1.2 변경 파일

| 파일 | 변경 | 비고 |
|---|---|---|
| `src/assetcache/core/analyzer/messages.py` | A1: BATCH_SPRITESHEET_PROMPT 에 palette tone group enum + hex 금지 + mood enum 추가, schema 의 `mood:[]` / `palette:[]` 빈 배열을 enum 안내로 교체. A2-prompt: 두 prompt 에 "Do NOT use 'other'" 가이드 추가 | Phase 1 green |
| `tests/test_batch_spritesheet_prompt_palette.py` | 신규 | Phase 1 red→green |
| `tests/test_prompt_no_other_fallback.py` | 신규 | Phase 1 red→green |

## 2. LIVE 검증 셋업 (Phase 2 gate)

### 2.1 합성 자산 생성

```powershell
$libDir = "$env:TEMP\m11_6_verify_data\library\m113_complex"
```
```powershell
Remove-Item -Recurse -Force "$env:TEMP\m11_6_verify_data" -ErrorAction SilentlyContinue
```
```powershell
New-Item -ItemType Directory -Path $libDir -Force | Out-Null
```
```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" scripts/make_complex_sheets.py $libDir
```

→ 8 파일 (6 PNG + 2 Aseprite JSON sidecar) 생성.

### 2.2 LIVE Gemini 배치 실행

```powershell
$env:GEMINI_API_KEY = "AIza..."
```
```powershell
& "$env:USERPROFILE\.venvs\gah\Scripts\python.exe" scripts/drive_live_batch.py "$env:TEMP\m11_6_verify_data"
```

→ M11.5 의 `scripts/drive_live_batch.py` 재사용 (Qt tray 우회).  chat_image batch → classify_image_assets 가 spritesheet promote → chat_spritesheet batch → polling 까지 진행.

## 3. LIVE 결과 표 — ✅ 2026-05-22

driver: `scripts/drive_live_batch.py` (Qt tray 우회).  Gemini batch inline destination.

batch_jobs:

| job_id | modality | state | asset_count | success | failure |
|---:|---|---|---:|---:|---:|
| 1 | chat_image | succeeded | 1 | 1 | 0 |
| 2 | chat_spritesheet | succeeded | 5 | 5 | 0 |

→ chat_image 가 6 자산 fetch → classify_image_assets 가 5 자산을 spritesheet kind 로 promote (elemental_cyan 포함) → crown_icon (sprite) 만 chat_image batch 진입.  chat_spritesheet 가 promote 된 5 자산 batch.  payload validation ValueError 0건.

| # | 자산 | 기대 결과 | LIVE 결과 | 평가 |
|---:|---|---|---|---|
| 1 | hero_warrior | palette 라벨 ≥ 1건 + animation 'other' 0건 | **palette=cool, neutral + animation=idle/walk/attack/hurt** ✅ | A1 + A2 효과 LIVE 통과 |
| 2 | mage_purple | 동일 | **palette=cool + animation=cast/idle/walk** ✅ | 동일 |
| 3 | knight_gold | 동일 | **palette=warm + animation=idle** ✅ | 동일 |
| 4 | monster_red | 동일 | **palette=warm + animation=idle** ✅ | 동일 |
| 5 | elemental_cyan | 동일 + animation 'other' 0건 | **palette=high_contrast + animation=idle** ✅ | A2-prompt 효과 LIVE 통과 |
| 6 | crown_icon | category=inventory_item 유지 + palette warm/high_contrast 유지 | **category=inventory_item + palette=high_contrast/warm** ✅ | regression 0 |

**시트 자산 palette 라벨 카운트**: 5/5 (모두 ≥ 1건).  M11.5 의 0/5 (별도 발견 #1) → 5/5 로 완전 해소.

**'other' fallback 라벨 카운트**:
* animation axis 'other' = **0건** (hero/mage/knight/monster/elemental 모두 idle/walk/cast/attack/hurt 같은 valid enum)
* category axis 'other' = **0건** (character/inventory_item 만 응답)
* mood axis 'other' = **0건** (minimalist/neutral/heroic/playful 만 응답)
* palette axis 'other' = **0건** (warm/cool/high_contrast/neutral 만 응답)

M11.5 의 animation='other' 6 자산 중 4 자산 합산 (별도 발견 #2) → 0/6 으로 완전 해소.  A2-prompt 가이드만으로 fallback 차단 충분 — **A2-filter 진입 불필요**.

### 3.1 별도 발견 (M11.6 범위 밖)

| 항목 | 상태 | 후속 |
|---|---|---|
| elemental_cyan / knight_gold / monster_red category=character | LLM 분류 한계 — 합성 자산 시각 (M11.5 와 동일).  실 게임 자산 영향 낮음 | M11.6 범위 밖 |
| crown_icon mood='heroic'/'playful' | inventory icon 임에도 mood 라벨 응답 — prompt 가 mood 필수 응답 요구.  실 게임 영향 낮음 (mood 검색 시 부합 가능) | M11.6 범위 밖 |
| spritesheet 자산도 mood 라벨 응답 (4 자산 minimalist/neutral) | M11.6 A1 의 mood enum 추가 효과로 mood 도 채워짐 — bonus | M11.6 범위 내 (예상 외 추가 효과) |

## 4. Phase 3 — A2-filter 분기 결정 — ✅ 2026-05-22

| trigger | LIVE 결과 | 결정 |
|---|---|---|
| 시트 palette ≥ 1건 | **5/5 ✓** | A1 LIVE 통과 |
| animation 'other' 0건 | **0/6 ✓** | A2-prompt 충분 |
| category 'other' 0건 | **0/6 ✓** | A2-prompt 충분 |
| regression 0 | **crown=inventory_item 유지, elemental=spritesheet 유지, kind/frame_count/animations 모두 유지 ✓** | 0 regression |

→ **결정**: **A2-filter SKIP** — A2-prompt 만으로 'other' 0건 달성, defense layer 불필요.

## 5. Phase 4 — 옵트인 LIVE 확장 — ✅ 2026-05-22

`tests/test_llm_backend_gemini_inventory_item_integration.py` 확장 (`pytestmark = pytest.mark.llm_integration`, 기본 deselect):

* `_make_warrior_strip_png` 신규 — 4-frame 가로 strip 합성 (검 든 캐릭터, warm-ish tone, frame 별 칼 위치 변화로 움직임 hint)
* `test_spritesheet_response_has_palette_label_from_tone_group` — composite strip → BATCH_SPRITESHEET_PROMPT system 메시지 + user 메시지 → 응답 palette 라벨 ≥ 1건 + 모든 토큰이 `{warm, cool, monochrome, high_contrast, pastel, neutral}` 안 + hex 0건
* `test_spritesheet_response_does_not_use_other_fallback` — 동일 strip → 응답의 animation_hint/category/style/mood/palette 5 axis 모두 'other' literal 0건

LIVE 옵트인 결과 (gemini-2.5-flash, 2026-05-22):

```
tests/test_llm_backend_gemini_inventory_item_integration.py::test_crown_classified_as_inventory_item_not_character PASSED
tests/test_llm_backend_gemini_inventory_item_integration.py::test_ui_button_classified_as_ui_icon_not_character PASSED
tests/test_llm_backend_gemini_inventory_item_integration.py::test_spritesheet_response_has_palette_label_from_tone_group PASSED
tests/test_llm_backend_gemini_inventory_item_integration.py::test_spritesheet_response_does_not_use_other_fallback PASSED

4 passed in 22.60s
```

→ Gemini 가 strict acceptable set 안에서 응답 + tone group enum 안에서 palette 응답 + 'other' 0건.  M11.6 A1 + A2-prompt 의 효과가 옵트인 1회 통과 확인.

PR → main → tag v0.2.5 → Trusted Publishing OIDC 7회째 자동 (~30초) 가 다음 단계.

## 6. 알려진 한계 (M11.6 범위 밖)

| 항목 | 상태 | 후속 |
|---|---|---|
| Gemini 모델 업그레이드 (3.1-flash-lite → 3.1-flash) | M12 별도 spec | LIVE 정확도 부족 시 trigger |
| BATCH_SPRITESHEET_PROMPT category 강제 완화 (multi-frame inventory) | M12+ 별도 마일스톤 | 회전 coin 등 요구 시점 |
| spritesheet palette 판단 안정성 (composite strip 의 4-frame 색 평균 vs 단일 frame) | M11.6 LIVE 결과 보고 결정 | 불안정하면 strip 대신 첫 frame 만 palette 분석으로 분기 |

## 7. 현재 진행 상태 (2026-05-22)

| Phase | 상태 |
|---|---|
| 1 — prompt fix TDD (A1 + A2-prompt) | ✅ green, 1597 passed (+5) |
| 2 — LIVE 검증 (gate) | ✅ chat_image 1/1 + chat_spritesheet 5/5 success.  palette 5/5 ≥ 1건 + 'other' 0/6 |
| 3 — A2-filter 분기 결정 | ✅ SKIP (A2-prompt 만으로 'other' 0건 달성) |
| 4 — 옵트인 LIVE 확장 + PR | ✅ 신규 옵트인 2 PASSED (palette tone group + 'other' 0건). 회귀 1597 + 옵트인 deselect 61 |
