# 2026-05-22 — M11.6 Design Spec: BATCH_SPRITESHEET_PROMPT palette + 'other' fallback 정리 (v0.2.5 candidate)

## 0. 본 spec 의 위치

- 상위 roadmap: [`2026-05-20-roadmap-design.md`](./2026-05-20-roadmap-design.md)
- 전제: [PR #23](https://github.com/v0o0v/assetcache-mcp/pull/23) M11.5 main 머지 (`ed47403`) + PR #24 별→별도 정리 (`1be53ae`)
- 다음: `milestones/M11_6_plan.md` (starter)
- Version 후보: **v0.2.5 patch** (M11.5 LIVE 검증에서 발견된 2 별도 발견 항목 해소)

## 1. 한 줄 요약

[`M11_5_verification.md §3.1`](../../milestones/M11_5_verification.md) 의 별도 발견 2건 — (a) 시트 자산 palette 라벨 부재 + (b) animation='other' fallback 라벨 합산 — 을 prompt + 검증 두 갈래로 정리.

## 2. 결정 매트릭스

| # | 항목 | 작업량 | 효과 범위 | 마이그 | 채택 |
|---|---|---:|---|---|---|
| A1 | **`BATCH_SPRITESHEET_PROMPT` 에 palette enum 추가** — BATCH_IMAGE_PROMPT 의 tone group 가이드 (warm/cool/monochrome/high_contrast/pastel/neutral) 동일 반영 + hex 금지 | ~0.3일 | 시트 자산 palette 라벨 채워짐, palette filter 검색 가능 | 0 | ✅ |
| A2-prompt | **`'other'` fallback 응답 금지** — BATCH_IMAGE_PROMPT + BATCH_SPRITESHEET_PROMPT 에 "do NOT use 'other' — always pick the closest enum value" 명시 | ~0.2일 | LLM 단계에서 'other' 응답 자체 차단 | 0 | ✅ |
| A2-filter | **`LabelRegistry` 또는 `validate_*_payload` 가 'other' 응답을 reject + 'unknown' 으로 강등** | ~0.3일 | prompt 가 'other' 를 응답해도 DB 저장 단계에서 제거 (방어 layer) | 0 | △ A2-prompt 효과 LIVE 확인 후 결정 |

**채택**: A1 + A2-prompt 무조건.  A2-filter 는 LIVE 결과 보고 결정 (Phase 분기).

## 3. Architecture — A1 BATCH_SPRITESHEET_PROMPT palette enum

### 3.1 현재 state

`BATCH_SPRITESHEET_PROMPT` ([core/analyzer/messages.py](../../src/assetcache/core/analyzer/messages.py)) 는 spritesheet 전용으로 category/animation 위주 응답을 받고 palette/mood 는 명시 안 함.  M11.5 LIVE 에서 시트 5 자산 모두 palette 라벨 0건 ([verification §3.1](../../milestones/M11_5_verification.md)).

### 3.2 fix

`BATCH_IMAGE_PROMPT` 의 palette 줄 + tone group enum (`warm`/`cool`/`monochrome`/`high_contrast`/`pastel`/`neutral`) + hex 금지 가이드를 `BATCH_SPRITESHEET_PROMPT` 에도 동일 적용.  단 spritesheet 의 composite preview (4-frame strip) 에서 palette 판단이 안정적인지 LIVE 로 확인.

## 4. Architecture — A2 'other' fallback 제거

### 4.1 현재 state

M11.5 LIVE 결과의 animation 라벨에서 `'other'` 가 6 자산 중 4 자산에 합산됨 (elemental_cyan/hero_warrior/knight_gold/mage_purple).  category 라벨에서는 'other' 응답이 strict acceptable set 통과로 1건 (M11.5 Phase 5 strict 화 후).

### 4.2 prompt fix (A2-prompt)

`BATCH_IMAGE_PROMPT` + `BATCH_SPRITESHEET_PROMPT` 의 각 axis 응답 블록에 다음 추가:

```
- Do NOT use "other" as a response.  If no enum value fits, pick the closest one and explain in `notes` (free text).
```

`notes` 필드는 응답 schema 에 이미 있거나 추가 (option).

### 4.3 filter fix (A2-filter, 조건부)

`validate_image_payload` / `validate_audio_payload` 가 `'other'` 응답을 axis 별로 drop:

```python
# core/analyzer/payload_parser.py
if (label or "").lower() == "other":
    continue  # drop 'other' fallback — prompt 거부됐는데도 응답에 등장한 경우 방어
```

LIVE 에서 A2-prompt 만으로 'other' 0건 되면 A2-filter 불필요.

## 5. Module breakdown

### 5.1 변경 파일

| 파일 | 변경 | 조건 |
|---|---|---|
| `src/assetcache/core/analyzer/messages.py` | A1: BATCH_SPRITESHEET_PROMPT palette enum 추가 + A2-prompt: 두 prompt 에 'other' 금지 가이드 | 무조건 |
| `src/assetcache/core/analyzer/payload_parser.py` | A2-filter: validate_image_payload + validate_audio_payload 가 'other' 응답을 axis 별로 drop | A2-prompt 효과 부족 시 |
| `tests/test_batch_spritesheet_prompt_palette.py` (신규) | BATCH_SPRITESHEET_PROMPT palette enum + hex 금지 + tone group 가이드 노출 | 무조건 |
| `tests/test_prompt_no_other_fallback.py` (신규) | 두 prompt 에 'other' 금지 가이드 노출 | 무조건 |
| `tests/test_payload_parser_other_drop.py` (신규) | validate_*_payload 가 'other' 응답을 drop 한다 | A2-filter 채택 시 |
| `tests/test_llm_backend_gemini_inventory_item_integration.py` (확장) | 옵트인 LIVE — 'other' 응답 0건 + 시트 palette 응답 ≥ 1건 | 무조건 |

### 5.2 의존성

신규 의존성 0.  M11.4/M11.5 의 prompt + payload_parser 인프라 재사용.

## 6. Test strategy

### 6.1 자동 테스트

- BATCH_SPRITESHEET_PROMPT 에 `palette` 줄 + `warm` / `cool` / `monochrome` / `high_contrast` / `pastel` / `neutral` 6 토큰 모두 명시 — 단위 test 1
- BATCH_SPRITESHEET_PROMPT 에 `do NOT use hex codes like #FDD835` — 단위 test 1
- 두 prompt 모두 `do NOT use "other"` 가이드 — 단위 test 2 (각 prompt 별 1)
- validate_image_payload + validate_audio_payload 가 'other' axis 라벨 drop (A2-filter 채택 시) — 단위 test 3
- 신규 시드 변경 없음 — LabelRegistry seed 검증 unchanged

### 6.2 LIVE 검증

`scripts/drive_live_batch.py` 재실행 — M11.5 LIVE setup 그대로 (6 자산).  목표:

- 시트 자산 (5개) 모두 palette 라벨 ≥ 1건
- animation axis 'other' 0건
- category axis 'other' 0건
- 회귀: crown_icon=inventory_item ✓ + elemental_cyan kind=spritesheet ✓

LIVE 결과로 A2-filter 채택 여부 결정.

## 7. 알려진 한계 (M11.6 범위 밖)

| 항목 | 우선순위 | 후속 |
|---|---|---|
| Gemini 모델 업그레이드 (3.1-flash-lite → 3.1-flash) | 중 | M12 별도 spec |
| BATCH_SPRITESHEET_PROMPT category 강제 완화 (multi-frame inventory) | 낮 | M12+ |
| elemental_cyan category=character (합성 자산 시각 한계) | 낮 | 범위 밖 |
| spritesheet palette 판단 안정성 (composite strip 의 4-frame 색 평균 vs 단일 frame) | 중 | LIVE 결과 보고 결정 — 불안정하면 strip 대신 첫 frame 만 palette 분석으로 분기 |

## 8. 다음 단계

1. 이 spec 사용자 검토.
2. `milestones/M11_6_plan.md` 작성 (Phase 분할 — Phase 1 prompt fix + 단위 test → Phase 2 LIVE 검증 → Phase 3 분기 A2-filter 결정 → Phase 4 PR).
3. TDD red → green.
4. LIVE 검증 (M11.5 setup 재사용).
5. `M11_6_verification.md` — auto + 옵트인 + LIVE.
6. PR → main → tag v0.2.5 → Trusted Publishing 7회째 자동 (M11.4 의 v0.2.3 publish 보류 + M11.5 의 v0.2.4 보류 결번 — 0.2.2 → 0.2.5 직접 bump).

작업 시간 추정: **~1일** (Phase 1 0.5일 + Phase 2 0.2일 + Phase 3 분기 0.2일 + Phase 4 0.1일).
